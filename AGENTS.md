# AGENTS.md

本文件是 xiaohongshureport 项目长期有效的开发规则，适用于所有贡献者与编码代理。

## 产品目标

- 本项目是单机运行的“小红书账号运营研究工具”。
- 当前核心链路：关键词/账号 → 公开内容采集 → 账号与笔记归档 → SQLite → 飞书多维表格 → 事实型账号运营报告。
- 第一优先级是让真实、可验证的数据链路跑通；不做 SaaS、网页 UI、复杂 Agent、消息队列、云部署或过度架构。

## 技术栈

- Python 3.12+，使用 uv 管理 Python 与依赖。
- Playwright 有头 Chromium、Pydantic v2、pydantic-settings、httpx、Loguru、SQLite、Typer、Rich、pytest。
- HTML 解析可使用 BeautifulSoup4 与 lxml。
- 不引入 Selenium、Scrapy、Redis、PostgreSQL、Celery、FastAPI 或前端框架。

## 数据结构原则

- 数据模型必须账号优先：Account 是一级实体，Note 是 Account 下面的二级实体。
- 所有 Account 和 Note 必须使用从平台 ID 或规范化 URL 派生的稳定去重 ID。
- 所有采集数据必须保存 `source_url`；模型中的主页或笔记 URL 不能省略来源语义。
- 页面未展示的数据保存为 `null`，不得猜测；数值 `0` 与缺失值 `null` 必须严格区分。
- 所有时间字段统一保存 ISO 8601；无法可靠解析的时间保存为 `null` 并保留调试信息。
- 原始采集事实与统计、规则判断、推断必须分开存储和呈现。
- 不允许把推断结果伪装成原始事实。报告必须明确使用“当前采集数据中观察到”“统计结果”等限定语。
- SQLite 写入必须有唯一约束、索引、版本迁移和幂等 upsert，重复运行不得制造大量重复记录。

## 浏览器与采集合规

- 只处理当前登录用户通过正常页面可见的公开内容。
- 不要求或接收 Cookie 字符串，不读取用户正常 Chrome 的私人 profile。
- Playwright 使用独立的 `.data/xhs-profile/` persistent context 和正常有头浏览器。
- secrets、Cookie、浏览器 session、数据库、运行日志和采集产物禁止进入 Git。
- 不做验证码绕过，不做反爬绕过，不做 stealth hack；遇到验证码或明确阻止时停止并提示用户。
- 访问必须限速，详情页默认随机等待 1.5～3 秒，禁止高并发轰炸。
- 主页与搜索页滚动停止条件基于页面高度和稳定 ID 集合，不得只写死滚动次数。
- 每发现一个新 Note 就立即 upsert 到 SQLite，以支持故障恢复和 `--resume`。

## Parser 与调试规则

- 小红书 selector 集中放在 `src/xiaohongshureport/xhs/selectors.py`，不得散落在业务代码中。
- selector 优先使用稳定属性、文本、链接结构和 URL pattern，最后才使用易变 CSS class。
- 页面结构变化或 parser 失败时必须保存 `.debug/<timestamp>/screenshot.png`、`page.html`、`url.txt`。
- 日志必须指出失败的 parser 和页面 URL，不得静默返回空数据。
- pytest 不依赖真实小红书，页面解析使用 fixture HTML。

## 配置与安全

- 所有本地数据默认位于 `.data/`，报告位于 `reports/`，调试产物位于 `.debug/`。
- 飞书凭据只从环境变量或未提交的 `.env` 读取，绝不写入源码、测试 fixture、日志或 Git。
- 任何新增敏感配置都必须同步加入 `.env.example` 的空值模板和 `.gitignore`。

## 工作流程与质量

1. 开始前阅读本文件和 `TASK.md`，检查当前仓库状态，保护用户已有改动。
2. 只做当前 Sprint 所需的最小可运行实现，优先端到端链路，不做无意义重构。
3. 每完成一个功能就更新 `TASK.md` 对应 checkbox。
4. 每个阶段完成后运行相关 pytest；提交前运行完整测试、Ruff lint 和格式检查。
5. 不通过跳过测试、弱化断言、吞掉异常或伪造数据制造“通过”。
6. README 必须始终保留从零开始、真实可执行且与当前代码一致的启动说明。
7. 若验证因扫码、验证码、外部凭据或平台阻止而无法继续，准确记录已完成验证和唯一阻塞点。

## Git 规则

- 只操作当前项目自己的 Git 仓库，禁止修改其他 repository。
- 禁止 force push，禁止提交 `.data/`、`.debug/`、`.env`、浏览器 profile 或任何 secret。
- 提交前检查 `git status` 和 `git diff`。

## 指令优先级

冲突时依次遵循：用户明确要求、当前目录树中更具体的 `AGENTS.md`、本文件、项目已有惯例。
