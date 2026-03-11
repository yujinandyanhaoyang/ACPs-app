# 远程访问 ACPs-app 解决方案

## 🚨 当前状态

- ✅ 服务已启动并正常运行
- ✅ 监听地址：`0.0.0.0:8100`
- ❌ 服务器是内网 IP（172.24.247.19），无法直接从外部访问

---

## 💡 解决方案

### 方案 1：SSH 反向隧道（推荐，无需额外工具）

如果你有另一台**有公网 IP 的服务器**（如阿里云 ECS），可以使用 SSH 反向隧道：

```bash
# 在你的公网服务器上执行（假设公网 IP 是 1.2.3.4）
ssh -R 8100:localhost:8100 root@1.2.3.4

# 然后访问 http://1.2.3.4:8100 即可
```

### 方案 2：使用内网穿透工具

#### 选项 A: Ngrok（简单，但有流量限制）

```bash
# 1. 注册 ngrok: https://ngrok.com
# 2. 下载并安装
# 3. 运行:
ngrok http 8100
```

#### 选项 B: Cloudflare Tunnel（免费，稳定）

```bash
# 1. 安装 cloudflared
curl -L --output cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared

# 2. 登录 Cloudflare Zero Trust (https://dash.teams.cloudflare.com)
# 3. 创建 Tunnel
# 4. 运行:
./cloudflared tunnel --url http://localhost:8100
```

#### 选项 C: 花生壳（国内，付费）

```bash
# 访问 https://hsk.oray.com
# 注册并下载客户端
# 配置内网穿透
```

### 方案 3：使用 Cloudflare Workers 代理（高级）

如果你有 Cloudflare 账号，可以创建一个 Worker 代理到你的服务。

### 方案 4：使用 frp（需要公网 VPS）

```bash
# 1. 在公网 VPS 上运行 frps
# 2. 在本地运行 frpc
# 3. 配置端口转发
```

---

## 🎯 快速测试（当前可用）

### 在服务器本地测试
```bash
# 使用 curl 测试
curl http://localhost:8100

# 或者使用浏览器（如果你有服务器桌面环境）
# 打开 http://localhost:8100
```

### 使用 tmux 保持服务运行
```bash
# 创建 tmux 会话
tmux new -s acps-demo

# 启动服务
cd /root/WORK/SCHOOL/ACPs-app
python -m reading_concierge.reading_concierge

# 按 Ctrl+B 然后按 D 退出 tmux
```

---

## 📋 推荐方案

**如果你有公网 VPS** → 使用 SSH 反向隧道（方案 1）  
**如果你没有公网 VPS** → 使用 Ngrok（方案 2A）  
**如果你想要稳定免费** → 使用 Cloudflare Tunnel（方案 2B）  
**如果你愿意付费** → 使用花生壳（方案 2C）

---

## 🔧 需要帮助？

告诉我你选择哪个方案，我可以帮你完成配置！

---

**最后更新**: 2026-03-10 13:15
