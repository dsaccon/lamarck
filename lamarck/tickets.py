"""Second workload: a synthetic customer-support inbox with exact ground truth.

Each ticket has one hidden intent, phrased combinatorially (opener, one of many intent phrasings, a detail,
sometimes a decoy that mentions another intent in the negative, a closer), so no two tickets read alike and
neither keyword search nor a template catalog recovers the intent. Answering needs reading.
"""
from __future__ import annotations

import random
import re

from lamarck.tasks import KINDS, Task

INTENTS = ["refund", "cancel", "shipping", "login", "double_charge", "praise"]
INTENT_WEIGHTS = [3, 2, 3, 2, 2, 2]
INTENT_WORDS = {"refund": "asked for a refund", "cancel": "asked to cancel their subscription",
                "shipping": "reported a shipping delay", "login": "reported a login problem",
                "double_charge": "reported being charged twice", "praise": "sent praise"}
DISTINCT_INTENTS = ["refund", "cancel", "login", "double_charge"]
PLANS = ["free", "pro", "team"]
SIZES = {"train": 1500, "gate": 1500, "long": 12000}

PHRASES = {
    "refund": ["I'd like my money back for {item}", "please refund {item} I bought", "can I get a refund on {item}",
               "I want to return {item} and be reimbursed", "requesting a full refund for order {order}",
               "how do I get reimbursed for {item}", "{item} was faulty and I want my money returned",
               "please put the money for order {order} back on my card"],
    "cancel": ["please cancel my subscription", "I want to end my plan at the end of this month",
               "how do I stop being billed every month, I'm done", "close my account and stop the membership",
               "I no longer need the service, cancel it please", "turn off auto-renewal and cancel everything",
               "I'm leaving, terminate my subscription", "unsubscribe me from the paid plan"],
    "shipping": ["my package still hasn't arrived", "order {order} was supposed to come last week",
                 "tracking hasn't updated in {n} days", "where is my delivery? it's been {n} days",
                 "the courier keeps postponing my parcel", "still waiting on {item}, it's very late",
                 "my shipment seems stuck somewhere", "the estimated delivery date passed and nothing came"],
    "login": ["I can't sign in to my account", "the password reset email never arrives",
              "it says my credentials are wrong but they aren't", "the two-factor code keeps getting rejected",
              "I'm locked out after too many attempts", "the app logs me out right after I enter my password",
              "I can't get past the login screen", "my account access stopped working this morning"],
    "double_charge": ["I was billed twice for order {order}", "two identical charges hit my card",
                      "you charged me double this month", "there's a duplicate payment on my statement",
                      "the same amount was taken from my account two times", "I see {n} charges for one purchase",
                      "my card got charged again for something I already paid", "please fix the duplicate billing"],
    "praise": ["just wanted to say the support team was great", "love the new update, it works perfectly",
               "thanks, everything arrived early", "your app has made my week easier", "five stars, keep it up",
               "really happy with {item}", "the service has been excellent lately", "great experience overall"],
}
DECOYS = {
    "refund": ["I'm not asking for a refund", "I don't want my money back"],
    "cancel": ["I'm not cancelling", "I want to keep my subscription"],
    "shipping": ["the delivery itself was fine", "the package arrived on time"],
    "login": ["logging in works fine", "I can sign in without trouble"],
    "double_charge": ["my billing looks correct", "I was only charged once"],
}
OPENERS = ["Hi,", "Hello team,", "Hey,", "Good morning,", "To whom it may concern,", "Hi there,", "Hello,", ""]
DETAILS = ["This is the second time I'm writing.", "I've been a customer for {n} years.", "I tried the help center.",
           "My order number is {order}.", "Using the mobile app.", "On the website, from my laptop.", "", ""]
CLOSERS = ["Thanks.", "Regards.", "Please help.", "Cheers!", "Appreciate it.", "Thank you in advance.", ""]
ITEMS = ["the blender", "my headphones", "the winter jacket", "a phone case", "the desk lamp", "the running shoes",
         "a coffee grinder", "the backpack", "the smart watch", "a yoga mat"]

TICKET_RE = re.compile(r"\bt\d{5}\b")
CUSTOMER_RE = re.compile(r"\bc\d{4}\b")
INTENT_RE = re.compile(r"\b(refund|cancel|shipping|login|double_charge|praise)")


def _fill(rng: random.Random, s: str) -> str:
    return s.format(item=rng.choice(ITEMS), order=f"#{rng.randrange(10000, 99999)}", n=rng.randrange(2, 12))


def _ticket(rng: random.Random, customers: list[str], intent: str | None = None, plan: str | None = None) -> dict:
    intent = intent or rng.choices(INTENTS, weights=INTENT_WEIGHTS)[0]
    core = _fill(rng, rng.choice(PHRASES[intent]))
    parts = [rng.choice(OPENERS), core[0].upper() + core[1:] + "."]
    if intent != "praise" and rng.random() < 0.3:
        other = rng.choice([i for i in DECOYS if i != intent])
        parts.insert(1 if rng.random() < 0.5 else 2, rng.choice(DECOYS[other]).capitalize() + ",")
    parts += [_fill(rng, rng.choice(DETAILS)), rng.choice(CLOSERS)]
    return {"cust": rng.choice(customers), "plan": plan or rng.choice(PLANS), "intent": intent,
            "minute": rng.randrange(0, 24 * 60), "text": " ".join(p for p in parts if p)}


def _ask_needle(rng, recs, customers, idx):
    code = f"ZX-{rng.randrange(1000, 9999)}"
    target = _ticket(rng, customers, intent="shipping")
    target["text"] = f"Hello, order {code} arrived with a cracked screen and I need help."
    recs.insert(rng.randrange(len(recs) // 10, len(recs)), target)
    return f"Which ticket mentions order {code}? Answer with the ticket id only.", target


def _ask_topk(rng, recs, customers, idx):
    plan = rng.choice(PLANS)
    counts = {i: sum(1 for r in recs if r["plan"] == plan and r["intent"] == i) for i in INTENTS}
    target = rng.choice(INTENTS)
    rival = max(c for i, c in counts.items() if i != target)
    for _ in range(max(0, rival + 2 - counts[target])):  # unique winner by a margin of at least 2
        recs.insert(rng.randrange(len(recs)), _ticket(rng, customers, intent=target, plan=plan))
    return (f"Among tickets from customers on the {plan} plan, which issue is most common? Answer with one of: "
            f"{', '.join(INTENTS)}.", target)


def _ask_distinct(rng, recs, customers, idx):
    intent = DISTINCT_INTENTS[(idx // len(KINDS)) % len(DISTINCT_INTENTS)]
    n = len({r["cust"] for r in recs if r["intent"] == intent})
    return f"How many distinct customers {INTENT_WORDS[intent]} (any wording)? Answer with a single integer.", n


def _ask_pairs(rng, recs, customers, idx):
    both = sorted({r["cust"] for r in recs if r["intent"] == "login"} & {r["cust"] for r in recs if r["intent"] == "refund"})
    if not both:
        c = rng.choice(customers)
        for intent in ("login", "refund"):
            r = _ticket(rng, customers, intent=intent)
            r["cust"] = c
            recs.insert(rng.randrange(len(recs)), r)
        both = [c]
    return ("Which customers both reported a login problem and asked for a refund (any wording)? Answer with the "
            "customer ids as a comma-separated list.", both)


ASK = {"needle": _ask_needle, "topk": _ask_topk, "distinct": _ask_distinct, "pairs": _ask_pairs}


def make_task(split: str, idx: int, n: int | None = None) -> Task:
    n = n or SIZES[split]
    rng = random.Random(f"lamarck-tickets:{split}:{idx}:{n}")
    kind = KINDS[idx % len(KINDS)]
    customers = [f"c{k:04d}" for k in rng.sample(range(10000), max(30, n // 6))]
    recs = [_ticket(rng, customers) for _ in range(n)]
    question, answer = ASK[kind](rng, recs, customers, idx)
    lines = []
    for i, r in enumerate(recs):
        r["id"] = f"T{i:05d}"
        lines.append(f'{r["id"]} | {r["minute"] // 60:02d}:{r["minute"] % 60:02d} | cust={r["cust"]} | '
                     f'plan={r["plan"]} | "{r["text"]}"')
    if kind == "needle":
        answer = answer["id"]
    return Task(id=f"tickets-{split}-{idx}-{n}", split=split, idx=idx, kind=kind, question=question,
                context="\n".join(lines), answer=answer, workload="tickets")


def score(task: Task, answer: str) -> float:
    a = (answer or "").lower().replace("double charge", "double_charge").replace("double-charge", "double_charge")
    if task.kind == "needle":
        return float(set(TICKET_RE.findall(a)) == {task.answer.lower()})
    if task.kind == "topk":
        return float(set(INTENT_RE.findall(a)) == {task.answer})
    if task.kind == "distinct":  # partial credit: reading-based counts are noisy, so near misses still teach
        nums = re.findall(r"-?\d+", a.replace(",", ""))
        return round(max(0.0, 1 - 10 * abs(int(nums[0]) - task.answer) / task.answer), 4) if nums else 0.0
    got, want = set(CUSTOMER_RE.findall(a)), set(task.answer)
    tp = len(got & want)
    if tp == 0:
        return 0.0
    p, r = tp / len(got), tp / len(want)
    return round(2 * p * r / (p + r), 4)
