# TASK.md

## 当前 Sprint：账号研究 MVP

- [x] 审计现有仓库、运行环境与 Git 边界
- [x] 更新长期开发规则与 Sprint 清单
- [x] 调整为 `xiaohongshureport` 单一 Python 包并补齐依赖
- [x] 实现 Account、Note、关键词关系、采集任务和报告模型
- [x] 实现 SQLite migration、索引与幂等 upsert
- [x] 实现数字、时间、账号、笔记卡片和笔记详情 parser
- [x] 实现 parser 失败时的 screenshot、HTML、URL 调试产物
- [x] 实现 Playwright persistent context 与 `xhs-report login`
- [x] 实现账号完整滚动、即时落库、详情限速采集与 `--resume`
- [x] 实现关键词 discover、关系统计和候选账号排名
- [x] 实现 Markdown + JSON 事实型账号运营报告
- [x] 实现飞书配置检查、字段初始化、payload 和幂等同步
- [x] 补齐离线 HTML fixture 与所有核心单元测试
- [x] 重写从零可执行的 README 与 `.env.example`
- [x] 执行 `uv sync` 与安装 Playwright Chromium
- [x] 执行完整 pytest、Ruff lint 和格式检查
- [ ] 使用真实登录会话验证“哇叽星球”与“清梧的爸爸”链路
- [x] 初始化当前目录独立 Git、配置目标 origin、提交并推送

## Sprint 验收记录

- `uv sync`：通过，CPython 3.12.14，锁定 35 个包。
- `uv run playwright install chromium`：通过，Chromium 140.0.7339.16 可启动。
- `uv run pytest`：18 项通过。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：24 个 Python 文件格式正确。
- 真实 `discover --keyword "哇叽星球"` 已运行；平台返回安全限制错误 `300012`，未获得账号或笔记数据。
- 根据真实失败产物新增严格登录状态和平台阻止检测；没有尝试绕过或重复请求。

## 当前外部阻塞

- 小红书返回“IP存在风险，请切换可靠网络环境后重试”（错误码 `300012`）。
- 未配置飞书凭据，因此未执行真实飞书写入；payload 与幂等客户端已通过离线测试。
