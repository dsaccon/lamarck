from lamarck import tasks, tickets
from lamarck.tasks import Task


def test_ticket_tasks_are_deterministic_and_dispatched_by_workload():
    a = tasks.make_task("train", 3, n_lines=300, workload="tickets")
    assert a == tasks.make_task("train", 3, n_lines=300, workload="tickets")
    assert a.workload == "tickets" and a.context != tasks.make_task("train", 3, n_lines=300).context


def test_kinds_rotate_and_answers_are_well_formed():
    ts = [tickets.make_task("train", i, 600) for i in range(4)]
    assert [t.kind for t in ts] == tasks.KINDS
    assert ts[0].context.count(f"{ts[0].answer} |") == 1
    assert ts[1].answer in tickets.INTENTS
    assert ts[2].answer > 0
    assert len(ts[3].answer) >= 1


def test_decoys_mention_other_intents_in_the_negative():
    ctx = tickets.make_task("train", 2, 800).context
    assert any(d in ctx for decoys in tickets.DECOYS.values() for d in decoys)


def test_every_ticket_reads_differently():
    lines = [l.split('"')[1] for l in tickets.make_task("train", 1, 500).context.splitlines()]
    assert len(set(lines)) > 0.9 * len(lines)


def _t(kind, answer):
    return Task(id="t", split="x", idx=0, kind=kind, question="q", context="", answer=answer, workload="tickets")


def test_ticket_scoring_tolerates_loose_phrasing():
    assert tasks.score(_t("needle", "T00012"), "The ticket is T00012.") == 1.0
    assert tasks.score(_t("topk", "double_charge"), "**Double charge**") == 1.0
    assert tasks.score(_t("topk", "cancel"), "Cancellations") == 1.0
    assert tasks.score(_t("topk", "refund"), "refund or cancel") == 0.0
    assert tasks.score(_t("distinct", 17), "17 customers") == 1.0
    assert tasks.score(_t("pairs", ["c0001", "c0002"]), "c0001, c0003") == 0.5
