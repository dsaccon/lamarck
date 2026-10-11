# Spike: is there a gap for evolution to close?

Run on 2026-10-11 with `scripts/spike.py --lines 800 2000 --per-kind 2` (8 tasks per row, Gemini 3.8 Flash, thinking low).

```
   800 lines  gen0      acc=0.88  by_kind={'needle': 1.0, 'topk': 1.0, 'distinct': 0.5, 'pairs': 1.0}  tok/task=65,763  cost=$0.536  wall=112s  errors=0
   800 lines  hand_rlm  acc=1.00  by_kind={'needle': 1.0, 'topk': 1.0, 'distinct': 1.0, 'pairs': 1.0}  tok/task=33,822  cost=$0.272  wall=98s  errors=0
  2000 lines  gen0      acc=0.75  by_kind={'needle': 1.0, 'topk': 1.0, 'distinct': 0.0, 'pairs': 0.98}  tok/task=155,647  cost=$1.157  wall=174s  errors=0
  2000 lines  hand_rlm  acc=1.00  by_kind={'needle': 1.0, 'topk': 1.0, 'distinct': 1.0, 'pairs': 1.0}  tok/task=33,819  cost=$0.243  wall=44s  errors=0
```

Every gen-0 failure is a near miss: distinct-user counts off by one or two (expected 78, got 76; 69 vs 68; 34 vs 33) and one pairs list at F1 0.97. That is context rot on aggregation, and exact counting in code removes it. The hand-written RLM genome (data in the REPL, code for counting, sub-calls for judgment) scores 1.00 at both sizes for about 34k tokens per task, 4.6x fewer than inline at 2000 lines.

Decision: train and gate tasks use 2000 log lines (about 155k tokens inline). The long split uses 16000 lines (8x, about 1.2M tokens), beyond the 1M-token window: an inline harness cannot read it, while a REPL-based one never puts it in context. Gen-0 at 0.75 is above the spec target of 0.4, so the visible gain on train is about 25 points plus a 4-5x token cut; the long split carries the generalization result. The hand-written genome is a yardstick only; the evolver never sees it.
