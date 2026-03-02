"""P1a — Build the book knowledge graph from the Goodreads processed dataset.

Outputs (all under data/processed/):
  knowledge_graph.json      — full NetworkX node-link JSON (Graph, undirected)
  kg_author_index.json      — {author_node_id: [book_node_id, ...]}
  kg_genre_index.json       — {genre_node_id: [book_node_id, ...]}

Node ID convention:
  book:gr_2767052
  author:Suzanne_Collins
  genre:young_adult
  publisher:Scholastic_Press

Edge types (stored as edge attribute "type"):
  written_by    book ─ author
  has_genre     book ─ genre
  published_by  book ─ publisher   (only when publisher is non-empty)

Run:
  venv/Scripts/python.exe scripts/build_knowledge_graph.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

try:
    import networkx as nx  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit("networkx is required: pip install networkx") from exc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MERGED_BOOKS_PATH = PROJECT_ROOT / "data" / "processed" / "books_master_merged.jsonl"
_GOODREADS_BOOKS_PATH = PROJECT_ROOT / "data" / "processed" / "goodreads" / "books_master.jsonl"
BOOKS_PATH = _MERGED_BOOKS_PATH if _MERGED_BOOKS_PATH.exists() else _GOODREADS_BOOKS_PATH
OUT_DIR = PROJECT_ROOT / "data" / "processed"

OUT_GRAPH = OUT_DIR / "knowledge_graph.json"
OUT_AUTHOR_INDEX = OUT_DIR / "kg_author_index.json"
OUT_GENRE_INDEX = OUT_DIR / "kg_genre_index.json"

# Goodreads user-shelf tags that are NOT real genres and should be excluded
_SHELF_TAGS: frozenset[str] = frozenset(
    [
        "to_read",
        "favorites",
        "currently_reading",
        "owned",
        "books_i_own",
        "books-i-own",
        "default",
        "read",
        "did_not_finish",
        "dnf",
        "abandoned",
        "wishlist",
        "want_to_read",
        "re_read",
        "reread",
        "library",
        "lent",
        "borrowed",
        "own_it",
        "ebook",
        "audiobook",
        "kindle",
        "paperback",
        "hardcover",
        "british",
        "unfinished",
        "not_finished",
        "gave_up",
        "school",
        "college",
        "work",
        "english",
    ]
)


def _normalise_token(value: str) -> str:
    """Lower-case, replace spaces/hyphens with underscores, strip non-alphanum."""
    token = (value or "").strip().lower()
    token = re.sub(r"[\s\-]+", "_", token)
    token = re.sub(r"[^a-z0-9_]", "", token)
    return token.strip("_")


def _author_node_id(author: str) -> str:
    return "author:" + _normalise_token(author)


def _genre_node_id(genre: str) -> str:
    return "genre:" + _normalise_token(genre)


def _publisher_node_id(publisher: str) -> str:
    return "publisher:" + _normalise_token(publisher)


def _book_node_id(book_id: str) -> str:
    return "book:" + _normalise_token(book_id)


def _iter_books(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build_graph(books_path: Path = BOOKS_PATH) -> nx.Graph:
    """Build an undirected NetworkX Graph from the books dataset."""
    G: nx.Graph = nx.Graph()

    for record in _iter_books(books_path):
        book_id = str(record.get("book_id") or "").strip()
        if not book_id:
            continue

        title = str(record.get("title") or "").strip()
        author = str(record.get("author") or "").strip()
        publisher = str(record.get("publisher") or "").strip()
        genres: List[str] = [
            g for g in (record.get("genres") or [])
            if isinstance(g, str) and _normalise_token(g) not in _SHELF_TAGS and _normalise_token(g)
        ]

        b_node = _book_node_id(book_id)

        # --- book node ---
        G.add_node(
            b_node,
            node_type="book",
            book_id=book_id,
            title=title,
        )

        # --- author edge ---
        if author:
            a_node = _author_node_id(author)
            G.add_node(a_node, node_type="author", name=author)
            G.add_edge(b_node, a_node, type="written_by")

        # --- genre edges ---
        for genre in genres:
            norm = _normalise_token(genre)
            if not norm:
                continue
            g_node = _genre_node_id(norm)
            G.add_node(g_node, node_type="genre", name=norm)
            G.add_edge(b_node, g_node, type="has_genre")

        # --- publisher edge (sparse — only if non-empty) ---
        if publisher:
            p_node = _publisher_node_id(publisher)
            G.add_node(p_node, node_type="publisher", name=publisher)
            G.add_edge(b_node, p_node, type="published_by")

    return G


def build_author_index(G: nx.Graph) -> Dict[str, List[str]]:
    """Return {author_node_id: [book_node_id, ...]}."""
    index: Dict[str, List[str]] = defaultdict(list)
    for u, v, data in G.edges(data=True):
        if data.get("type") == "written_by":
            book_node = u if G.nodes[u].get("node_type") == "book" else v
            author_node = v if G.nodes[u].get("node_type") == "book" else u
            index[author_node].append(book_node)
    return dict(index)


def build_genre_index(G: nx.Graph) -> Dict[str, List[str]]:
    """Return {genre_node_id: [book_node_id, ...]}."""
    index: Dict[str, List[str]] = defaultdict(list)
    for u, v, data in G.edges(data=True):
        if data.get("type") == "has_genre":
            book_node = u if G.nodes[u].get("node_type") == "book" else v
            genre_node = v if G.nodes[u].get("node_type") == "book" else u
            index[genre_node].append(book_node)
    return dict(index)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the book knowledge graph")
    parser.add_argument("--books", type=Path, default=BOOKS_PATH)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    books_path: Path = args.books
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading books from: {books_path}")
    if not books_path.exists():
        raise SystemExit(f"Books file not found: {books_path}")

    print("Building knowledge graph …")
    G = build_graph(books_path)

    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()
    book_nodes = sum(1 for n, d in G.nodes(data=True) if d.get("node_type") == "book")
    author_nodes = sum(1 for n, d in G.nodes(data=True) if d.get("node_type") == "author")
    genre_nodes = sum(1 for n, d in G.nodes(data=True) if d.get("node_type") == "genre")
    publisher_nodes = sum(1 for n, d in G.nodes(data=True) if d.get("node_type") == "publisher")
    print(
        f"  Nodes: {node_count:,}  (books={book_nodes:,}, authors={author_nodes:,}, "
        f"genres={genre_nodes:,}, publishers={publisher_nodes:,})"
    )
    print(f"  Edges: {edge_count:,}")

    # Persist graph in node-link JSON format
    out_graph = out_dir / "knowledge_graph.json"
    data = nx.node_link_data(G)
    with out_graph.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  Saved graph → {out_graph}")

    # Persist author index
    out_author = out_dir / "kg_author_index.json"
    author_index = build_author_index(G)
    with out_author.open("w", encoding="utf-8") as fh:
        json.dump(author_index, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  Saved author index → {out_author}  ({len(author_index):,} authors)")

    # Persist genre index
    out_genre = out_dir / "kg_genre_index.json"
    genre_index = build_genre_index(G)
    with out_genre.open("w", encoding="utf-8") as fh:
        json.dump(genre_index, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  Saved genre index  → {out_genre}  ({len(genre_index):,} genres)")

    print("Done.")


if __name__ == "__main__":
    main()
