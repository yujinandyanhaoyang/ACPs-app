#!/usr/bin/env python3
"""
实验数据采集与图表生成脚本

整合实验数据采集和性能对比图表生成功能。
支持从现有 benchmark 结果生成可视化报告。

使用方法:
    # 运行完整实验并生成图表
    python scripts/run_experiment_and_generate_charts.py
    
    # 从现有实验数据生成图表
    python scripts/run_experiment_and_generate_charts.py --from-file experiments/experiment_xxx.json
    
    # 指定输出目录
    python scripts/run_experiment_and_generate_charts.py --output-dir ./results
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到路径
_CURRENT_DIR = Path(__file__).parent
_PROJECT_ROOT = _CURRENT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.experiment_data_collector import (
    create_collector,
    ExperimentDataCollector,
    RecommendationMetrics,
    PerformanceMetrics,
)
from services.performance_chart_generator import (
    create_chart_generator,
    PerformanceChartGenerator,
    MethodComparison,
)
from services.evaluation_metrics import compute_recommendation_metrics
from services.phase4_benchmark import evaluate_method_case


async def run_experiment_with_collection(
    cases: List[Dict[str, Any]],
    methods: Dict[str, Any],
    collector: ExperimentDataCollector,
    experiment_name: str = "推荐系统实验",
    dataset_info: str = "merged",
) -> None:
    """运行实验并采集数据"""
    from services.baseline_rankers import traditional_hybrid_rank, multi_agent_sequential_rank, llm_only_rank
    from reading_concierge.reading_concierge import handle_recommendation_request
    
    batch = collector.start_experiment(
        experiment_name=experiment_name,
        dataset=dataset_info,
        notes="自动化实验采集",
    )
    
    # 方法映射
    method_funcs = {
        "acps_multi_agent": handle_recommendation_request,
        "traditional_hybrid": traditional_hybrid_rank,
        "multi_agent_proxy": multi_agent_sequential_rank,
        "llm_only": llm_only_rank,
    }
    
    total_runs = len(cases) * len(method_funcs)
    current_run = 0
    
    for case in cases:
        for method_name, method_func in method_funcs.items():
            current_run += 1
            print(f"运行 [{current_run}/{total_runs}]: {method_name} - {case.get('case_id', 'unknown')}")
            
            try:
                import time
                start_time = time.time()
                
                # 运行方法
                if method_name == "acps_multi_agent":
                    # ACPS 多智能体方法
                    result = await method_func(case)
                    recommendations = result.get('recommendations', [])
                else:
                    # 基线方法
                    result = method_func(case)
                    recommendations = result if isinstance(result, list) else result.get('recommendations', [])
                
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000
                
                # 计算指标
                ground_truth_ids = case.get('constraints', {}).get('ground_truth_ids', [])
                metrics_dict = evaluate_method_case(recommendations, ground_truth_ids, top_k=5)
                
                rec_metrics = RecommendationMetrics(
                    precision_at_k=metrics_dict.get('precision_at_k', 0.0),
                    recall_at_k=metrics_dict.get('recall_at_k', 0.0),
                    ndcg_at_k=metrics_dict.get('ndcg_at_k', 0.0),
                    diversity=metrics_dict.get('diversity', 0.0),
                    novelty=metrics_dict.get('novelty', 0.0),
                )
                
                perf_metrics = PerformanceMetrics(
                    latency_ms=latency_ms,
                )
                
                # 记录运行
                collector.record_run(
                    case_id=case.get('case_id', 'unknown'),
                    method=method_name,
                    recommendations=recommendations,
                    ground_truth_ids=ground_truth_ids,
                    query=case.get('query', ''),
                    top_k=5,
                    recommendation_metrics=rec_metrics,
                    performance_metrics=perf_metrics,
                    success=True,
                )
                
            except Exception as e:
                # 记录失败
                collector.record_run(
                    case_id=case.get('case_id', 'unknown'),
                    method=method_name,
                    recommendations=[],
                    ground_truth_ids=case.get('constraints', {}).get('ground_truth_ids', []),
                    query=case.get('query', ''),
                    success=False,
                    error_message=str(e),
                )
                print(f"  ❌ 错误：{e}")
    
    # 保存数据
    output_path = collector.save_batch()
    print(f"\n✅ 实验数据已保存到：{output_path}")


def generate_charts_from_experiment(experiment_path: Path, output_dir: Optional[Path] = None) -> Dict[str, Path]:
    """从实验数据文件生成图表"""
    generator = create_chart_generator(output_dir)
    return generator.generate_from_experiment_data(experiment_path)


def generate_charts_from_summary(
    summary_data: Dict[str, Any],
    experiment_name: str = "性能对比",
    output_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    """从汇总数据生成图表"""
    generator = create_chart_generator(output_dir)
    
    methods = []
    methods_data = summary_data.get('methods', {})
    
    for method_name, stats in methods_data.items():
        methods.append(MethodComparison(
            method_name=method_name,
            precision_at_k=stats.get('precision_avg', 0.0),
            recall_at_k=stats.get('recall_avg', 0.0),
            ndcg_at_k=stats.get('ndcg_avg', 0.0),
            diversity=stats.get('diversity_avg', 0.5),
            novelty=stats.get('novelty_avg', 0.5),
            latency_ms=stats.get('latency_avg', 0.0),
        ))
    
    return generator.generate_all_charts(methods, experiment_name)


def load_benchmark_cases(cases_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """加载 benchmark 测试用例"""
    if cases_path is None:
        cases_path = _CURRENT_DIR / "phase4_cases.json"
    
    if not cases_path.exists():
        print(f"⚠️  测试用例文件不存在：{cases_path}")
        print("使用默认测试用例...")
        return create_default_cases()
    
    with cases_path.open('r', encoding='utf-8') as f:
        return json.load(f)


def create_default_cases() -> List[Dict[str, Any]]:
    """创建默认测试用例"""
    return [
        {
            "case_id": "case_001",
            "query": "Recommend science fiction books similar to Dune.",
            "user_profile": {"preferred_language": "en"},
            "history": [
                {"title": "Dune", "genres": ["science_fiction"], "rating": 5, "language": "en"},
            ],
            "books": [
                {"book_id": "b1", "title": "Foundation", "description": "Civilization science fiction.", "genres": ["science_fiction"]},
                {"book_id": "b2", "title": "Hyperion", "description": "Layered speculative narrative.", "genres": ["science_fiction"]},
                {"book_id": "b3", "title": "Neuromancer", "description": "Cyberpunk classic.", "genres": ["science_fiction", "cyberpunk"]},
            ],
            "constraints": {
                "scenario": "warm",
                "top_k": 5,
                "ground_truth_ids": ["b1", "b2"],
            },
        },
        {
            "case_id": "case_002",
            "query": "Recommend mystery novels.",
            "user_profile": {"preferred_language": "en"},
            "history": [],
            "books": [
                {"book_id": "b4", "title": "Gone Girl", "description": "Psychological thriller.", "genres": ["mystery", "thriller"]},
                {"book_id": "b5", "title": "The Da Vinci Code", "description": "Historical mystery.", "genres": ["mystery", "historical"]},
            ],
            "constraints": {
                "scenario": "cold",
                "top_k": 5,
                "ground_truth_ids": ["b4"],
            },
        },
    ]


def main():
    parser = argparse.ArgumentParser(description="实验数据采集与图表生成")
    parser.add_argument(
        "--from-file",
        type=Path,
        help="从现有实验数据文件生成图表",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        help="测试用例文件路径",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="输出目录",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="推荐系统性能实验",
        help="实验名称",
    )
    parser.add_argument(
        "--skip-experiment",
        action="store_true",
        help="跳过实验运行，仅生成图表",
    )
    
    args = parser.parse_args()
    
    output_dir = args.output_dir or (_PROJECT_ROOT / "experiments")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果指定了现有文件，直接生成图表
    if args.from_file:
        print(f"📊 从文件生成图表：{args.from_file}")
        charts = generate_charts_from_experiment(args.from_file, output_dir / "charts")
        
        print("\n✅ 生成的图表:")
        for chart_type, path in charts.items():
            print(f"  - {chart_type}: {path}")
        return
    
    # 运行实验
    if not args.skip_experiment:
        print("🔬 开始运行实验...")
        cases = load_benchmark_cases(args.cases)
        print(f"加载了 {len(cases)} 个测试用例")
        
        collector = create_collector(output_dir)
        
        # 运行实验
        asyncio.run(run_experiment_with_collection(
            cases=cases,
            methods={},
            collector=collector,
            experiment_name=args.experiment_name,
        ))
    
    # 生成图表
    print("\n📊 生成性能对比图表...")
    
    # 查找最新的实验文件
    experiment_files = list(output_dir.glob("experiment_*.json"))
    if experiment_files:
        latest_file = max(experiment_files, key=lambda p: p.stat().st_mtime)
        print(f"使用实验文件：{latest_file}")
        
        charts = generate_charts_from_experiment(latest_file, output_dir / "charts")
        
        print("\n✅ 生成的图表:")
        for chart_type, path in charts.items():
            print(f"  - {chart_type}: {path}")
    else:
        print("⚠️  未找到实验数据文件")


if __name__ == "__main__":
    main()
