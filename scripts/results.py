"""Print a markdown summary of an evolution run from MongoDB: the champion's path and every verdict."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lamarck import engineer, store  # noqa: E402


def fmt(sc: dict | None) -> str:
    return "-" if not sc else f"{sc['acc']:.2f}"


def main(run: str = "main") -> None:
    lineage = store.lineage(run)
    champ = store.champion(run)
    by_id = {g["_id"]: g for g in lineage}
    path, cur = [], by_id.get(champ)
    while cur:
        path.insert(0, cur)
        cur = by_id.get(cur["parent_id"])
    print(f"## Champion path ({run})\n")
    print("| gen | genome | train | gate | long | tokens/task (train) | patch |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for g in path:
        sc = g.get("scores", {})
        tok = sc.get("train", {}).get("tokens", "-")
        print(f"| {g['generation']} | {g['_id']} | {fmt(sc.get('train'))} | {fmt(sc.get('gate'))} | {fmt(sc.get('long'))} "
              f"| {tok:,} | {engineer.describe_ops(g.get('ops', []))[:120] or 'generation 0'} |")
    print("\n## Every candidate\n")
    print("| gen | genome | focus | status | train | tokens/task | reason |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for g in lineage:
        if g["parent_id"] is None:
            continue
        tr = g.get("scores", {}).get("train")
        tok = f"{tr['tokens']:,}" if tr else "-"
        print(f"| {g['generation']} | {g['_id']} | {g['focus']} | {g['status']} | {fmt(tr)} | {tok} | {g['reason'][:110]} |")


if __name__ == "__main__":
    main(*sys.argv[1:])
