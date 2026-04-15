"""实验变体配置 — S1（Full）及 S2~S6 消融变体。"""
from __future__ import annotations
from typing import Any, Dict, List

API_BASE = "http://8.146.235.243:8210"
USER_API = f"{API_BASE}/user_api"

# 测试用户集（可按需扩充）
TEST_USERS: List[str] = [
    "gr_u_26334",
    "gr_u_12345",
    "gr_u_55678",
    "gr_u_78901",
    "gr_u_99001",
]

# 测试查询集（覆盖不同品类）
TEST_QUERIES: List[str] = [
    "mystery thriller detective",
    "science fiction space exploration",
    "historical romance 19th century",
    "self-help productivity mindfulness",
    "fantasy magic world building",
]

TOP_K = 5
REQUEST_TIMEOUT = 120  # 秒

# ── 实验变体定义 ──────────────────────────────────────────────────────────────

VARIANTS: List[Dict[str, Any]] = [
    {
        "id": "S1",
        "name": "Full System",
        "description": "所有模块全量开启，自适应仲裁权重",
        "constraints": {
            "top_k": TOP_K,
        },
    },
    {
        "id": "S2",
        "name": "w/o BCA Alignment",
        "description": "禁用 BCA 偏好对齐，内容提案不使用用户偏好类型",
        "constraints": {
            "top_k": TOP_K,
            "ablation_flags": {"disable_alignment": True},
        },
    },
    {
        "id": "S3",
        "name": "w/o RDA Arbitration",
        "description": "固定仲裁权重，不走 RDA 自适应学习路径",
        "constraints": {
            "top_k": TOP_K,
            "ablation_flags": {"fixed_arbitration_weights": True},
            # 使用均等固定权重
            "scoring_weights": {
                "semantic": 0.35,
                "collaborative": 0.25,
                "diversity": 0.20,
                "knowledge": 0.20,
            },
        },
    },
    {
        "id": "S4",
        "name": "w/o CF Path",
        "description": "纯 ANN/FAISS 语义召回，关闭协同过滤路径",
        "constraints": {
            "top_k": TOP_K,
            "ablation_flags": {"disable_cf_path": True},
            "scoring_weights": {
                "semantic": 0.6,
                "collaborative": 0.0,
                "diversity": 0.25,
                "knowledge": 0.15,
            },
        },
    },
    {
        "id": "S5",
        "name": "w/o MMR Rerank",
        "description": "禁用 MMR 多样性重排，mmr_lambda=1.0（纯相关性排序）",
        "constraints": {
            "top_k": TOP_K,
            "ablation_flags": {"disable_mmr": True},
        },
    },
    {
        "id": "S6",
        "name": "w/o Explain Constraint",
        "description": "禁用解释质量约束，不做 confidence penalty 惩罚",
        "constraints": {
            "top_k": TOP_K,
            "ablation_flags": {"disable_explain_constraint": True},
        },
    },
]
