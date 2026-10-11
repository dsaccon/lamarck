import time

from lamarck.pool import run_many


def test_results_come_back_in_job_order():
    out = run_many("tests.pool_targets:echo", [{"v": i} for i in range(5)], max_parallel=3, timeout_s=60)
    assert [o["result"]["v"] for o in out] == [0, 1, 2, 3, 4]


def test_a_hung_job_is_killed_and_reported():
    t0 = time.monotonic()
    out = run_many("tests.pool_targets:hang", [{}], max_parallel=1, timeout_s=3)
    assert not out[0]["ok"] and "timeout" in out[0]["error"]
    assert time.monotonic() - t0 < 20


def test_crash_and_exception_are_reported():
    out = run_many("tests.pool_targets:crash", [{}], max_parallel=1, timeout_s=60)
    assert not out[0]["ok"] and "exit" in out[0]["error"]
    out = run_many("tests.pool_targets:boom", [{}], max_parallel=1, timeout_s=60)
    assert out[0] == {"ok": False, "error": "ValueError: boom"}
