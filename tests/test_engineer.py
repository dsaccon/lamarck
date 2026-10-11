from lamarck import engineer
from lamarck.genome import GEN0

CHAMP = {"_id": "g0", "generation": 0, "genome": GEN0.model_dump(),
         "scores": {"train": {"acc": 0.25, "n": 12, "by_kind": {"needle": 1.0, "pairs": 0.0},
                              "tokens": 30000, "cost": 0.3, "errors": 0}}}
FAILURE = {"task_id": "train-3-800", "kind": "pairs", "score": 0.2, "question": "Which users had both?",
           "expected": ["u0001"], "answer": "u0002", "error": None, "steps": 1, "subcalls": 0,
           "tokens_in": 30000, "tokens_out": 500,
           "trace": [{"step": 1, "role": "model", "text": "I scanned the data. FINAL: u0002"}]}
HISTORY = [{"_id": "g0", "parent_id": None, "generation": 0},
           {"_id": "c1", "parent_id": "g0", "generation": 1, "focus": "cost", "status": "rejected_no_gain",
            "reason": "no train gain", "ops": [{"op": "add_note", "text": "be brief"}], "scores": {}}]
VALID = {"diagnosis": "context rot", "hypothesis": "offload the data",
         "ops": [{"op": "set", "path": "repl", "value_json": "true"},
                 {"op": "set", "path": "context_mode", "value_json": "\"repl\""}]}


def test_manual_renders_without_placeholders():
    text = engineer.manual()
    assert "{" not in text and "gemini-3.8-flash" in text and "limits.max_steps" in text


def test_prompt_contains_focus_failures_and_lineage():
    p = engineer.build_prompt(CHAMP, [FAILURE], HISTORY, "accuracy")
    assert engineer.FOCI["accuracy"] in p
    assert "Which users had both?" in p and "Expected: ['u0001']" in p
    assert "add_note 'be brief'" in p and "rejected_no_gain" in p


def test_propose_retries_once_after_an_invalid_patch():
    answers = [{"diagnosis": "d", "hypothesis": "h", "ops": [{"op": "set", "path": "context_mode", "value_json": "\"repl\""}]}, VALID]
    prompts = []

    def call(prompt, system, schema):
        prompts.append(prompt)
        return answers.pop(0)

    out = engineer.propose(CHAMP, [FAILURE], HISTORY, "free", call=call)
    assert out["ok"] and out["genome"]["context_mode"] == "repl"
    assert "previous proposal was invalid" in prompts[1]


def test_propose_gives_up_after_two_invalid_answers():
    bad = {"diagnosis": "d", "hypothesis": "h", "ops": [{"op": "set", "path": "base_prompt", "value_json": "\"x\""}]}
    out = engineer.propose(CHAMP, [FAILURE], HISTORY, "free", call=lambda p, s, sc: bad)
    assert not out["ok"] and "not settable" in out["error"]


def test_failures_are_labelled_with_their_genome():
    sibling = {**FAILURE, "genome_id": "c1", "task_id": "train-5-800"}
    p = engineer.build_prompt(CHAMP, [{**FAILURE, "genome_id": "g0"}, sibling], HISTORY, "accuracy")
    assert "from champion g0" in p and "from candidate c1" in p
