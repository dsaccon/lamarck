import pytest

from lamarck import llm


class Err(Exception):
    def __init__(self, code):
        super().__init__(f"code {code}")
        self.code = code


def test_with_retries_retries_rate_limits_then_succeeds():
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise Err(429)
        return "ok"

    assert llm.with_retries(fn, sleep=sleeps.append) == "ok"
    assert len(calls) == 3 and len(sleeps) == 2


def test_with_retries_does_not_retry_client_errors():
    calls = []

    def fn():
        calls.append(1)
        raise Err(400)

    with pytest.raises(Err):
        llm.with_retries(fn, sleep=lambda s: None)
    assert len(calls) == 1


def test_with_retries_gives_up_after_attempts():
    def fn():
        raise Err(503)

    with pytest.raises(Err):
        llm.with_retries(fn, attempts=3, sleep=lambda s: None)


def test_claude_command_disables_tools_and_requests_schema(tmp_path):
    cmd = llm.claude_command({"type": "object"}, tmp_path / "s.md")
    assert cmd[1] == "-p"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--json-schema" in cmd and "--no-session-persistence" in cmd


def test_claude_env_drops_nesting_flag_and_secrets(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("MONGODB_URI", "y")
    env = llm.claude_env()
    assert not {"CLAUDECODE", "GEMINI_API_KEY", "MONGODB_URI"} & set(env)


def test_claude_timeout_and_missing_binary_become_engineer_errors(monkeypatch):
    import subprocess

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(llm.subprocess, "run", timeout)
    with pytest.raises(llm.EngineerError, match="timed out"):
        llm.claude_json("p", "s", {"type": "object"}, timeout_s=1)

    def missing(*a, **k):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(llm.subprocess, "run", missing)
    with pytest.raises(llm.EngineerError, match="not found"):
        llm.claude_json("p", "s", {"type": "object"})
