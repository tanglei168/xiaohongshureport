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
- [x] 使用真实登录会话验证“哇叽星球”与“清梧的爸爸”本地链路
- [x] 使用真实飞书配置完成四张多维表格的初始化与数据同步
- [x] 初始化当前目录独立 Git、配置目标 origin、提交并推送

## Sprint 验收记录

- `uv sync`：通过，CPython 3.12.14，锁定 35 个包。
- `uv run playwright install chromium`：通过，Chromium 140.0.7339.16 可启动。
- `uv run pytest`：24 项通过。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：24 个 Python 文件格式正确。
- `login` 已通过真实扫码验证，并确认 profile + storage state 能跨进程复用登录会话。
- 真实 `discover --keyword "哇叽星球"` 已完成：本轮发现 27 篇笔记、26 个账号并补全 27 篇详情；生成候选账号排行榜。
- 真实抓取“清梧的爸爸”已完成：主页滚动至稳定后发现 114 篇笔记，SQLite 中 114 篇详情已完成。
- 已生成 `reports/5b3de7ba6b58b70d04c0dd57.md` 与同名 JSON；可解析时间范围为 2022-10-24 至 2025-09-02。
- 根据真实 DOM 补充了搜索页和主页的临时详情导航；临时访问参数只在当前进程使用，不写 SQLite、报告或 Git。
- 真实页面显示有 43 篇缺少发布时间、1 篇缺少正文、全部 114 篇未展示分享数；均按 `null` 保存，没有猜测。
- 飞书真实初始化与同步已完成：账号 32 条、笔记 146 条、采集任务 13 条、运营报告 1 条；远端计数已通过 OpenAPI 回读核验。
- 飞书同步按稳定 ID upsert；真实同步中发生的读取超时已验证可安全续跑，并补充了超时、限流和服务端短暂错误的有限重试。

## 当前外部阻塞

- 无。
