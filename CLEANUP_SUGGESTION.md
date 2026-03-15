# 🗑️ ACPs-app 数据清理建议

**当前存储使用情况：**
- 总空间：40GB
- 已用：29GB (78%)
- 可用：8.4GB ⚠️

---

## 📊 大文件分析

| 路径 | 大小 | 说明 | 建议 |
|------|------|------|------|
| `/root/DataSet/processed.zip` | **2.5GB** | 已解压的压缩包 | ✅ **可删除** |
| `/root/DataSet/processed/merged/` | 3.5GB | 合并后的数据集 | ⚠️ 保留 |
| `/root/DataSet/processed/amazon_books/` | 2.1GB | 原始亚马逊图书数据 | ⚠️ 可选 |
| `/root/DataSet/processed/amazon_kindle/` | 1.5GB | 原始 Kindle 数据 | ⚠️ 可选 |
| `/root/ACPs-app/venv/` | 7.3GB | Python 虚拟环境 | ❌ 必需 |

---

## ✅ 推荐清理方案

### 方案 1：安全清理（立即执行）

**删除已解压的压缩包：**
```bash
rm /root/DataSet/processed.zip
```
**释放空间：2.5GB**

---

### 方案 2：进阶清理（可选）

**删除原始数据集，保留合并后的数据：**
```bash
rm -rf /root/DataSet/processed/amazon_books/
rm -rf /root/DataSet/processed/amazon_kindle/
rm -rf /root/DataSet/processed/goodreads/
```
**额外释放空间：~5GB**

**注意：** 删除后如需重新合并数据集，需要原始文件。

---

### 方案 3：保守清理

如果不确定是否需要某些文件，可以：

1. **移动到低成本存储**（如对象存储）
2. **压缩不常用的文件**

---

## 📋 当前各 Agent 需要的核心文件

以下文件**必须保留**：

| 文件 | 大小 | 用途 |
|------|------|------|
| `cf_item_factors.npy` | 23MB | 图书协同过滤向量 |
| `cf_book_id_index.json` | 3MB | 图书索引 |
| `cf_user_factors.npy` | 179MB | 用户协同过滤向量 |
| `cf_user_id_index.json` | 28MB | 用户索引 |
| `books_master_merged.jsonl` | 809MB | 合并后的图书数据 |
| `interactions_merged.jsonl` | 2.9GB | 合并后的交互数据 |
| `knowledge_graph.json` | 273MB | 知识图谱 |
| `kg_author_index.json` | 38MB | 作者索引 |
| `kg_genre_index.json` | 1MB | 类型索引 |

**核心数据总计：~4.2GB**

---

## 🎯 建议操作顺序

1. **立即删除** `processed.zip`（2.5GB）
2. 观察系统运行情况
3. 如仍需空间，考虑压缩或迁移原始数据集

---

**执行命令：**
```bash
# 安全删除压缩包
rm /root/DataSet/processed.zip

# 验证删除
ls -lh /root/DataSet/
```
