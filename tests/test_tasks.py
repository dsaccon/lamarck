from lamarck.tasks import KINDS, SERVICES, Task, make_task, score


def test_tasks_are_deterministic():
    assert make_task("train", 3, n_lines=300) == make_task("train", 3, n_lines=300)


def test_splits_differ():
    assert make_task("train", 0, n_lines=300).context != make_task("gate", 0, n_lines=300).context


def test_kinds_rotate():
    assert [make_task("train", i, n_lines=200).kind for i in range(4)] == KINDS


def test_needle_trace_is_unique_in_context():
    t = make_task("train", 0, n_lines=500)
    assert t.kind == "needle"
    assert t.context.count(f"trace={t.answer}") == 1


def test_answers_are_well_formed():
    assert make_task("train", 1, n_lines=500).answer in SERVICES
    assert make_task("train", 2, n_lines=500).answer > 0
    assert len(make_task("train", 3, n_lines=500).answer) >= 1


def test_line_count_at_least_requested():
    assert len(make_task("train", 1, n_lines=400).context.splitlines()) >= 400


def _t(kind, answer):
    return Task(id="t", split="x", idx=0, kind=kind, question="q", context="", answer=answer)


def test_score_tolerates_loose_phrasing():
    assert score(_t("needle", "0123456789ab"), "The trace id is 0123456789AB.") == 1.0
    assert score(_t("needle", "0123456789ab"), "0123456789ab or 0123456789ac") == 0.0
    assert score(_t("topk", "checkout"), "**Checkout**") == 1.0
    assert score(_t("topk", "checkout"), "checkout or payments") == 0.0
    assert score(_t("distinct", 42), "The answer is 42.") == 1.0
    assert score(_t("distinct", 1234), "1,234 users") == 1.0
    assert score(_t("pairs", ["u0001", "u0002"]), "u0001 and u0002") == 1.0
    assert score(_t("pairs", ["u0001", "u0002"]), "u0001, u0003") == 0.5
    assert score(_t("pairs", ["u0001"]), "") == 0.0
