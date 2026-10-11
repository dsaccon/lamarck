"""Deterministic synthetic workload: questions over production-style service logs.

Ground truth comes from the generated records, never from parsing the text, so scoring is exact.
Event messages are paraphrased several ways, so answering needs semantic judgment, not one regex.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from lamarck import config

SERVICES = ["gateway", "auth", "checkout", "payments", "search", "inventory", "profile", "notifications"]
KINDS = ["needle", "topk", "distinct", "pairs"]
OK_STATUSES = [200, 200, 200, 201, 204]
OK_MSGS = ["request completed", "served {n} items", "cache hit for key k{n}", "rendered page in {ms}ms",
           "health check passed", "returned {n} results", "session refreshed", "wrote {n} rows"]
EVENTS: dict[str, tuple[list[int], list[str]]] = {
    "timeout": ([504, 503, 500], ["upstream timed out after {ms}ms", "deadline exceeded calling {svc2}",
                                  "no response from {svc2} within {ms}ms", "request to {svc2} took too long, aborting",
                                  "context deadline exceeded", "gave up waiting for {svc2} after {ms}ms"]),
    "ratelimit": ([429, 429, 503], ["rate limit exceeded for client", "too many requests, slow down",
                                    "quota exhausted for user", "throttled: {n} req/s over limit",
                                    "request shed by limiter"]),
    "decline": ([402, 400], ["card declined by issuer", "insufficient funds", "payment authorization refused",
                             "issuer rejected charge code PD-{code}", "charge blocked by fraud rules"]),
    "db": ([500, 503], ["connection pool exhausted", "deadlock detected, rolling back",
                        "replica lag too high, refusing read", "could not connect to primary",
                        "too many open cursors"]),
    "authfail": ([401, 403], ["invalid credentials", "token expired", "signature mismatch on JWT", "session revoked"]),
    "notfound": ([404], ["no such item i{n}", "route not found", "unknown sku s{n}"]),
}
EVENT_WEIGHTS = {"timeout": 6, "ratelimit": 5, "decline": 4, "db": 4, "authfail": 4, "notfound": 5}
EVENT_SERVICES = {"decline": ["payments", "checkout"]}
EVENT_RATE = 0.28
CATEGORY_WORDS = {"timeout": "timeout failure", "ratelimit": "rate-limiting or throttling error",
                  "authfail": "authentication or authorization failure", "db": "database error"}
DISTINCT_CATS = ["ratelimit", "authfail", "timeout", "db"]
START = datetime(2026, 10, 11, tzinfo=timezone.utc)
SPAN_S = 6 * 3600

TRACE_RE = re.compile(r"\b[0-9a-f]{12}\b")
USER_RE = re.compile(r"\bu\d{4}\b")
INT_RE = re.compile(r"-?\d+")


@dataclass(frozen=True)
class Task:
    id: str
    split: str
    idx: int
    kind: str
    question: str
    context: str
    answer: Any
    workload: str = "logs"


def _at(rng: random.Random, lo: float = 0.0, hi: float = SPAN_S) -> datetime:
    return START + timedelta(seconds=rng.uniform(lo, hi))


def _record(rng: random.Random, at: datetime, users: list[str], cat: str | None = None, svc: str | None = None) -> dict:
    if cat is None:
        cat = "ok" if rng.random() >= EVENT_RATE else rng.choices(list(EVENT_WEIGHTS), weights=list(EVENT_WEIGHTS.values()))[0]
    if cat == "ok":
        status, template = rng.choice(OK_STATUSES), rng.choice(OK_MSGS)
    else:
        statuses, templates = EVENTS[cat]
        status, template = rng.choice(statuses), rng.choice(templates)
    svc = svc or rng.choice(EVENT_SERVICES.get(cat, SERVICES))
    msg = template.format(n=rng.randrange(1, 500), ms=rng.randrange(800, 30000),
                          svc2=rng.choice(SERVICES), code=rng.randrange(1000, 9000))
    dur = rng.randrange(800, 30000) if cat == "timeout" else rng.randrange(3, 900)
    return {"at": at, "svc": svc, "status": status, "user": rng.choice(users),
            "trace": f"{rng.getrandbits(48):012x}", "dur": dur, "msg": msg, "cat": cat}


def _fmt(r: dict) -> str:
    return (f'{r["at"]:%Y-%m-%dT%H:%M:%S}Z svc={r["svc"]} status={r["status"]} user={r["user"]} '
            f'trace={r["trace"]} dur_ms={r["dur"]} msg="{r["msg"]}"')


def _ask_needle(rng, recs, users, idx):
    code = rng.randrange(9000, 10000)  # ordinary decline codes are 1000-8999, so this one is unique
    target = _record(rng, _at(rng, 0.1 * SPAN_S, 0.9 * SPAN_S), users, cat="decline", svc="payments")
    target["msg"], target["status"] = f"issuer rejected charge code PD-{code}", 402
    recs.append(target)
    return (f"What is the trace id of the request in which the card issuer rejected charge code PD-{code}? "
            "Answer with the trace id only.", target["trace"])


def _ask_topk(rng, recs, users, idx):
    h = rng.randrange(0, 5)
    lo, hi = START + timedelta(hours=h), START + timedelta(hours=h + 2)
    counts = {s: 0 for s in SERVICES}
    for r in recs:
        if r["cat"] == "timeout" and lo <= r["at"] < hi:
            counts[r["svc"]] += 1
    target = rng.choice(SERVICES)
    rival = max(c for s, c in counts.items() if s != target)
    for _ in range(max(0, rival + 2 - counts[target])):  # unique winner by a margin of at least 2
        recs.append(_record(rng, _at(rng, h * 3600, (h + 2) * 3600 - 1), users, cat="timeout", svc=target))
    return (f"Between {h:02d}:00 and {h + 2:02d}:00 UTC, which service logged the most timeout failures "
            "(any wording, any status code)? Answer with the service name only.", target)


def _ask_distinct(rng, recs, users, idx):
    cat = DISTINCT_CATS[(idx // len(KINDS)) % len(DISTINCT_CATS)]
    n = len({r["user"] for r in recs if r["cat"] == cat})
    return (f"How many distinct users experienced at least one {CATEGORY_WORDS[cat]} "
            "(any service, any wording, any status code)? Answer with a single integer.", n)


def _ask_pairs(rng, recs, users, idx):
    both = sorted({r["user"] for r in recs if r["cat"] == "decline"} & {r["user"] for r in recs if r["cat"] == "timeout"})
    if not both:
        u = rng.choice(users)
        for cat in ("decline", "timeout"):
            r = _record(rng, _at(rng), users, cat=cat)
            r["user"] = u
            recs.append(r)
        both = [u]
    return ("Which users had at least one payment decline AND at least one timeout failure "
            "(any service, any wording)? Answer with the user ids as a comma-separated list.", both)


ASK = {"needle": _ask_needle, "topk": _ask_topk, "distinct": _ask_distinct, "pairs": _ask_pairs}


def make_task(split: str, idx: int, n_lines: int | None = None, workload: str = "logs") -> Task:
    if workload == "tickets":
        from lamarck import tickets
        return tickets.make_task(split, idx, n_lines)
    n_lines = n_lines or config.SPLITS[split][1]
    rng = random.Random(f"lamarck:{split}:{idx}:{n_lines}")
    kind = KINDS[idx % len(KINDS)]
    users = [f"u{n:04d}" for n in rng.sample(range(10000), max(40, n_lines // 10))]
    recs = [_record(rng, _at(rng), users) for _ in range(n_lines)]
    question, answer = ASK[kind](rng, recs, users, idx)
    recs.sort(key=lambda r: r["at"])
    return Task(id=f"{split}-{idx}-{n_lines}", split=split, idx=idx, kind=kind, question=question,
                context="\n".join(_fmt(r) for r in recs), answer=answer)


def score(task: Task, answer: str) -> float:
    if task.workload == "tickets":
        from lamarck import tickets
        return tickets.score(task, answer)
    a = (answer or "").lower()
    if task.kind == "needle":
        return float(set(TRACE_RE.findall(a)) == {task.answer})
    if task.kind == "topk":
        return float({s for s in SERVICES if re.search(rf"\b{s}\b", a)} == {task.answer})
    if task.kind == "distinct":
        nums = INT_RE.findall(a.replace(",", ""))
        return float(bool(nums) and int(nums[0]) == task.answer)
    got, want = set(USER_RE.findall(a)), set(task.answer)
    tp = len(got & want)
    if tp == 0:
        return 0.0
    p, r = tp / len(got), tp / len(want)
    return round(2 * p * r / (p + r), 4)
