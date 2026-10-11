import pytest

from lamarck import cli
from lamarck.genome import GEN0


def summary(acc, tokens=1000, n=12):
    return {"acc": acc, "tokens": tokens, "n": n, "by_kind": {}, "cost": 0.0, "errors": 0}


class FakeStore:
    def __init__(self):
        self.g = {"g0": {"_id": "g0", "run": "r", "parent_id": None, "generation": 0, "genome": GEN0.model_dump(),
                         "ops": [], "status": "accepted", "reason": "", "focus": "",
                         "scores": {"train": summary(0.5), "gate": summary(0.5, n=8)}}}
        self.champs, self.n, self.logs, self.workloads = {"r": "g0"}, 0, [], {}

    def champion(self, run):
        return self.champs.get(run)

    def set_champion(self, run, gid):
        self.champs[run] = gid

    def workload(self, run):
        return self.workloads.get(run, "logs")

    def set_workload(self, run, workload):
        self.workloads[run] = workload

    def get_genome(self, gid):
        return self.g.get(gid)

    def failing_runs(self, gid, split, limit):
        return []

    def lineage(self, run):
        return sorted((g for g in self.g.values() if g["run"] == run), key=lambda x: x["generation"])

    def log(self, run, msg):
        self.logs.append(msg)

    def insert_genome(self, run, genome, parent_id, generation, *, ops=None, hypothesis="", diagnosis="",
                      focus="", status="candidate", reason=""):
        self.n += 1
        gid = f"c{self.n}"
        self.g[gid] = {"_id": gid, "run": run, "parent_id": parent_id, "generation": generation, "genome": genome,
                       "ops": ops or [], "status": status, "reason": reason, "focus": focus, "scores": {}}
        return gid

    def set_status(self, gid, status, reason):
        self.g[gid].update(status=status, reason=reason)


@pytest.fixture
def fake(monkeypatch):
    store = FakeStore()
    for name in ("champion", "set_champion", "get_genome", "failing_runs", "lineage", "log", "insert_genome",
                 "set_status", "workload", "set_workload"):
        monkeypatch.setattr(cli.store, name, getattr(store, name))

    def propose(champ, failures, history, focus):
        if focus == "free":
            return {"ok": False, "error": "path 'x' is not settable", "hypothesis": "", "diagnosis": ""}
        genome = {**GEN0.model_dump(), "system_notes": [focus]}
        return {"ok": True, "genome": genome, "ops": [{"op": "add_note", "text": focus}], "hypothesis": "h",
                "diagnosis": "d"}

    monkeypatch.setattr(cli.engineer, "propose", propose)
    return store


def use_scores(monkeypatch, store, table):
    def evaluate_many(pairs, run=None):
        out = {}
        for gid, split in pairs:
            out[(gid, split)] = table[(gid, split)]
            store.g[gid]["scores"][split] = table[(gid, split)]
        return out

    monkeypatch.setattr(cli, "evaluate_many", evaluate_many)


def test_best_candidate_is_gated_and_accepted_runner_up_not_selected(monkeypatch, fake):
    use_scores(monkeypatch, fake, {("c1", "train"): summary(0.75), ("c2", "train"): summary(0.6),
                                   ("c1", "gate"): summary(0.5, n=8)})
    cli.generation("r", 1, 3)
    assert fake.champs["r"] == "c1" and fake.g["c1"]["status"] == "accepted"
    assert fake.g["c2"]["status"] == "not_selected"
    assert fake.g["c3"]["status"] == "invalid" and "not settable" in fake.g["c3"]["reason"]


def test_train_gain_that_fails_the_gate_is_overfit_and_champion_stays(monkeypatch, fake):
    use_scores(monkeypatch, fake, {("c1", "train"): summary(0.75), ("c2", "train"): summary(0.4),
                                   ("c1", "gate"): summary(0.25, n=8)})
    cli.generation("r", 1, 3)
    assert fake.champs["r"] == "g0" and fake.g["c1"]["status"] == "rejected_overfit"
    assert fake.g["c2"]["status"] == "rejected_no_gain"


def test_evolve_refuses_while_candidates_are_in_flight(monkeypatch, fake):
    fake.insert_genome("r", GEN0.model_dump(), "g0", 1)  # status "candidate": another evolve is mid-evaluation
    calls = []
    monkeypatch.setattr(cli, "generation", lambda run, g, k: calls.append(g))
    with pytest.raises(SystemExit, match="still being evaluated"):
        cli.main(["evolve", "--run", "r"])
    cli.main(["evolve", "--run", "r", "--force"])
    assert calls == [2]


def test_a_run_keeps_its_workload(monkeypatch, fake):
    calls = []
    monkeypatch.setattr(cli, "generation", lambda run, g, k: calls.append((run, g)))
    with pytest.raises(SystemExit, match="workload"):
        cli.main(["evolve", "--run", "r", "--workload", "tickets"])  # r already exists as a logs run
    cli.main(["evolve", "--run", "fresh", "--workload", "tickets"])
    assert fake.workload("fresh") == "tickets" and calls == [("fresh", 1)]
