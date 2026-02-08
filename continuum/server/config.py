import os
from pathlib import Path

CONTINUUM_HOME = Path(os.environ.get("CONTINUUM_HOME", os.path.expanduser("~/.continuum")))
DB_PATH = Path(os.environ.get("CONTINUUM_DB_PATH", str(CONTINUUM_HOME / "continuum.db")))
CHROMA_PATH = Path(os.environ.get("CONTINUUM_CHROMA_PATH", str(CONTINUUM_HOME / "chroma_db")))
CONTINUUM_PORT = int(os.environ.get("CONTINUUM_PORT", "8000"))

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


def ensure_directories():
    """Create storage directories if they don't exist."""
    CONTINUUM_HOME.mkdir(parents=True, exist_ok=True)
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
