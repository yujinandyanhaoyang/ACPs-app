from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent

if str(_PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(_PROJECT_ROOT))

from services.model_backends import generate_text_embeddings


def _cosine(left: List[float], right: List[float]) -> float:
    size = min(len(left), len(right))
    if size <= 0:
        return 0.0
    dot = sum(left[i] * right[i] for i in range(size))
    ln = math.sqrt(sum(left[i] * left[i] for i in range(size)))
    rn = math.sqrt(sum(right[i] * right[i] for i in range(size)))
    if ln == 0.0 or rn == 0.0:
        return 0.0
    return dot / (ln * rn)


def _load_eval_data() -> Dict[str, Dict[str, object]]:
    zh_docs = {
        "zh_doc_1": "白鹿原 乡土文学 家族 历史 关中 社会变迁",
        "zh_doc_2": "中国 基层 治理 发展 报告 公共管理 政策",
        "zh_doc_3": "儿童 快乐 童话 故事 温暖 治愈",
        "zh_doc_4": "悬疑 恐怖 推理 小说 黑暗 氛围",
    }
    en_docs = {
        "en_doc_1": "rural literature family history social transformation",
        "en_doc_2": "grassroots governance public administration report",
        "en_doc_3": "happy fairy tales for children uplifting stories",
        "en_doc_4": "horror suspense thriller dark atmosphere",
    }

    zh_queries = [
        ("我想看陈忠实风格的乡土文学小说", "zh_doc_1"),
        ("中国基层治理发展报告", "zh_doc_2"),
        ("我喜欢快乐的儿童童话故事", "zh_doc_3"),
        ("推荐恐怖悬疑小说", "zh_doc_4"),
    ]
    en_queries = [
        ("recommend rural literature and family history", "en_doc_1"),
        ("books about grassroots governance and policy", "en_doc_2"),
        ("happy fairy tales for kids", "en_doc_3"),
        ("horror and suspense novels", "en_doc_4"),
    ]

    return {
        "zh": {"docs": zh_docs, "queries": zh_queries},
        "en": {"docs": en_docs, "queries": en_queries},
    }


def _evaluate_model(model_name: str) -> Dict[str, object]:
    data = _load_eval_data()
    result: Dict[str, object] = {"model": model_name, "languages": {}}

    for lang in ["zh", "en"]:
        docs = data[lang]["docs"]  # type: ignore[index]
        queries = data[lang]["queries"]  # type: ignore[index]

        doc_ids = list(docs.keys())
        doc_texts = [docs[doc_id] for doc_id in doc_ids]
        query_texts = [query for query, _ in queries]

        start = time.perf_counter()
        doc_vectors, doc_meta = generate_text_embeddings(doc_texts, model_name=model_name, fallback_dim=128)
        query_vectors, query_meta = generate_text_embeddings(query_texts, model_name=model_name, fallback_dim=128)
        elapsed_ms = (time.perf_counter() - start) * 1000

        top1 = 0
        mrr = 0.0
        for index, (query_text, expected_id) in enumerate(queries):
            qv = query_vectors[index] if index < len(query_vectors) else []
            scores: List[Tuple[str, float]] = []
            for didx, doc_id in enumerate(doc_ids):
                dv = doc_vectors[didx] if didx < len(doc_vectors) else []
                scores.append((doc_id, _cosine(qv, dv)))
            scores.sort(key=lambda item: item[1], reverse=True)
            ranked_ids = [item[0] for item in scores]
            if ranked_ids and ranked_ids[0] == expected_id:
                top1 += 1
            if expected_id in ranked_ids:
                rank = ranked_ids.index(expected_id) + 1
                mrr += 1.0 / rank

        q_count = max(1, len(queries))
        result["languages"][lang] = {
            "top1": round(top1 / q_count, 4),
            "mrr": round(mrr / q_count, 4),
            "latency_ms": round(elapsed_ms, 2),
            "backend": query_meta.get("backend") or doc_meta.get("backend"),
            "vector_dim": query_meta.get("vector_dim") or doc_meta.get("vector_dim"),
        }

    zh_top1 = float(result["languages"]["zh"]["top1"])  # type: ignore[index]
    en_top1 = float(result["languages"]["en"]["top1"])  # type: ignore[index]
    result["score"] = round(0.6 * zh_top1 + 0.4 * en_top1, 4)
    return result


def _select_recommendation(results: List[Dict[str, object]]) -> Dict[str, str]:
    if not results:
        return {
            "zh_default": "all-MiniLM-L6-v2",
            "en_default": "all-MiniLM-L6-v2",
            "mixed_default": "all-MiniLM-L6-v2",
        }

    zh_best = max(results, key=lambda row: float(row["languages"]["zh"]["top1"]))  # type: ignore[index]
    en_best = max(results, key=lambda row: float(row["languages"]["en"]["top1"]))  # type: ignore[index]
    overall_best = max(results, key=lambda row: float(row["score"]))

    return {
        "zh_default": str(zh_best["model"]),
        "en_default": str(en_best["model"]),
        "mixed_default": str(overall_best["model"]),
    }


def _write_report(payload: Dict[str, object]) -> None:
    json_path = _CURRENT_DIR / "phase0_embedding_benchmark_report.json"
    md_path = _CURRENT_DIR / "phase0_embedding_benchmark_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase 0.4 Embedding Benchmark Report",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Models: {', '.join(payload.get('models', []))}",
        "",
        "## Results",
    ]

    for row in payload.get("results", []):
        model = row.get("model")
        zh = row.get("languages", {}).get("zh", {})
        en = row.get("languages", {}).get("en", {})
        lines.extend(
            [
                f"### {model}",
                f"- zh: top1={zh.get('top1')}, mrr={zh.get('mrr')}, backend={zh.get('backend')}, latency_ms={zh.get('latency_ms')}",
                f"- en: top1={en.get('top1')}, mrr={en.get('mrr')}, backend={en.get('backend')}, latency_ms={en.get('latency_ms')}",
                f"- combined score={row.get('score')}",
                "",
            ]
        )

    rec = payload.get("recommendation", {})
    lines.extend(
        [
            "## Recommended Defaults",
            f"- zh_default: {rec.get('zh_default')}",
            f"- en_default: {rec.get('en_default')}",
            f"- mixed_default: {rec.get('mixed_default')}",
            "",
            "## Gate Check",
            f"- Non-regressive English vs baseline: {payload.get('gate_check', {}).get('english_non_regressive')}",
            f"- Improved Chinese relevance vs baseline: {payload.get('gate_check', {}).get('chinese_improved')}",
            f"- Gate passed: {payload.get('gate_check', {}).get('passed')}",
        ]
    )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    models_env = os.getenv("PHASE0_EMBED_MODELS", "")
    models = [item.strip() for item in models_env.split(",") if item.strip()] or [
        "all-MiniLM-L6-v2",
        "paraphrase-multilingual-MiniLM-L12-v2",
        "zh-char-ngram-v1",
    ]

    results = [_evaluate_model(model_name) for model_name in models]
    recommendation = _select_recommendation(results)

    baseline = next((row for row in results if row.get("model") == "all-MiniLM-L6-v2"), results[0])
    zh_baseline = float(baseline["languages"]["zh"]["top1"])  # type: ignore[index]
    en_baseline = float(baseline["languages"]["en"]["top1"])  # type: ignore[index]

    zh_selected = next(row for row in results if row.get("model") == recommendation["zh_default"])
    en_selected = next(row for row in results if row.get("model") == recommendation["en_default"])

    gate_check = {
        "english_non_regressive": float(en_selected["languages"]["en"]["top1"]) >= en_baseline,  # type: ignore[index]
        "chinese_improved": float(zh_selected["languages"]["zh"]["top1"]) >= zh_baseline,  # type: ignore[index]
    }
    gate_check["passed"] = gate_check["english_non_regressive"] and gate_check["chinese_improved"]

    payload: Dict[str, object] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": models,
        "results": results,
        "recommendation": recommendation,
        "gate_check": gate_check,
    }

    _write_report(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
