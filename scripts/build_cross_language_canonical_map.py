from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EN_BOOKS_PATH = PROJECT_ROOT / "data" / "processed" / "goodreads" / "books_master.jsonl"
ZH_BOOKS_PATH = PROJECT_ROOT / "data" / "processed" / "books_master_zh.jsonl"
OUT_DIR = PROJECT_ROOT / "data" / "processed"


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield payload


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_text(value: Any) -> str:
    token = _clean_text(value).lower()
    token = re.sub(r"[^\w\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", "", token)
    return token


def _normalize_isbn(value: Any) -> str:
    token = re.sub(r"[^0-9Xx]", "", _clean_text(value)).upper()
    if len(token) in {10, 13}:
        return token
    return ""


def _signature(row: Dict[str, Any]) -> str:
    title = _normalize_text(row.get("title"))
    author = _normalize_text(row.get("author"))
    if not title and not author:
        return ""
    return f"{title}|{author}"


def _signature_bucket_keys(signature: str) -> List[str]:
    if not signature:
        return []
    title = signature.split("|", 1)[0]
    head = title[:2] if len(title) >= 2 else title
    length_bucket = str(len(signature) // 8)
    if not head:
        head = "_"
    return [f"{head}:{length_bucket}"]


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    def _ngrams(text: str, size: int = 2) -> set[str]:
        if len(text) <= size:
            return {text}
        return {text[idx : idx + size] for idx in range(len(text) - size + 1)}

    left_set = _ngrams(left)
    right_set = _ngrams(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _generated_canonical(counter: int) -> str:
    return f"cw_auto_{counter:07d}"


def build_canonical_map(
    en_books_path: Path = EN_BOOKS_PATH,
    zh_books_path: Path = ZH_BOOKS_PATH,
    out_dir: Path = OUT_DIR,
    fuzzy_threshold: float = 0.93,
) -> Dict[str, Any]:
    if not en_books_path.exists():
        raise FileNotFoundError(f"English books file not found: {en_books_path}")
    if not zh_books_path.exists():
        raise FileNotFoundError(f"Chinese books file not found: {zh_books_path}")

    combined: List[Dict[str, Any]] = []
    seen_book_ids: set[str] = set()
    for path in [en_books_path, zh_books_path]:
        for row in _iter_jsonl(path):
            book_id = _clean_text(row.get("book_id"))
            if not book_id or book_id in seen_book_ids:
                continue
            seen_book_ids.add(book_id)
            combined.append({**row, "book_id": book_id})

    isbn_to_canonical: Dict[str, str] = {}
    declared_cw_to_canonical: Dict[str, str] = {}
    canonical_signatures: List[Tuple[str, str]] = []
    signature_exact_to_canonical: Dict[str, str] = {}
    signature_buckets: Dict[str, List[Tuple[str, str]]] = {}

    canonical_map: Dict[str, str] = {}
    merged_rows: List[Dict[str, Any]] = []
    generated_counter = 1

    for row in combined:
        book_id = str(row.get("book_id") or "").strip()
        declared_cw = _clean_text(row.get("canonical_work_id"))
        isbn13 = _normalize_isbn(row.get("isbn13"))
        isbn10 = _normalize_isbn(row.get("isbn10"))
        signature = _signature(row)

        canonical: str | None = None

        for isbn in [isbn13, isbn10]:
            if isbn and isbn in isbn_to_canonical:
                canonical = isbn_to_canonical[isbn]
                break

        if canonical is None and declared_cw:
            canonical = declared_cw_to_canonical.get(declared_cw, declared_cw)

        if canonical is None and signature:
            exact = signature_exact_to_canonical.get(signature)
            if exact is not None:
                canonical = exact

        if canonical is None and signature:
            best_score = 0.0
            best_canonical: str | None = None
            candidate_pairs: List[Tuple[str, str]] = []
            for key in _signature_bucket_keys(signature):
                bucket_rows = signature_buckets.get(key, [])
                if bucket_rows:
                    candidate_pairs.extend(bucket_rows[-200:])
            if not candidate_pairs:
                candidate_pairs = canonical_signatures[-200:]

            for existing_canonical, existing_signature in candidate_pairs:
                if abs(len(existing_signature) - len(signature)) > 12:
                    continue
                score = _similarity(signature, existing_signature)
                if score > best_score:
                    best_score = score
                    best_canonical = existing_canonical
            if best_canonical is not None and best_score >= fuzzy_threshold:
                canonical = best_canonical

        if canonical is None:
            if declared_cw:
                canonical = declared_cw
            else:
                canonical = _generated_canonical(generated_counter)
                generated_counter += 1

        canonical_map[book_id] = canonical

        if declared_cw:
            declared_cw_to_canonical[declared_cw] = canonical
        for isbn in [isbn13, isbn10]:
            if isbn:
                isbn_to_canonical[isbn] = canonical

        if signature and all(existing_canonical != canonical for existing_canonical, _ in canonical_signatures):
            pair = (canonical, signature)
            canonical_signatures.append(pair)
            signature_exact_to_canonical[signature] = canonical
            for key in _signature_bucket_keys(signature):
                signature_buckets.setdefault(key, []).append(pair)

        merged_rows.append({**row, "canonical_work_id": canonical})

    out_dir.mkdir(parents=True, exist_ok=True)
    canonical_map_path = out_dir / "book_canonical_map.json"
    merged_path = out_dir / "books_master_merged.jsonl"

    with canonical_map_path.open("w", encoding="utf-8") as f:
        json.dump(canonical_map, f, ensure_ascii=False, indent=2)

    with merged_path.open("w", encoding="utf-8") as f:
        for row in merged_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "book_count": len(merged_rows),
        "canonical_count": len(set(canonical_map.values())),
        "outputs": {
            "book_canonical_map": str(canonical_map_path),
            "books_master_merged": str(merged_path),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cross-language canonical map and merged master books file.")
    parser.add_argument("--en-books", type=Path, default=EN_BOOKS_PATH)
    parser.add_argument("--zh-books", type=Path, default=ZH_BOOKS_PATH)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--fuzzy-threshold", type=float, default=0.93)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = build_canonical_map(
        en_books_path=args.en_books,
        zh_books_path=args.zh_books,
        out_dir=args.out_dir,
        fuzzy_threshold=args.fuzzy_threshold,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
