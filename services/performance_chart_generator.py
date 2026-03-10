"""
性能对比图表生成模块 - Performance Comparison Chart Generator

用于生成推荐系统性能对比的可视化图表。
支持多种图表类型和导出格式。

功能:
- 生成方法间性能对比图 (柱状图、雷达图)
- 生成指标趋势图 (折线图)
- 生成热力图 (相关性分析)
- 支持导出为 PNG、SVG、PDF 格式
- 支持导出为交互式 HTML (Plotly)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from dataclasses import dataclass

# 尝试导入 matplotlib，如果不可用则使用备用方案
try:
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

# 尝试导入 plotly 用于交互式图表
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None


@dataclass
class MethodComparison:
    """方法对比数据"""
    method_name: str
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    ndcg_at_k: float = 0.0
    diversity: float = 0.0
    novelty: float = 0.0
    latency_ms: float = 0.0
    throughput_qps: float = 0.0
    success_rate: float = 1.0


class PerformanceChartGenerator:
    """性能对比图表生成器"""
    
    # 颜色方案
    COLOR_PALETTE = [
        '#2E86AB',  # 蓝色
        '#A23B72',  # 紫色
        '#F18F01',  # 橙色
        '#C73E1D',  # 红色
        '#6A994E',  # 绿色
        '#577590',  # 深蓝
        '#BC4B51',  # 深红
        '#F9C74F',  # 黄色
    ]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "experiments" / "charts"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_all_charts(
        self,
        methods: Sequence[MethodComparison],
        experiment_name: str = "性能对比",
        formats: Optional[List[str]] = None,
    ) -> Dict[str, Path]:
        """生成所有类型的图表"""
        if formats is None:
            formats = ['png', 'html']
        
        generated = {}
        
        # 1. 综合指标对比柱状图
        chart_path = self.generate_metrics_bar_chart(methods, experiment_name, formats)
        generated['metrics_bar'] = chart_path
        
        # 2. 雷达图
        chart_path = self.generate_radar_chart(methods, experiment_name, formats)
        generated['radar'] = chart_path
        
        # 3. 延迟对比图
        chart_path = self.generate_latency_chart(methods, experiment_name, formats)
        generated['latency'] = chart_path
        
        # 4. 综合评分图
        chart_path = self.generate_overall_score_chart(methods, experiment_name, formats)
        generated['overall_score'] = chart_path
        
        return generated
    
    def generate_metrics_bar_chart(
        self,
        methods: Sequence[MethodComparison],
        title: str = "推荐指标对比",
        formats: Optional[List[str]] = None,
    ) -> Path:
        """生成指标对比柱状图"""
        if formats is None:
            formats = ['png', 'html']
        
        method_names = [m.method_name for m in methods]
        metrics = ['precision', 'recall', 'ndcg', 'diversity', 'novelty']
        metric_values = {
            'precision': [m.precision_at_k for m in methods],
            'recall': [m.recall_at_k for m in methods],
            'ndcg': [m.ndcg_at_k for m in methods],
            'diversity': [m.diversity for m in methods],
            'novelty': [m.novelty for m in methods],
        }
        
        if MATPLOTLIB_AVAILABLE and 'png' in formats:
            return self._generate_bar_chart_matplotlib(
                method_names, metric_values, metrics, title, 'png'
            )
        
        if PLOTLY_AVAILABLE and 'html' in formats:
            return self._generate_bar_chart_plotly(
                method_names, metric_values, metrics, title, 'html'
            )
        
        # 降级方案：生成文本报告
        return self._generate_text_report(methods, title)
    
    def _generate_bar_chart_matplotlib(
        self,
        method_names: List[str],
        metric_values: Dict[str, List[float]],
        metrics: List[str],
        title: str,
        format: str,
    ) -> Path:
        """使用 matplotlib 生成柱状图"""
        fig, ax = plt.subplots(figsize=(12, 7))
        
        x = range(len(method_names))
        width = 0.15
        num_metrics = len(metrics)
        
        for i, metric in enumerate(metrics):
            offset = (i - num_metrics / 2) * width + width / 2
            ax.bar(
                [xi + offset for xi in x],
                metric_values[metric],
                width,
                label=metric.capitalize(),
                color=self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)],
            )
        
        ax.set_xlabel('Method', fontsize=12)
        ax.set_ylabel('Score', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(method_names, rotation=15, ha='right')
        ax.legend(loc='upper right')
        ax.set_ylim(0, 1.0)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        
        output_path = self.output_dir / f"metrics_comparison.{format}"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _generate_bar_chart_plotly(
        self,
        method_names: List[str],
        metric_values: Dict[str, List[float]],
        metrics: List[str],
        title: str,
        format: str,
    ) -> Path:
        """使用 Plotly 生成交互式柱状图"""
        fig = go.Figure()
        
        for i, metric in enumerate(metrics):
            fig.add_trace(go.Bar(
                name=metric.capitalize(),
                x=method_names,
                y=metric_values[metric],
                marker_color=self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)],
            ))
        
        fig.update_layout(
            title=title,
            xaxis_title='Method',
            yaxis_title='Score',
            barmode='group',
            yaxis=dict(range=[0, 1.0]),
            legend_title='Metrics',
            height=600,
        )
        
        output_path = self.output_dir / f"metrics_comparison.{format}"
        fig.write_html(output_path)
        
        return output_path
    
    def generate_radar_chart(
        self,
        methods: Sequence[MethodComparison],
        title: str = "综合能力雷达图",
        formats: Optional[List[str]] = None,
    ) -> Path:
        """生成雷达图"""
        if formats is None:
            formats = ['png', 'html']
        
        metrics = ['precision_at_k', 'recall_at_k', 'ndcg_at_k', 'diversity', 'novelty']
        metric_labels = ['Precision', 'Recall', 'NDCG', 'Diversity', 'Novelty']
        
        if MATPLOTLIB_AVAILABLE and 'png' in formats:
            return self._generate_radar_matplotlib(methods, metrics, metric_labels, title, 'png')
        
        if PLOTLY_AVAILABLE and 'html' in formats:
            return self._generate_radar_plotly(methods, metrics, metric_labels, title, 'html')
        
        return self._generate_text_report(methods, title)
    
    def _generate_radar_matplotlib(
        self,
        methods: Sequence[MethodComparison],
        metrics: List[str],
        metric_labels: List[str],
        title: str,
        format: str,
    ) -> Path:
        """使用 matplotlib 生成雷达图"""
        num_vars = len(metrics)
        angles = [n / num_vars * 2 * 3.14159 for n in range(num_vars)]
        angles += angles[:1]  # 闭合
        
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
        
        for i, method in enumerate(methods):
            values = [getattr(method, m) for m in metrics]
            values += values[:1]  # 闭合
            
            ax.plot(angles, values, 'o-', linewidth=2, label=method.method_name,
                   color=self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)])
            ax.fill(angles, values, alpha=0.15, color=self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)])
        
        ax.set_theta_offset(3.14159 / 2)
        ax.set_theta_direction(-1)
        ax.set_thetagrids([a * 180 / 3.14159 for a in angles[:-1]], metric_labels)
        ax.set_rgrids([0.2, 0.4, 0.6, 0.8, 1.0], angle=0)
        ax.set_ylim(0, 1.0)
        
        plt.title(title, fontsize=14, fontweight='bold', pad=20)
        plt.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
        
        output_path = self.output_dir / f"radar_comparison.{format}"
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _generate_radar_plotly(
        self,
        methods: Sequence[MethodComparison],
        metrics: List[str],
        metric_labels: List[str],
        title: str,
        format: str,
    ) -> Path:
        """使用 Plotly 生成交互式雷达图"""
        fig = go.Figure()
        
        for i, method in enumerate(methods):
            values = [getattr(method, m) for m in metrics]
            
            fig.add_trace(go.Scatterpolar(
                r=values + [values[0]],  # 闭合
                theta=metric_labels + [metric_labels[0]],
                fill='toself',
                name=method.method_name,
                line=dict(color=self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)]),
            ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 1]
                )),
            showlegend=True,
            title=title,
            height=600,
        )
        
        output_path = self.output_dir / f"radar_comparison.{format}"
        fig.write_html(output_path)
        
        return output_path
    
    def generate_latency_chart(
        self,
        methods: Sequence[MethodComparison],
        title: str = "延迟对比",
        formats: Optional[List[str]] = None,
    ) -> Path:
        """生成延迟对比图"""
        if formats is None:
            formats = ['png', 'html']
        
        method_names = [m.method_name for m in methods]
        latencies = [m.latency_ms for m in methods]
        
        if MATPLOTLIB_AVAILABLE and 'png' in formats:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            colors = [self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)] for i in range(len(methods))]
            bars = ax.bar(method_names, latencies, color=colors)
            
            # 添加数值标签
            for bar, latency in zip(bars, latencies):
                height = bar.get_height()
                ax.annotate(f'{latency:.0f}ms',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom', fontsize=10)
            
            ax.set_xlabel('Method', fontsize=12)
            ax.set_ylabel('Latency (ms)', fontsize=12)
            ax.set_title(title, fontsize=14, fontweight='bold')
            ax.grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            
            output_path = self.output_dir / f"latency_comparison.{format}"
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return output_path
        
        if PLOTLY_AVAILABLE and 'html' in formats:
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                x=method_names,
                y=latencies,
                marker_color=colors,
                text=[f'{lat:.0f}ms' for lat in latencies],
                textposition='outside',
            ))
            
            fig.update_layout(
                title=title,
                xaxis_title='Method',
                yaxis_title='Latency (ms)',
                height=500,
            )
            
            output_path = self.output_dir / f"latency_comparison.{format}"
            fig.write_html(output_path)
            
            return output_path
        
        return self._generate_text_report(methods, title)
    
    def generate_overall_score_chart(
        self,
        methods: Sequence[MethodComparison],
        title: str = "综合评分对比",
        formats: Optional[List[str]] = None,
    ) -> Path:
        """生成综合评分图"""
        if formats is None:
            formats = ['png', 'html']
        
        # 计算综合评分 (简单加权平均)
        weights = {
            'ndcg_at_k': 0.35,
            'precision_at_k': 0.25,
            'recall_at_k': 0.20,
            'diversity': 0.10,
            'novelty': 0.10,
        }
        
        method_names = [m.method_name for m in methods]
        overall_scores = []
        
        for method in methods:
            score = (
                method.ndcg_at_k * weights['ndcg_at_k'] +
                method.precision_at_k * weights['precision_at_k'] +
                method.recall_at_k * weights['recall_at_k'] +
                method.diversity * weights['diversity'] +
                method.novelty * weights['novelty']
            )
            overall_scores.append(score)
        
        if MATPLOTLIB_AVAILABLE and 'png' in formats:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            colors = [self.COLOR_PALETTE[i % len(self.COLOR_PALETTE)] for i in range(len(methods))]
            bars = ax.bar(method_names, overall_scores, color=colors)
            
            # 添加数值标签
            for bar, score in zip(bars, overall_scores):
                height = bar.get_height()
                ax.annotate(f'{score:.3f}',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom', fontsize=11, fontweight='bold')
            
            ax.set_xlabel('Method', fontsize=12)
            ax.set_ylabel('Overall Score', fontsize=12)
            ax.set_title(title, fontsize=14, fontweight='bold')
            ax.set_ylim(0, 1.0)
            ax.grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            
            output_path = self.output_dir / f"overall_score_comparison.{format}"
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return output_path
        
        if PLOTLY_AVAILABLE and 'html' in formats:
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                x=method_names,
                y=overall_scores,
                marker_color=colors,
                text=[f'{score:.3f}' for score in overall_scores],
                textposition='outside',
            ))
            
            fig.update_layout(
                title=title,
                xaxis_title='Method',
                yaxis_title='Overall Score',
                yaxis=dict(range=[0, 1.0]),
                height=500,
            )
            
            output_path = self.output_dir / f"overall_score_comparison.{format}"
            fig.write_html(output_path)
            
            return output_path
        
        return self._generate_text_report(methods, title)
    
    def _generate_text_report(
        self,
        methods: Sequence[MethodComparison],
        title: str,
    ) -> Path:
        """降级方案：生成文本格式报告"""
        output_path = self.output_dir / f"{title.replace(' ', '_')}_report.md"
        
        lines = [
            f"# {title}",
            "",
            "## 方法对比",
            "",
            "| Method | Precision | Recall | NDCG | Diversity | Novelty | Latency (ms) |",
            "|--------|-----------|--------|------|-----------|---------|--------------|",
        ]
        
        for method in methods:
            lines.append(
                f"| {method.method_name} | {method.precision_at_k:.3f} | "
                f"{method.recall_at_k:.3f} | {method.ndcg_at_k:.3f} | "
                f"{method.diversity:.3f} | {method.novelty:.3f} | {method.latency_ms:.1f} |"
            )
        
        # 计算综合评分
        lines.extend([
            "",
            "## 综合评分",
            "",
            "综合评分 = 0.35×NDCG + 0.25×Precision + 0.20×Recall + 0.10×Diversity + 0.10×Novelty",
            "",
            "| Method | Overall Score |",
            "|--------|---------------|",
        ])
        
        weights = {'ndcg_at_k': 0.35, 'precision_at_k': 0.25, 'recall_at_k': 0.20, 'diversity': 0.10, 'novelty': 0.10}
        for method in methods:
            score = (
                method.ndcg_at_k * weights['ndcg_at_k'] +
                method.precision_at_k * weights['precision_at_k'] +
                method.recall_at_k * weights['recall_at_k'] +
                method.diversity * weights['diversity'] +
                method.novelty * weights['novelty']
            )
            lines.append(f"| {method.method_name} | {score:.4f} |")
        
        with output_path.open('w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return output_path
    
    def generate_from_experiment_data(
        self,
        experiment_path: Path,
        title: Optional[str] = None,
    ) -> Dict[str, Path]:
        """从实验数据文件生成图表"""
        with experiment_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 从实验数据中提取方法汇总
        summary = data.get('summary', {})
        methods_data = summary.get('methods', {})
        
        methods = []
        for method_name, method_stats in methods_data.items():
            methods.append(MethodComparison(
                method_name=method_name,
                precision_at_k=method_stats.get('precision_avg', 0.0),
                recall_at_k=method_stats.get('recall_avg', 0.0),
                ndcg_at_k=method_stats.get('ndcg_avg', 0.0),
                diversity=0.5,  # 需要时从详细数据计算
                novelty=0.5,
                latency_ms=method_stats.get('latency_avg', 0.0),
            ))
        
        experiment_name = title or data.get('metadata', {}).get('experiment_name', '实验')
        return self.generate_all_charts(methods, experiment_name)


def create_chart_generator(output_dir: Optional[Path] = None) -> PerformanceChartGenerator:
    """创建图表生成器实例"""
    return PerformanceChartGenerator(output_dir)


if __name__ == "__main__":
    # 示例使用
    generator = create_chart_generator()
    
    # 创建示例数据
    methods = [
        MethodComparison("acps_multi_agent", 0.82, 0.75, 0.78, 0.65, 0.58, 1500.0),
        MethodComparison("traditional_hybrid", 0.78, 0.70, 0.72, 0.55, 0.50, 800.0),
        MethodComparison("multi_agent_proxy", 0.80, 0.73, 0.76, 0.60, 0.55, 1200.0),
        MethodComparison("llm_only", 0.75, 0.68, 0.70, 0.50, 0.45, 2000.0),
    ]
    
    # 生成所有图表
    generated = generator.generate_all_charts(methods, "ACPs 推荐系统性能对比")
    
    print("生成的图表:")
    for chart_type, path in generated.items():
        print(f"  - {chart_type}: {path}")
