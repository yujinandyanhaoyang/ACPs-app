#!/usr/bin/env python3
"""
传统推荐算法基线实现

用于与 ACPs 多 Agent 系统进行对比实验。

包含：
1. Item-KNN（基于物品的协同过滤）
2. Matrix Factorization（矩阵分解）
3. Hybrid Recommender（混合推荐：CF + 内容）
"""

import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np

from services.data_paths import get_processed_data_path


class ItemKNN:
    """基于物品的协同过滤"""
    
    def __init__(self, k: int = 20):
        self.k = k  # 邻居数量
        self.item_similarity: Dict[str, Dict[str, float]] = {}
        self.user_history: Dict[str, List[str]] = {}
        
    def fit(self, interactions_path: Path):
        """训练模型：构建物品相似度矩阵"""
        # 加载交互数据
        user_items: Dict[str, List[str]] = defaultdict(list)
        item_users: Dict[str, List[str]] = defaultdict(list)
        
        with interactions_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    user_id = str(data.get('user_id', ''))
                    book_id = str(data.get('book_id', ''))
                    if user_id and book_id:
                        user_items[user_id].append(book_id)
                        item_users[book_id].append(user_id)
                except json.JSONDecodeError:
                    continue
        
        self.user_history = dict(user_items)
        
        # 计算物品相似度（余弦相似度）
        items = list(item_users.keys())
        self.item_similarity = {item: {} for item in items}
        
        for i, item1 in enumerate(items):
            users1 = set(item_users[item1])
            for item2 in items[i+1:]:
                users2 = set(item_users[item2])
                # 余弦相似度
                intersection = len(users1 & users2)
                if intersection > 0:
                    similarity = intersection / (math.sqrt(len(users1)) * math.sqrt(len(users2)))
                    self.item_similarity[item1][item2] = similarity
                    self.item_similarity[item2][item1] = similarity
        
        return self
    
    def predict(self, user_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """为用户生成推荐"""
        history = self.user_history.get(user_id, [])
        if not history:
            return []
        
        # 聚合邻居物品的评分
        scores: Dict[str, float] = defaultdict(float)
        for item in history:
            neighbors = self.item_similarity.get(item, {})
            for neighbor, sim in neighbors.items():
                if neighbor not in history:
                    scores[neighbor] += sim
        
        # 排序并返回 top_k
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"book_id": bid, "score": score} for bid, score in sorted_items]


class MatrixFactorization:
    """矩阵分解推荐"""
    
    def __init__(self, n_factors: int = 50, n_epochs: int = 20, lr: float = 0.005, reg: float = 0.02):
        self.n_factors = n_factors
        self.n_epochs = n_epochs
        self.lr = lr
        self.reg = reg
        self.user_factors: Dict[str, np.ndarray] = {}
        self.item_factors: Dict[str, np.ndarray] = {}
        self.global_mean: float = 0.0
        self.user_bias: Dict[str, float] = {}
        self.item_bias: Dict[str, float] = {}
        
    def fit(self, interactions_path: Path):
        """训练模型：SGD 优化"""
        # 加载数据
        ratings: List[Tuple[str, str, float]] = []
        with interactions_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    user_id = str(data.get('user_id', ''))
                    book_id = str(data.get('book_id', ''))
                    rating = float(data.get('rating', 0))
                    if user_id and book_id and rating > 0:
                        ratings.append((user_id, book_id, rating))
                except (json.JSONDecodeError, ValueError):
                    continue
        
        if not ratings:
            return self
        
        # 初始化
        self.global_mean = sum(r[2] for r in ratings) / len(ratings)
        users = set(r[0] for r in ratings)
        items = set(r[1] for r in ratings)
        
        np.random.seed(42)
        self.user_factors = {u: np.random.normal(0, 0.1, self.n_factors) for u in users}
        self.item_factors = {i: np.random.normal(0, 0.1, self.n_factors) for i in items}
        self.user_bias = {u: 0.0 for u in users}
        self.item_bias = {i: 0.0 for i in items}
        
        # SGD 训练
        for epoch in range(self.n_epochs):
            np.random.shuffle(ratings)
            for user_id, item_id, rating in ratings:
                # 预测
                pred = (self.global_mean + 
                       self.user_bias[user_id] + 
                       self.item_bias[item_id] + 
                       np.dot(self.user_factors[user_id], self.item_factors[item_id]))
                
                # 误差
                error = rating - pred
                
                # 更新
                self.user_bias[user_id] += self.lr * (error - self.reg * self.user_bias[user_id])
                self.item_bias[item_id] += self.lr * (error - self.reg * self.item_bias[item_id])
                
                user_factor = self.user_factors[user_id].copy()
                self.user_factors[user_id] += self.lr * (error * self.item_factors[item_id] - self.reg * user_factor)
                self.item_factors[item_id] += self.lr * (error * user_factor - self.reg * self.item_factors[item_id])
        
        return self
    
    def predict(self, user_id: str, all_items: List[str], top_k: int = 10) -> List[Dict[str, Any]]:
        """为用户生成推荐"""
        if user_id not in self.user_factors:
            return []
        
        scores = []
        for item_id in all_items:
            if item_id not in self.item_factors:
                continue
            score = (self.global_mean + 
                    self.user_bias.get(user_id, 0) + 
                    self.item_bias.get(item_id, 0) + 
                    np.dot(self.user_factors[user_id], self.item_factors[item_id]))
            scores.append((item_id, float(score)))
        
        sorted_items = sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]
        return [{"book_id": bid, "score": score} for bid, score in sorted_items]


class HybridRecommender:
    """混合推荐：CF + 内容相似度"""
    
    def __init__(self, cf_weight: float = 0.6, content_weight: float = 0.4):
        self.cf_weight = cf_weight
        self.content_weight = content_weight
        self.cf_model = ItemKNN(k=20)
        self.item_content: Dict[str, Dict[str, Any]] = {}
        
    def fit(self, interactions_path: Path, books_path: Path):
        """训练模型"""
        # 训练 CF 部分
        self.cf_model.fit(interactions_path)
        
        # 加载书籍内容
        with books_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    book = json.loads(line)
                    book_id = str(book.get('book_id', ''))
                    if book_id:
                        self.item_content[book_id] = {
                            'genres': set(book.get('genres', [])),
                            'author': book.get('author', ''),
                        }
                except json.JSONDecodeError:
                    continue
        
        return self
    
    def _content_similarity(self, item1: str, item2: str) -> float:
        """计算内容相似度"""
        if item1 not in self.item_content or item2 not in self.item_content:
            return 0.0
        
        content1 = self.item_content[item1]
        content2 = self.item_content[item2]
        
        # 类型相似度（Jaccard）
        genres1 = content1['genres']
        genres2 = content2['genres']
        if genres1 and genres2:
            genre_sim = len(genres1 & genres2) / len(genres1 | genres2)
        else:
            genre_sim = 0.0
        
        # 作者相似度
        author_sim = 1.0 if content1['author'] == content2['author'] else 0.0
        
        return 0.7 * genre_sim + 0.3 * author_sim
    
    def predict(self, user_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """为用户生成推荐"""
        history = self.cf_model.user_history.get(user_id, [])
        if not history:
            return []
        
        # CF 分数
        cf_recs = self.cf_model.predict(user_id, top_k=top_k * 3)
        cf_scores = {r['book_id']: r['score'] for r in cf_recs}
        
        # 内容分数
        content_scores: Dict[str, float] = defaultdict(float)
        for item in history:
            for candidate in self.item_content.keys():
                if candidate not in history:
                    sim = self._content_similarity(item, candidate)
                    content_scores[candidate] += sim
        
        # 归一化
        max_cf = max(cf_scores.values()) if cf_scores else 1.0
        max_content = max(content_scores.values()) if content_scores else 1.0
        
        # 融合
        all_candidates = set(cf_scores.keys()) | set(content_scores.keys())
        final_scores = []
        for candidate in all_candidates:
            cf_norm = cf_scores.get(candidate, 0) / max_cf
            content_norm = content_scores.get(candidate, 0) / max_content
            final_score = self.cf_weight * cf_norm + self.content_weight * content_norm
            final_scores.append((candidate, final_score))
        
        sorted_items = sorted(final_scores, key=lambda x: x[1], reverse=True)[:top_k]
        return [{"book_id": bid, "score": score} for bid, score in sorted_items]


def load_books_list(books_path: Path) -> List[str]:
    """加载书籍 ID 列表"""
    books = []
    with books_path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                book = json.loads(line)
                book_id = str(book.get('book_id', ''))
                if book_id:
                    books.append(book_id)
            except json.JSONDecodeError:
                continue
    return books


if __name__ == "__main__":
    # 测试
    import time
    
    DATA_ROOT = Path("/home/dataset/bookset/processed")
    interactions_path = DATA_ROOT / "merged" / "interactions_merged.jsonl"
    books_path = DATA_ROOT / "merged" / "books_master_merged.jsonl"
    
    print("测试传统推荐算法基线...")
    
    # Item-KNN
    print("\n1. Item-KNN...")
    start = time.time()
    knn = ItemKNN(k=20)
    knn.fit(interactions_path)
    recs = knn.predict("gr_u_2", top_k=5)
    print(f"   训练时间：{time.time() - start:.2f}s")
    print(f"   推荐结果：{len(recs)} 个")
    if recs:
        print(f"   示例：{recs[0]}")
    
    # MF
    print("\n2. Matrix Factorization...")
    start = time.time()
    mf = MatrixFactorization(n_factors=20, n_epochs=5)
    mf.fit(interactions_path)
    all_books = load_books_list(books_path)[:1000]  # 限制数量加速测试
    recs = mf.predict("gr_u_2", all_books, top_k=5)
    print(f"   训练时间：{time.time() - start:.2f}s")
    print(f"   推荐结果：{len(recs)} 个")
    if recs:
        print(f"   示例：{recs[0]}")
    
    # Hybrid
    print("\n3. Hybrid Recommender...")
    start = time.time()
    hybrid = HybridRecommender(cf_weight=0.6, content_weight=0.4)
    hybrid.fit(interactions_path, books_path)
    recs = hybrid.predict("gr_u_2", top_k=5)
    print(f"   训练时间：{time.time() - start:.2f}s")
    print(f"   推荐结果：{len(recs)} 个")
    if recs:
        print(f"   示例：{recs[0]}")
    
    print("\n✅ 基线算法测试完成！")
