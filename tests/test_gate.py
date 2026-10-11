from lamarck.gate import Score, gate_verdict, train_passes

N_TRAIN, N_GATE = 12, 8


def test_train_needs_one_more_task_or_cheaper_at_equal_accuracy():
    p = Score(0.5, 10_000)
    assert train_passes(p, Score(0.5 + 1 / 12, 12_000), N_TRAIN)[0]
    assert train_passes(p, Score(0.5, 8_000), N_TRAIN)[0]
    assert not train_passes(p, Score(0.5, 9_000), N_TRAIN)[0]
    assert not train_passes(p, Score(0.45, 1_000), N_TRAIN)[0]


def test_gate_allows_one_task_of_noise():
    v = gate_verdict(Score(0.5, 1), Score(0.6, 1), Score(0.5, 1), Score(0.375, 1), N_TRAIN, N_GATE)
    assert v.status == "accepted"


def test_big_train_gain_that_does_not_hold_out_is_overfit():
    v = gate_verdict(Score(0.5, 1), Score(0.5 + 2 / 12, 1), Score(0.5, 1), Score(0.25, 1), N_TRAIN, N_GATE)
    assert v.status == "rejected_overfit"


def test_small_train_gain_that_does_not_hold_out_is_no_gain():
    v = gate_verdict(Score(0.5, 1), Score(0.5 + 1 / 12, 1), Score(0.5, 1), Score(0.25, 1), N_TRAIN, N_GATE)
    assert v.status == "rejected_no_gain"
