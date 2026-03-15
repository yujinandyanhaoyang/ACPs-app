#!/bin/bash
# 实验进度监控脚本

LOG_FILE="experiments/ablation_run_$(date +%Y%m%d).log"
SESSION_ID="fast-shore"

echo "=========================================="
echo "📊 ACPs 实验进度监控报告"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# 检查消融实验进程
echo "🔬 任务 1: 消融实验 (Ablation Study)"
if ps aux | grep "run_ablation.py" | grep -v grep > /dev/null; then
    echo "   状态：🟢 正在运行"
    # 统计日志中的完成数量
    if [ -f "$LOG_FILE" ]; then
        COMPLETED=$(grep -c "reading_orchestration_complete" "$LOG_FILE" 2>/dev/null || echo "0")
        echo "   进度：已完成约 $COMPLETED 个用户测试"
        echo "   日志文件：$LOG_FILE"
    fi
else
    echo "   状态：⏹️ 未运行或已完成"
fi
echo ""

# 检查输出文件
echo "📁 实验输出文件:"
ls -lh experiments/ablation_study_large_*.json 2>/dev/null || echo "   尚未生成输出文件"
echo ""

# 检查基准测试
echo "🎯 任务 2: 基准对比测试 (Benchmark)"
if ps aux | grep "phase4_benchmark_compare.py" | grep -v grep > /dev/null; then
    echo "   状态：🟢 正在运行"
else
    echo "   状态：⏸️ 等待开始"
fi
echo ""

echo "=========================================="
