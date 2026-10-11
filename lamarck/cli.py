"""Lamarck CLI: evolve | long | status | rollback | ping."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

from lamarck import config, engineer, gate, store
from lamarck.evaluate import evaluate_many
from lamarck.genome import GEN0


def ensure_root(run: str) -> str:
    gid = store.champion(run)
    if gid:
        return gid
    gid = store.insert_genome(run, GEN0.model_dump(), None, 0, status="accepted",
                              reason="generation 0: plain inline harness")
    store.set_champion(run, gid)
    store.log(run, f"created generation 0 ({gid})")
    return gid


def ensure_scores(run: str, gid: str, splits: tuple[str, ...] = ("train", "gate")) -> dict:
    missing = [(gid, s) for s in splits if s not in store.get_genome(gid).get("scores", {})]
    if missing:
        store.log(run, f"evaluating {gid} on {', '.join(s for _, s in missing)}")
        evaluate_many(missing, run)
    return store.get_genome(gid)


def generation(run: str, g: int, k: int) -> None:
    champ = ensure_scores(run, ensure_root(run))
    history = store.lineage(run)[-12:]
    failures = store.failing_runs(champ["_id"], "train", limit=4)
    for prev in [x["_id"] for x in history if x["generation"] == g - 1 and x["status"] not in ("invalid", "accepted")]:
        failures += store.failing_runs(prev, "train", limit=2)
    failures = failures[:8]
    foci = list(engineer.FOCI)[:k]
    store.log(run, f"gen {g}: engineer reading {len(failures)} failing runs of champion {champ['_id']} "
                   f"(train acc {champ['scores']['train']['acc']:.2f}); foci: {', '.join(foci)}")
    with ThreadPoolExecutor(len(foci)) as ex:
        proposals = list(ex.map(lambda f: engineer.propose(champ, failures, history, f), foci))
    cands = []
    for focus, p in zip(foci, proposals):
        if not p["ok"]:
            store.insert_genome(run, champ["genome"], champ["_id"], g, hypothesis=p["hypothesis"],
                                diagnosis=p["diagnosis"], focus=focus, status="invalid", reason=p["error"][:500])
            store.log(run, f"gen {g} [{focus}] invalid proposal: {p['error'][:160]}")
            continue
        gid = store.insert_genome(run, p["genome"], champ["_id"], g, ops=p["ops"], hypothesis=p["hypothesis"],
                                  diagnosis=p["diagnosis"], focus=focus)
        cands.append(gid)
        store.log(run, f"gen {g} [{focus}] {gid}: {engineer.describe_ops(p['ops'])} | {p['hypothesis'][:220]}")
    if not cands:
        store.log(run, f"gen {g}: no valid proposals")
        return
    sums = evaluate_many([(c, "train") for c in cands], run)
    n_train, n_gate = config.SPLITS["train"][0], config.SPLITS["gate"][0]
    parent_train = gate.Score.of(champ["scores"]["train"])
    ranked = sorted(cands, key=lambda c: (sums[(c, "train")]["acc"], -sums[(c, "train")]["tokens"]), reverse=True)
    for c in ranked:
        s = sums[(c, "train")]
        store.log(run, f"gen {g} {c}: train acc {s['acc']:.2f} {s['by_kind']}, {s['tokens']:,} tok/task, ${s['cost']:.3f}")
    best = ranked[0]
    for c in ranked[1:]:
        ok, why = gate.train_passes(parent_train, gate.Score.of(sums[(c, "train")]), n_train)
        store.set_status(c, "not_selected" if ok else "rejected_no_gain", why)
    ok, why = gate.train_passes(parent_train, gate.Score.of(sums[(best, "train")]), n_train)
    if not ok:
        store.set_status(best, "rejected_no_gain", why)
        store.log(run, f"gen {g}: no candidate beat the champion ({why})")
        return
    gate_sum = evaluate_many([(best, "gate")], run)[(best, "gate")]
    v = gate.gate_verdict(parent_train, gate.Score.of(sums[(best, "train")]), gate.Score.of(champ["scores"]["gate"]),
                          gate.Score.of(gate_sum), n_train, n_gate)
    store.set_status(best, v.status, f"{why}; {v.reason}")
    if v.status == "accepted":
        store.set_champion(run, best)
    store.log(run, f"gen {g}: {best} {v.status.upper()} ({why}; {v.reason})")


def cmd_evolve(a: argparse.Namespace) -> None:
    if a.workload:
        if store.lineage(a.run) and store.workload(a.run) != a.workload:
            raise SystemExit(f"run {a.run!r} already uses workload {store.workload(a.run)!r}; pick another run name")
        store.set_workload(a.run, a.workload)
    ensure_root(a.run)
    lineage = store.lineage(a.run)
    busy = [x["_id"] for x in lineage if x["status"] == "candidate"]
    if busy and not a.force:
        raise SystemExit(f"run {a.run!r} has candidates still being evaluated ({', '.join(busy)}): another evolve "
                         "may be running. Wait for it, or pass --force if it crashed.")
    start = max(x["generation"] for x in lineage) + 1
    for g in range(start, start + a.gens):
        generation(a.run, g, a.candidates)


def cmd_long(a: argparse.Namespace) -> None:
    ids = list(dict.fromkeys([store.lineage(a.run)[0]["_id"], store.champion(a.run)]))
    for gid in ids:
        ensure_scores(a.run, gid, ("long",))
    for gid in ids:
        s = store.get_genome(gid)["scores"]["long"]
        store.log(a.run, f"long split: {gid} acc {s['acc']:.2f} {s['by_kind']}, {s['tokens']:,} tok/task, ${s['cost']:.3f}")


def cmd_status(a: argparse.Namespace) -> None:
    champ = store.champion(a.run)
    for x in store.lineage(a.run):
        sc = x.get("scores", {})
        acc = {s: sc.get(s, {}).get("acc", "-") for s in ("train", "gate", "long")}
        print(f"{'*' if x['_id'] == champ else ' '} g{x['generation']:<2} {x['_id']} {x['status']:<17} "
              f"train={acc['train']} gate={acc['gate']} long={acc['long']}  {engineer.describe_ops(x.get('ops', []))[:90]}")


def cmd_rollback(a: argparse.Namespace) -> None:
    g = store.get_genome(a.to)
    if not g or g["run"] != a.run or g["status"] != "accepted":
        raise SystemExit(f"{a.to} is not an accepted genome of run {a.run!r}")
    store.set_champion(a.run, a.to)
    store.log(a.run, f"rollback: champion is now {a.to}")


def cmd_ping(_a: argparse.Namespace) -> None:
    store.ping()
    print("ping ok")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="lamarck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("evolve", cmd_evolve), ("long", cmd_long), ("status", cmd_status),
                     ("rollback", cmd_rollback), ("ping", cmd_ping)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if name != "ping":
            p.add_argument("--run", default="main")
        if name == "evolve":
            p.add_argument("--gens", type=int, default=1)
            p.add_argument("--candidates", type=int, default=3, choices=[1, 2, 3])
            p.add_argument("--force", action="store_true", help="evolve even if candidates look in flight")
            p.add_argument("--workload", choices=["logs", "tickets"], help="task family for a new run (default logs)")
        if name == "rollback":
            p.add_argument("--to", required=True)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
