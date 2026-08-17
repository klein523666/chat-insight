# Chat Insight · 群聊情报

Multi-platform group intelligence and AI report system.

Chat Insight 实时采集你有权查看、且明确启用的 QQ 群与 Telegram
群/超级群/频道消息，统一保存、统计和 AI 分析，并按小时或自然日自动发送
飞书报告。

> **状态：v0.1.0 开发版。** 自动化测试和 Telegram 真实闭环已通过；发布前仍需
> 完成专用 QQ、LLM、飞书、报告和完整重启验收。2C4G VPS 性能尚未验证，不会被
> 描述为“已验证”。

## 功能

- Telegram 个人账号：QR、手机号、验证码、2FA、邮箱验证、Session 持久化。
- Telegram 群、超级群、频道发现；默认关闭；实时更新与 3 小时历史补采。
- QQ 个人号：NapCat + OneBot v11 + AstrBot 薄插件，SQLite Outbox 防短暂断线丢失。
- SQLite WAL 单写者、批量写入、跨平台去重和 90 天默认消息保留策略。
- 小时报、日报、QQ+Telegram 混合报告；确定性统计与结构化 AI 分析。
- OpenAI-compatible Chat Completions，结构化输出降级，引用 message ID 回填。
- 多飞书 Custom Bot Target、签名、卡片分片与有界重试。
- 中文 React WebUI、一次性 Setup Token、Argon2id、Session、CSRF、密钥加密。

## 快速开始（Linux amd64）

需要 Docker Engine、Docker Compose v2、OpenSSL，以及用户自己的 Telegram
API ID/API Hash。QQ 功能还受 NapCat 上游非商业许可约束。

```bash
git clone https://github.com/klein523666/chat-insight.git
cd chat-insight
sh deploy/init.sh
cd deploy
docker compose up -d
```

通过 SSH Tunnel 打开仅绑定本机的 WebUI：

```bash
ssh -L 8080:127.0.0.1:8080 user@your-server
```

浏览器访问 `http://127.0.0.1:8080`，使用初始化脚本打印的一次性 Setup Token
创建管理员，然后依次配置 Telegram、消息源、AI、飞书和报告任务。

### QQ 可选 Profile

首次配置时临时映射 NapCat/AstrBot 管理端口：

```bash
docker compose -f compose.yml -f compose.admin.yml --profile qq up -d
ssh -L 6185:127.0.0.1:6185 -L 6099:127.0.0.1:6099 user@your-server
```

完成 QQ 扫码、NapCat → AstrBot OneBot v11 连接和插件确认后，改用基础
`compose.yml` 重建，移除管理端口映射：

```bash
docker compose --profile qq up -d
```

## 开发

```bash
python -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
pip install --no-deps -e .
pytest
ruff check src tests integrations

cd apps/web
corepack enable
pnpm install
pnpm run build
```

后端开发入口为 `python -m chat_insight.main`；前端 `pnpm dev` 会代理到
`127.0.0.1:8080`。所有平台凭据必须使用本地环境变量/secret，禁止加入 Git。

## 安全、隐私与许可

- WebUI 默认只绑定 `127.0.0.1`；生产使用 HTTPS 反向代理或 SSH Tunnel。
- 所有 Source 默认关闭；没有作者服务器、Telemetry 或公共 API 凭据。
- 聊天内容只会发送给用户配置的 AI Provider 和飞书目标。
- Core/Web/Telegram Collector 为 MIT；AstrBot Adapter 为 AGPL-3.0-only。
- TDLib 为 Boost-1.0。NapCat 有独立的有限、非商业许可，本项目不复制或改包。

参见 [SECURITY.md](SECURITY.md)、[PRIVACY.md](PRIVACY.md) 和
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

## English

Chat Insight is a self-hosted QQ and Telegram group intelligence system. It
stores only explicitly enabled sources, computes deterministic statistics,
optionally runs structured AI analysis, and sends hourly/daily Feishu reports.

The initial Docker target is Linux amd64. Run `sh deploy/init.sh`, start
`docker compose` from `deploy/`, and reach the loopback-only UI through an SSH
tunnel or HTTPS reverse proxy. You must supply your own Telegram, QQ, model,
and Feishu credentials. No telemetry or author-operated service is used.

Chat Insight is independent and is not affiliated with Telegram, Tencent,
QQ, Feishu, ByteDance, AstrBot, or NapCat.
