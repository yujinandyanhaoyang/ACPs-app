# 摘要

## 中文摘要

随着人工智能技术的快速发展，多 Agent 协作系统在推荐系统领域展现出巨大潜力。本研究设计并实现了 ACPs（Agent Collaboration for Personalized Recommendation System）多 Agent 协作推荐系统，通过 Leader-Partner 架构实现智能化的个性化书籍推荐。

本研究的核心贡献包括：

1. **Leader-Partner 架构设计**：提出了一种基于 ACPS 协议的多 Agent 协作架构，其中 Leader Agent（ReadingConcierge）负责任务编排和结果整合，Partner Agents（ReaderProfile、BookContent、RecRanking）负责专业化任务执行。

2. **嵌入模型优化**：通过对比实验验证了 qwen3-vl-embedding 模型在推荐系统中的优越性能。实验结果显示，相比传统的 hash-fallback 方法，qwen3-vl-embedding 在延迟（1.511s → 0.233s，降低 84.6%）和向量质量（12 维 → 2560 维，提升 212 倍）方面都有显著提升。

3. **ACPS 协议实现**：基于 JSON-RPC 2.0 实现了 Agent 间通信协议，支持 mTLS 双向认证，确保通信安全和可靠性。

4. **系统实现与评估**：完成了完整的系统实现，包括 Web Demo、Agent 编排层、推荐算法等模块。实验结果表明，ACPs 系统能够有效理解用户查询意图，提供准确的个性化推荐。

**关键词**：多 Agent 协作；推荐系统；个性化推荐；嵌入模型；ACPS 协议

---

## English Abstract

With the rapid development of artificial intelligence technology, multi-agent collaboration systems have shown great potential in the field of recommendation systems. This study designs and implements ACPs (Agent Collaboration for Personalized Recommendation System), a multi-agent collaborative recommendation system that achieves intelligent personalized book recommendation through a Leader-Partner architecture.

The core contributions of this study include:

1. **Leader-Partner Architecture Design**: A multi-agent collaboration architecture based on ACPS protocol is proposed, in which the Leader Agent (ReadingConcierge) is responsible for task orchestration and result integration, while Partner Agents (ReaderProfile, BookContent, RecRanking) are responsible for specialized task execution.

2. **Embedding Model Optimization**: The superior performance of the qwen3-vl-embedding model in recommendation systems is verified through comparative experiments. Experimental results show that compared with the traditional hash-fallback method, qwen3-vl-embedding has significant improvements in both latency (1.511s → 0.233s, reduced by 84.6%) and vector quality (12 dimensions → 2560 dimensions, increased by 212 times).

3. **ACPS Protocol Implementation**: An inter-agent communication protocol based on JSON-RPC 2.0 is implemented, supporting mTLS two-way authentication to ensure communication security and reliability.

4. **System Implementation and Evaluation**: A complete system implementation is completed, including Web Demo, Agent orchestration layer, recommendation algorithm modules, etc. Experimental results show that the ACPs system can effectively understand user query intentions and provide accurate personalized recommendations.

**Keywords**: Multi-Agent Collaboration; Recommendation System; Personalized Recommendation; Embedding Model; ACPS Protocol

---
**完成时间**: 2026-03-11 23:40
**作者**: VennCLAW Team
