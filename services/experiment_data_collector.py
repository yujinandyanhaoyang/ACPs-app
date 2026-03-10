"""
实验数据采集模块 - Experimental Data Collection Module

用于在推荐系统实验过程中采集和记录各种性能指标数据。
支持可复现的数据采集和导出。

功能:
- 采集推荐结果指标 (Precision, Recall, NDCG, Diversity, Novelty)
- 记录系统性能指标 (延迟、吞吐量、错误率)
- 支持多种数据导出格式 (JSON, CSV)
- 实验元数据记录
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import uuid


@dataclass
class ExperimentMetadata:
    """实验元数据"""
    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    experiment_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    dataset: str = ""
    dataset_size: int = 0
    model_version: str = ""
    notes: str = ""
    environment: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationMetrics:
    """推荐指标"""
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    ndcg_at_k: float = 0.0
    diversity: float = 0.0
    novelty: float = 0.0
    mrr: float = 0.0  # Mean Reciprocal Rank
    hit_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    latency_ms: float = 0.0
    throughput_qps: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    api_calls: int = 0
    cache_hit_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentRun:
    """单次实验运行记录"""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    case_id: str = ""
    method: str = ""
    user_id: str = ""
    query: str = ""
    top_k: int = 10
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    ground_truth_ids: List[str] = field(default_factory=list)
    
    # 指标
    recommendation_metrics: RecommendationMetrics = field(default_factory=RecommendationMetrics)
    performance_metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    
    # 状态
    success: bool = True
    error_message: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    
    # 额外上下文
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['recommendation_metrics'] = self.recommendation_metrics.to_dict()
        data['performance_metrics'] = self.performance_metrics.to_dict()
        return data
    
    @property
    def duration_ms(self) -> float:
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time) * 1000
        return self.performance_metrics.latency_ms


@dataclass
class ExperimentBatch:
    """实验批次 - 包含多次运行"""
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    metadata: ExperimentMetadata = field(default_factory=ExperimentMetadata)
    runs: List[ExperimentRun] = field(default_factory=list)
    
    def add_run(self, run: ExperimentRun) -> None:
        self.runs.append(run)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取批次汇总统计"""
        if not self.runs:
            return {}
        
        successful_runs = [r for r in self.runs if r.success]
        
        # 按方法分组统计
        methods_summary = {}
        for run in successful_runs:
            method = run.method
            if method not in methods_summary:
                methods_summary[method] = {
                    'count': 0,
                    'precision_sum': 0.0,
                    'recall_sum': 0.0,
                    'ndcg_sum': 0.0,
                    'diversity_sum': 0.0,
                    'novelty_sum': 0.0,
                    'latency_sum': 0.0,
                }
            
            m = methods_summary[method]
            m['count'] += 1
            m['precision_sum'] += run.recommendation_metrics.precision_at_k
            m['recall_sum'] += run.recommendation_metrics.recall_at_k
            m['ndcg_sum'] += run.recommendation_metrics.ndcg_at_k
            m['diversity_sum'] += run.recommendation_metrics.diversity
            m['novelty_sum'] += run.recommendation_metrics.novelty
            m['latency_sum'] += run.duration_ms
        
        # 计算平均值
        for method, summary in methods_summary.items():
            count = summary['count']
            summary['precision_avg'] = summary['precision_sum'] / count
            summary['recall_avg'] = summary['recall_sum'] / count
            summary['ndcg_avg'] = summary['ndcg_sum'] / count
            summary['diversity_avg'] = summary['diversity_sum'] / count
            summary['novelty_avg'] = summary['novelty_sum'] / count
            summary['latency_avg'] = summary['latency_sum'] / count
        
        return {
            'total_runs': len(self.runs),
            'successful_runs': len(successful_runs),
            'success_rate': len(successful_runs) / len(self.runs) if self.runs else 0.0,
            'methods': methods_summary,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'batch_id': self.batch_id,
            'metadata': self.metadata.to_dict(),
            'summary': self.get_summary(),
            'runs': [run.to_dict() for run in self.runs],
        }


class ExperimentDataCollector:
    """实验数据采集器"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "experiments"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_batch: Optional[ExperimentBatch] = None
    
    def start_experiment(
        self,
        experiment_name: str = "",
        dataset: str = "",
        dataset_size: int = 0,
        model_version: str = "",
        notes: str = "",
    ) -> ExperimentBatch:
        """开始新的实验批次"""
        metadata = ExperimentMetadata(
            experiment_name=experiment_name,
            dataset=dataset,
            dataset_size=dataset_size,
            model_version=model_version,
            notes=notes,
        )
        self.current_batch = ExperimentBatch(metadata=metadata)
        return self.current_batch
    
    def record_run(
        self,
        case_id: str,
        method: str,
        recommendations: List[Dict[str, Any]],
        ground_truth_ids: List[str],
        user_id: str = "",
        query: str = "",
        top_k: int = 10,
        recommendation_metrics: Optional[RecommendationMetrics] = None,
        performance_metrics: Optional[PerformanceMetrics] = None,
        success: bool = True,
        error_message: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ExperimentRun:
        """记录单次实验运行"""
        if self.current_batch is None:
            raise RuntimeError("Must call start_experiment() first")
        
        run = ExperimentRun(
            case_id=case_id,
            method=method,
            user_id=user_id,
            query=query,
            top_k=top_k,
            recommendations=recommendations,
            ground_truth_ids=ground_truth_ids,
            recommendation_metrics=recommendation_metrics or RecommendationMetrics(),
            performance_metrics=performance_metrics or PerformanceMetrics(),
            success=success,
            error_message=error_message,
            context=context or {},
        )
        
        self.current_batch.add_run(run)
        return run
    
    def save_batch(self, filename: Optional[str] = None) -> Path:
        """保存当前实验批次到文件"""
        if self.current_batch is None:
            raise RuntimeError("No active experiment batch")
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"experiment_{self.current_batch.batch_id}_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(self.current_batch.to_dict(), f, indent=2, ensure_ascii=False)
        
        # 同时保存 CSV 格式（仅汇总数据）
        csv_path = output_path.with_suffix('.csv')
        self._save_runs_csv(self.current_batch.runs, csv_path)
        
        self.current_batch = None
        return output_path
    
    def _save_runs_csv(self, runs: Sequence[ExperimentRun], path: Path) -> None:
        """保存运行记录到 CSV"""
        if not runs:
            return
        
        fieldnames = [
            'run_id', 'case_id', 'method', 'user_id', 'query', 'top_k',
            'precision_at_k', 'recall_at_k', 'ndcg_at_k', 'diversity', 'novelty',
            'latency_ms', 'success', 'error_message',
        ]
        
        with path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for run in runs:
                row = {
                    'run_id': run.run_id,
                    'case_id': run.case_id,
                    'method': run.method,
                    'user_id': run.user_id,
                    'query': run.query[:100] if run.query else '',  # 截断长查询
                    'top_k': run.top_k,
                    'precision_at_k': run.recommendation_metrics.precision_at_k,
                    'recall_at_k': run.recommendation_metrics.recall_at_k,
                    'ndcg_at_k': run.recommendation_metrics.ndcg_at_k,
                    'diversity': run.recommendation_metrics.diversity,
                    'novelty': run.recommendation_metrics.novelty,
                    'latency_ms': run.duration_ms,
                    'success': run.success,
                    'error_message': run.error_message[:200] if run.error_message else '',
                }
                writer.writerow(row)
    
    def load_batch(self, path: Path) -> ExperimentBatch:
        """从文件加载实验批次"""
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        batch = ExperimentBatch(batch_id=data['batch_id'])
        batch.metadata = ExperimentMetadata(**data['metadata'])
        
        for run_data in data['runs']:
            rec_metrics = RecommendationMetrics(**run_data['recommendation_metrics'])
            perf_metrics = PerformanceMetrics(**run_data['performance_metrics'])
            
            run = ExperimentRun(
                run_id=run_data['run_id'],
                case_id=run_data['case_id'],
                method=run_data['method'],
                user_id=run_data.get('user_id', ''),
                query=run_data.get('query', ''),
                top_k=run_data.get('top_k', 10),
                recommendations=run_data.get('recommendations', []),
                ground_truth_ids=run_data.get('ground_truth_ids', []),
                recommendation_metrics=rec_metrics,
                performance_metrics=perf_metrics,
                success=run_data.get('success', True),
                error_message=run_data.get('error_message', ''),
                context=run_data.get('context', {}),
            )
            batch.add_run(run)
        
        return batch


def create_collector(output_dir: Optional[Path] = None) -> ExperimentDataCollector:
    """创建实验数据采集器实例"""
    return ExperimentDataCollector(output_dir)


if __name__ == "__main__":
    # 示例使用
    collector = create_collector()
    
    batch = collector.start_experiment(
        experiment_name="推荐系统基准测试",
        dataset="Goodreads+Amazon",
        dataset_size=1000000,
        model_version="v1.0.0",
        notes="首次完整实验",
    )
    
    # 模拟记录一次运行
    collector.record_run(
        case_id="case_001",
        method="acps_multi_agent",
        recommendations=[{"book_id": "b1", "score": 0.9}],
        ground_truth_ids=["b1", "b2"],
        user_id="user_123",
        query="推荐科幻小说",
        top_k=5,
        recommendation_metrics=RecommendationMetrics(
            precision_at_k=0.8,
            recall_at_k=0.6,
            ndcg_at_k=0.75,
            diversity=0.5,
            novelty=0.4,
        ),
        performance_metrics=PerformanceMetrics(
            latency_ms=1500.0,
            throughput_qps=10.0,
        ),
        success=True,
    )
    
    output_path = collector.save_batch()
    print(f"实验数据已保存到：{output_path}")
