"""Guard against committing credentials (G2).

A live TigerGraph secret was once pasted into `.env.example` and pushed (RISKS.md S16). These
tests make that failure mode loud and immediate rather than something discovered by an audit.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Keys whose values must always be blank in the committed template.
MUST_BE_EMPTY = ("TG_SECRET", "TG_PASSWORD", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "TG_HOST")

# Anything that looks like wallet key material must never appear at all.
FORBIDDEN_PATTERNS = (
    re.compile(r"\bPRIVATE_KEY\s*=\s*\S", re.I),
    re.compile(r"\b(SEED_PHRASE|MNEMONIC)\s*=\s*\S", re.I),
    re.compile(r"\b0x[0-9a-f]{64}\b", re.I),  # a 32-byte hex value, i.e. a private key
)


def read_env_example() -> str:
    return (REPO_ROOT / ".env.example").read_text()


@pytest.mark.parametrize("key", MUST_BE_EMPTY)
def test_template_key_is_blank(key):
    """`.env.example` is committed, so every credential field in it must be empty."""
    for line in read_env_example().splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            value = stripped.split("=", 1)[1].strip()
            assert value == "", (
                f"{key} in .env.example has a value ({value[:6]}...). Credentials and "
                f"instance-specific hosts belong in .env, which is gitignored."
            )


@pytest.mark.parametrize("pattern", FORBIDDEN_PATTERNS, ids=lambda p: p.pattern[:28])
def test_no_key_material_in_template(pattern):
    assert not pattern.search(read_env_example()), (
        "`.env.example` appears to contain wallet key material. TraceLedger is read-only "
        "and must never hold keys or seed phrases (G2)."
    )


def test_env_is_not_tracked_by_git():
    """The real .env must never be in the index."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=REPO_ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert result.returncode != 0, ".env is tracked by git. It must be gitignored (G2)."


def test_gitignore_covers_env():
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT, capture_output=True, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, ".gitignore does not cover .env (G2)."
