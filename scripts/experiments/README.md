# ACPs-app 消融实验框架

## 目录结构

```
scripts/experiments/
├── README.md                  # 本文件
├── config.py                  # 实验配置（S1~S6 各变体参数）
├── run_experiments.py         # 批量请求脚本（对所有用户 × 所有变体）
├── evaluate.py                # 离线评估（NDCG@5、P@5、ILD、Coverage）
└── visualize.py               # 生成论文图表

artifacts/experiments/
├── raw/                       # run_experiments.py 的原始输出（JSON）
├── metrics/                   # evaluate.py 的指标输出（CSV）
└── figures/                   # visualize.py 的图表（PNG/PDF）
```

## 快速开始

```bash
# 1. 确保服务已启动
curl http://8.146.235.243:8210/demo/status

# 2. 运行所有实验（约需 20~40 分钟）
cd /root/WORK/ACPs-app
.venv/bin/python scripts/experiments/run_experiments.py

# 3. 离线评估
.venv/bin/python scripts/experiments/evaluate.py

# 4. 生成图表
.venv/bin/python scripts/experiments/visualize.py
```

## 实验变体说明

| ID | 名称 | 禁用组件 |
|----|------|----------|
| S1 | Full System | 无（全量） |
| S2 | w/o BCA Alignment | disable_alignment |
| S3 | w/o RDA Arbitration | fixed_arbitration_weights |
| S4 | w/o CF Path | disable_cf_path |
| S5 | w/o MMR Rerank | disable_mmr |
| S6 | w/o Explain Constraint | disable_explain_constraint |
