"""Spike: is there a gap for evolution to close? Gen-0 vs a hand-written RLM genome at several input sizes.

The hand-written genome is a yardstick only; the evolver never sees it.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lamarck import pool  # noqa: E402
from lamarck.genome import GEN0, Genome  # noqa: E402

HAND_RLM = Genome(repl=True, context_mode="repl", limits={"max_steps": 14, "max_subcalls": 80},
                  system_notes=["The data is large. Inspect it with code, use code for exact filtering and counting, "
                                "and use llm_query_batch on small chunks only for judgments code cannot make."])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, nargs="+", default=[800, 2000])
    ap.add_argument("--per-kind", type=int, default=2)
    ap.add_argument("--dump", help="write every run result to this JSONL file")
    a = ap.parse_args()
    dump = open(a.dump, "w") if a.dump else None
    for n_lines in a.lines:
        for name, genome in (("gen0", GEN0), ("hand_rlm", HAND_RLM)):
            jobs = [{"genome": genome.model_dump(), "split": "spike", "idx": i, "n_lines": n_lines}
                    for i in range(4 * a.per_kind)]
            t0 = time.time()
            outs = pool.run_many("lamarck.worker:run_job", jobs, max_parallel=16, timeout_s=600)
            rows = [o["result"] if o["ok"] else {"score": 0.0, "kind": "?", "tokens_in": 0, "tokens_out": 0,
                                                 "cost": 0.0, "error": o["error"]} for o in outs]
            if dump:
                for r in rows:
                    dump.write(json.dumps({"genome": name, "n_lines": n_lines, **r}) + "\n")
                dump.flush()
            kinds = defaultdict(list)
            for r in rows:
                kinds[r["kind"]].append(r["score"])
            acc = sum(r["score"] for r in rows) / len(rows)
            tok = sum(r["tokens_in"] + r["tokens_out"] for r in rows) / len(rows)
            errs = [r["error"] for r in rows if r.get("error")]
            print(f"{n_lines:>6} lines  {name:<9} acc={acc:.2f}  by_kind={ {k: round(sum(v) / len(v), 2) for k, v in kinds.items()} }  "
                  f"tok/task={tok:,.0f}  cost=${sum(r['cost'] for r in rows):.3f}  wall={time.time() - t0:.0f}s  errors={len(errs)}",
                  flush=True)
            for e in errs[:3]:
                print("      error:", e[:200], flush=True)


if __name__ == "__main__":
    main()
