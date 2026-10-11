"""The genome: everything about the harness the evolver may change, plus typed patches over it."""
from __future__ import annotations

import ast
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from lamarck import config

OP_NAMES = ("set", "add_note", "remove_note", "put_skill", "del_skill", "put_validator", "del_validator")
SETTABLE = {"root_model", "sub_model", "thinking_level", "context_mode", "repl", "max_obs_chars", "stop_at_output",
            "limits.max_steps", "limits.max_subcalls"}
MAX_NOTES, MAX_NOTE_CHARS, MAX_SKILLS, MAX_VALIDATORS, MAX_SOURCE_CHARS = 12, 500, 8, 4, 6000


class PatchError(ValueError):
    pass


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int = Field(12, ge=1, le=30)
    max_subcalls: int = Field(40, ge=0, le=200)


def _check_source(name: str, src: str, must_define: str) -> None:
    if not name.isidentifier():
        raise ValueError(f"{name!r} is not a valid Python identifier")
    if len(src) > MAX_SOURCE_CHARS:
        raise ValueError(f"{name}: source longer than {MAX_SOURCE_CHARS} chars")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise ValueError(f"{name}: syntax error: {e}") from None
    if not any(isinstance(n, ast.FunctionDef) and n.name == must_define for n in tree.body):
        raise ValueError(f"{name}: source must define a top-level function {must_define}()")


class Genome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_model: str = config.DEFAULT_WORKER
    sub_model: str = config.DEFAULT_WORKER
    thinking_level: str = config.THINKING_LEVELS[0]
    context_mode: Literal["inline", "repl", "both"] = "inline"
    repl: bool = False
    max_obs_chars: int = Field(4000, ge=200, le=50000)
    stop_at_output: bool = False
    system_notes: list[str] = Field(default_factory=list)
    skills: dict[str, str] = Field(default_factory=dict)
    validators: dict[str, str] = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)

    @model_validator(mode="after")
    def _consistent(self) -> "Genome":
        for m in (self.root_model, self.sub_model):
            if m not in config.WORKER_MODELS:
                raise ValueError(f"unknown worker model {m!r}; allowed: {sorted(config.WORKER_MODELS)}")
        if self.thinking_level not in config.THINKING_LEVELS:
            raise ValueError(f"thinking_level must be one of {config.THINKING_LEVELS}")
        if self.context_mode != "inline" and not self.repl:
            raise ValueError("context_mode 'repl' or 'both' requires repl=true")
        if len(self.system_notes) > MAX_NOTES or any(len(n) > MAX_NOTE_CHARS for n in self.system_notes):
            raise ValueError(f"at most {MAX_NOTES} notes of at most {MAX_NOTE_CHARS} chars")
        if len(self.skills) > MAX_SKILLS or len(self.validators) > MAX_VALIDATORS:
            raise ValueError(f"at most {MAX_SKILLS} skills and {MAX_VALIDATORS} validators")
        for name, src in self.skills.items():
            _check_source(name, src, must_define=name)
        for name, src in self.validators.items():
            _check_source(name, src, must_define="check")
        return self


GEN0 = Genome()


class Op(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set", "add_note", "remove_note", "put_skill", "del_skill", "put_validator", "del_validator"]
    path: str | None = None
    value_json: str | None = None
    text: str | None = None
    index: int | None = None
    name: str | None = None
    source: str | None = None


def _need(o: Op, *fields: str) -> None:
    missing = [f for f in fields if getattr(o, f) is None]
    if missing:
        raise PatchError(f"op {o.op} needs {', '.join(missing)}")


def apply(genome: Genome, ops: list[Op]) -> Genome:
    if not ops:
        raise PatchError("empty patch")
    d = genome.model_dump()
    for o in ops:
        if o.op == "set":
            _need(o, "path", "value_json")
            if o.path not in SETTABLE:
                raise PatchError(f"path {o.path!r} is not settable; settable: {sorted(SETTABLE)}")
            try:
                value = json.loads(o.value_json)
            except json.JSONDecodeError as e:
                raise PatchError(f"value_json is not valid JSON: {e}") from None
            *parents, leaf = o.path.split(".")
            target = d
            for p in parents:
                target = target[p]
            target[leaf] = value
        elif o.op == "add_note":
            _need(o, "text")
            d["system_notes"].append(o.text)
        elif o.op == "remove_note":
            _need(o, "index")
            if not 0 <= o.index < len(d["system_notes"]):
                raise PatchError(f"no note at index {o.index}")
            d["system_notes"].pop(o.index)
        elif o.op in ("put_skill", "put_validator"):
            _need(o, "name", "source")
            d["skills" if o.op == "put_skill" else "validators"][o.name] = o.source
        else:
            _need(o, "name")
            bucket = d["skills" if o.op == "del_skill" else "validators"]
            if o.name not in bucket:
                raise PatchError(f"no {o.op.removeprefix('del_')} named {o.name!r}")
            del bucket[o.name]
    try:
        child = Genome.model_validate(d)
    except ValidationError as e:
        raise PatchError(str(e)) from None
    if child == genome:
        raise PatchError("patch does not change the genome")
    return child
