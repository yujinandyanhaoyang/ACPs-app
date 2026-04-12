from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.enrich_utils import (
    OpenAICompatibleClient,
    clean_text,
    clean_enriched_description,
    compact_jsonl_row,
    build_description_messages,
    has_valid_description,
    is_fatal_provider_error,
    iter_amazon_records,
    iter_goodreads_records,
    load_config,
    record_key,
    resolve_input_paths,
    UnifiedBookRecord,
)


def _load_resume_keys(path: Path) -> Set[Tuple[str, str]]:
    keys: Set[Tuple[str, str]] = set()
    if not path.exists():
        return keys

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            source = clean_text(row.get("source"))
            book_id = clean_text(row.get("book_id"))
            if source and book_id:
                keys.add((source, book_id))
    return keys


def _flatten_records(goodreads_path: Path, amazon_paths: Sequence[Path]) -> Iterable[UnifiedBookRecord]:
    yield from iter_goodreads_records(goodreads_path)
    for path in amazon_paths:
        yield from iter_amazon_records(path)


def _should_enrich(record: UnifiedBookRecord) -> bool:
    return bool(record.title) and not has_valid_description(record.description)


def _is_kept_amazon_record(record: UnifiedBookRecord) -> bool:
    return bool(record.title.strip()) and bool(record.author.strip()) and bool(record.genres)


def _tokens_estimate(chars: int) -> int:
    return max(0, round(chars / 4))


@asynccontextmanager
async def _null_client():
    yield None


async def _enrich_one(
    client: OpenAICompatibleClient,
    record: UnifiedBookRecord,
) -> Tuple[Dict[str, Any], str, int, int, Optional[str]]:
    messages = build_description_messages(record.title, record.author, record.genres)
    prompt_chars = sum(len(message.get("content", "")) for message in messages)
    response_text, error = await client.chat_completion(messages)
    if error:
        return compact_jsonl_row(record, "", "empty"), "failed", prompt_chars, 0, error

    response_text = clean_enriched_description(response_text or "")
    if len(response_text) < 10:
        return compact_jsonl_row(record, "", "empty"), "failed", prompt_chars, 0, "response shorter than 10 chars"
    return compact_jsonl_row(record, response_text, "llm_generated"), "enriched", prompt_chars, len(response_text), None


def _write_report(report_path: Path, summary: Dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Book Enrichment Report",
        "",
        f"- Output file: `{summary['output_path']}`",
        f"- Total input records: **{summary['seen']:,}**",
        f"- Goodreads records written: **{summary['goodreads_written']:,}**",
        f"- Amazon original kept: **{summary['amazon_original_kept']:,}**",
        f"- Amazon enriched by LLM: **{summary['amazon_enriched']:,}**",
        f"- Amazon dropped incomplete: **{summary['amazon_dropped_incomplete']:,}**",
        f"- LLM failed: **{summary['llm_failed']:,}**",
        f"- Total records in output: **{summary['written']:,}**",
        f"- Elapsed: **{summary['elapsed_total']:.1f}s**",
        f"- Stopped early: **{'yes' if summary['stop_requested'] else 'no'}**",
    ]
    if summary.get("stop_reason"):
        lines.append(f"- Stop reason: {summary['stop_reason']}")
    lines.extend(
        [
            "",
            "## Token Estimate",
            "",
            f"- Input tokens approx: **{_tokens_estimate(summary['prompt_chars_total']):,}**",
            f"- Output tokens approx: **{_tokens_estimate(summary['response_chars_total']):,}**",
            "",
            "## Sample Enrichments",
            "",
        ]
    )
    samples = summary.get("enriched_samples") or []
    if samples:
        for sample in samples[:5]:
            lines.append(f"### {sample.get('book_id', '')} | {sample.get('title', '')}")
            lines.append("")
            lines.append(sample.get("description", ""))
            lines.append("")
    else:
        lines.append("_No enriched samples captured._")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


async def _run_pipeline(
    *,
    config,
    goodreads_path: Path,
    amazon_paths: Sequence[Path],
    limit: Optional[int],
    max_concurrency: int,
    request_delay: float,
    max_requests_per_minute: Optional[int],
    resume: bool,
    dry_run: bool,
    report_path: Optional[Path],
) -> Dict[str, Any]:
    output_path: Path = config.output_path
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    resume_keys = _load_resume_keys(output_path) if resume else set()
    seen_keys: Set[Tuple[str, str]] = set(resume_keys)
    if resume and output_path.exists():
        print(f"[resume] loaded {len(resume_keys):,} completed book_id+source pairs from {output_path}")

    seen = 0
    kept = 0
    dropped_no_title = 0
    dropped_unusable = 0
    dropped_duplicate = 0
    resume_skipped = 0
    skipped_original = 0
    needs_enrichment = 0
    llm_enriched = 0
    llm_failed = 0
    goodreads_written = 0
    amazon_original_kept = 0
    amazon_enriched = 0
    amazon_dropped_incomplete = 0
    enriched_samples: List[Dict[str, Any]] = []
    prompt_chars_total = 0
    response_chars_total = 0
    written = 0
    last_flush_written = 0
    stop_requested = False
    stop_reason = ""
    started = time.perf_counter()

    output_file = None
    if not dry_run:
        mode = "a" if resume and output_path.exists() else "w"
        output_file = output_path.open(mode, encoding="utf-8")

    pending: Set[asyncio.Task[Tuple[Dict[str, Any], str, int, int, Optional[str]]]] = set()

    async def drain_pending(force: bool = False) -> None:
        nonlocal pending, written, last_flush_written, llm_enriched, llm_failed, amazon_enriched, prompt_chars_total, response_chars_total, stop_requested, stop_reason
        if not pending:
            return
        if not force and len(pending) < max_concurrency * 2:
            return
        done, pending_set = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        pending = pending_set
        for task in done:
            row, status, prompt_chars, response_chars, error = task.result()
            prompt_chars_total += prompt_chars
            response_chars_total += response_chars
            if status == "enriched":
                llm_enriched += 1
                if row.get("source") == "amazon":
                    amazon_enriched += 1
                if len(enriched_samples) < 5:
                    enriched_samples.append(row)
                if not dry_run and output_file is not None:
                    output_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                    written += 1
                    if written - last_flush_written >= 500:
                        output_file.flush()
                        os.fsync(output_file.fileno())
                        last_flush_written = written
            else:
                llm_failed += 1
                if error:
                    print(f"[llm-failed] book_id={row.get('book_id')} source={row.get('source')} error={error}")
                    if is_fatal_provider_error(error):
                        stop_requested = True
                        stop_reason = error

        if stop_requested:
            for task in pending:
                task.cancel()
            pending.clear()

    client_manager = (
        _null_client()
        if dry_run
        else OpenAICompatibleClient(
            base_url=config.augmentation_base_url,
            api_key=config.augmentation_api_key,
            model=config.augmentation_model,
            min_request_interval=request_delay,
            max_requests_per_minute=max_requests_per_minute,
        )
    )

    async with client_manager as client:
        for record in _flatten_records(goodreads_path, amazon_paths):
            if stop_requested:
                break
            if limit is not None and seen >= limit:
                break
            seen += 1

            if not record.title.strip():
                if not record.author.strip() and not record.genres:
                    dropped_unusable += 1
                else:
                    dropped_no_title += 1
                continue

            key = record_key(record)
            if key in seen_keys:
                if key in resume_keys:
                    resume_skipped += 1
                else:
                    dropped_duplicate += 1
                continue
            seen_keys.add(key)

            if record.source == "amazon" and not _is_kept_amazon_record(record):
                amazon_dropped_incomplete += 1
                continue

            kept += 1

            if has_valid_description(record.description):
                skipped_original += 1
                output_row = compact_jsonl_row(record, clean_text(record.description), "original")
                if not dry_run and output_file is not None:
                    output_file.write(json.dumps(output_row, ensure_ascii=False) + "\n")
                    written += 1
                    if record.source == "goodreads":
                        goodreads_written += 1
                    if record.source == "amazon":
                        amazon_original_kept += 1
                    if written - last_flush_written >= 500:
                        output_file.flush()
                        os.fsync(output_file.fileno())
                        last_flush_written = written
            elif _should_enrich(record):
                needs_enrichment += 1
                if dry_run:
                    continue
                assert client is not None
                task = asyncio.create_task(_enrich_one(client, record))
                pending.add(task)
                await drain_pending(force=False)
                if stop_requested:
                    break
            else:
                # No useful title/description path to enrich. Keep an empty record.
                skipped_original += 1
                output_row = compact_jsonl_row(record, "", "empty")
                if not dry_run and output_file is not None:
                    output_file.write(json.dumps(output_row, ensure_ascii=False) + "\n")
                    written += 1
                    if record.source == "goodreads":
                        goodreads_written += 1
                    if written - last_flush_written >= 500:
                        output_file.flush()
                        os.fsync(output_file.fileno())
                        last_flush_written = written

            if seen % 1000 == 0:
                elapsed = time.perf_counter() - started
                print(
                    f"[progress] seen={seen} kept={kept} skipped={skipped_original} "
                    f"enriched={llm_enriched} failed={llm_failed} elapsed={elapsed:.1f}s"
                )

            if stop_requested:
                break

        await drain_pending(force=True)
        while pending:
            await drain_pending(force=True)

    if output_file is not None:
        output_file.flush()
        os.fsync(output_file.fileno())
        output_file.close()

    elapsed_total = time.perf_counter() - started
    return {
        "seen": seen,
        "kept": kept,
        "dropped_no_title": dropped_no_title,
        "dropped_unusable": dropped_unusable,
        "dropped_duplicate": dropped_duplicate,
        "resume_skipped": resume_skipped,
        "skipped_original": skipped_original,
        "needs_enrichment": needs_enrichment,
        "llm_enriched": llm_enriched,
        "llm_failed": llm_failed,
        "amazon_original_kept": amazon_original_kept,
        "amazon_enriched": amazon_enriched,
        "amazon_dropped_incomplete": amazon_dropped_incomplete,
        "goodreads_written": goodreads_written,
        "enriched_samples": enriched_samples,
        "prompt_chars_total": prompt_chars_total,
        "response_chars_total": response_chars_total,
        "stop_requested": stop_requested,
        "stop_reason": stop_reason,
        "written": written,
        "elapsed_total": elapsed_total,
        "output_path": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline book enrichment and preprocessing pipeline.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N input records total.")
    parser.add_argument("--max-concurrency", type=int, default=8, help="Max parallel LLM requests.")
    parser.add_argument("--request-delay", type=float, default=0.0, help="Minimum seconds between LLM requests globally.")
    parser.add_argument("--max-requests-per-minute", type=int, default=0, help="Global cap on LLM requests per minute; 0 disables.")
    parser.add_argument("--resume", action="store_true", help="Resume from an existing output file.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and filter input without LLM calls or output writes.")
    args = parser.parse_args()

    config = load_config()
    goodreads_path, amazon_paths = resolve_input_paths(config.raw_root)

    summary = asyncio.run(
        _run_pipeline(
            config=config,
            goodreads_path=goodreads_path,
            amazon_paths=amazon_paths,
            limit=args.limit,
            max_concurrency=max(1, args.max_concurrency),
            request_delay=max(0.0, args.request_delay),
            max_requests_per_minute=(args.max_requests_per_minute or None),
            resume=args.resume,
            dry_run=args.dry_run,
            report_path=None,
        )
    )

    print("=== Enrichment Complete ===")
    print(f"Total input records : {summary['seen']:,}")
    print(f"Dropped (unusable)  : {summary['dropped_unusable']:,}")
    print(f"Dropped (no title)  : {summary['dropped_no_title']:,}")
    print(f"Dropped (duplicate) : {summary['dropped_duplicate']:,}")
    print(f"Kept                : {summary['kept']:,}")
    print(f"Already had description (original) : {summary['skipped_original']:,}")
    print(f"Needs enrichment    : {summary['needs_enrichment']:,}")
    print(f"LLM enriched        : {summary['llm_enriched']:,}")
    print(f"LLM failed          : {summary['llm_failed']:,}")
    print(f"Already in output   : {summary['resume_skipped']:,}")
    if args.dry_run:
        print(f"Output planned to   : {summary['output_path']} (dry-run, not written)")
    else:
        print(f"Output written to   : {summary['output_path']}")
    approx_input_tokens = _tokens_estimate(summary["prompt_chars_total"])
    approx_output_tokens = _tokens_estimate(summary["response_chars_total"])
    print(
        "Estimated tokens used (approx): "
        f"input ~{approx_input_tokens / 1_000_000:.2f}M, "
        f"output ~{approx_output_tokens / 1_000_000:.2f}M"
    )
    print(f"Elapsed             : {summary['elapsed_total']:.1f}s")
    if summary["stop_requested"]:
        print(f"Stopped early       : yes ({summary['stop_reason']})")
    else:
        print("Stopped early       : no")
    print("=== Final Dataset Summary ===")
    print(f"Goodreads records written   : {summary['goodreads_written']:,}")
    print(f"Amazon original (kept)      : {summary['amazon_original_kept']:,}")
    print(f"Amazon enriched by LLM      : {summary['amazon_enriched']:,}")
    print(f"Amazon dropped (incomplete) : {summary['amazon_dropped_incomplete']:,}")
    print(f"Amazon LLM failed           : {summary['llm_failed']:,}")
    print(f"Total records in output     : {summary['written']:,}")
    print(f"Output file                 : {summary['output_path']}")

    if summary["enriched_samples"]:
        print("=== Sample Enrichments ===")
        for sample in summary["enriched_samples"][:5]:
            print(f"- {sample.get('book_id')} | {sample.get('title')}")
            print(f"  {sample.get('description')}")

    report_path = Path(summary["output_path"]).with_suffix(".report.md")
    _write_report(report_path, summary)
    print(f"Report written to      : {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
