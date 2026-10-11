"""The harness engineer: reads the champion's failures and proposes one typed patch (Opus via Claude Code)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from lamarck import config, llm
from lamarck.genome import OP_NAMES, SETTABLE, Genome, Op, PatchError, apply

MANUAL = (Path(__file__).parent / "prompts" / "engineer.md").read_text()

FOCI = {
    "accuracy": "Fix the most common failure mechanism you see in the failing runs.",
    "cost": "Keep accuracy at least as high while cutting tokens per task.",
    "free": "Make the change you believe will most improve accuracy on unseen tasks, including a larger architectural change.",
}

PROPOSAL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["diagnosis", "hypothesis", "ops"],
    "properties": {
        "diagnosis": {"type": "string"},
        "hypothesis": {"type": "string"},
        "ops": {"type": "array", "minItems": 1, "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False, "required": ["op"],
            "properties": {"op": {"type": "string", "enum": list(OP_NAMES)}, "path": {"type": "string"},
                           "value_json": {"type": "string"}, "text": {"type": "string"},
                           "index": {"type": "integer"}, "name": {"type": "string"},
                           "source": {"type": "string"}}}}},
}


def manual() -> str:
    return MANUAL.format(models=", ".join(sorted(config.WORKER_MODELS)), levels=", ".join(config.THINKING_LEVELS),
                         paths=", ".join(sorted(SETTABLE)))


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n // 2] + "\n...\n" + s[-n // 2:]


def describe_ops(ops: list[dict]) -> str:
    parts = []
    for o in ops:
        if o["op"] == "set":
            parts.append(f"set {o['path']}={o['value_json']}")
        elif o["op"] == "add_note":
            parts.append(f"add_note {o['text'][:80]!r}")
        elif o["op"] == "remove_note":
            parts.append(f"remove_note #{o['index']}")
        else:
            parts.append(f"{o['op']} {o['name']}")
    return "; ".join(parts) or "(none)"


def build_prompt(champ: dict, failures: list[dict], history: list[dict], focus: str) -> str:
    train = champ["scores"]["train"]
    parts = [f"## Focus\n{FOCI[focus]}",
             f"## Champion genome {champ['_id']} (generation {champ['generation']})\n```json\n"
             f"{json.dumps(champ['genome'], indent=2)}\n```",
             f"## Champion on train\naccuracy {train['acc']:.2f} over {train['n']} tasks; by kind {train['by_kind']}; "
             f"{train['tokens']} tokens per task; ${train['cost']:.3f} total; {train['errors']} errors",
             f"## Failing train runs ({len(failures)} shown; candidates are last generation's, see the lineage)"]
    for r in failures:
        steps = r.get("trace", [])
        shown = steps[:1] + (steps[-4:] if len(steps) > 5 else steps[1:])
        trace = "\n".join(f"[{s['role']} {s['step']}] {_clip(s['text'], 1200)}" for s in shown)
        gid = r.get("genome_id")
        origin = "" if gid is None else (f", from champion {gid}" if gid == champ["_id"] else f", from candidate {gid}")
        parts.append(f"### {r['task_id']} ({r['kind']}{origin}), score {r['score']}\nQuestion: {r['question']}\n"
                     f"Expected: {r['expected']}\nGot: {r['answer'][:300]!r}\nError: {r.get('error')}\n"
                     f"Steps: {r['steps']}, sub-calls: {r['subcalls']}, tokens: {r['tokens_in'] + r['tokens_out']}\n"
                     f"Trace (first and last steps):\n{trace or '(no steps recorded)'}")
    tried = [g for g in history if g.get("parent_id")]
    parts.append("## Lineage so far (oldest first)\n" + ("\n".join(
        f"- gen {g['generation']} {g['_id']} [{g.get('focus', '')}] {describe_ops(g.get('ops', []))} -> "
        f"{g['status']}: {g.get('reason', '')} (train acc {g.get('scores', {}).get('train', {}).get('acc', '?')})"
        for g in tried) or "(no patches tried yet)"))
    parts.append("Propose one patch now.")
    return "\n\n".join(parts)


def propose(champ: dict, failures: list[dict], history: list[dict], focus: str,
            call: Callable[[str, str, dict], dict] = llm.claude_json) -> dict:
    prompt = build_prompt(champ, failures, history, focus)
    error: str | None = None
    out: dict = {}
    for _ in range(2):
        attempt = prompt if error is None else (f"{prompt}\n\n## Your previous proposal was invalid\n{error}\n"
                                                "Fix it and propose again.")
        try:
            out = call(attempt, manual(), PROPOSAL_SCHEMA)
            ops = [Op.model_validate(o) for o in out["ops"]]
            child = apply(Genome.model_validate(champ["genome"]), ops)
            return {"ok": True, "genome": child.model_dump(), "ops": [o.model_dump(exclude_none=True) for o in ops],
                    "hypothesis": out.get("hypothesis", ""), "diagnosis": out.get("diagnosis", "")}
        except (llm.EngineerError, PatchError, ValidationError, KeyError, TypeError) as e:
            error = str(e)[:1500]
    return {"ok": False, "error": error or "unknown error", "hypothesis": out.get("hypothesis", ""),
            "diagnosis": out.get("diagnosis", "")}
