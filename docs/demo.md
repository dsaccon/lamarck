# Demo script

## 1-minute video (submission)

1. **0:00 Hook (10 s).** "Agents get worse as their context grows, and people hand-tune harnesses to fix it. Lamarck is a harness that rewrites its own architecture from its own failures."
2. **0:10 The live view (15 s).** Open `http://localhost:8077/?run=main`. Point at the lineage tree: generation 0 on the left, the gold-ringed champion on the right, green accepted, grey no-gain, red overfit.
3. **0:25 The overfit catch (15 s).** Click the red generation-1 node. "It aced practice but invented REPL outputs on held-out tasks. The gate threw it out." Click the generation-2 node: show the engineer's diagnosis naming that failure and the fix (`stop_at_output`, `log_catalog` skill).
4. **0:40 The result (15 s).** The curve: accuracy up, tokens down. Then the long split: gen-0 0.38 at 1.4M tokens per task; the evolved harness 1.00 at about 12k tokens, on inputs 8x longer than it trained on.
5. **0:55 Close (5 s).** "Built today on MongoDB Atlas: every genome, run and trace is in the lineage, with rollback."

## 3-minute live demo

1. **Problem (30 s).** Context rot; harness choice moves cost up to 5x; the frontier is jagged so no hand-built harness fits every workload; Prime Agent's self-edits have no acceptance gate.
2. **The loop (30 s).** One sentence each: genome, worker, engineer, gate, MongoDB. Show the round diagram from the explainer doc.
3. **Live (60 s).** Run `python -m lamarck.cli evolve --run main --gens 1 --candidates 2` in a terminal next to the live view. The feed shows the engineer reading failures and its proposals within about a minute; the candidates' evaluation then streams in. Narrate while it runs; do not wait for the verdict.
4. **The lineage (45 s).** Walk the tree: gen 1 overfit rejection and why; gen 2 accepted with its diagnosis; gens 3 and 5 cutting tokens; gens 4 and 6 rejected for saving under 15%.
5. **Generalization (15 s).** The long split numbers. "It never saw an input this long, and it still gets every answer."

Run only one `evolve` per run at a time: `evolve` refuses while another run's candidates are still being
evaluated (`--force` overrides it after a crash).

## Backup if the network fails

`python -m lamarck.cli status --run main` and `python scripts/results.py main` print the whole lineage from Atlas; `docs/results.md` has the same tables.
