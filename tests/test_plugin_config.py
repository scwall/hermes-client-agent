"""Unit tests for the windows_control plugin config and multi-agent logic."""
import json
import tempfile
from pathlib import Path

import pytest

import windows_control.tools as tools


class TestLoadStateFallback:
    """Tests for _load_state_fallback() — state.json parsing."""

    def test_flat_format_auto_converted(self):
        """Old flat state.json is converted to multi-agent format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "agent_url": "http://192.168.1.4:8765",
                "token": "test-token",
                "timeout": 30,
                "enabled": True,
            }, f)
            tmp = Path(f.name)

        try:
            tools.STATE_FILE = tmp
            cfg = tools._load_state_fallback()
            assert "agents" in cfg
            assert "default" in cfg["agents"]
            assert cfg["agents"]["default"]["url"] == "http://192.168.1.4:8765"
            assert cfg["agents"]["default"]["token"] == "test-token"
            assert cfg["default_agent"] == "default"
        finally:
            tmp.unlink(missing_ok=True)

    def test_multi_agent_format_parsed(self):
        """New multi-agent state.json is parsed correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "agents": {
                    "laptop": {"url": "http://1.1.1.1:8765", "token": "tok1", "timeout": 30},
                    "server": {"url": "http://2.2.2.2:8765", "token": "tok2", "timeout": 20},
                },
                "default_agent": "laptop",
            }, f)
            tmp = Path(f.name)

        try:
            orig = tools.STATE_FILE
            tools.STATE_FILE = tmp
            cfg = tools._load_state_fallback()
            assert len(cfg["agents"]) == 2
            assert cfg["default_agent"] == "laptop"
        finally:
            tools.STATE_FILE = orig
            tmp.unlink(missing_ok=True)

    def test_no_state_file_returns_defaults(self):
        """No state.json → default config returned."""
        orig = tools.STATE_FILE
        tools.STATE_FILE = Path("/nonexistent/state.json")
        try:
            cfg = tools._load_state_fallback()
            assert "agents" in cfg
            assert "default" in cfg["agents"]
        finally:
            tools.STATE_FILE = orig

    def test_invalid_json_returns_defaults(self):
        """Corrupt state.json → default config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json {{{")
            tmp = Path(f.name)

        try:
            orig = tools.STATE_FILE
            tools.STATE_FILE = tmp
            cfg = tools._load_state_fallback()
            assert "agents" in cfg
        finally:
            tools.STATE_FILE = orig
            tmp.unlink(missing_ok=True)


class TestGetAgentConfig:
    """Tests for _get_agent_config() — agent resolution."""

    def test_specific_agent_returned(self):
        config = {
            "agents": {
                "laptop": {"url": "http://a", "token": "t1"},
                "server": {"url": "http://b", "token": "t2"},
            },
            "default_agent": "laptop",
        }
        cfg = tools._get_agent_config(config, "server")
        assert cfg["url"] == "http://b"

    def test_default_agent_fallback(self):
        config = {
            "agents": {
                "laptop": {"url": "http://a", "token": "t1"},
                "server": {"url": "http://b", "token": "t2"},
            },
            "default_agent": "server",
        }
        cfg = tools._get_agent_config(config)
        assert cfg["url"] == "http://b"

    def test_first_agent_fallback_when_no_default(self):
        config = {
            "agents": {
                "laptop": {"url": "http://a", "token": "t1"},
            },
        }
        cfg = tools._get_agent_config(config)
        assert cfg["url"] == "http://a"

    def test_no_agents_raises(self):
        config = {"agents": {}, "default_agent": ""}
        with pytest.raises(RuntimeError, match="No agents configured"):
            tools._get_agent_config(config)


class TestMaskToken:
    """Tests for _mask_token() — token obfuscation."""

    def test_short_token_masked(self):
        assert tools._mask_token("abc") == "abc***"

    def test_normal_token_masked(self):
        masked = tools._mask_token("hermes-windows-agent-secret-change-me")
        assert "***" in masked
        assert masked.startswith("hermes")
        assert masked.endswith("e-me")

    def test_env_var_preserved(self):
        assert tools._mask_token("${LAPTOP_TOKEN}") == "${LAPTOP_TOKEN}"

    def test_empty_token(self):
        assert tools._mask_token("") == ""


class TestLoadConfig:
    """Tests for _load_config() — config.yaml vs state.json."""

    def test_returns_config_and_source(self):
        config, source = tools._load_config()
        assert "agents" in config
        assert source in ("config.yaml", "state.json")
