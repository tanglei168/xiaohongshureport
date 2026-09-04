"""Feishu Bitable schema initialization and idempotent record synchronization."""

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from xiaohongshureport.config import Settings
from xiaohongshureport.models import Account, CrawlRun, Note
from xiaohongshureport.storage import Database

FEISHU_API = "https://open.feishu.cn/open-apis"
MAX_REQUEST_ATTEMPTS = 4
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

ACCOUNT_FIELDS = (
    "账号ID",
    "昵称",
    "主页URL",
    "小红书号",
    "简介",
    "粉丝数",
    "关注数",
    "获赞与收藏",
    "IP属地",
    "来源关键词",
    "收录笔记数",
    "最早笔记时间",
    "最近笔记时间",
    "累计点赞",
    "累计收藏",
    "累计评论",
    "更新时间",
    "运营报告",
)

NOTE_FIELDS = (
    "笔记ID",
    "账号ID",
    "账号昵称",
    "标题",
    "正文",
    "笔记URL",
    "封面",
    "发布时间",
    "点赞",
    "收藏",
    "评论",
    "分享",
    "标签",
    "来源关键词",
    "抓取时间",
)

REPORT_FIELDS = ("账号ID", "账号昵称", "主页URL", "生成时间", "运营报告", "结构化报告")
RUN_FIELDS = (
    "任务ID",
    "模式",
    "目标",
    "状态",
    "开始时间",
    "结束时间",
    "账号数",
    "笔记数",
    "完成详情数",
    "错误",
)

NUMBER_FIELDS = {
    "粉丝数",
    "关注数",
    "获赞与收藏",
    "收录笔记数",
    "累计点赞",
    "累计收藏",
    "累计评论",
    "点赞",
    "收藏",
    "评论",
    "分享",
    "账号数",
    "笔记数",
    "完成详情数",
}


class FeishuConfigurationError(ValueError):
    pass


class FeishuApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeishuTables:
    account: str
    note: str
    report: str
    run: str

    def as_dict(self) -> dict[str, str]:
        return {
            "FEISHU_ACCOUNT_TABLE_ID": self.account,
            "FEISHU_NOTE_TABLE_ID": self.note,
            "FEISHU_REPORT_TABLE_ID": self.report,
            "FEISHU_RUN_TABLE_ID": self.run,
        }


def account_payload(
    account: Account, notes: list[Note], report_markdown: str | None
) -> dict[str, Any]:
    dated = sorted(note.publish_time for note in notes if note.publish_time)
    return _without_none(
        {
            "账号ID": account.account_id,
            "昵称": account.nickname,
            "主页URL": account.profile_url,
            "小红书号": account.xhs_number,
            "简介": account.bio,
            "粉丝数": account.follower_count,
            "关注数": account.following_count,
            "获赞与收藏": account.likes_collections_count,
            "IP属地": account.ip_location,
            "来源关键词": account.source_keyword,
            "收录笔记数": len(notes),
            "最早笔记时间": dated[0] if dated else None,
            "最近笔记时间": dated[-1] if dated else None,
            "累计点赞": sum(note.like_count or 0 for note in notes),
            "累计收藏": sum(note.collect_count or 0 for note in notes),
            "累计评论": sum(note.comment_count or 0 for note in notes),
            "更新时间": account.last_seen_at,
            "运营报告": report_markdown,
        }
    )


def note_payload(note: Note, account_nickname: str | None) -> dict[str, Any]:
    return _without_none(
        {
            "笔记ID": note.note_id,
            "账号ID": note.account_id,
            "账号昵称": account_nickname,
            "标题": note.title,
            "正文": note.content,
            "笔记URL": note.note_url,
            "封面": note.cover_url,
            "发布时间": note.publish_time,
            "点赞": note.like_count,
            "收藏": note.collect_count,
            "评论": note.comment_count,
            "分享": note.share_count,
            "标签": "、".join(note.hashtags),
            "来源关键词": note.source_keyword,
            "抓取时间": note.crawl_time,
        }
    )


def run_payload(run: CrawlRun) -> dict[str, Any]:
    return _without_none(
        {
            "任务ID": run.run_id,
            "模式": run.mode,
            "目标": run.target,
            "状态": run.status,
            "开始时间": run.started_at,
            "结束时间": run.finished_at,
            "账号数": run.accounts_found,
            "笔记数": run.notes_found,
            "完成详情数": run.notes_completed,
            "错误": run.error,
        }
    )


def _without_none(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


class FeishuClient:
    """Minimal official OpenAPI client; no credentials are persisted or logged."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        missing = [
            name
            for name, value in (
                ("FEISHU_APP_ID", settings.feishu_app_id),
                ("FEISHU_APP_SECRET", settings.feishu_app_secret),
                ("FEISHU_BITABLE_APP_TOKEN", settings.feishu_bitable_app_token),
            )
            if not value
        ]
        if missing:
            raise FeishuConfigurationError("缺少飞书配置：" + ", ".join(missing))
        self.settings = settings
        self.app_token = settings.feishu_bitable_app_token or ""
        self.client = httpx.Client(base_url=FEISHU_API, timeout=30, transport=transport)
        self._access_token: str | None = None

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "FeishuClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def access_token(self) -> str:
        if self._access_token:
            return self._access_token
        response = self._send_with_retry(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
        )
        payload = self._response_data(response, unwrap=False)
        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuApiError("飞书鉴权响应未包含 tenant_access_token")
        self._access_token = str(token)
        return self._access_token

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.access_token()}"
        response = self._send_with_retry(method, path, headers=headers, **kwargs)
        return self._response_data(response)

    def _send_with_retry(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Retry bounded transient failures without retrying ordinary API errors."""

        last_error: httpx.TransportError | None = None
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            try:
                response = self.client.request(method, path, **kwargs)
            except httpx.TransportError as error:
                last_error = error
                if attempt == MAX_REQUEST_ATTEMPTS - 1:
                    break
            else:
                if response.status_code not in TRANSIENT_STATUS_CODES:
                    return response
                if attempt == MAX_REQUEST_ATTEMPTS - 1:
                    return response
            time.sleep(2**attempt)
        raise FeishuApiError(
            f"飞书网络请求连续失败（已重试 {MAX_REQUEST_ATTEMPTS} 次）："
            f"{type(last_error).__name__ if last_error else '未知网络错误'}"
        ) from last_error

    @staticmethod
    def _response_data(response: httpx.Response, *, unwrap: bool = True) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as error:
            raise FeishuApiError(f"飞书返回非 JSON 响应：HTTP {response.status_code}") from error
        if response.is_error or payload.get("code", 0) != 0:
            raise FeishuApiError(
                f"飞书 API 失败：HTTP {response.status_code}, code={payload.get('code')}, "
                f"message={payload.get('msg') or payload.get('message')}"
            )
        if unwrap:
            data = payload.get("data", {})
            return data if isinstance(data, dict) else {}
        return payload

    def initialize_tables(self) -> FeishuTables:
        configured = {
            "account": self.settings.feishu_account_table_id,
            "note": self.settings.feishu_note_table_id,
            "report": self.settings.feishu_report_table_id,
            "run": self.settings.feishu_run_table_id,
        }
        specs = {
            "account": ("账号", ACCOUNT_FIELDS),
            "note": ("笔记", NOTE_FIELDS),
            "report": ("运营报告", REPORT_FIELDS),
            "run": ("采集任务", RUN_FIELDS),
        }
        resolved: dict[str, str] = {}
        for key, (name, fields) in specs.items():
            table_id = configured[key] or self._find_or_create_table(name)
            self._ensure_fields(table_id, fields)
            resolved[key] = table_id
        return FeishuTables(**resolved)

    def _find_or_create_table(self, name: str) -> str:
        data = self.request(
            "GET", f"/bitable/v1/apps/{self.app_token}/tables", params={"page_size": 100}
        )
        for table in data.get("items", []):
            if table.get("name") == name:
                return str(table["table_id"])
        created = self.request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables",
            json={"table": {"name": name}},
        )
        table = created.get("table", created)
        table_id = table.get("table_id")
        if not table_id:
            raise FeishuApiError(f"创建飞书数据表后未获得 table_id：{name}")
        return str(table_id)

    def _ensure_fields(self, table_id: str, field_names: tuple[str, ...]) -> None:
        data = self.request(
            "GET",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
            params={"page_size": 100},
        )
        existing = {field.get("field_name") for field in data.get("items", [])}
        for field_name in field_names:
            if field_name in existing:
                continue
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                json={"field_name": field_name, "type": 2 if field_name in NUMBER_FIELDS else 1},
            )

    def upsert_record(
        self, table_id: str, unique_field: str, unique_value: str, fields: dict[str, Any]
    ) -> str:
        path = f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        search = self.request(
            "POST",
            f"{path}/search",
            params={"page_size": 20},
            json={
                "filter": {
                    "conjunction": "and",
                    "conditions": [
                        {
                            "field_name": unique_field,
                            "operator": "is",
                            "value": [unique_value],
                        }
                    ],
                }
            },
        )
        items = search.get("items", [])
        if items:
            record_id = str(items[0]["record_id"])
            self.request("PUT", f"{path}/{record_id}", json={"fields": fields})
            return record_id
        created = self.request("POST", path, json={"fields": fields})
        record = created.get("record", created)
        record_id = record.get("record_id")
        if not record_id:
            raise FeishuApiError(f"创建记录后未获得 record_id：{unique_field}={unique_value}")
        return str(record_id)


def sync_database(database: Database, client: FeishuClient, tables: FeishuTables) -> dict[str, int]:
    reports = {str(item["account_id"]): item for item in database.list_reports()}
    accounts = database.list_accounts()
    note_total = 0
    for account in accounts:
        notes = database.list_notes(account.account_id)
        report = reports.get(account.account_id)
        client.upsert_record(
            tables.account,
            "账号ID",
            account.account_id,
            account_payload(account, notes, str(report["markdown"]) if report else None),
        )
        for note in notes:
            client.upsert_record(
                tables.note,
                "笔记ID",
                note.note_id,
                note_payload(note, account.nickname),
            )
            note_total += 1
    for run in database.list_crawl_runs():
        client.upsert_record(tables.run, "任务ID", run.run_id, run_payload(run))
    for account_id, report in reports.items():
        account = database.get_account(account_id)
        fields = _without_none(
            {
                "账号ID": account_id,
                "账号昵称": account.nickname if account else None,
                "主页URL": account.profile_url if account else report["source_url"],
                "生成时间": report["generated_at"],
                "运营报告": report["markdown"],
                "结构化报告": report["report_json"],
            }
        )
        client.upsert_record(tables.report, "账号ID", account_id, fields)
    return {
        "accounts": len(accounts),
        "notes": note_total,
        "runs": len(database.list_crawl_runs()),
        "reports": len(reports),
    }
