#!/usr/bin/env python3
"""
冒烟测试脚本

验证 ACPs-app 核心功能是否正常工作，然后才能部署到服务器执行正式实验。

测试内容：
1. 嵌入模型 API 调用
2. 数据加载
3. 消融实验（小规模）
4. 基线算法（小规模）
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any

# 添加项目路径
_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_CURRENT_DIR))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")


def test_embedding_api() -> Dict[str, Any]:
    """测试嵌入模型 API 调用"""
    print("\n" + "="*60)
    print("测试 1: 嵌入模型 API 调用")
    print("="*60)
    
    try:
        from services.model_backends import generate_text_embeddings
        
        start = time.time()
        embeddings, meta = generate_text_embeddings(['测试文本'], model_name='qwen3-vl-embedding')
        elapsed = time.time() - start
        
        if embeddings and len(embeddings) > 0:
            print(f"✅ 通过")
            print(f"   Backend: {meta.get('backend')}")
            print(f"   Model: {meta.get('model')}")
            print(f"   Vector dim: {meta.get('vector_dim')}")
            print(f"   延迟：{elapsed:.2f}s")
            return {"status": "pass", "backend": meta.get('backend'), "dim": meta.get('vector_dim')}
        else:
            print(f"❌ 失败：无嵌入向量返回")
            return {"status": "fail", "error": "no_embeddings"}
    except Exception as e:
        print(f"❌ 失败：{str(e)}")
        return {"status": "fail", "error": str(e)}


def test_data_loading() -> Dict[str, Any]:
    """测试数据加载"""
    print("\n" + "="*60)
    print("测试 2: 数据加载")
    print("="*60)
    
    try:
        from services.evaluation_metrics import load_test_interactions
        from services.book_retrieval import load_books
        
        # 测试交互数据加载
        start = time.time()
        interactions = load_test_interactions(n=100)
        interaction_time = time.time() - start
        
        # 测试书籍数据加载
        start = time.time()
        books = load_books()[:100]  # 只加载前 100 本
        books_time = time.time() - start
        
        if interactions and len(interactions) > 0:
            print(f"✅ 通过")
            print(f"   交互数据：{len(interactions)} 条 ({interaction_time:.2f}s)")
            print(f"   书籍数据：{len(books)} 册 ({books_time:.2f}s)")
            print(f"   示例交互：{interactions[0]}")
            return {"status": "pass", "interactions": len(interactions), "books": len(books)}
        else:
            print(f"❌ 失败：无数据加载")
            return {"status": "fail", "error": "no_data"}
    except Exception as e:
        print(f"❌ 失败：{str(e)}")
        return {"status": "fail", "error": str(e)}


def test_ablation_small_scale() -> Dict[str, Any]:
    """小规模消融实验测试"""
    print("\n" + "="*60)
    print("测试 3: 消融实验（小规模，n_users=3）")
    print("="*60)
    
    try:
        import asyncio
        from scripts.run_ablation import run_ablation
        
        async def run():
            start = time.time()
            result = await run_ablation(n_users=3, top_k=5, min_history=1, min_ground_truth=1)
            elapsed = time.time() - start
            return result, elapsed
        
        result, elapsed = asyncio.run(run())
        
        # 检查关键指标
        full_result = result.get('full', {})
        evaluated_users = full_result.get('evaluated_users', 0)
        
        if evaluated_users > 0:
            print(f"✅ 通过")
            print(f"   评估用户数：{evaluated_users}")
            print(f"   执行时间：{elapsed:.2f}s")
            print(f"   NDCG@5: {full_result.get('ndcg_at_5', 0):.4f}")
            return {"status": "pass", "evaluated_users": evaluated_users, "ndcg": full_result.get('ndcg_at_5', 0)}
        else:
            print(f"❌ 失败：evaluated_users = 0")
            return {"status": "fail", "error": "evaluated_users_is_zero"}
    except Exception as e:
        print(f"❌ 失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "fail", "error": str(e)}


def test_baseline_algorithms() -> Dict[str, Any]:
    """基线算法测试"""
    print("\n" + "="*60)
    print("测试 4: 基线算法（小规模）")
    print("="*60)
    
    try:
        from services.baseline_recommenders import ItemKNN, HybridRecommender
        from services.data_paths import get_processed_data_path
        
        data_root = get_processed_data_root()
        interactions_path = data_root / "merged" / "interactions_merged.jsonl"
        books_path = data_root / "merged" / "books_master_merged.jsonl"
        
        results = {}
        
        # Item-KNN（只训练前 1000 条交互）
        print("   测试 Item-KNN...")
        start = time.time()
        knn = ItemKNN(k=10)
        # 简化测试：只加载少量数据
        knn.user_history = {"gr_u_2": ["gr_26", "gr_33"]}
        knn.item_similarity = {"gr_26": {"gr_3": 0.5}, "gr_33": {"gr_3": 0.3}}
        recs = knn.predict("gr_u_2", top_k=5)
        knn_time = time.time() - start
        results['item_knn'] = {"status": "pass" if recs else "fail", "time": knn_time}
        print(f"      Item-KNN: {'✅' if recs else '❌'} ({knn_time:.2f}s, {len(recs)} 推荐)")
        
        # Hybrid
        print("   测试 Hybrid...")
        start = time.time()
        hybrid = HybridRecommender(cf_weight=0.6, content_weight=0.4)
        hybrid.user_history = {"gr_u_2": ["gr_26", "gr_33"]}
        hybrid.item_content = {
            "gr_26": {"genres": {"fiction"}, "author": "Author A"},
            "gr_3": {"genres": {"fiction"}, "author": "Author B"},
        }
        recs = hybrid.predict("gr_u_2", top_k=5)
        hybrid_time = time.time() - start
        results['hybrid'] = {"status": "pass" if recs else "fail", "time": hybrid_time}
        print(f"      Hybrid: {'✅' if recs else '❌'} ({hybrid_time:.2f}s, {len(recs)} 推荐)")
        
        all_pass = all(r['status'] == 'pass' for r in results.values())
        if all_pass:
            print(f"✅ 通过")
            return {"status": "pass", "results": results}
        else:
            print(f"❌ 失败：部分算法未通过")
            return {"status": "fail", "results": results}
    except Exception as e:
        print(f"❌ 失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "fail", "error": str(e)}


def main():
    """执行所有冒烟测试"""
    print("\n" + "="*80)
    print("🔥 ACPs-app 冒烟测试")
    print("="*80)
    print(f"数据集路径：{os.getenv('DATASET_ROOT', '未设置')}")
    print(f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = {
        "embedding_api": test_embedding_api(),
        "data_loading": test_data_loading(),
        "ablation_small": test_ablation_small_scale(),
        "baseline_algorithms": test_baseline_algorithms(),
    }
    
    # 汇总
    print("\n" + "="*80)
    print("📊 测试结果汇总")
    print("="*80)
    
    passed = sum(1 for r in results.values() if r.get('status') == 'pass')
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅" if result.get('status') == 'pass' else "❌"
        print(f"{status} {test_name}: {result.get('status', 'unknown')}")
    
    print(f"\n总计：{passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！可以部署到服务器执行正式实验")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请修复后再部署")
        return 1


if __name__ == "__main__":
    sys.exit(main())
