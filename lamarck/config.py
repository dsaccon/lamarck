"""Project-wide constants. The hard caps here are protected: no genome op can reach them."""
import os
from pathlib import Path

from dotenv import load_dotenv

from lamarck import net

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
net.install()  # every process imports config, including spawned workers

# Worker models the evolver may choose: id -> ($ per M input tokens, $ per M output tokens).
WORKER_MODELS: dict[str, tuple[float, float]] = {"gemini-3.8-flash": (0.75, 3.75)}
DEFAULT_WORKER = "gemini-3.8-flash"
THINKING_LEVELS = ("low", "high")
ENGINEER_MODEL = "claude-opus-5-5"
ENGINEER_EFFORT = "high"
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

# split -> (number of tasks, log lines per task). Line counts are fixed by the spike (Task 6).
SPLITS: dict[str, tuple[int, int]] = {"train": (12, 800), "gate": (8, 800), "long": (8, 8000)}

# Protected hard caps.
TASK_TIMEOUT_S = 420
STEP_TIMEOUT_S = 60
TOKEN_CEILING = 3_000_000
MAX_PARALLEL = 16

DB_NAME = os.environ.get("MONGODB_DB", "lamarck")
