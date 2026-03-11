# ACPs-app 启动指南

## ✅ 配置已更新

### 模型服务配置
- **Provider**: 阿里云百炼 (Bailian)
- **Base URL**: `https://coding.dashscope.aliyuncs.com/v1`
- **API Key**: `sk-sp-8e9adfc76cf2415a821ec052417875bd`
- **默认模型**: `qwen3.5-plus`

### 远程访问配置
- **监听地址**: `0.0.0.0:8100` (允许远程访问)
- **服务器 IP**: `172.24.247.19`

---

## 🚀 启动服务

### 方法 1：直接启动（推荐）

```bash
cd /root/WORK/SCHOOL/ACPs-app
python -m reading_concierge.reading_concierge
```

### 方法 2：后台启动

```bash
cd /root/WORK/SCHOOL/ACPs-app
nohup python -m reading_concierge.reading_concierge > reading_concierge.log 2>&1 &
```

### 方法 3：使用 tmux（推荐用于长期运行）

```bash
# 创建 tmux 会话
tmux new -s acps-app

# 启动服务
cd /root/WORK/SCHOOL/ACPs-app
python -m reading_concierge.reading_concierge

# 按 Ctrl+B 然后按 D 退出 tmux（服务继续运行）
```

---

## 🌐 访问方式

### 本地访问
```
http://localhost:8100
```

### 远程访问（服务器外设备）
```
http://172.24.247.19:8100
```

### 移动端访问
用手机浏览器打开：
```
http://172.24.247.19:8100
```

---

## 📋 服务信息

### 主要端点
| 端点 | 用途 |
|------|------|
| `/user_api` | 主要 API 端点（POST） |
| `/` | Web Demo 页面（GET） |

### Agent 配置
| Agent | 角色 | 状态 |
|-------|------|------|
| ReadingConcierge | Leader | ✅ 已配置 |
| ReaderProfile | Partner | ✅ 已配置 |
| BookContent | Partner | ✅ 已配置 |
| RecRanking | Partner | ✅ 已配置 |

---

## 🔧 环境变量

以下环境变量可在 `.env` 文件中配置：

```bash
# 模型服务
OPENAI_API_KEY=sk-sp-8e9adfc76cf2415a821ec052417875bd
OPENAI_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
OPENAI_MODEL=qwen3.5-plus

# 服务配置
READING_CONCIERGE_HOST=0.0.0.0
READING_CONCIERGE_PORT=8100

# 日志级别
READING_CONCIERGE_LOG_LEVEL=INFO
```

---

## ✅ 验证服务

启动后，可以通过以下方式验证：

### 1. 检查进程
```bash
ps aux | grep reading_concierge
```

### 2. 检查端口
```bash
netstat -tlnp | grep 8100
```

### 3. 访问 Web Demo
浏览器打开：`http://172.24.247.19:8100`

### 4. 测试 API
```bash
curl http://172.24.247.19:8100/user_api \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query":"test","user_profile":{},"history":[],"books":[],"constraints":{"scenario":"cold","top_k":3}}'
```

---

## 🎯 新增功能

### Agent 协作展示板块
Web Demo 页面已新增：
- ✅ 4 个 Agent 状态卡片
- ✅ 协作流程图
- ✅ 性能指标面板
- ✅ 响应式设计（支持移动端）

---

## ⚠️ 注意事项

1. **防火墙**: 确保服务器防火墙允许 8100 端口访问
   ```bash
   # 如果需要，开放端口
   sudo ufw allow 8100/tcp
   ```

2. **安全性**: 当前为开发环境，生产环境建议：
   - 启用 HTTPS
   - 添加认证机制
   - 限制访问 IP

3. **日志**: 服务日志输出到控制台，使用后台启动时会保存到 `reading_concierge.log`

---

## 📞 故障排查

### 问题 1：无法远程访问
**检查**:
- 服务器 IP 是否正确
- 防火墙是否开放 8100 端口
- 服务是否监听 `0.0.0.0`

### 问题 2：API 调用失败
**检查**:
- `.env` 文件中的 API Key 是否正确
- 网络连接是否正常
- 查看日志文件获取详细错误信息

### 问题 3：模型响应慢
**解决**:
- 检查网络连接
- 降低 `OPENAI_MAX_TOKENS` 值
- 使用更小的模型（如 `qwen3-coder-next`）

---

**最后更新**: 2026-03-10 13:05  
**配置版本**: Bailian Provider
