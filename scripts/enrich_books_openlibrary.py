from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "merged" / "books_master_merged.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "merged" / "books_master_merged_enriched.jsonl"
SEARCH_URL = "https://openlibrary.org/search.json"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_title(value: str) -> str:
    token = _clean_text(value).lower()
    token = re.sub(r"[^\w\s]", "", token, flags=re.UNICODE)
    return re.sub(r"\s+", " ", token).strip()


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                yield row


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _best_doc(title: str, author: str, docs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    norm_title = _normalize_title(title)
    norm_author = _normalize_title(author)
    best: Optional[Dict[str, Any]] = None
    best_score = -1.0
    for doc in docs:
        doc_title = _normalize_title(doc.get("title") or "")
        doc_author = _normalize_title(" ".join(doc.get("author_name") or []))
        score = 0.0
        if doc_title == norm_title:
            score += 2.0
        elif norm_title and norm_title in doc_title:
            score += 1.0
        if norm_author and doc_author == norm_author:
            score += 2.0
        elif norm_author and norm_author in doc_author:
            score += 1.0
        if doc.get("first_publish_year"):
            score += 0.25
        if doc.get("publisher"):
            score += 0.25
        if score > best_score:
            best = doc
            best_score = score
    return best if best_score > 0 else None


def _normalize_subjects(doc: Dict[str, Any], max_subjects: int = 8) -> List[str]:
    subjects = doc.get("subject") or []
    normalized: List[str] = []
    seen = set()
    for item in subjects:
        token = _clean_text(item).lower().replace("-", " ")
        token = re.sub(r"\s+", "_", token)
        token = re.sub(r"[^a-z0-9_]+", "", token)
        token = token.strip("_")
        if token and token not in seen:
            normalized.append(token)
            seen.add(token)
        if len(normalized) >= max_subjects:
            break
    return normalized


def enrich_row(session: requests.Session, row: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    title = _clean_text(row.get("title"))
    author = _clean_text(row.get("author"))
    if not title:
        return row

    response = session.get(
        SEARCH_URL,
        params={"title": title, "author": author, "limit": 5},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    docs = payload.get("docs") or []
    if not isinstance(docs, list) or not docs:
        return row

    doc = _best_doc(title, author, docs)
    if not doc:
        return row

    enriched = dict(row)
    if not _clean_text(enriched.get("publisher")):
        publishers = doc.get("publisher") or []
        if isinstance(publishers, list) and publishers:
            enriched["publisher"] = _clean_text(publishers[0])
    if not enriched.get("published_year") and doc.get("first_publish_year"):
        enriched["published_year"] = doc.get("first_publish_year")
    if not isinstance(enriched.get("genres"), list) or not enriched.get("genres"):
        enriched["genres"] = _normalize_subjects(doc)
    else:
        merged_genres = list(enriched.get("genres") or [])
        for subject in _normalize_subjects(doc):
            if subject not in merged_genres:
                merged_genres.append(subject)
        enriched["genres"] = merged_genres[:12]
    source = _clean_text(enriched.get("source"))
    if "openlibrary" not in source:
        enriched["source"] = "+".join([part for part in [source, "openlibrary"] if part])
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich normalized book metadata with Open Library search results.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-books", type=int, default=5000)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Missing input corpus: {args.input}")

    session = requests.Session()
    session.headers.update({"User-Agent": "acps-reading-recsys/1.0"})

    enriched_rows: List[Dict[str, Any]] = []
    processed = 0
    for row in _iter_jsonl(args.input):
        if args.max_books > 0 and processed >= args.max_books:
            enriched_rows.append(row)
            continue
        try:
            enriched = enrich_row(session, row, timeout=args.timeout)
        except Exception:
            enriched = row
        enriched_rows.append(enriched)
        processed += 1
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    count = _write_jsonl(args.output, enriched_rows)
    print(f"enriched_rows: {count}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()