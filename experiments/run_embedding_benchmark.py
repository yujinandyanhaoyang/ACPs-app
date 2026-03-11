#!/usr/bin/env python3
"""
嵌入模型基准测试脚本

用法:
    python run_embedding_benchmark.py --model qwen3-vl-embedding --output results_qwen3vl.json
    python run_embedding_benchmark.py --model hash-fallback --output results_baseline.json
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# 添加项目路径
_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.model_backends import generate_text_embeddings
from services.book_retrieval import load_books, retrieve_books_by_query

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 测试查询（8 个标准场景）
TEST_QUERIES = [
    {"id": "S1", "type": "明确类型", "query": "科幻小说 太空歌剧"},
    {"id": "S2", "type": "模糊偏好", "query": "感人的书"},
    {"id": "S3", "type": "作者导向", "query": "刘慈欣 类似作品"},
    {"id": "S4", "type": "主题探索", "query": "人工智能 伦理"},
    {"id": "S5", "type": "跨类型", "query": "历史 悬疑"},
    {"id": "S6", "type": "冷启动", "query": "推理"},
    {"id": "S7", "type": "长尾查询", "query": "赛博朋克 日本 1980s"},
    {"id": "S8", "type": "多样性", "query": "推荐一些不同的书"}
]


def load_test_books() -> List[Dict[str, Any]]:
    """加载测试书籍池"""
    books_path = _PROJECT_ROOT / "data" / "processed" / "books_with_embeddings.json"
    
    if books_path.exists():
        with open(books_path, 'r', encoding='utf-8') as f:
            books = json.load(f)
        logger.info(f"✓ 加载书籍池：{len(books)} 册")
        return books
    
    # 如果书籍池不存在，使用备用方案
    logger.warning("⚠ 书籍池不存在，使用在线检索")
    return []


def run_benchmark(model_name: str, output_path: str, top_k: int = 10) -> Dict[str, Any]:
    """
    运行嵌入模型基准测试
    
    Args:
        model_name: 模型名称（hash-fallback 或 qwen3-vl-embedding）
        output_path: 输出文件路径
        top_k: 返回 Top-K 结果
    
    Returns:
        测试结果字典
    """
    logger.info(f"🧪 开始基准测试 - 模型：{model_name}")
    logger.info(f"📊 测试查询数量：{len(TEST_QUERIES)}")
    
    results = []
    total_latency = 0.0
    total_embedding_time = 0.0
    total_retrieval_time = 0.0
    api_calls = 0
    api_failures = 0
    
    for i, test_case in enumerate(TEST_QUERIES, 1):
        query_id = test_case["id"]
        query_type = test_case["type"]
        query = test_case["query"]
        
        logger.info(f"[{i}/{len(TEST_QUERIES)}] 测试 {query_id} ({query_type}): {query}")
        
        # 生成嵌入向量
        start_time = time.time()
        try:
            embeddings, meta = generate_text_embeddings([query], model_name=model_name)
            embed_time = time.time() - start_time
            total_embedding_time += embed_time
            
            if not embeddings:
                logger.warning(f"  ⚠ 嵌入生成失败，使用 fallback")
                api_failures += 1
                # 重试使用 hash-fallback
                embeddings, meta = generate_text_embeddings([query], model_name="hash-fallback")
                meta["fallback_used"] = True
            else:
                api_calls += 1
                
        except Exception as e:
            logger.error(f"  ✗ 嵌入生成错误：{e}")
            embed_time = time.time() - start_time
            embeddings = []
            meta = {"error": str(e), "fallback_used": True}
            api_failures += 1
        
        # 检索书籍
        start_time = time.time()
        try:
            recommendations = retrieve_books_by_query(query, top_k=top_k)
            retrieve_time = time.time() - start_time
            total_retrieval_time += retrieve_time
        except Exception as e:
            logger.error(f"  ✗ 检索错误：{e}")
            retrieve_time = time.time() - start_time
            recommendations = []
        
        total_time = embed_time + retrieve_time
        total_latency += total_time
        
        # 记录结果
        result = {
            "query_id": query_id,
            "query_type": query_type,
            "query": query,
            "embeddings": embeddings[0] if embeddings else [],
            "embedding_meta": meta,
            "recommendations": [
                {
                    "book_id": book.get("book_id", ""),
                    "title": book.get("title", ""),
                    "score": book.get("score", 0.0)
                }
                for book in recommendations[:top_k]
            ],
            "latency": {
                "embedding_sec": round(embed_time, 4),
                "retrieval_sec": round(retrieve_time, 4),
                "total_sec": round(total_time, 4)
            }
        }
        results.append(result)
        
        logger.info(f"  ✓ 完成 - 总延迟：{total_time:.3f}s, 推荐数：{len(recommendations)}")
    
    # 汇总统计
    summary = {
        "experiment_info": {
            "model": model_name,
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(TEST_QUERIES),
            "top_k": top_k
        },
        "performance": {
            "avg_latency_sec": round(total_latency / len(TEST_QUERIES), 4),
            "avg_embedding_time_sec": round(total_embedding_time / len(TEST_QUERIES), 4),
            "avg_retrieval_time_sec": round(total_retrieval_time / len(TEST_QUERIES), 4),
            "total_latency_sec": round(total_latency, 4)
        },
        "api_stats": {
            "total_calls": api_calls,
            "failures": api_failures,
            "failure_rate": round(api_failures / len(TEST_QUERIES) * 100, 2) if TEST_QUERIES else 0
        },
        "results": results
    }
    
    # 保存结果
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✓ 结果已保存到：{output_file}")
    logger.info(f"📊 平均延迟：{summary['performance']['avg_latency_sec']:.3f}s")
    logger.info(f"📊 API 调用成功率：{100 - summary['api_stats']['failure_rate']:.1f}%")
    
    return summary


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='嵌入模型基准测试')
    parser.add_argument(
        '--model',
        type=str,
        required=True,
        choices=['hash-fallback', 'qwen3-vl-embedding'],
        help='嵌入模型名称'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='输出文件路径'
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=10,
        help='返回 Top-K 结果（默认：10）'
    )
    
    args = parser.parse_args()
    
    # 检查 API Key（仅 qwen3-vl-embedding 需要）
    if args.model == 'qwen3-vl-embedding':
        api_key = os.getenv('DASHSCOPE_API_KEY')
        if not api_key:
            logger.warning("⚠ 未设置 DASHSCOPE_API_KEY，将自动降级到 hash-fallback")
            logger.warning("💡 请在 .env 文件中配置：DASHSCOPE_API_KEY=sk-xxx")
    
    # 运行基准测试
    summary = run_benchmark(args.model, args.output, args.top_k)
    
    # 打印汇总
    print("\n" + "="*60)
    print("📊 实验汇总")
    print("="*60)
    print(f"模型：{summary['experiment_info']['model']}")
    print(f"测试查询：{summary['experiment_info']['total_queries']}")
    print(f"平均延迟：{summary['performance']['avg_latency_sec']:.3f}s")
    print(f"API 成功率：{100 - summary['api_stats']['failure_rate']:.1f}%")
    print(f"输出文件：{summary['experiment_info']['timestamp']}")
    print("="*60)


if __name__ == "__main__":
    main()
