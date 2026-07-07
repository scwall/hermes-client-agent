"""Unit tests for the windows_control plugin config and multi-agent logic."""
import pytest

import windows_control.tools as tools


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
