"""Configuration loading and startup assertions.

Fails loudly rather than guessing: a wrong-network RPC or a missing token allow-list
is a correctness bug (RISKS.md P6), not something to degrade gracefully around.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# Keys that must never appear in configuration. Presence is a hard error (G2).
FORBIDDEN_KEY_SUBSTRINGS = ("PRIVATE_KEY", "SEED_PHRASE", "MNEMONIC", "WALLET_BACKUP")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    rpc_url: str
    chain_id: int
    chain_name: str
    token_contracts: dict[str, str]  # lowercase address -> label from .env, e.g. "USDC"
    tg_host: str | None
    tg_graph: str
    tg_username: str | None
    tg_password: str | None
    tg_secret: str | None
    llm_provider: str
    llm_model: str
    llm_api_key: str | None
    db_path: Path

    @property
    def allowed_contracts(self) -> frozenset[str]:
        return frozenset(self.token_contracts)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


# A Savanna workspace id is a 32-character hex string; its endpoint is <id>.i.tgcloud.io.
_WORKSPACE_ID = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
SAVANNA_HOST_SUFFIX = ".i.tgcloud.io"


def normalise_tg_host(raw: str | None) -> str | None:
    """Turn whatever the user could find in the Savanna console into a usable host.

    Accepts, because all of these are what people actually have to hand:
      * a full URL            https://abc.i.tgcloud.io  (with or without trailing slash)
      * a bare hostname       abc.i.tgcloud.io
      * a bare workspace id   7c141e8c7669404f923623083ba01da9
      * localhost / 127.0.0.1 for a self-hosted instance

    pyTigerGraph >=2.0 raises `Invalid URL scheme` on a bare hostname while TigerGraph's own
    older docs show exactly that form, so the scheme is supplied here rather than demanded of
    the user (RISKS.md S11, S12). Savanna is HTTPS-only. A trailing slash is stripped because
    the client appends ports and paths to this value.
    """
    if not raw:
        return None
    host = raw.strip().rstrip("/")
    if not host:
        return None
    # A bare workspace id -> the Savanna endpoint it belongs to.
    if _WORKSPACE_ID.match(host):
        return f"https://{host.lower()}{SAVANNA_HOST_SUFFIX}"
    if "://" not in host:
        # Bare hostname. Localhost is plain http; anything else (i.e. Savanna) is https.
        bare = host.split(":", 1)[0].lower()
        scheme = "http" if bare in ("localhost", "127.0.0.1") else "https"
        host = f"{scheme}://{host}"
    return host


def _assert_no_key_material() -> None:
    for name in os.environ:
        upper = name.upper()
        for bad in FORBIDDEN_KEY_SUBSTRINGS:
            if bad in upper:
                raise ConfigError(
                    f"Environment variable {name} looks like wallet key material. "
                    "TraceLedger is read-only and must never be given keys or seed phrases (G2)."
                )


def load_config(env_file: str | os.PathLike[str] | None = None) -> Config:
    load_dotenv(env_file or REPO_ROOT / ".env")
    _assert_no_key_material()

    raw_chain_id = _require("EVM_CHAIN_ID")
    try:
        chain_id = int(raw_chain_id)
    except ValueError as exc:
        raise ConfigError(f"EVM_CHAIN_ID must be an integer, got {raw_chain_id!r}") from exc

    tokens: dict[str, str] = {}
    for label in ("USDC", "USDT"):
        address = os.getenv(f"{label}_CONTRACT", "").strip().lower()
        if not address:
            continue
        if not (address.startswith("0x") and len(address) == 42):
            raise ConfigError(f"{label}_CONTRACT is not a 20-byte hex address: {address!r}")
        tokens[address] = label
    if not tokens:
        raise ConfigError("No token contracts configured. Set USDC_CONTRACT and/or USDT_CONTRACT.")

    return Config(
        rpc_url=_require("EVM_RPC_URL"),
        chain_id=chain_id,
        chain_name=os.getenv("EVM_CHAIN_NAME", f"chain-{chain_id}"),
        token_contracts=tokens,
        tg_host=normalise_tg_host(os.getenv("TG_HOST")),
        tg_graph=os.getenv("TG_GRAPH", "TraceLedger"),
        tg_username=os.getenv("TG_USERNAME") or None,
        tg_password=os.getenv("TG_PASSWORD") or None,
        tg_secret=os.getenv("TG_SECRET") or None,
        llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
        llm_model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        llm_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or None,
        db_path=REPO_ROOT / os.getenv("TRACELEDGER_DB", "data/traceledger.sqlite"),
    )
