import os
from pathlib import Path

CONTINUUM_HOME = Path(os.environ.get("CONTINUUM_HOME", os.path.expanduser("~/.continuum")))
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://conversive:conversive@localhost:5433/continuum_dev",
)
CONTINUUM_PORT = int(os.environ.get("CONTINUUM_PORT", "8000"))

# Embedding model and dimensions (all-MiniLM-L6-v2 → 384-dim)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Importance score mapping
IMPORTANCE_SCORES = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.5,
    "low": 0.3,
    "ephemeral": 0.1,
}

# Temporal decay rate (per day)
TEMPORAL_DECAY_RATE = 0.02

# Search weight configuration
SEARCH_WEIGHT_VECTOR = 0.60
SEARCH_WEIGHT_IMPORTANCE = 0.25
SEARCH_WEIGHT_FRESHNESS = 0.15

# Extraction pipeline configuration
EXTRACTION_AUTO_SAVE_THRESHOLD = float(os.environ.get("CONTINUUM_AUTO_SAVE_THRESHOLD", "0.85"))
EXTRACTION_QUEUE_THRESHOLD = float(os.environ.get("CONTINUUM_QUEUE_THRESHOLD", "0.50"))
EXTRACTION_TTL_HOURS = int(os.environ.get("CONTINUUM_EXTRACTION_TTL_HOURS", "24"))

# Cross-project promotion
ENABLE_PROMOTION = os.environ.get("CONTINUUM_ENABLE_PROMOTION", "true").lower() == "true"
PROMOTION_THRESHOLD = float(os.environ.get("CONTINUUM_PROMOTION_THRESHOLD", "0.85"))
PROMOTION_MIN_PROJECTS = int(os.environ.get("CONTINUUM_PROMOTION_MIN_PROJECTS", "3"))


def ensure_directories():
    CONTINUUM_HOME.mkdir(parents=True, exist_ok=True)
