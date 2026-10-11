# Lamarck

**An agent harness that rewrites its own architecture from its own failures.**

A run of the harness is fully determined by a typed *genome*: context policy, REPL and tool access,
recursion budgets, rules, skills, validators and models. An *engineer* agent (Claude Opus 5.5) reads
the champion genome's failing traces and proposes typed patches; an *eval gate* accepts a patch only if
it beats its parent on training tasks **and** does not regress on held-out tasks. Every genome, run and
trace lives in MongoDB Atlas as a lineage tree with rollback.

Variation is Lamarckian (directed changes acquired from the harness's own experience are written into
the genome its descendants inherit), selection is Darwinian (the gate).

## Result

| harness | train | held-out gate | 8x longer inputs | tokens per task (train / long) |
| --- | --- | --- | --- | --- |
| generation 0 (plain inline) | 0.83 | 0.87 | 0.38 | 149,983 / 1,438,737 |
| evolved champion (generation 5 of 8) | 1.00 | 1.00 | 1.00 | 4,261 / 5,079 |

In 8 generations the harness moved its data out of the model's context into a REPL, wrote its own
parsing and template-picking skills, turned on a guard against imagined tool output, and trimmed itself.
On inputs 8x longer than any it trained on it answers everything for about 283x fewer tokens. Generation 0
cannot keep up there: each long input is about 1.03M tokens, right at Gemini's 1M window, so 3 of its 8 runs
overflowed the window as soon as it needed a second turn, and it got 3 of the other 5 right. The evolved
harness never puts the data in context. Along the way the gate rejected a candidate that aced training but
failed held-out tasks. Full lineage:
[docs/results.md](docs/results.md); spike: [docs/spike.md](docs/spike.md).


## A second workload, a different species

The same loop, unchanged, on a synthetic support inbox (intents phrased many ways, with negated decoys):

| harness | train | held-out gate | 8x longer inputs | tokens per task (train / long) |
| --- | --- | --- | --- | --- |
| generation 0 (plain inline) | 0.95 | 0.97 | 0.30 | 117,740 / 709,538 |
| evolved champion (generation 3 of 5) | 1.00 | 1.00 | 0.87 | 65,714 / 266,782 |

On logs it evolved toward computing: parse and count in Python, no sub-model calls. On tickets it evolved
toward delegating reading: a `tag_records` skill has the sub-model tag each unique ticket text, then code
counts. The two species scale differently: on 8x longer inputs the logs harness's cost barely moved, while
the tickets harness's grew with the data until it hit its sub-call budget.

## Why

- **Context rot.** Agents that append every observation to their context degrade as it grows. The fix
  is architectural (keep the data out of the context, compute over it, recurse on pieces; Zhang &
  Khattab's *Recursive Language Models*), not a better prompt.
- **The frontier is jagged.** What a model is good at varies by task, so no hand-built harness fits
  every workload. The harness should adapt to the workload it actually sees.
- **Harnesses move cost.** HarnessTax finds harness choice changes cost up to 5× at similar success.
  Lamarck's gate counts tokens as well as accuracy.
- **Self-edits need a gate.** Prime Agent's Continual Harness carries typed self-edits across runs but
  has no acceptance test; its authors call for "auditable rollback of contaminated refinements". Lamarck
  is that gate, applied to the whole architecture.

## How it works

```
             ┌──────────────── MongoDB Atlas ────────────────┐
             │ genomes (lineage)  runs (+traces)  feed  meta │
             └──────▲───────────────▲─────────────────▲──────┘
                    │               │                 │
  champion ──► engineer (Opus 5.5, claude -p) ──► typed patch ──► candidate genome
                                                                      │
                     gate ◄── train eval (12 tasks) ◄── Gemini 3.8 Flash workers, one process per task
                      │
         beats parent on train? ──► held-out gate eval (8 tasks) ──► accept / reject (no gain | overfit)
```

- **Genome** (`lamarck/genome.py`): `context_mode` (inline / repl / both), `repl`, `max_obs_chars`,
  `limits`, `system_notes`, `skills` (Python functions preloaded into the REPL), `validators`
  (`check(answer, question)`), models and thinking level. The base prompt, scorer, task data and hard
  caps are outside the genome, so no patch can touch them.
- **Harness** (`lamarck/harness.py`): the RLM text protocol. The worker replies with a ```` ```python ````
  block (run in a persistent REPL with `llm_query` / `llm_query_batch` sub-calls) or `FINAL:` /
  `FINAL_VAR(name)`. Each task runs in its own spawned process with timeouts, after secrets are removed
  from its environment.
- **Workload** (`lamarck/tasks.py`): deterministic synthetic production logs with exact ground truth.
  Questions: find a trace id (needle), service with most timeouts in a window (top-k), distinct users
  with an error category (count), users with both a payment decline and a timeout (pairs). Event
  messages are paraphrased, so answers need judgment, not one regex.
- **Gate** (`lamarck/gate.py`): one more train task right, or equal accuracy at ≥15% fewer tokens;
  then at most one held-out task worse. A big train gain that does not hold out is labelled overfit.

## Run it

```bash
uv venv --python python3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY and MONGODB_URI
.venv/bin/python -m lamarck.cli evolve --run main --gens 8 --candidates 3
.venv/bin/python -m lamarck.cli long --run main      # gen-0 vs champion on 8x longer inputs
.venv/bin/python -m lamarck.cli status --run main
.venv/bin/uvicorn lamarck.server:app --port 8077      # live view: http://localhost:8077/?run=main
.venv/bin/python -m pytest -q
```

The engineer runs through headless Claude Code (`claude -p`) with whatever login the local `claude`
CLI already has.

## Provenance

Built entirely on 2026-10-11 at the Harness Engineering & Model Wrangling hackathon (Statement 1:
Recursive Harnessing). Ideas, not code, come from the author's earlier harness project: an event log as
the single source of truth, and promoting failures into regression cases. Design and plan:
`docs/superpowers/specs/`, `docs/superpowers/plans/`; spike: `docs/spike.md`.

## References

See `refs.txt`: Recursive Language Models (arXiv 2512.24601); Prime Agent (arXiv 2608.23552); Zhang,
"Language model harnesses are compositional generalizers" and "Language Model Shape"; HarnessTax;
Chroma, "Context Rot"; Karpathy on jagged intelligence; Dell'Acqua et al., "Navigating the Jagged
Technological Frontier".
