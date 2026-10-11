"""One isolated task run, executed in a spawned process by pool.run_many."""
import os
import tempfile

from lamarck import llm
from lamarck.genome import Genome
from lamarck.harness import run_task
from lamarck.tasks import make_task

SECRETS = ("GEMINI_API_KEY", "MONGODB_URI")


def run_job(job: dict) -> dict:
    client = llm.GeminiClient(os.environ["GEMINI_API_KEY"])
    for key in SECRETS:  # model-written code runs after this point; it must not be able to echo secrets
        os.environ.pop(key, None)
    os.chdir(tempfile.mkdtemp(prefix="lamarck-task-"))  # and not next to .env
    genome = Genome.model_validate(job["genome"])
    task = make_task(job["split"], job["idx"], job.get("n_lines"), job.get("workload", "logs"))
    return run_task(genome, task, client).model_dump(mode="json")
