#!/usr/bin/env python3
"""
实验数据采集与图表生成模块测试

验证新添加的实验数据采集和图表生成功能。
"""

import sys
from pathlib import Path

_CURRENT_DIR = Path(__file__).parent
_PROJECT_ROOT = _CURRENT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.experiment_data_collector import (
    create_collector,
    RecommendationMetrics,
    PerformanceMetrics,
)
from services.performance_chart_generator import (
    create_chart_generator,
    MethodComparison,
)


def test_data_collector():
    """测试数据采集器"""
    print("🔬 测试实验数据采集器...")
    
    collector = create_collector(output_dir=_PROJECT_ROOT / "experiments" / "test")
    
    batch = collector.start_experiment(
        experiment_name="测试实验",
        dataset="test_dataset",
        dataset_size=1000,
        model_version="v1.0.0-test",
        notes="模块测试",
    )
    
    # 记录几次运行
    for i in range(3):
        collector.record_run(
            case_id=f"test_case_{i:03d}",
            method="acps_multi_agent" if i % 2 == 0 else "traditional_hybrid",
            recommendations=[{"book_id": f"b{j}", "score": 0.9 - j * 0.1} for j in range(5)],
            ground_truth_ids=["b0", "b1"],
            user_id=f"user_{i}",
            query=f"测试查询 {i}",
            top_k=5,
            recommendation_metrics=RecommendationMetrics(
                precision_at_k=0.8 - i * 0.05,
                recall_at_k=0.7 - i * 0.05,
                ndcg_at_k=0.75 - i * 0.05,
                diversity=0.5 + i * 0.05,
                novelty=0.4 + i * 0.05,
            ),
            performance_metrics=PerformanceMetrics(
                latency_ms=1000.0 + i * 200,
            ),
            success=True,
        )
    
    output_path = collector.save_batch()
    print(f"  ✅ 数据已保存：{output_path}")
    
    # 验证文件存在
    assert output_path.exists(), "输出文件不存在"
    assert output_path.with_suffix('.csv').exists(), "CSV 文件不存在"
    
    print("  ✅ 数据采集器测试通过")
    return output_path


def test_chart_generator(experiment_path: Path):
    """测试图表生成器"""
    print("\n📊 测试图表生成器...")
    
    generator = create_chart_generator(output_dir=_PROJECT_ROOT / "experiments" / "test" / "charts")
    
    # 从实验数据生成图表
    charts = generator.generate_from_experiment_data(experiment_path)
    
    print(f"  ✅ 生成了 {len(charts)} 个图表:")
    for chart_type, path in charts.items():
        print(f"    - {chart_type}: {path}")
        assert path.exists(), f"图表文件不存在：{path}"
    
    # 测试直接生成
    methods = [
        MethodComparison("acps_multi_agent", 0.82, 0.75, 0.78, 0.65, 0.58, 1500.0),
        MethodComparison("traditional_hybrid", 0.78, 0.70, 0.72, 0.55, 0.50, 800.0),
        MethodComparison("multi_agent_proxy", 0.80, 0.73, 0.76, 0.60, 0.55, 1200.0),
    ]
    
    charts2 = generator.generate_all_charts(methods, "测试对比")
    print(f"  ✅ 直接生成 {len(charts2)} 个图表")
    
    print("  ✅ 图表生成器测试通过")


def test_metrics_classes():
    """测试指标类"""
    print("\n📐 测试指标类...")
    
    rec_metrics = RecommendationMetrics(
        precision_at_k=0.8,
        recall_at_k=0.7,
        ndcg_at_k=0.75,
        diversity=0.6,
        novelty=0.5,
    )
    
    metrics_dict = rec_metrics.to_dict()
    assert metrics_dict['precision_at_k'] == 0.8
    assert metrics_dict['recall_at_k'] == 0.7
    
    perf_metrics = PerformanceMetrics(
        latency_ms=1500.0,
        throughput_qps=10.0,
    )
    
    perf_dict = perf_metrics.to_dict()
    assert perf_dict['latency_ms'] == 1500.0
    
    print("  ✅ 指标类测试通过")


def main():
    print("=" * 60)
    print("实验数据采集与图表生成模块测试")
    print("=" * 60)
    
    try:
        # 测试指标类
        test_metrics_classes()
        
        # 测试数据采集器
        experiment_path = test_data_collector()
        
        # 测试图表生成器
        test_chart_generator(experiment_path)
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
