from lamarck.genome import GEN0, Genome
from lamarck.harness import SUB_SYSTEM, Repl, clip, run_task
from lamarck.tasks import Task

CTX = "\n".join(f"line {i}" for i in range(10))


def task(kind="distinct", answer=10):
    return Task(id="t-0", split="test", idx=0, kind=kind, question="How many lines?", context=CTX, answer=answer)


class FakeModel:
    def __init__(self, replies, sub_reply="SUB"):
        self.replies, self.sub_reply, self.systems, self.stops = list(replies), sub_reply, [], []

    def generate(self, model, system, history, thinking_level, stop=None):
        if system == SUB_SYSTEM:
            return self.sub_reply, None, {"in": 10, "out": 2}
        self.systems.append(system)
        self.stops.append(stop)
        return self.replies.pop(0), None, {"in": 100, "out": 20}


REPL = Genome(repl=True, context_mode="repl")


def test_inline_answer_in_one_step():
    r = run_task(GEN0, task(), FakeModel(["Counting carefully.\nFINAL: 10"]))
    assert (r.answer, r.score, r.steps, r.tokens_in) == ("10", 1.0, 1, 100)
    assert r.cost > 0


def test_repl_code_then_final_var():
    model = FakeModel(["```python\nn = len(context.splitlines())\nprint(n)\n```", "FINAL_VAR(n)"])
    r = run_task(REPL, task(), model)
    assert r.answer == "10" and r.score == 1.0 and r.steps == 2
    assert any("OUTPUT:\n10" in s["text"] for s in r.trace)


def test_final_in_same_reply_as_code_is_deferred():
    model = FakeModel(["```python\nprint(1)\n```\nFINAL: 3", "FINAL: 10"])
    r = run_task(REPL, task(), model)
    assert r.answer == "10" and r.steps == 2
    assert any("ignored" in s["text"] for s in r.trace)


def test_prose_reply_is_nudged():
    r = run_task(REPL, task(), FakeModel(["Let me think about it.", "FINAL: 10"]))
    assert r.answer == "10" and any("Reply with a ```python block" in s["text"] for s in r.trace)


def test_fences_and_markdown_final_parse():
    model = FakeModel(["```py\nx = 4\n```", "```repl\ny = x + 6\n```", "**FINAL:** 10"])
    assert run_task(REPL, task(), model).answer == "10"


def test_validator_rejection_is_fed_back():
    g = Genome(validators={"is_int": 'def check(answer, question):\n    return None if answer.strip().isdigit() else "answer must be an integer"\n'})
    r = run_task(g, task(), FakeModel(["FINAL: about ten", "FINAL: 10"]))
    assert r.answer == "10" and any("rejected by validator is_int" in s["text"] for s in r.trace)


def test_step_limit_forces_a_final_answer():
    g = Genome(repl=True, context_mode="repl", limits={"max_steps": 2, "max_subcalls": 5})
    r = run_task(g, task(), FakeModel(["thinking", "still thinking", "FINAL: 10"]))
    assert r.answer == "10" and r.steps == 3


def test_subcall_budget_is_enforced():
    g = Genome(repl=True, context_mode="repl", limits={"max_steps": 5, "max_subcalls": 2})
    code = "```python\nfor _ in range(3):\n    print(llm_query('hi'))\n```"
    r = run_task(g, task(), FakeModel([code, "FINAL: 10"]))
    assert r.subcalls == 2 and any("budget of 2 exhausted" in s["text"] for s in r.trace)


def test_skills_are_preloaded_and_listed():
    g = Genome(repl=True, context_mode="repl",
               skills={"n_lines": 'def n_lines(text):\n    """Count lines in text."""\n    return text.count("\\n") + 1\n'})
    model = FakeModel(["```python\nk = n_lines(context)\n```", "FINAL_VAR(k)"])
    r = run_task(g, task(), model)
    assert r.answer == "10" and "n_lines(text): Count lines in text." in model.systems[0]


def test_repl_step_timeout():
    out = Repl({}, step_timeout=0.5).run("while True:\n    pass")
    assert "TimeoutError" in out


def test_repl_shows_trailing_expression_and_errors():
    repl = Repl({}, step_timeout=5)
    assert repl.run("x = 2\nx * 21").strip() == "42"
    assert "ZeroDivisionError" in repl.run("1/0")


def test_clip():
    assert clip("abc", 10) == "abc"
    assert clip("a" * 100, 10).startswith("a" * 10) and "cut 90 chars" in clip("a" * 100, 10)


def test_stop_at_output_gene_sends_a_stop_sequence_to_the_root_model():
    model = FakeModel(["FINAL: 10"])
    run_task(Genome(repl=True, context_mode="repl", stop_at_output=True), task(), model)
    assert model.stops == [["```output"]]
    model = FakeModel(["FINAL: 10"])
    run_task(REPL, task(), model)
    assert model.stops == [None]
