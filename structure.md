# 项目结构

```text
chat-insight/
├── src/chat_insight/                 # Core、Server、Telegram Collector
├── apps/web/                         # React WebUI
├── integrations/astrbot_plugin_chat_insight/
├── migrations/                       # Alembic migrations
├── deploy/                           # Compose、初始化脚本、反向代理示例
├── docs/                             # 技术设计、安装与运维
├── tests/                            # Python unit/integration tests
├── uv.lock                           # Python 全平台解析锁
├── requirements.lock                 # 生产镜像哈希锁
├── requirements-dev.lock             # CI/开发哈希锁
├── agents.md                         # 核心记忆与规范
├── progress.md                       # 当前进度
├── findings.md                       # 调研与踩坑
└── task_plan.md                      # 大型任务分解
```

目录随实现同步更新，不在这里记录易过期的逐文件清单。
