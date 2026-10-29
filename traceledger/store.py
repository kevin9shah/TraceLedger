"""Case storage and the audit log. SQLite, append-only for decisions.

The audit log is **append-only by design**: a reviewer decision is a record of what a human
concluded at a point in time, so it is never updated or deleted. A later decision is a new row.
That is what makes the log worth having.

Deliberately NOT claimed: the log is not tamper-proof or immutable. It is a SQLite file on disk
and anyone with filesystem access can edit it. Calling it immutable would be an unearned claim
(G10, P10), so the schema says what it is -- append-only by convention, enforced in this module.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# The four reviewer actions CP9 requires.
REVIEW_ACTIONS = ("confirm", "reject", "request_evidence", "unresolved")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id      TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    created_at   REAL NOT NULL,
    state        TEXT NOT NULL,
    tx_hash      TEXT,
    payload      TEXT NOT NULL      -- the case inputs as JSON
);
CREATE TABLE IF NOT EXISTS findings (
    case_id      TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    code         TEXT NOT NULL,
    status       TEXT NOT NULL,
    summary      TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,
    detail       TEXT NOT NULL,
    PRIMARY KEY (case_id, seq)
);
CREATE TABLE IF NOT EXISTS reports (
    case_id      TEXT PRIMARY KEY,
    created_at   REAL NOT NULL,
    payload      TEXT NOT NULL      -- the investigation as JSON, or null if LLM unavailable
);
-- Append-only. No UPDATE or DELETE statement against this table exists in the codebase.
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id     TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL,
    at           REAL NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    rationale    TEXT NOT NULL,
    context      TEXT NOT NULL      -- what the reviewer was looking at, as JSON
);
CREATE INDEX IF NOT EXISTS ix_audit_case ON audit_log(case_id, at);
"""


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    case_id: str
    at: float
    actor: str
    action: str
    rationale: str
    context: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "case_id": self.case_id, "at": self.at,
                "actor": self.actor, "action": self.action, "rationale": self.rationale,
                "context": self.context}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ cases

    def create_case(self, title: str, payload: dict[str, Any],
                    tx_hash: str | None = None, case_id: str | None = None) -> str:
        cid = case_id or f"CASE-{uuid.uuid4().hex[:8].upper()}"
        if self.get_case(cid):
            raise StoreError(f"case {cid} already exists")
        self._conn.execute(
            "INSERT INTO cases (case_id, title, created_at, state, tx_hash, payload) "
            "VALUES (?,?,?,?,?,?)",
            (cid, title, time.time(), "open", tx_hash, json.dumps(payload)))
        self._conn.commit()
        return cid

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            return None
        case = dict(row)
        case["payload"] = json.loads(case["payload"])
        return case

    def list_cases(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT case_id, title, created_at, state, tx_hash FROM cases "
            "ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def set_state(self, case_id: str, state: str) -> None:
        """The case's workflow state. Distinct from the audit log, which records why."""
        self._conn.execute("UPDATE cases SET state = ? WHERE case_id = ?", (state, case_id))
        self._conn.commit()

    # ------------------------------------------------------------------ findings and report

    def save_findings(self, case_id: str, findings: Iterable[dict[str, Any]]) -> None:
        self._conn.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))
        for seq, finding in enumerate(findings):
            self._conn.execute(
                "INSERT INTO findings (case_id, seq, code, status, summary, evidence_ids, detail) "
                "VALUES (?,?,?,?,?,?,?)",
                (case_id, seq, finding["code"], finding["status"], finding["summary"],
                 json.dumps(finding.get("evidence_ids") or []),
                 json.dumps(finding.get("detail") or {})))
        self._conn.commit()

    def get_findings(self, case_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM findings WHERE case_id = ? ORDER BY seq", (case_id,)).fetchall()
        out = []
        for row in rows:
            finding = dict(row)
            finding["evidence_ids"] = json.loads(finding["evidence_ids"])
            finding["detail"] = json.loads(finding["detail"])
            out.append(finding)
        return out

    def save_report(self, case_id: str, report: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO reports (case_id, created_at, payload) VALUES (?,?,?)",
            (case_id, time.time(), json.dumps(report)))
        self._conn.commit()

    def get_report(self, case_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload FROM reports WHERE case_id = ?", (case_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    # ------------------------------------------------------------------ audit log

    def record_review(self, case_id: str, actor: str, action: str, rationale: str,
                      context: dict[str, Any] | None = None) -> AuditEntry:
        """Append a reviewer decision. Never updates or deletes an earlier one.

        A rationale is required: a decision without a stated reason is not reviewable, which
        defeats the purpose of having a human in the loop.
        """
        if action not in REVIEW_ACTIONS:
            raise StoreError(f"unknown action {action!r}; expected one of {REVIEW_ACTIONS}")
        if not rationale.strip():
            raise StoreError("a rationale is required: a decision with no stated reason "
                             "cannot be reviewed later")
        if self.get_case(case_id) is None:
            raise StoreError(f"no such case: {case_id}")
        entry = AuditEntry(entry_id=f"AUD-{uuid.uuid4().hex[:10].upper()}", case_id=case_id,
                           at=time.time(), actor=actor or "unknown", action=action,
                           rationale=rationale.strip(), context=context or {})
        self._conn.execute(
            "INSERT INTO audit_log (entry_id, case_id, at, actor, action, rationale, context) "
            "VALUES (?,?,?,?,?,?,?)",
            (entry.entry_id, entry.case_id, entry.at, entry.actor, entry.action,
             entry.rationale, json.dumps(entry.context)))
        # The workflow state follows the latest decision; the log keeps every one.
        self._conn.execute("UPDATE cases SET state = ? WHERE case_id = ?",
                           (f"reviewed:{action}", case_id))
        self._conn.commit()
        return entry

    def audit_trail(self, case_id: str | None = None) -> list[AuditEntry]:
        if case_id:
            rows = self._conn.execute(
                "SELECT * FROM audit_log WHERE case_id = ? ORDER BY at", (case_id,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM audit_log ORDER BY at DESC").fetchall()
        return [AuditEntry(entry_id=r["entry_id"], case_id=r["case_id"], at=r["at"],
                           actor=r["actor"], action=r["action"], rationale=r["rationale"],
                           context=json.loads(r["context"])) for r in rows]
