from fastapi.testclient import TestClient

from lamarck import server


def test_run_endpoint_returns_lineage(monkeypatch):
    monkeypatch.setattr(server.store, "lineage", lambda run: [{"_id": "g0", "parent_id": None, "generation": 0}])
    monkeypatch.setattr(server.store, "champion", lambda run: "g0")
    body = TestClient(server.app).get("/api/run/main").json()
    assert body == {"run": "main", "champion": "g0", "genomes": [{"_id": "g0", "parent_id": None, "generation": 0}]}


def test_unknown_genome_is_404(monkeypatch):
    monkeypatch.setattr(server.store, "get_genome", lambda gid: None)
    assert TestClient(server.app).get("/api/genome/nope").status_code == 404


def test_index_is_served():
    assert "Lamarck" in TestClient(server.app).get("/").text


def test_runs_endpoint_lists_every_run(monkeypatch):
    monkeypatch.setattr(server.store, "runs", lambda: ["main", "tickets"])
    assert TestClient(server.app).get("/api/runs").json() == ["main", "tickets"]
