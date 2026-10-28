"""Config guardrails: key material is rejected, bad addresses are rejected (G2, G7)."""
from __future__ import annotations

import pytest

from traceledger.config import ConfigError, load_config

BASE_ENV = {
    "EVM_RPC_URL": "http://test",
    "EVM_CHAIN_ID": "137",
    "USDC_CONTRACT": "0x3C499C542CEF5E3811E1192CE70D8CC03D5C3359",
}


def write_env(tmp_path, overrides=None, base=BASE_ENV):
    env = {**base, **(overrides or {})}
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in env.items() if v is not None))
    return path


# load_dotenv() does NOT override variables already present in os.environ, so a value leaked
# by an earlier test silently wins over the .env written by a later one. Every key any test
# touches must be cleared here, or tests pass alone and fail in the suite.
MANAGED_KEYS = list(BASE_ENV) + [
    "USDT_CONTRACT", "EVM_CHAIN_NAME", "WALLET_PRIVATE_KEY",
    "TG_HOST", "TG_GRAPH", "TG_SECRET", "TG_USERNAME", "TG_PASSWORD",
    "LLM_PROVIDER", "LLM_MODEL", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "TRACELEDGER_DB",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in MANAGED_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_addresses_are_normalised_to_lowercase(tmp_path):
    cfg = load_config(write_env(tmp_path))
    assert "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359" in cfg.allowed_contracts

def test_label_is_kept_but_identity_is_the_address(tmp_path):
    cfg = load_config(write_env(tmp_path, {"USDT_CONTRACT": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"}))
    assert cfg.token_contracts["0xc2132d05d31c914a87c6611c10748aeb04b58e8f"] == "USDT"
    assert len(cfg.allowed_contracts) == 2

def test_missing_rpc_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="EVM_RPC_URL"):
        load_config(write_env(tmp_path, base={k: v for k, v in BASE_ENV.items() if k != "EVM_RPC_URL"}))

def test_non_integer_chain_id_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="integer"):
        load_config(write_env(tmp_path, {"EVM_CHAIN_ID": "polygon"}))

def test_malformed_contract_address_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="hex address"):
        load_config(write_env(tmp_path, {"USDC_CONTRACT": "0xdeadbeef"}))

def test_no_tokens_configured_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="No token contracts"):
        load_config(write_env(tmp_path, base={k: v for k, v in BASE_ENV.items() if k != "USDC_CONTRACT"}))

def test_key_material_in_the_environment_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLET_PRIVATE_KEY", "0xdeadbeef")
    with pytest.raises(ConfigError, match="read-only"):
        load_config(write_env(tmp_path))


class TestTigerGraphHost:
    """pyTigerGraph >=2.0 raises on a bare hostname, but TigerGraph's own older docs show the
    bare form, so both spellings must work (RISKS.md S11)."""

    @pytest.mark.parametrize("raw,expected", [
        ("abc123.i.tgcloud.io", "https://abc123.i.tgcloud.io"),
        ("https://abc123.i.tgcloud.io", "https://abc123.i.tgcloud.io"),
        ("https://abc123.i.tgcloud.io/", "https://abc123.i.tgcloud.io"),
        ("  abc123.i.tgcloud.io  ", "https://abc123.i.tgcloud.io"),
        ("http://abc123.i.tgcloud.io", "http://abc123.i.tgcloud.io"),
        ("localhost", "http://localhost"),
        ("localhost:14240", "http://localhost:14240"),
        ("127.0.0.1", "http://127.0.0.1"),
        ("", None),
        (None, None),
    ])
    def test_host_is_normalised(self, raw, expected):
        from traceledger.config import normalise_tg_host
        assert normalise_tg_host(raw) == expected

    def test_bare_host_from_env_gets_a_scheme(self, tmp_path):
        cfg = load_config(write_env(tmp_path, {"TG_HOST": "abc123.i.tgcloud.io"}))
        assert cfg.tg_host == "https://abc123.i.tgcloud.io"

    def test_normalised_host_is_accepted_by_pytigergraph(self, tmp_path):
        """The whole point: the value we hand the client must not raise on construction."""
        pytest.importorskip("pyTigerGraph")
        from pyTigerGraph import TigerGraphConnection
        cfg = load_config(write_env(tmp_path, {"TG_HOST": "abc123.i.tgcloud.io"}))
        conn = TigerGraphConnection(host=cfg.tg_host, graphname="TraceLedger", gsqlSecret="x")
        assert "abc123.i.tgcloud.io" in conn.host

    def test_bare_host_would_have_failed_without_normalisation(self):
        """Documents the actual failure we are protecting against."""
        pytest.importorskip("pyTigerGraph")
        from pyTigerGraph import TigerGraphConnection
        with pytest.raises(Exception, match="(?i)scheme"):
            TigerGraphConnection(host="abc123.i.tgcloud.io", graphname="G", gsqlSecret="x")


class TestSavannaWorkspaceId:
    """A Savanna workspace id is often the only connection detail a user can find in the
    console, so it is accepted directly (RISKS.md S12)."""

    WS_ID = "7c141e8c7669404f923623083ba01da9"

    def test_bare_workspace_id_becomes_the_endpoint(self):
        from traceledger.config import normalise_tg_host
        assert normalise_tg_host(self.WS_ID) == f"https://{self.WS_ID}.i.tgcloud.io"

    def test_uppercase_id_is_lowercased(self):
        from traceledger.config import normalise_tg_host
        assert normalise_tg_host(self.WS_ID.upper()) == f"https://{self.WS_ID}.i.tgcloud.io"

    def test_a_hostname_is_not_mistaken_for_an_id(self):
        from traceledger.config import normalise_tg_host
        assert normalise_tg_host(f"{self.WS_ID}.i.tgcloud.io") == f"https://{self.WS_ID}.i.tgcloud.io"

    def test_non_hex_name_is_treated_as_a_hostname_not_an_id(self):
        from traceledger.config import normalise_tg_host
        assert normalise_tg_host("r_alliance.i.tgcloud.io") == "https://r_alliance.i.tgcloud.io"

    def test_wrong_length_hex_is_not_treated_as_an_id(self):
        from traceledger.config import normalise_tg_host
        assert normalise_tg_host("deadbeef") == "https://deadbeef"

    def test_workspace_id_from_env_constructs_a_real_connection(self, tmp_path):
        pytest.importorskip("pyTigerGraph")
        from pyTigerGraph import TigerGraphConnection
        cfg = load_config(write_env(tmp_path, {"TG_HOST": self.WS_ID}))
        conn = TigerGraphConnection(host=cfg.tg_host, graphname="TraceLedger", gsqlSecret="x")
        assert self.WS_ID in conn.host and conn.host.startswith("https://")
