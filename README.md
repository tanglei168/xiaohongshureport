# xiaohongshureport

单机运行的小红书账号运营研究工具。它使用独立的 Playwright 浏览器 profile，在当前登录用户正常可见的公开页面中发现账号、归档笔记，将事实保存到 SQLite，并生成 Markdown/JSON 账号运营报告；配置飞书后可幂等同步到多维表格。

项目不读取私人 Chrome profile，不接收 Cookie 字符串，不绕过验证码、登录限制或反爬机制。

## 1. 环境与安装

要求 Python 3.12+。依赖和虚拟环境统一由 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理。

```bash
# macOS/Linux 安装 uv（也可使用官方提供的其他安装方式）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 在项目根目录安装锁定依赖
uv sync

# 安装 Playwright Chromium
uv run playwright install chromium

# 创建本地配置；.env 不会进入 Git
cp .env.example .env
```

本仓库将 Playwright 固定为 `1.55.0`，因为项目当前验证机器为 macOS 12；该版本的 Chromium 已在本机完成安装与启动验证。

## 2. 登录

```bash
uv run xhs-report login
```

命令会启动正常的有头 Chromium。请在窗口中自行扫码登录；成功后 session 只保存在 `.data/xhs-profile/`。后续命令会复用此 profile。不要同时启动两个使用同一 profile 的任务。

如果 session 失效，再次执行 `login`。程序不会读取系统 Chrome 的用户目录。

## 3. 搜索发现

真实研究示例：

```bash
uv run xhs-report discover --keyword "哇叽星球"
```

命令持续滚动搜索结果，建立 Account、Note 和 AccountKeywordRelation，写入 SQLite，并打印候选账号排行榜。排名由相关笔记数、当前可见互动量和可计算时间跨度的简单公式产生，不使用 AI。

默认最多收集 100 篇搜索结果，可调整：

```bash
uv run xhs-report discover --keyword "哇叽星球" --max-notes 200
```

## 4. 抓取账号

真实测试账号“清梧的爸爸”：

```bash
uv run xhs-report crawl-account \
  --url "https://www.xiaohongshu.com/user/profile/5b3de7ba6b58b70d04c0dd57" \
  --all
```

程序会滚动主页，直到页面高度和 note ID 集合连续 4 次均无变化。发现新笔记时立即写入 SQLite，之后按 1.5～3 秒随机间隔串行访问详情页。

可用选项：

```bash
# 最多抓 20 篇；未指定 --all/--max-notes 时默认 50 篇
uv run xhs-report crawl-account --url URL --max-notes 20

# 跳过已经完成详情采集的笔记
uv run xhs-report crawl-account --url URL --all --resume

# 默认有头；调试之外确有需要时可显式无头运行
uv run xhs-report crawl-account --url URL --all --headless
```

`--all` 与 `--max-notes` 不能同时使用。

## 5. 生成账号报告

抓取命令结束时会显示稳定账号 ID。使用它生成报告：

```bash
uv run xhs-report report --account 5b3de7ba6b58b70d04c0dd57
```

输出：

- `reports/<account_id>.md`
- `reports/<account_id>.json`
- SQLite `reports` 表中的最新报告

报告包含账号概况、月度时间线、起号阶段、规则关键词主题变化、爆款、产品词首次观察、发布节奏、关键词关系和数据完整性。报告只表述当前采集事实和明确标注的统计规则，不把推断写成事实。

## 6. 飞书配置

在飞书开放平台创建自建应用，给应用配置多维表格读写权限，并确保目标多维表格已授权给该应用。然后在本地 `.env` 填写：

```dotenv
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BITABLE_APP_TOKEN=

# 可选；未填写时 feishu init 会按名称查找或创建表
FEISHU_ACCOUNT_TABLE_ID=
FEISHU_NOTE_TABLE_ID=
FEISHU_REPORT_TABLE_ID=
FEISHU_RUN_TABLE_ID=
```

检查凭据、创建/检查表和字段，并打印最终 table ID：

```bash
uv run xhs-report feishu init
```

将账号、笔记、采集任务和报告同步到多维表格：

```bash
uv run xhs-report feishu sync
```

同步按“账号ID”“笔记ID”“任务ID”进行查询后更新或创建；重复执行不会有意创建重复记录。

## 7. 本地数据位置

| 路径 | 内容 | 是否进入 Git |
| --- | --- | --- |
| `.data/xhs_report.db` | SQLite 数据库 | 否 |
| `.data/xhs-profile/` | Playwright 登录 session | 否 |
| `reports/` | Markdown 与 JSON 报告 | 否 |
| `.debug/<timestamp>/` | parser 失败的截图、HTML、URL | 否 |
| `.env` | 本地配置与飞书 secret | 否 |

SQLite 当前包含 `accounts`、`notes`、`keywords`、`note_keywords`、`account_keyword_relations`、`crawl_runs`、`reports` 与 `schema_migrations`。写入使用唯一约束和 upsert。

## 8. 开发与测试

pytest 全部使用本地 fixture HTML，不访问真实小红书：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 9. 常见问题

### 提示登录会话不存在或已失效

执行 `uv run xhs-report login`，在项目 Chromium 窗口中重新扫码。不要手工复制 Cookie。

### 浏览器 profile 正在使用

关闭其他由本项目打开的 Chromium，再重新运行。一个 persistent profile 同一时间只能被一个浏览器进程占用。

### 页面没有抓到数据或 parser 报错

查看日志中的 parser 名称，并检查最新的 `.debug/<timestamp>/screenshot.png`、`page.html`、`url.txt`。小红书页面变化后应先用这些真实产物调整 `src/xiaohongshureport/xhs/selectors.py`，不要凭空添加 selector。

### 遇到验证码或访问限制

停止自动化，在有头浏览器中按平台正常流程处理。项目不会自动绕过验证码或限制。

### 某些字段是 null

这表示当前页面没有展示或 parser 无法可靠读取。程序不会用 `0` 或猜测值替代缺失事实。

### 飞书返回权限错误

确认应用已启用多维表格权限、版本已发布，并且目标多维表格已授权给该应用。运行 `uv run xhs-report feishu init` 获取具体 API 错误和最终 table ID。
