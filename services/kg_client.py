"""P1b — Local NetworkX Knowledge Graph client.

Provides three levels of access to the pre-built knowledge graph:
  - Low-level:   get_neighbors(node_id, edge_type) -> [node_ids]
  - Mid-level:   get_book_context(book_id) -> {authors, genres, co_genre_books}
  - High-level:  compute_kg_signal(book_ids) -> {book_id: float}

The graph is loaded lazily on the first call and cached for the process lifetime.
Designed to be safe to import even when the graph file does not yet exist
(returns empty results gracefully until build_knowledge_graph.py has been run).

Usage:
    from services.kg_client import LocalKGClient
    client = LocalKGClient()
    ctx = client.get_book_context("gr_2767052")
    signals = client.compute_kg_signal(["gr_2767052", "gr_3"])
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.data_paths import get_processed_data_path

try:
    import networkx as nx  # type: ignore
    _NX_AVAILABLE = True
except ImportError:  # pragma: no cover
    nx = None  # type: ignore
    _NX_AVAILABLE = False

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_GRAPH_PATH = get_processed_data_path("knowledge_graph.json")

# Max co-genre books returned per book (avoid huge lists for popular genres)
_MAX_CO_GENRE_BOOKS = 15


def _normalise_token(value: str) -> str:
    """Lowercase, replace spaces/hyphens with underscores, strip non-alphanum."""
    token = (value or "").strip().lower()
    token = re.sub(r"[\s\-]+", "_", token)
    token = re.sub(r"[^a-z0-9_]", "", token)
    return token.strip("_")


def _to_node_id(book_id: str) -> str:
    """Convert a raw book_id (e.g. 'gr_2767052') to the graph node ID ('book:gr_2767052').

    Accepts both raw IDs and already-prefixed IDs ('book:gr_2767052').
    """
    bid = (book_id or "").strip()
    if bid.startswith("book:"):
        return bid
    return "book:" + _normalise_token(bid)


class LocalKGClient:
    """In-memory NetworkX knowledge graph client.

    A single module-level instance ``_DEFAULT_CLIENT`` is created at the bottom
    of this module.  Import it directly for agent use:

        from services.kg_client import kg_client
        ctx = kg_client.get_book_context("gr_2767052")

    Alternatively, create a custom instance pointing at a different graph file:

        client = LocalKGClient(graph_path=Path("my_graph.json"))
    """

    def __init__(self, graph_path: Optional[Path] = None) -> None:
        self._graph_path: Path = graph_path or _DEFAULT_GRAPH_PATH
        self._graph: Any = None  # nx.Graph, loaded lazily
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the graph from disk.  Called at most once per instance."""
        if self._loaded:
            return
        self._loaded = True  # set before any early returns so we never retry

        if not _NX_AVAILABLE:
            logger.warning(
                "event=kg_client_no_networkx "
                "message='networkx not installed; KG features disabled'"
            )
            return

        if not self._graph_path.exists():
            logger.warning(
                "event=kg_graph_missing path=%s "
                "message='Run scripts/build_knowledge_graph.py first'",
                self._graph_path,
            )
            return

        try:
            with self._graph_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._graph = nx.node_link_graph(data)
            n = self._graph.number_of_nodes()
            e = self._graph.number_of_edges()
            logger.info("event=kg_graph_loaded nodes=%d edges=%d path=%s", n, e, self._graph_path)
        except Exception as exc:
            logger.warning("event=kg_graph_load_failed error=%s path=%s", exc, self._graph_path)
            self._graph = None

    @property
    def _g(self) -> Any:
        """Return the loaded graph (or None if unavailable)."""
        self._load()
        return self._graph

    def is_available(self) -> bool:
        """Return True if the graph is loaded and usable."""
        return self._g is not None

    # ------------------------------------------------------------------
    # P1b public API
    # ------------------------------------------------------------------

    def get_neighbors(self, node_id: str, edge_type: Optional[str] = None) -> List[str]:
        """Return adjacent node IDs for *node_id*, optionally filtered by edge *type*.

        Parameters
        ----------
        node_id:   full graph node ID, e.g. ``"book:gr_2767052"``
        edge_type: one of ``"written_by"``, ``"has_genre"``, ``"published_by"``,
                   or None to return all neighbours.
        """
        g = self._g
        if g is None or node_id not in g:
            return []

        neighbors: List[str] = []
        for neighbour, edge_data in g[node_id].items():
            if edge_type is None or edge_data.get("type") == edge_type:
                neighbors.append(neighbour)
        return neighbors

    def get_book_context(self, book_id: str) -> Dict[str, List[str]]:
        """Return structured graph context for a book.

        Parameters
        ----------
        book_id: raw book_id (``"gr_2767052"``) or prefixed node ID
                 (``"book:gr_2767052"``).

        Returns
        -------
        dict with keys:
          - ``authors``        — author node IDs connected to this book
          - ``genres``         — genre node IDs connected to this book
          - ``co_genre_books`` — up to _MAX_CO_GENRE_BOOKS other book node IDs
                                 that share at least one genre with this book
        """
        node_id = _to_node_id(book_id)
        g = self._g
        if g is None or node_id not in g:
            return {"authors": [], "genres": [], "co_genre_books": []}

        authors = self.get_neighbors(node_id, edge_type="written_by")
        genres = self.get_neighbors(node_id, edge_type="has_genre")

        co_books: List[str] = []
        seen: set[str] = {node_id}
        for g_node in genres:
            if len(co_books) >= _MAX_CO_GENRE_BOOKS:
                break
            for neighbor in g[g_node]:
                if neighbor in seen:
                    continue
                if (g.nodes[neighbor].get("node_type") == "book"):
                    co_books.append(neighbor)
                    seen.add(neighbor)
                    if len(co_books) >= _MAX_CO_GENRE_BOOKS:
                        break

        return {"authors": authors, "genres": genres, "co_genre_books": co_books}

    def compute_kg_signal(self, book_ids: List[str]) -> Dict[str, float]:
        """Compute a normalised connectivity score in [0, 1] for each book.

        The score reflects how well-connected a book is in the graph
        (author + genre + publisher neighbour count), normalised within the
        provided pool.  An optional bonus is added when books share an author,
        since that indicates a known-good author for the user.

        Parameters
        ----------
        book_ids: list of raw book IDs or prefixed node IDs.

        Returns
        -------
        dict mapping each *raw* book_id to its signal in [0.0, 1.0].
        """
        if not book_ids:
            return {}

        g = self._g
        if g is None:
            return {str(bid): 0.0 for bid in book_ids}

        node_ids = [_to_node_id(bid) for bid in book_ids]

        # --- step 1: count structural neighbours for each book ---
        raw_counts: Dict[str, int] = {}
        for node_id in node_ids:
            if node_id not in g:
                raw_counts[node_id] = 0
            else:
                # Count non-book neighbours (authors, genres, publishers)
                raw_counts[node_id] = sum(
                    1 for nb in g[node_id]
                    if g.nodes[nb].get("node_type") != "book"
                )

        # --- step 2: author-overlap bonus within the pool ---
        author_sets: Dict[str, set[str]] = {
            node_id: set(self.get_neighbors(node_id, "written_by"))
            for node_id in node_ids
        }
        for i, nid_a in enumerate(node_ids):
            for nid_b in node_ids[i + 1:]:
                shared = author_sets.get(nid_a, set()) & author_sets.get(nid_b, set())
                if shared:
                    raw_counts[nid_a] = raw_counts.get(nid_a, 0) + len(shared)
                    raw_counts[nid_b] = raw_counts.get(nid_b, 0) + len(shared)

        # --- step 3: min-max normalise within the pool ---
        values = list(raw_counts.values())
        mn, mx = min(values), max(values)
        span = mx - mn

        result: Dict[str, float] = {}
        for bid, node_id in zip(book_ids, node_ids):
            raw = raw_counts.get(node_id, 0)
            if span > 0:
                normalized = (raw - mn) / span
                # Soft floor: books with any connectivity get at least 0.1 so
                # that pool-minimum books are still distinguished from truly
                # disconnected books (raw == 0).
                score = (0.1 + 0.9 * normalized) if raw > 0 else 0.0
            else:
                # All books have equal connectivity; assign mid-range to avoid zero
                score = 0.5 if raw > 0 else 0.1
            result[str(bid)] = round(min(1.0, max(0.0, score)), 4)

        return result


# Module-level default instance used by book_content_agent
kg_client = LocalKGClient()
