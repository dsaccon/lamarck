"""Runs each job in a fresh spawned process with its own wall-clock limit.

A hung, crashed or misbehaving task costs one job, never the evaluation.
"""
from __future__ import annotations

import importlib
import multiprocessing as mp
import time
from typing import Any, Callable


def _child(target: str, job: dict, conn) -> None:
    try:
        module, _, name = target.partition(":")
        result = getattr(importlib.import_module(module), name)(job)
        conn.send({"ok": True, "result": result})
    except BaseException as e:  # noqa: BLE001 — report everything, including SystemExit from model code
        conn.send({"ok": False, "error": f"{type(e).__name__}: {e}"})
    finally:
        conn.close()


def run_many(target: str, jobs: list[dict], max_parallel: int, timeout_s: float,
             on_done: Callable[[int, dict], None] | None = None) -> list[dict]:
    ctx = mp.get_context("spawn")
    results: list[dict | None] = [None] * len(jobs)
    pending = list(range(len(jobs)))
    running: dict[int, tuple[Any, Any, float]] = {}

    def finish(i: int, outcome: dict) -> None:
        results[i] = outcome
        running.pop(i)
        if on_done:
            on_done(i, outcome)

    while pending or running:
        while pending and len(running) < max_parallel:
            i = pending.pop(0)
            recv, send = ctx.Pipe(duplex=False)
            p = ctx.Process(target=_child, args=(target, jobs[i], send), daemon=True)
            p.start()
            send.close()
            running[i] = (p, recv, time.monotonic())
        for i, (p, recv, t0) in list(running.items()):
            if recv.poll():
                try:
                    outcome = recv.recv()
                except EOFError:
                    p.join(5)
                    outcome = {"ok": False, "error": f"worker exited with code {p.exitcode} before reporting"}
                p.join(5)
                finish(i, outcome)
            elif not p.is_alive():
                finish(i, {"ok": False, "error": f"worker exited with code {p.exitcode}"})
            elif time.monotonic() - t0 > timeout_s:
                p.kill()
                p.join()
                finish(i, {"ok": False, "error": f"timeout after {timeout_s:.0f}s"})
        time.sleep(0.05)
    return results  # type: ignore[return-value]
