"""Runs one task under one genome: the RLM text protocol over a persistent Python REPL."""
from __future__ import annotations

import ast
import contextlib
import io
import re
import signal
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from lamarck import config
from lamarck.genome import Genome
from lamarck.llm import Turn
from lamarck.tasks import Task, score

# --- protected: no genome op can change anything in this block --------------------------------
BASE_PROMPT = """You are a careful analyst answering one question about a dataset.

{mode}

End your work with a line of the form
FINAL: <answer>
where <answer> is only the answer: a name, a number, an id, or a comma-separated list.{notes}"""

MODE_INLINE = "The dataset is in the user's message. Read it carefully and reason step by step before answering."

MODE_REPL = """You have a persistent Python REPL. To run code, reply with a fenced block:
```python
print(...)
```
The printed output (cut to {max_obs_chars} characters) comes back in the next message. Variables persist between steps. Only the Python standard library is available.

In the REPL:
{context_line}- llm_query(prompt: str) -> str: asks a sub-model, which sees only the prompt you pass.
- llm_query_batch(prompts: list[str]) -> list[str]: the same, run in parallel.
{skills}
You may also finish with FINAL_VAR(name) to answer with the value of a REPL variable.
Budget: {max_steps} replies and {max_subcalls} sub-model calls."""

SUB_SYSTEM = "Answer the request precisely and concisely."
OUTPUT_STOPS = ["```output"]  # used when the genome sets stop_at_output
LIMIT_MESSAGE = "Step limit reached. Reply now with only 'FINAL: <best answer>'."
MAX_VALIDATOR_REJECTIONS = 2
# -----------------------------------------------------------------------------------------------

CODE_RE = re.compile(r"```(?:python|py|repl)?[ \t]*\n(.*?)```", re.S)
FINAL_VAR_RE = re.compile(r"FINAL_VAR\(\s*([A-Za-z_]\w*)\s*\)")
FINAL_RE = re.compile(r"^[\s*_#]*FINAL[\s*_]*:[\s*_]*(.+?)[\s*_]*$", re.M)


@dataclass
class Usage:
    by_model: dict[str, list[int]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, u: dict) -> None:
        with self.lock:
            m = self.by_model.setdefault(model, [0, 0])
            m[0] += u.get("in", 0)
            m[1] += u.get("out", 0)

    @property
    def tokens_in(self) -> int:
        return sum(v[0] for v in self.by_model.values())

    @property
    def tokens_out(self) -> int:
        return sum(v[1] for v in self.by_model.values())

    def cost(self) -> float:
        total = 0.0
        for model, (tin, tout) in self.by_model.items():
            pin, pout = config.WORKER_MODELS.get(model, (0.0, 0.0))
            total += tin / 1e6 * pin + tout / 1e6 * pout
        return total


class RunResult(BaseModel):
    task_id: str
    split: str
    kind: str
    question: str
    expected: Any
    answer: str
    score: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    steps: int = 0
    subcalls: int = 0
    error: str | None = None
    trace: list[dict] = []


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f"\n...[cut {len(s) - n} chars]"


def error_result(task: Task, message: str) -> RunResult:
    return RunResult(task_id=task.id, split=task.split, kind=task.kind, question=task.question,
                     expected=task.answer, answer="", score=0.0, error=message)


class StepTimeout(BaseException):  # BaseException so model code's `except Exception` cannot swallow it
    pass


class Repl:
    """Persistent namespace. run() returns printed output, a trailing expression's repr, or the error."""

    def __init__(self, ns: dict, step_timeout: float):
        self.ns, self.step_timeout = ns, step_timeout

    def run(self, code: str) -> str:
        buf = io.StringIO()
        use_alarm = threading.current_thread() is threading.main_thread()
        if use_alarm:
            def _alarm(signum, frame):
                raise StepTimeout(f"step exceeded {self.step_timeout}s")
            old = signal.signal(signal.SIGALRM, _alarm)
            signal.setitimer(signal.ITIMER_REAL, self.step_timeout)
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                tree = ast.parse(code)
                last = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
                exec(compile(tree, "<repl>", "exec"), self.ns)
                if last is not None:
                    value = eval(compile(ast.Expression(last.value), "<repl>", "eval"), self.ns)
                    if value is not None:
                        print(repr(value))
        except StepTimeout as e:
            buf.write(f"\nTimeoutError: {e}\n")
        except BaseException:  # noqa: BLE001 — model code may raise anything, including SystemExit
            buf.write(traceback.format_exc(limit=-3))
        finally:
            if use_alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)
        return buf.getvalue()


def _doc_line(src: str, name: str) -> str:
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            return f"- {name}({', '.join(a.arg for a in node.args.args)}): {doc[0] if doc else ''}"
    return f"- {name}()"


def build_system(genome: Genome, task: Task) -> str:
    notes = "".join(f"\n- {n}" for n in genome.system_notes)
    notes = f"\n\nRules:{notes}" if notes else ""
    if not genome.repl:
        return BASE_PROMPT.format(mode=MODE_INLINE, notes=notes)
    n_lines = task.context.count("\n") + 1
    context_line = (f"- context: str, the dataset ({len(task.context)} characters, {n_lines} lines).\n"
                    if genome.context_mode != "inline" else "")
    skills = "".join(_doc_line(src, name) + "\n" for name, src in genome.skills.items())
    mode = MODE_REPL.format(max_obs_chars=genome.max_obs_chars, context_line=context_line,
                            skills=f"Preloaded functions:\n{skills}" if skills else "",
                            max_steps=genome.limits.max_steps, max_subcalls=genome.limits.max_subcalls)
    if genome.context_mode == "both":
        mode = MODE_INLINE + "\n\n" + mode
    return BASE_PROMPT.format(mode=mode, notes=notes)


def build_first_message(genome: Genome, task: Task) -> str:
    n_lines = task.context.count("\n") + 1
    if genome.context_mode == "repl":
        preview = "\n".join(task.context.splitlines()[:5])
        return (f"The dataset is in the REPL variable `context` ({n_lines} lines). Its first lines:\n{preview}\n\n"
                f"QUESTION: {task.question}")
    text = f"DATA ({n_lines} lines):\n{task.context}\n\nQUESTION: {task.question}"
    if genome.context_mode == "both":
        text += "\n\n(The same data is also in the REPL variable `context`.)"
    return text


def run_validators(validators: dict[str, str], answer: str, question: str) -> str | None:
    for name, src in validators.items():
        ns: dict = {}
        try:
            exec(src, ns)
            message = ns["check"](answer, question)
        except Exception:  # a broken validator never blocks an answer
            continue
        if message:
            return f"{name}: {message}"
    return None


def run_task(genome: Genome, task: Task, model: Any, step_timeout: float = config.STEP_TIMEOUT_S) -> RunResult:
    usage, trace = Usage(), []
    sub, sub_lock = {"n": 0}, threading.Lock()

    def llm_query(prompt: str) -> str:
        with sub_lock:
            if sub["n"] >= genome.limits.max_subcalls:
                raise RuntimeError(f"sub-call budget of {genome.limits.max_subcalls} exhausted")
            sub["n"] += 1
        text, _, u = model.generate(genome.sub_model, SUB_SYSTEM, [Turn("user", str(prompt))], genome.thinking_level)
        usage.add(genome.sub_model, u)
        return text

    def llm_query_batch(prompts: list[str]) -> list[str]:
        with ThreadPoolExecutor(max_workers=16) as ex:
            return list(ex.map(llm_query, list(prompts)))

    ns: dict = {"__name__": "__repl__"}
    if genome.repl:
        ns.update(llm_query=llm_query, llm_query_batch=llm_query_batch)
        if genome.context_mode != "inline":
            ns["context"] = task.context
        for name, src in genome.skills.items():
            try:
                exec(src, ns)
            except Exception as e:
                trace.append({"step": 0, "role": "harness", "text": f"skill {name} failed to load: {e}"})
    repl = Repl(ns, step_timeout)
    system = build_system(genome, task)
    history = [Turn("user", build_first_message(genome, task))]
    answer: str | None = None
    error: str | None = None
    rejections = 0
    steps = 0

    def ask(turns: list[Turn]) -> tuple[str, Any]:
        nonlocal steps
        steps += 1
        text, raw, u = model.generate(genome.root_model, system, turns, genome.thinking_level,
                                      stop=OUTPUT_STOPS if genome.stop_at_output else None)
        usage.add(genome.root_model, u)
        trace.append({"step": steps, "role": "model", "text": clip(text, 3000)})
        return text, raw

    try:
        while steps < genome.limits.max_steps:
            text, raw = ask(history)
            history.append(Turn("model", text or "(empty reply)", raw))
            if usage.tokens_in + usage.tokens_out > config.TOKEN_CEILING:
                error = "token ceiling reached"
                break
            blocks = CODE_RE.findall(text) if genome.repl else []
            prose = CODE_RE.sub("", text)
            notes: list[str] = []
            if blocks:
                out = "".join(repl.run(b) for b in blocks)
                notes.append("OUTPUT:\n" + clip(out or "(no output)", genome.max_obs_chars))
            candidate = None
            var = FINAL_VAR_RE.search(prose) if genome.repl else None
            fin = FINAL_RE.search(prose)
            if var:
                if var.group(1) in ns:
                    candidate = str(ns[var.group(1)])
                else:
                    notes.append(f"FINAL_VAR: there is no REPL variable named {var.group(1)!r}.")
            elif fin and not blocks:
                candidate = fin.group(1)
            elif fin:
                notes.append("Your FINAL line was ignored because code ran in the same reply. Check the output, then answer.")
            if candidate is not None:
                complaint = run_validators(genome.validators, candidate, task.question)
                if complaint and rejections < MAX_VALIDATOR_REJECTIONS:
                    rejections += 1
                    notes.append(f"Answer rejected by validator {complaint}")
                else:
                    answer = candidate
                    break
            if not notes:
                notes.append("Reply with a ```python block to run code, or finish with a line 'FINAL: <answer>'."
                             if genome.repl else "Finish with a line 'FINAL: <answer>'.")
            observation = "\n\n".join(notes)
            history.append(Turn("user", observation))
            trace.append({"step": steps, "role": "user", "text": clip(observation, 3000)})
        if answer is None and error is None:
            last = history[-1]
            turns = (history[:-1] + [Turn("user", f"{last.text}\n\n{LIMIT_MESSAGE}")] if last.role == "user"
                     else history + [Turn("user", LIMIT_MESSAGE)])
            text, _ = ask(turns)
            fin = FINAL_RE.search(CODE_RE.sub("", text))
            answer = fin.group(1) if fin else ""
    except Exception as e:  # noqa: BLE001 — a provider failure ends this run, not the evaluation
        error = f"{type(e).__name__}: {e}"
    answer = (answer or "").strip()
    return RunResult(task_id=task.id, split=task.split, kind=task.kind, question=task.question,
                     expected=task.answer, answer=answer, score=score(task, answer),
                     tokens_in=usage.tokens_in, tokens_out=usage.tokens_out, cost=round(usage.cost(), 6),
                     steps=steps, subcalls=sub["n"], error=error, trace=trace)
