#!/usr/bin/env python3
"""
调用大模型生成各虚拟角色的论文审查意见
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 配置
load_dotenv(Path(__file__).parent.parent / ".env")

# 配置
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
)

MODEL = os.getenv("OPENAI_MODEL", "qwen3.5-plus-2026-02-15")

# 论文材料
PAPER_CONTEXT = """
# ACPs 多 Agent 协作推荐系统 - 论文审查材料

## 论文结构
- 摘要 (Abstract): ✅ 已完成
- 第 1 章 绪论：🟡 框架有，需扩展
- 第 2 章 相关工作：❌ 待撰写
- 第 3 章 系统设计：✅ 完成
- 第 4 章 系统实现：✅ 完成
- 第 5 章 实验与评估：🟡 部分完成（缺真实数据）
- 第 6 章 结论与展望：✅ 完成
- 参考文献：❌ 待补充

## 实验状态
1. 嵌入模型对比实验：⚠️ 已运行但 API 调用异常（实际用了 hash-fallback 而非 qwen3-vl-embedding）
2. 消融实验：⚠️ evaluated_users: 0，数据加载有问题
3. Agent 协作消融实验：❌ 未完成
4. 系统性能测试：❌ 未完成
5. 基线对比实验：❌ 未完成

## 核心问题
1. 嵌入模型实验数据异常 - 需要在新服务器重新跑
2. 消融实验 evaluated_users=0 - 数据加载逻辑问题
3. 第 2 章相关工作缺失 - 需文献调研
4. 基线对比实验未完成 - 需补充

## 技术栈
- 后端：Python 3.10, FastAPI
- 协议：JSON-RPC 2.0 (ACPS 协议)
- 安全：mTLS 双向认证
- 嵌入模型：qwen3-vl-embedding (DashScope)
- 数据集：Goodreads + Amazon Books (99 万册书籍)

## 系统架构
Leader-Partner 架构：
- Leader: ReadingConcierge (任务编排)
- Partners: ReaderProfile, BookContent, RecRanking

## 实验数据集
- 书籍池：991,409 册 (books_master_merged.jsonl, 809MB)
- 交互数据：interactions_merged.jsonl (2.9GB)
- 知识图谱：knowledge_graph.json (285MB)
"""

def generate_review(role_name: str, role_info: dict) -> str:
    """生成单个角色的审查意见"""
    
    system_prompt = f"""你是一位{role_info['role']}，在{role_info['expertise']}领域有深厚造诣。

你的职责：
{chr(10).join(f"- {r}" for r in role_info['responsibilities'])}

审查重点：{role_info['review_focus']}
语气风格：{role_info['tone']}

请基于提供的论文材料，生成专业的审查意见。"""

    user_prompt = f"""请审查以下 ACPs 多 Agent 协作推荐系统论文材料：

{PAPER_CONTEXT}

请从你的专业角度，生成详细的审查意见，包括：
1. 当前工作的优点/亮点
2. 发现的问题/缺陷
3. 具体改进建议
4. 下一步优先任务（按优先级排序）
5. 是否同意当前论文状态可以提交（是/否/条件同意）

要求：
- 具体、可操作的建议
- 指出具体章节/实验的问题
- 给出明确的时间估算
- 语气专业但不失建设性"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ 生成失败：{str(e)}"


def main():
    # 加载角色配置
    with open("/root/WORK/SCHOOL/ACPs-app/thesis_review/role_prompts.json", "r", encoding="utf-8") as f:
        roles = json.load(f)
    
    print("=" * 80)
    print("🎓 ACPs 论文审查 - 虚拟角色审查意见生成")
    print("=" * 80)
    print(f"模型：{MODEL}")
    print(f"时间：{json.dumps({'timestamp': __import__('datetime').datetime.now().isoformat()})}")
    print("=" * 80)
    
    reviews = {}
    
    for role_name, role_info in roles.items():
        print(f"\n🔔 正在调用 {role_name} 生成审查意见...")
        review = generate_review(role_name, role_info)
        reviews[role_name] = review
        
        # 保存到文件
        output_path = Path(f"/root/WORK/SCHOOL/ACPs-app/thesis_review/{role_name}_review.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# {role_name} 审查意见\n\n")
            f.write(f"**生成时间**: {__import__('datetime').datetime.now().isoformat()}\n")
            f.write(f"**角色**: {role_info['role']}\n")
            f.write(f"**审查重点**: {role_info['review_focus']}\n\n")
            f.write("---\n\n")
            f.write(review)
        
        print(f"✅ {role_name} 审查意见已保存到：{output_path}")
    
    # 生成汇总报告
    summary_path = Path("/root/WORK/SCHOOL/ACPs-app/thesis_review/summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# ACPs 论文审查 - 汇总报告\n\n")
        f.write(f"**生成时间**: {__import__('datetime').datetime.now().isoformat()}\n")
        f.write(f"**模型**: {MODEL}\n\n")
        f.write("---\n\n")
        
        for role_name, review in reviews.items():
            f.write(f"## {role_name} 审查意见\n\n")
            f.write(review)
            f.write("\n\n---\n\n")
    
    print(f"\n✅ 汇总报告已保存到：{summary_path}")
    print("\n" + "=" * 80)
    print("审查意见生成完成！")
    print("=" * 80)


if __name__ == "__main__":
    main()
