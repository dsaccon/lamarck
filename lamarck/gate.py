"""The acceptance rule, as pure functions.

A candidate must beat its parent on train (one more task right, or the same accuracy for at least 15%
fewer tokens), and must not lose more than one task's worth of accuracy on the held-out gate split.
"""
from __future__ import annotations

from dataclasses import dataclass

EPS = 1e-9
TOKEN_SAVING = 0.85


@dataclass(frozen=True)
class Score:
    acc: float
    tokens: float

    @classmethod
    def of(cls, summary: dict) -> "Score":
        return cls(summary["acc"], summary["tokens"])


@dataclass(frozen=True)
class Verdict:
    status: str  # accepted | rejected_no_gain | rejected_overfit
    reason: str


def train_passes(parent: Score, cand: Score, n_train: int) -> tuple[bool, str]:
    if cand.acc >= parent.acc + 1 / n_train - EPS:
        return True, f"train acc {parent.acc:.2f} -> {cand.acc:.2f}"
    if cand.acc >= parent.acc - EPS and cand.tokens <= TOKEN_SAVING * parent.tokens:
        return True, f"train acc held at {cand.acc:.2f}; tokens/task {parent.tokens:,.0f} -> {cand.tokens:,.0f}"
    return False, (f"no train gain: acc {parent.acc:.2f} -> {cand.acc:.2f}, "
                   f"tokens/task {parent.tokens:,.0f} -> {cand.tokens:,.0f}")


def gate_verdict(p_train: Score, c_train: Score, p_gate: Score, c_gate: Score, n_train: int, n_gate: int) -> Verdict:
    detail = f"gate acc {p_gate.acc:.2f} -> {c_gate.acc:.2f}"
    if c_gate.acc >= p_gate.acc - 1 / n_gate - EPS:
        return Verdict("accepted", detail)
    if c_train.acc - p_train.acc >= 2 / n_train - EPS:
        return Verdict("rejected_overfit", f"train gain {c_train.acc - p_train.acc:+.2f} did not hold out: {detail}")
    return Verdict("rejected_no_gain", f"gate regression: {detail}")
