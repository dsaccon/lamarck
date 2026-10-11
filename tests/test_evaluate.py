from lamarck.evaluate import summarize


def test_summarize():
    rows = [
        {"kind": "needle", "score": 1.0, "tokens_in": 900, "tokens_out": 100, "cost": 0.01, "error": None},
        {"kind": "pairs", "score": 0.5, "tokens_in": 1900, "tokens_out": 100, "cost": 0.02, "error": "timeout"},
    ]
    s = summarize(rows)
    assert s == {"acc": 0.75, "tokens": 1500, "cost": 0.03, "n": 2, "errors": 1,
                 "by_kind": {"needle": 1.0, "pairs": 0.5}}
