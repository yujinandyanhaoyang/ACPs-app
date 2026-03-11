# ACPs Personalized Reading Recsys

> 🤖 **Multi-Agent Collaboration System**  
> 最后更新：2026-03-10 | 版本：1.0.0

---

## 🚀 快速开始

### 远程访问（SSH 端口转发）

如果你无法直接访问服务器的 IP 地址，可以使用 SSH 端口转发：

```bash
# 在你的本地电脑上执行（不是服务器）
ssh -L 8100:localhost:8100 root@你的服务器IP

# 保持 SSH 连接，然后在浏览器打开
http://localhost:8100
```

**说明**：
- 这会将你本地的 8100 端口转发到服务器的 8100 端口
- SSH 连接保持期间，你可以随时访问 Web 界面
- 支持所有功能：Agent 协作展示、性能监控等

### 启动服务

```bash
cd /root/WORK/SCHOOL/ACPs-app

# 前台启动（开发调试）
python -m reading_concierge.reading_concierge

# 后台启动（生产环境）
nohup python -m reading_concierge.reading_concierge > reading_concierge.log 2>&1 &

# 查看日志
tail -f reading_concierge.log

# 停止服务
pkill -f reading_concierge
```

---

## 🤖 VennCLAW Agent 团队

VennCLAW 是一个智能 Agent 协作系统，包含以下成员：

| Agent | 角色 | 职责 | 模型 |
|-------|------|------|------|
| **ReadingConcierge** | 👑 Leader | 编排协调所有 Agent | qwen3.5-plus |
| **ReaderProfile** | 🎯 Partner | 读者画像分析 | qwen3.5-plus |
| **BookContent** | 📖 Partner | 书籍内容分析 | qwen3.5-plus |
| **RecRanking** | 📊 Partner | 推荐排序决策 | qwen3.5-plus |

### 协作流程

```
User Query → ReadingConcierge → ReaderProfile → BookContent → RecRanking → Result
```

---

## 📁 项目结构

```
ACPs-app/
├── reading_concierge/     # Leader Agent（编排器）
├── agents/                # Partner Agents
│   ├── reader_profile_agent/
│   ├── book_content_agent/
│   └── rec_ranking_agent/
├── acps_aip/             # ACPS 协议实现
├── services/             # 公共服务
├── web_demo/             # Web 界面
└── scripts/              # 工具脚本
```

---

## 🔧 配置

### 模型服务（阿里云百炼）

编辑 `.env` 文件：

```bash
OPENAI_API_KEY=sk-sp-8e9adfc76cf2415a821ec052417875bd
OPENAI_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
OPENAI_MODEL=qwen3.5-plus
```

### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| ReadingConcierge | 8100 | 主服务（Web Demo） |
| ReaderProfile | 8211 | 读者画像 Agent |
| BookContent | 8212 | 书籍内容 Agent |
| RecRanking | 8213 | 推荐排序 Agent |

---

## 📊 功能特性

### ✅ 已实现
- 多 Agent 协作架构
- ACPS 协议通信
- mTLS 安全认证
- Web Demo 界面
- Agent 协作状态可视化
- 性能指标监控

### 🚧 计划中
- 实时日志查看
- Agent 性能分析
- 历史会话管理
- 批量推荐处理

---

## 📖 文档

- [启动指南](STARTUP_GUIDE.md)
- [远程访问](REMOTE_ACCESS.md)
- [工程分析报告](docs/feishu-imports/01-工程结构分析报告.md)
- [Agent 协作分析](docs/feishu-imports/02-Agent 协作分析报告.md)
- [ACPS 协议分析](docs/feishu-imports/03-ACPS 协议分析报告.md)

---

## 🛠 mTLS Development Setup (P7)

### 1) Generate local dev certificates

- Windows (PowerShell):

```powershell
./scripts/gen_dev_certs.ps1
```

- Linux/Mac:

```bash
bash ./scripts/gen_dev_certs.sh
```

Both scripts generate certificates under `certs/` by default:
- `ca.crt`, `ca.key`
- `reading_concierge_001.crt/.key`
- `reader_profile_agent_001.crt/.key`
- `book_content_agent_001.crt/.key`
- `rec_ranking_agent_001.crt/.key`
- plus `reader_profile`, `book_content`, `rec_ranking` cert pairs for existing example config files.

### 2) Enable mTLS startup

Set environment variables before launching any service:

```powershell
$env:AGENT_MTLS_ENABLED = "true"
$env:AGENT_MTLS_CERT_DIR = "<absolute_path_to>/certs"
```

Optional per-service config path overrides:
- `READING_CONCIERGE_MTLS_CONFIG_PATH`
- `READER_PROFILE_MTLS_CONFIG_PATH`
- `BOOK_CONTENT_MTLS_CONFIG_PATH`
- `REC_RANKING_MTLS_CONFIG_PATH`

### 3) Run services directly (uvicorn from module `__main__`)

```powershell
python -m reading_concierge.reading_concierge
python -m agents.reader_profile_agent.profile_agent
python -m agents.book_content_agent.book_content_agent
python -m agents.rec_ranking_agent.rec_ranking_agent
```

When `AGENT_MTLS_ENABLED=true`, services start with TLS and require client certs.

### 4) Verify HTTPS endpoint with dev CA

Example check (replace host/port as needed):

```bash
curl --cacert certs/ca.crt https://localhost:8100/demo/status
```

If mutual TLS client auth is required by the service, also provide client cert/key:

```bash
curl --cacert certs/ca.crt --cert certs/reader_profile.crt --key certs/reader_profile.key https://localhost:8211/acs
```
