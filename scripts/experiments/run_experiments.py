"""批量运行消融实验，对所有 (user, query, variant) 组合发送请求并保存原始结果。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from config import API_BASE, USER_API, TEST_USERS, TEST_QUERIES, VARIANTS, REQUEST_TIMEOUT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parents[2] / "artifacts" / "experiments" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def call_api(
    session: aiohttp.ClientSession,
    user_id: str,
    query: str,
    variant: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "query": query,
        "constraints": variant["constraints"],
    }
    t0 = time.perf_counter()
    try:
        async with session.post(
            USER_API,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            elapsed = time.perf_counter() - t0
            body = await resp.json()
            return {
                "variant_id": variant["id"],
                "variant_name": variant["name"],
                "user_id": user_id,
                "query": query,
                "status_code": resp.status,
                "elapsed_s": round(elapsed, 3),
                "response": body,
                "error": None,
            }
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        log.warning("Request failed user=%s variant=%s: %s", user_id, variant["id"], exc)
        return {
            "variant_id": variant["id"],
            "variant_name": variant["name"],
            "user_id": user_id,
            "query": query,
            "status_code": None,
            "elapsed_s": round(elapsed, 3),
            "response": None,
            "error": str(exc),
        }


async def run_variant(variant: Dict[str, Any], concurrency: int = 3) -> List[Dict[str, Any]]:
    """对单个变体运行所有 (user × query) 组合，限制并发避免打爆 LLM 限速。"""
    tasks = [
        (user_id, query)
        for user_id in TEST_USERS
        for query in TEST_QUERIES
    ]
    results: List[Dict[str, Any]] = []
    sem = asyncio.Semaphore(concurrency)

    async def bounded(user_id: str, query: str) -> None:
        async with sem:
            r = await call_api(session, user_id, query, variant)
            results.append(r)
            status = "OK" if r["error"] is None else "ERR"
            log.info(
                "[%s] %s variant=%s user=%s q='%s' → %s (%.1fs)",
                status, datetime.now().strftime("%H:%M:%S"),
                variant["id"], user_id, query[:30], r["status_code"], r["elapsed_s"],
            )

    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(*[bounded(u, q) for u, q in tasks])

    return results


async def main() -> None:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results: List[Dict[str, Any]] = []

    log.info("=== ACPs Ablation Experiment Run: %s ===", run_id)
    log.info("Variants: %s", [v["id"] for v in VARIANTS])
    log.info("Users: %d  Queries: %d  Variants: %d  Total calls: %d",
             len(TEST_USERS), len(TEST_QUERIES), len(VARIANTS),
             len(TEST_USERS) * len(TEST_QUERIES) * len(VARIANTS))

    for variant in VARIANTS:
        log.info("--- Starting variant %s: %s ---", variant["id"], variant["name"])
        results = await run_variant(variant, concurrency=2)
        all_results.extend(results)
        # 每个变体单独保存，防止中途崩溃丢失数据
        variant_file = OUTPUT_DIR / f"{run_id}_{variant['id']}.jsonl"
        with open(variant_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log.info("Saved %d records → %s", len(results), variant_file)

    # 汇总文件
    summary_file = OUTPUT_DIR / f"{run_id}_all.jsonl"
    with open(summary_file, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = sum(1 for r in all_results if r["error"] is None)
    log.info("=== Done. %d/%d successful. Summary → %s ===",
             success, len(all_results), summary_file)


if __name__ == "__main__":
    asyncio.run(main())
