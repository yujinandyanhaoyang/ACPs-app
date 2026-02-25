import os
import asyncio
import sys
from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = str(_CURRENT_DIR.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("OPENAI_BASE_URL", None)
os.environ["BOOK_CONTENT_EMBED_MODEL"] = "all-MiniLM-L6-v2"

from agents.rec_ranking_agent.rec_ranking_agent import _rank_candidates

payload = {
    "query": "recommend thoughtful science fiction",
    "profile_vector": {
        "genres": {"science_fiction": 0.8, "fiction": 0.2},
        "themes": {"identity": 0.7, "society": 0.3},
        "difficulty": {"intermediate": 1.0},
    },
    "candidates": [
        {"book_id": "b1", "title": "Dune", "vector": [0.7, 0.6, 0.5], "kg_signal": 0.4, "novelty_score": 0.3, "diversity_score": 0.2},
        {"book_id": "b2", "title": "Foundation", "vector": [0.6, 0.6, 0.4], "kg_signal": 0.5, "novelty_score": 0.2, "diversity_score": 0.3},
    ],
    "constraints": {"top_k": 2},
}

rows, meta = asyncio.run(_rank_candidates(payload))
print({
    "backend": meta.get("semantic_backend", {}).get("backend"),
    "model": meta.get("semantic_backend", {}).get("model"),
    "vector_dim": meta.get("semantic_backend", {}).get("vector_dim"),
    "ranked_count": len(rows),
})
