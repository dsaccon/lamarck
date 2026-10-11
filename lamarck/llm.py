"""Provider calls: Gemini workers through the raw API; the engineer through headless Claude Code."""
from __future__ import annotations

import json
import os
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lamarck import config

RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_NAMES = {"ConnectError", "ConnectTimeout", "ReadTimeout", "ReadError", "RemoteProtocolError",
                   "WriteError", "PoolTimeout"}


@dataclass
class Turn:
    role: str  # "user" | "model"
    text: str
    raw: Any = None  # provider-native content of a model turn (keeps Gemini thought signatures)


def is_retryable(e: BaseException) -> bool:
    return getattr(e, "code", None) in RETRYABLE_CODES or type(e).__name__ in RETRYABLE_NAMES


def with_retries(fn: Callable[[], Any], attempts: int = 6, base_s: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep) -> Any:
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            if not is_retryable(e) or i == attempts - 1:
                raise
            sleep(min(60.0, base_s * 2 ** i) * (0.5 + random.random()))
    raise AssertionError("unreachable")


class GeminiClient:
    def __init__(self, api_key: str):
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key)

    def generate(self, model: str, system: str, history: list[Turn], thinking_level: str) -> tuple[str, Any, dict]:
        types = self._types
        contents = [t.raw if t.role == "model" and t.raw is not None
                    else types.Content(role=t.role, parts=[types.Part(text=t.text)]) for t in history]
        cfg = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=16384,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        resp = with_retries(lambda: self._client.models.generate_content(model=model, contents=contents, config=cfg))
        cand = resp.candidates[0] if resp.candidates else None
        raw = cand.content if cand is not None and cand.content and cand.content.parts else None
        text = "".join(p.text for p in (raw.parts if raw else [])
                       if getattr(p, "text", None) and not getattr(p, "thought", False))
        um = resp.usage_metadata
        tin = (um.prompt_token_count or 0) if um else 0
        tout = ((um.candidates_token_count or 0) + (um.thoughts_token_count or 0)) if um else 0
        return text, raw, {"in": tin, "out": tout}


class EngineerError(RuntimeError):
    pass


def claude_command(schema: dict, system_file: Path) -> list[str]:
    return [config.CLAUDE_BIN, "-p", "--model", config.ENGINEER_MODEL, "--effort", config.ENGINEER_EFFORT,
            "--system-prompt-file", str(system_file), "--tools", "", "--strict-mcp-config",
            "--setting-sources", "project", "--disable-slash-commands", "--no-session-persistence",
            "--output-format", "json", "--json-schema", json.dumps(schema)]


def claude_env() -> dict[str, str]:
    drop = {"CLAUDECODE", "GEMINI_API_KEY", "MONGODB_URI"}
    return {k: v for k, v in os.environ.items() if k not in drop}


def claude_json(prompt: str, system: str, schema: dict, timeout_s: int = 900) -> dict:
    with tempfile.TemporaryDirectory(prefix="lamarck-eng-") as d:
        system_file = Path(d, "system.md")
        system_file.write_text(system)
        proc = subprocess.run(claude_command(schema, system_file), input=prompt, capture_output=True, text=True,
                              cwd=d, env=claude_env(), timeout=timeout_s)
    if proc.returncode != 0:
        raise EngineerError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[-1500:]}")
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise EngineerError(f"claude printed non-JSON: {proc.stdout[-1500:]}") from None
    if out.get("is_error"):
        raise EngineerError(f"claude reported an error: {str(out.get('result'))[-1500:]}")
    if isinstance(out.get("structured_output"), dict):
        return out["structured_output"]
    try:
        return json.loads(out.get("result", ""))
    except (TypeError, json.JSONDecodeError):
        raise EngineerError("claude returned no structured output") from None
