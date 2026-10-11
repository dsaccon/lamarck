"""Live view of an evolution run: lineage tree, per-genome detail and the feed, read from MongoDB."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from lamarck import store

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Lamarck")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/runs")
def runs_view() -> list[str]:
    return store.runs()


@app.get("/api/run/{run}")
def run_view(run: str) -> dict:
    return {"run": run, "champion": store.champion(run), "genomes": store.lineage(run)}


@app.get("/api/genome/{gid}")
def genome_view(gid: str) -> dict:
    g = store.get_genome(gid)
    if not g:
        raise HTTPException(404, f"no genome {gid}")
    return {"genome": g, "parent": store.get_genome(g["parent_id"]) if g.get("parent_id") else None}


@app.get("/api/run/{run}/feed")
def feed_view(run: str, after: float = 0.0) -> list[dict]:
    return store.feed(run, after)
