# Lamarck — design spec

**Date:** 2026-10-11 · **Event:** Harness Engineering & Model Wrangling hackathon, Statement 1 (Recursive
Harnessing) · **Submission:** 5:00 PM PT · **Team:** solo

## 1. What it is

Lamarck is an agent harness that rewrites its own architecture from its own failures. A run of the
harness is fully determined by a typed **genome** (context policy, tool access, recursion budgets, rules,
skills, validators, models). An **engineer** agent reads the failing traces of the current champion and
proposes typed patches; an **eval gate** accepts a patch only if it beats its parent on the training tasks
and does not regress on held-out tasks. Every version, run and trace lives in MongoDB Atlas as a
lineage tree with rollback.

The name: variation is *Lamarckian* (directed changes acquired from the harness's own experience are
written into the genome its descendants inherit — the evolutionary-computation sense of the term), and
selection is Darwinian (the gate).

**Why this matters (pitch):** context rot makes agents degrade as context grows; RLM-style offloading
fixes it architecturally (Zhang & Khattab); capability is jagged per task (Karpathy; Dell'Acqua et al.),
so no hand-built harness fits every workload; HarnessTax shows harness choice moves cost up to 5×.
Prime Agent's Continual Harness carries typed self-edits across runs but has no acceptance gate — its own
paper calls for "auditable rollback of contaminated refinements". Lamarck is that gate, applied to the
whole architecture rather than to notes and skills alone.

## 2. Success criteria

1. Gen-0 measurably fails the workload: train accuracy ≤ ~40%.
2. An unattended run of ≤ 10 generations yields a champion ≥ 30 points better on train and gate
   accuracy, and/or ≥ 30% cheaper at equal accuracy.
3. The champion beats gen-0 on the **long** split (8–16× longer inputs) — the generalization headline.
4. The lineage contains at least one rejected patch with a recorded reason (no gain, or overfit).
5. All state is in MongoDB Atlas; the live view renders the lineage from it.
6. The 3-minute demo runs one generation live.

**Non-goals:** training model weights; a security sandbox (subprocess + timeouts only); a general coding
agent; a multi-user product.

## 3. Providers

| Role | Model | Access | Why |
|---|---|---|---|
| Worker — root and sub-calls | `gemini-3.8-flash` (the evolver may pick other Gemini ids the key lists) | Gemini API key, `google-genai` SDK | raw control of every token in context, per-token metering for the cost axis, high parallelism, 1M context |
| Engineer | `claude-opus-5-5` | headless `claude -p` on the user's Max login | ~30–60 calls per run; `--json-schema` gives validated patches |

The engineer subprocess unsets `CLAUDECODE` (we run nested inside a Claude Code session) and passes
`--system-prompt-file`, `--tools ""`, `--strict-mcp-config`, `--no-session-persistence`,
`--output-format json`, `--json-schema`. Exact flags that work with subscription auth are confirmed in
the spike. Cost accounting uses Gemini `usage_metadata` × a price table in config
(`gemini-3.8-flash`: $0.75 / $3.75 per M input/output).

## 4. Components

All code is new, in a fresh public repo. Python 3.12, dependencies in a project `.venv` created with
`uv` (nothing system-wide): `google-genai`, `pymongo`, `fastapi`, `uvicorn`, `pydantic`,
`python-dotenv`, `pytest`.

| Unit | Responsibility | Interface |
|---|---|---|
| `lamarck/tasks.py` | Deterministic synthetic workload: production-style service logs with exact ground truth. Kinds: `needle` (find a trace id), `topk` (service with most 5xx in a window), `distinct` (distinct users hitting an error), `pairs` (users hitting both an auth timeout and a checkout 5xx). | `make_task(split, idx) -> Task`, `score(task, answer) -> float` (exact match; F1 for sets) |
| `lamarck/genome.py` | `Genome` pydantic schema, `GEN0`, typed patch ops, validation | `apply(genome, patch) -> Genome` |
| `lamarck/llm.py` | Provider calls | `gemini_chat(...) -> (text, usage)`, `claude_json(prompt, system, schema) -> dict` |
| `lamarck/harness.py` | Runs one task under one genome | `run_task(genome, task) -> RunResult` |
| `lamarck/store.py` | MongoDB access | collections `genomes`, `runs` (each with its embedded trace), `feed` (live log), `meta` (champion pointer) |
| `lamarck/evaluate.py` | Runs genomes over splits in isolated worker processes, records runs | `evaluate_many([(genome_id, split)]) -> {(genome_id, split): summary}` |
| `lamarck/engineer.py` | Builds the engineer prompt, calls Opus, returns a validated patch | `propose(champion, summary, failures, history, focus) -> Proposal` |
| `lamarck/gate.py` | Pure acceptance rule | `decide(parent, candidate) -> Verdict` |
| `lamarck/cli.py` | The generation loop and CLI: `evolve`, `long`, `status`, `rollback`, `ping` | `python -m lamarck.cli evolve --gens N --candidates K` |
| `lamarck/server.py` + `static/index.html` | Live view: lineage tree, genome diff and rationale per node, accuracy/cost curve, live feed (polls MongoDB; change stream optional) | FastAPI |
| `scripts/spike.py` | Gen-0 vs a hand-written RLM genome on a few tasks, to size the workload | CLI |

### 4.1 Genome

```json
{ "root_model": "gemini-3.8-flash", "sub_model": "gemini-3.8-flash",
  "context_mode": "inline",      // inline | repl | both
  "repl": false,                  // REPL available to the root model
  "max_obs_chars": 4000,          // how much REPL output re-enters the root context
  "system_notes": [],             // evolvable rules appended to the fixed base prompt
  "skills": {},                   // name -> Python source, preloaded into the REPL
  "validators": {},               // name -> source of check(answer, question) -> str | None
  "limits": { "max_steps": 12, "max_subcalls": 40 } }
```

Patch ops: `set` (a top-level field or `limits.*`), `add_note`, `remove_note`, `put_skill`,
`del_skill`, `put_validator`, `del_validator`. **Protected — no op can reach them:** the base prompt,
the scorer, task data, hard caps (per-task wall clock, per-task token ceiling, `max_steps` ≤ 30,
`max_subcalls` ≤ 200), and the schema itself.

### 4.2 Harness loop (RLM text protocol)

- The model replies with either a fenced ```` ```python ```` block (executed in the REPL; stdout
  truncated to `max_obs_chars` is appended as the next user turn) or a final line `FINAL: <answer>` /
  `FINAL_VAR(<name>)`.
- `inline`: the log text is in the first user message. `repl`: the log is the REPL variable `context`,
  and the model sees only its length and a short preview. `both`: both.
- Inside the REPL: `llm_query(prompt) -> str` and `llm_query_batch(prompts) -> list[str]` (bounded
  thread pool) call `sub_model`; each counts toward `max_subcalls`. Skills are preloaded and listed
  in the prompt with their docstrings.
- On a final answer, each validator runs; a returned message is fed back and the loop continues
  (at most 2 rejections).
- Each task runs in its own subprocess with a wall-clock timeout; each REPL step has a `signal.alarm`
  timeout. The Gemini key is read into the client and removed from `os.environ` before model code runs,
  so traces cannot echo it.

### 4.3 Workload splits

| Split | Count | Size | Visible to engineer |
|---|---|---|---|
| train | ~12 | ~30–40k tokens (final size set by spike) | failing traces, yes |
| gate | ~8 | same as train, different seeds | no |
| long | ~8 | 8–16× train | no; final test only |

### 4.4 Generation loop and gate

1. Engineer proposes K = 2–3 candidates in parallel, each with a different focus (accuracy failures;
   cost; a free choice). Input: champion genome, the search-space manual (what each gene does), ~6
   compressed failing traces (question, expected, got, last steps), and the last ~10 lineage entries
   with verdicts and reasons.
2. Evaluate every candidate on train (parallel workers).
3. `gate.decide` on the best train candidate vs its parent, on the same tasks:
   - train passes if accuracy ≥ parent + 1/12, or accuracy ≥ parent with tokens ≤ 0.85 × parent;
   - then evaluate on gate: accept if gate accuracy ≥ parent gate accuracy − 1/8;
   - failing train is `rejected_no_gain`; passing train but failing gate is `rejected_overfit` when the
     train gain is ≥ 2/12, otherwise `rejected_no_gain`.
4. Record every candidate with status (`accepted`, `rejected_no_gain`, `rejected_overfit`, `invalid`)
   and reason. An accepted candidate becomes champion. Rollback moves the champion pointer to any
   ancestor (`python -m lamarck.cli rollback --to <id>`).
5. After the run, evaluate gen-0 and the champion on long.

### 4.5 Data flow

`evolve` → `engineer` (`claude -p`, Opus) → patch → `genome.apply` → `genomes` (status `candidate`) →
`evaluate` (Gemini workers) → `runs` → `gate` → status update + `meta.champion`; every step also
writes a `feed` line → live view (polling).

## 5. Error handling

- Worker exception or timeout: the run is recorded as wrong, with its tokens and error.
- Gemini 429 / 5xx: exponential backoff with jitter, bounded retries.
- Engineer output that fails schema or `apply` validation: one retry with the error message, then the
  candidate is recorded `invalid`.
- REPL step error: the traceback is truncated and returned to the model as the observation.

## 6. Testing

- Unit tests for the pure parts: task determinism and scorer, `genome.apply` (valid ops, protected
  fields refused, caps enforced), `gate.decide` (each verdict branch).
- One harness-loop test with a scripted fake model: code block runs, `FINAL_VAR` resolves, a validator
  rejection is fed back, limits stop the loop.
- Integration is the spike itself and the first real generation.

## 7. Secrets and publishing

`.env` holds `GEMINI_API_KEY` and `MONGODB_URI` and is gitignored with mode 600. `start.txt` (venue
Wi-Fi credentials) is gitignored. The repo becomes public at submission. The README states that
everything was built today and that only ideas (event log as source of truth, failure → case → check)
come from the author's earlier harness project.

## 8. Timeline (hours from start)

| Hours | Work |
|---|---|
| 0–1.5 | Scaffold, tasks, genome, harness, spike: confirm gen-0 fails and a hand-written RLM genome succeeds; fix task sizes |
| 1.5–3 | Store, evaluate, engineer, gate, evolve loop |
| 3–4 | Real evolution runs; long-split evaluation |
| 4–5 | Live view |
| 5–6 | README, demo video, submission |

**Stretch, in order:** (1) a second workload to show different architectures emerging per workload;
(2) the engineer runs through the champion genome, making the recursion literal; (3) a second engineer
from another model family via the Devin CLI, for candidate diversity.

## 9. Open items

- MongoDB Atlas sandbox URI — the user is provisioning it.
- Whether the Raindrop RSI prize requires Raindrop's product — the user is checking.
- Gemini model ids and thinking controls available to the key — confirmed in the spike.
