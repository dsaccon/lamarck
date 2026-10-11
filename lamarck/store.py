"""MongoDB Atlas access.

Collections: genomes (the lineage tree), runs (one per genome x task, trace embedded),
feed (human-readable live log), meta (champion pointer per evolution run).
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from pymongo import ASCENDING, MongoClient

from lamarck import config

_db = None


def db():
    global _db
    if _db is None:
        client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=10_000, appname="lamarck")
        _db = client[config.DB_NAME]
        _db.genomes.create_index([("run", ASCENDING), ("generation", ASCENDING)])
        _db.runs.create_index([("genome_id", ASCENDING), ("split", ASCENDING)])
        _db.feed.create_index([("run", ASCENDING), ("ts", ASCENDING)])
    return _db


def ping() -> None:
    db().command("ping")


def insert_genome(run: str, genome: dict, parent_id: str | None, generation: int, *, ops: list | None = None,
                  hypothesis: str = "", diagnosis: str = "", focus: str = "", status: str = "candidate",
                  reason: str = "") -> str:
    gid = uuid.uuid4().hex[:8]
    db().genomes.insert_one({"_id": gid, "run": run, "parent_id": parent_id, "generation": generation,
                             "genome": genome, "ops": ops or [], "hypothesis": hypothesis, "diagnosis": diagnosis,
                             "focus": focus, "status": status, "reason": reason, "scores": {},
                             "created_at": datetime.now(timezone.utc)})
    return gid


def get_genome(gid: str) -> dict | None:
    return db().genomes.find_one({"_id": gid})


def set_status(gid: str, status: str, reason: str) -> None:
    db().genomes.update_one({"_id": gid}, {"$set": {"status": status, "reason": reason}})


def set_scores(gid: str, split: str, summary: dict) -> None:
    db().genomes.update_one({"_id": gid}, {"$set": {f"scores.{split}": summary}})


def champion(run: str) -> str | None:
    doc = db().meta.find_one({"_id": f"champion:{run}"})
    return doc["genome_id"] if doc else None


def set_champion(run: str, gid: str) -> None:
    db().meta.update_one({"_id": f"champion:{run}"}, {"$set": {"genome_id": gid}}, upsert=True)


def insert_runs(gid: str, split: str, results: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    db().runs.insert_many([{**r, "genome_id": gid, "split": split, "created_at": now} for r in results])


def failing_runs(gid: str, split: str, limit: int) -> list[dict]:
    return list(db().runs.find({"genome_id": gid, "split": split, "score": {"$lt": 1.0}})
                .sort("score", ASCENDING).limit(limit))


def lineage(run: str) -> list[dict]:
    return list(db().genomes.find({"run": run}).sort([("generation", ASCENDING), ("created_at", ASCENDING)]))


def log(run: str, msg: str) -> None:
    db().feed.insert_one({"run": run, "ts": time.time(), "msg": msg})
    print(msg, flush=True)


def feed(run: str, after: float = 0.0, limit: int = 300) -> list[dict]:
    return list(db().feed.find({"run": run, "ts": {"$gt": after}}, {"_id": 0}).sort("ts", ASCENDING).limit(limit))
