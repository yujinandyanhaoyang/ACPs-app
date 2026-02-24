"""Tests for services/kg_client.py — LocalKGClient.

Fixture graph (5 nodes, 4 edges):

    book:b1  ──written_by──>  author:a1
    book:b1  ──has_genre───>  genre:g1
    book:b2  ──has_genre───>  genre:g1
    book:b2  ──has_genre───>  genre:g2

Meaning:
  - b1 and b2 co-share genre g1 (co-genre relationship)
  - b1 has 1 author + 1 genre = 2 non-book neighbours
  - b2 has 0 authors + 2 genres  = 2 non-book neighbours (equal connectivity)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

from services.kg_client import LocalKGClient, _normalise_token, _to_node_id

pytestmark = pytest.mark.skipif(not _NX_AVAILABLE, reason="networkx not installed")

# ---------------------------------------------------------------------------
# Fixture: minimal 5-node graph written to a temp file
# ---------------------------------------------------------------------------

def _build_fixture_graph() -> Any:
    """Build a small but representative NetworkX graph for testing."""
    g = nx.Graph()

    # Nodes
    g.add_node("book:b1", node_type="book", title="Book One")
    g.add_node("book:b2", node_type="book", title="Book Two")
    g.add_node("author:a1", node_type="author", name="Author One")
    g.add_node("genre:g1", node_type="genre", name="Genre One")
    g.add_node("genre:g2", node_type="genre", name="Genre Two")

    # Edges
    g.add_edge("book:b1", "author:a1", type="written_by")
    g.add_edge("book:b1", "genre:g1", type="has_genre")
    g.add_edge("book:b2", "genre:g1", type="has_genre")
    g.add_edge("book:b2", "genre:g2", type="has_genre")

    return g


@pytest.fixture()
def graph_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Serialise the fixture graph to a temp JSON file and yield its path."""
    g = _build_fixture_graph()
    data = nx.node_link_data(g)
    p = tmp_path / "knowledge_graph.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    yield p


@pytest.fixture()
def client(graph_path: Path) -> LocalKGClient:
    """Return a LocalKGClient pre-loaded with the fixture graph."""
    c = LocalKGClient(graph_path=graph_path)
    c._load()  # force eager load
    return c


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_normalise_token_lowercase(self):
        assert _normalise_token("Young Adult") == "young_adult"

    def test_normalise_token_hyphens(self):
        assert _normalise_token("science-fiction") == "science_fiction"

    def test_normalise_token_special_chars(self):
        assert _normalise_token("Sci-Fi & Fantasy!") == "sci_fi__fantasy"

    def test_normalise_token_empty(self):
        assert _normalise_token("") == ""

    def test_to_node_id_raw(self):
        assert _to_node_id("gr_2767052") == "book:gr_2767052"

    def test_to_node_id_already_prefixed(self):
        assert _to_node_id("book:gr_2767052") == "book:gr_2767052"

    def test_to_node_id_strips_whitespace(self):
        assert _to_node_id("  gr_42  ") == "book:gr_42"


# ---------------------------------------------------------------------------
# Load / availability
# ---------------------------------------------------------------------------


class TestLoad:
    def test_is_available(self, client: LocalKGClient):
        assert client.is_available()

    def test_missing_path_not_available(self, tmp_path: Path):
        c = LocalKGClient(graph_path=tmp_path / "not_there.json")
        assert not c.is_available()

    def test_graph_node_count(self, client: LocalKGClient):
        assert client._g.number_of_nodes() == 5

    def test_graph_edge_count(self, client: LocalKGClient):
        assert client._g.number_of_edges() == 4

    def test_load_idempotent(self, client: LocalKGClient):
        """Calling _load() twice should not raise or change graph."""
        first = id(client._graph)
        client._load()  # second call
        assert id(client._graph) == first


# ---------------------------------------------------------------------------
# get_neighbors
# ---------------------------------------------------------------------------


class TestGetNeighbors:
    def test_get_all_neighbors_b1(self, client: LocalKGClient):
        result = set(client.get_neighbors("book:b1"))
        assert result == {"author:a1", "genre:g1"}

    def test_get_written_by_b1(self, client: LocalKGClient):
        result = client.get_neighbors("book:b1", edge_type="written_by")
        assert result == ["author:a1"]

    def test_get_has_genre_b2(self, client: LocalKGClient):
        result = set(client.get_neighbors("book:b2", edge_type="has_genre"))
        assert result == {"genre:g1", "genre:g2"}

    def test_wrong_edge_type_returns_empty(self, client: LocalKGClient):
        result = client.get_neighbors("book:b1", edge_type="published_by")
        assert result == []

    def test_missing_node_returns_empty(self, client: LocalKGClient):
        result = client.get_neighbors("book:nonexistent")
        assert result == []

    def test_missing_graph_returns_empty(self, tmp_path: Path):
        c = LocalKGClient(graph_path=tmp_path / "missing.json")
        assert c.get_neighbors("book:b1") == []


# ---------------------------------------------------------------------------
# get_book_context
# ---------------------------------------------------------------------------


class TestGetBookContext:
    def test_b1_context_authors(self, client: LocalKGClient):
        ctx = client.get_book_context("b1")
        assert ctx["authors"] == ["author:a1"]

    def test_b1_context_genres(self, client: LocalKGClient):
        ctx = client.get_book_context("b1")
        assert ctx["genres"] == ["genre:g1"]

    def test_b1_co_genre_books_includes_b2(self, client: LocalKGClient):
        ctx = client.get_book_context("b1")
        assert "book:b2" in ctx["co_genre_books"]

    def test_b1_co_genre_books_excludes_self(self, client: LocalKGClient):
        ctx = client.get_book_context("b1")
        assert "book:b1" not in ctx["co_genre_books"]

    def test_b2_has_two_genres(self, client: LocalKGClient):
        ctx = client.get_book_context("b2")
        assert set(ctx["genres"]) == {"genre:g1", "genre:g2"}

    def test_b2_no_authors(self, client: LocalKGClient):
        ctx = client.get_book_context("b2")
        assert ctx["authors"] == []

    def test_missing_book_returns_empty_context(self, client: LocalKGClient):
        ctx = client.get_book_context("b999")
        assert ctx == {"authors": [], "genres": [], "co_genre_books": []}

    def test_accepts_prefixed_node_id(self, client: LocalKGClient):
        ctx_raw = client.get_book_context("b1")
        ctx_prefixed = client.get_book_context("book:b1")
        assert ctx_raw == ctx_prefixed


# ---------------------------------------------------------------------------
# compute_kg_signal
# ---------------------------------------------------------------------------


class TestComputeKgSignal:
    def test_returns_entry_per_book(self, client: LocalKGClient):
        signals = client.compute_kg_signal(["b1", "b2"])
        assert set(signals.keys()) == {"b1", "b2"}

    def test_signal_range_between_0_and_1(self, client: LocalKGClient):
        signals = client.compute_kg_signal(["b1", "b2"])
        for v in signals.values():
            assert 0.0 <= v <= 1.0, f"Signal out of range: {v}"

    def test_empty_input_returns_empty_dict(self, client: LocalKGClient):
        assert client.compute_kg_signal([]) == {}

    def test_single_book_returns_midrange(self, client: LocalKGClient):
        """Single book with connectivity → signal should be 0.5 (all equal, connected)."""
        signals = client.compute_kg_signal(["b1"])
        assert signals["b1"] == pytest.approx(0.5, abs=0.01)

    def test_missing_graph_returns_zeros(self, tmp_path: Path):
        c = LocalKGClient(graph_path=tmp_path / "missing.json")
        result = c.compute_kg_signal(["b1", "b2"])
        assert result == {"b1": 0.0, "b2": 0.0}

    def test_unknown_book_gets_low_signal(self, client: LocalKGClient):
        """A book not in the graph should get 0 connectivity."""
        signals = client.compute_kg_signal(["b1", "b_unknown"])
        # b1 has higher connectivity than a missing book
        assert signals["b1"] >= signals["b_unknown"]

    def test_author_sharing_increases_signal(self, graph_path: Path):
        """Add a third book sharing author:a1 with b1; both should see increased signal."""
        # Load the graph, add book:b3 sharing author:a1
        with graph_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        g = nx.node_link_graph(data)
        g.add_node("book:b3", node_type="book", title="Book Three")
        g.add_edge("book:b3", "author:a1", type="written_by")
        new_data = nx.node_link_data(g)
        graph_path.write_text(json.dumps(new_data), encoding="utf-8")

        c = LocalKGClient(graph_path=graph_path)
        signals = c.compute_kg_signal(["b1", "b3"])
        # Because b1 and b3 share author:a1 the author-overlap bonus fires.
        # Both signals should be > 0 (may be equal, but not zero)
        assert signals["b1"] > 0.0
        assert signals["b3"] > 0.0
