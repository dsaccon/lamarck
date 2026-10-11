"""Runs genomes over task splits in isolated workers and records every run in MongoDB."""
from __future__ import annotations

from collections import defaultdict

from lamarck import config, pool, store
from lamarck.harness import error_result
from lamarck.tasks import make_task


def summarize(results: list[dict]) -> dict:
    n = len(results)
    kinds: dict[str, list[float]] = defaultdict(list)
    for r in results:
        kinds[r["kind"]].append(r["score"])
    return {"acc": round(sum(r["score"] for r in results) / n, 4),
            "tokens": round(sum(r["tokens_in"] + r["tokens_out"] for r in results) / n),
            "cost": round(sum(r["cost"] for r in results), 4),
            "n": n,
            "errors": sum(1 for r in results if r.get("error")),
            "by_kind": {k: round(sum(v) / len(v), 3) for k, v in sorted(kinds.items())}}


def evaluate_many(pairs: list[tuple[str, str]], run: str | None = None) -> dict[tuple[str, str], dict]:
    jobs, keys = [], []
    for gid, split in pairs:
        genome = store.get_genome(gid)["genome"]
        for i in range(config.SPLITS[split][0]):
            jobs.append({"genome": genome, "split": split, "idx": i})
            keys.append((gid, split, i))
    done = {"n": 0}

    def progress(_i: int, _outcome: dict) -> None:
        done["n"] += 1
        if run and (done["n"] % 6 == 0 or done["n"] == len(jobs)):
            store.log(run, f"  evaluated {done['n']}/{len(jobs)} task runs")

    outcomes = pool.run_many("lamarck.worker:run_job", jobs, config.MAX_PARALLEL, config.TASK_TIMEOUT_S, on_done=progress)
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for (gid, split, i), o in zip(keys, outcomes):
        grouped[(gid, split)].append(o["result"] if o["ok"]
                                     else error_result(make_task(split, i), o["error"]).model_dump(mode="json"))
    summaries = {}
    for (gid, split), results in grouped.items():
        store.insert_runs(gid, split, results)
        summaries[(gid, split)] = summarize(results)
        store.set_scores(gid, split, summaries[(gid, split)])
    return summaries
