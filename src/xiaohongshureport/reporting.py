"""Deterministic fact report generation without model-generated conclusions."""

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from xiaohongshureport.models import Account, Note
from xiaohongshureport.storage import Database
from xiaohongshureport.utils import iso_now

TOPIC_SEEDS = (
    "RAZ",
    "牛津树",
    "英语启蒙",
    "识字",
    "古诗",
    "数学",
    "纪录片",
    "学习计划",
    "小程序",
    "学习资源",
)

PRODUCT_TERMS = (
    "小程序",
    "宝藏小程序",
    "学习计划",
    "打卡",
    "会员",
    "课程",
    "APP",
    "购买",
    "免费",
    "RAZ",
    "牛津树",
)


def _date(note: Note) -> datetime | None:
    if not note.publish_time:
        return None
    try:
        return datetime.fromisoformat(note.publish_time)
    except ValueError:
        return None


def _text(note: Note) -> str:
    return " ".join(filter(None, [note.title, note.content, *note.hashtags]))


def _note_fact(note: Note, follower_count: int | None = None) -> dict[str, object]:
    interaction_rate = None
    if follower_count and follower_count > 0:
        interaction_rate = round(note.total_engagement / follower_count, 6)
    return {
        "note_id": note.note_id,
        "date": note.publish_time,
        "title": note.title,
        "url": note.note_url,
        "like_count": note.like_count,
        "collect_count": note.collect_count,
        "comment_count": note.comment_count,
        "share_count": note.share_count,
        "total_engagement": note.total_engagement,
        "interaction_rate": interaction_rate,
        "keywords": [seed for seed in TOPIC_SEEDS if seed.casefold() in _text(note).casefold()],
    }


def build_report(
    account: Account, notes: list[Note], keyword_notes: list[tuple[str, Note]]
) -> dict[str, object]:
    """Build a machine-readable report containing facts and labeled statistics."""

    dated = sorted(
        (note for note in notes if _date(note)), key=lambda note: _date(note) or datetime.min
    )
    monthly: dict[str, list[Note]] = defaultdict(list)
    weekly: Counter[str] = Counter()
    for note in dated:
        parsed = _date(note)
        if parsed is None:
            continue
        monthly[parsed.strftime("%Y-%m")].append(note)
        iso_year, iso_week, _ = parsed.isocalendar()
        weekly[f"{iso_year}-W{iso_week:02d}"] += 1

    timeline = []
    for month, month_notes in sorted(monthly.items()):
        likes = [note.like_count for note in month_notes if note.like_count is not None]
        topic_counts = Counter(
            seed
            for note in month_notes
            for seed in TOPIC_SEEDS
            if seed.casefold() in _text(note).casefold()
        )
        timeline.append(
            {
                "month": month,
                "note_count": len(month_notes),
                "average_likes": round(mean(likes), 2) if likes else None,
                "highest_likes": max(likes) if likes else None,
                "topic_keywords": dict(topic_counts),
                "topic_share": {
                    topic: round(count / len(month_notes), 4)
                    for topic, count in topic_counts.items()
                },
            }
        )

    monthly_counts = {item["month"]: item["note_count"] for item in timeline}
    average_monthly = mean(monthly_counts.values()) if monthly_counts else 0
    phases = []
    for month, count in monthly_counts.items():
        if average_monthly == 0:
            phase = "无可计算数据"
        elif count >= average_monthly * 1.5:
            phase = "增长期"
        elif count <= average_monthly * 0.5:
            phase = "低频期"
        else:
            phase = "稳定期"
        phases.append(
            {
                "month": month,
                "note_count": count,
                "statistical_label": phase,
                "rule": "相对当前采集月份平均发文量的 1.5 倍/0.5 倍阈值",
            }
        )

    earliest = [_note_fact(note, account.follower_count) for note in dated[:20]]
    by_likes = sorted(notes, key=lambda note: note.like_count or -1, reverse=True)[:20]
    by_collections = sorted(notes, key=lambda note: note.collect_count or -1, reverse=True)[:20]
    by_interaction_rate = sorted(
        notes,
        key=lambda note: (
            note.total_engagement / account.follower_count
            if account.follower_count and account.follower_count > 0
            else -1
        ),
        reverse=True,
    )[:20]

    first_observed = []
    for term in PRODUCT_TERMS:
        matched = [note for note in dated if term.casefold() in _text(note).casefold()]
        if matched:
            first_observed.append(
                {
                    "term": term,
                    "first_observed_at": matched[0].publish_time,
                    "note_id": matched[0].note_id,
                    "note_url": matched[0].note_url,
                    "statement_scope": "首次在当前采集数据中观察到",
                }
            )

    note_fields = (
        "title",
        "content",
        "publish_time",
        "like_count",
        "collect_count",
        "comment_count",
        "share_count",
    )
    missing = {
        field: sum(getattr(note, field) is None for note in notes)
        for field in note_fields
        if any(getattr(note, field) is None for note in notes)
    }
    related = [
        {"keyword": keyword, **_note_fact(note, account.follower_count)}
        for keyword, note in keyword_notes
    ]
    return {
        "report_type": "fact_based_account_operations_report",
        "generated_at": iso_now(),
        "source_url": account.profile_url,
        "account": account.model_dump(mode="json"),
        "overview": {
            "nickname": account.nickname,
            "follower_count": account.follower_count,
            "total_notes": len(notes),
            "earliest_publish_time": dated[0].publish_time if dated else None,
            "latest_publish_time": dated[-1].publish_time if dated else None,
        },
        "timeline_by_month": timeline,
        "early_stage_notes": earliest,
        "topic_seed_method": {
            "type": "rule_based_keyword_match",
            "seeds": list(TOPIC_SEEDS),
            "notice": "主题仅表示关键词命中，不代表业务结论。",
        },
        "top_notes": {
            "by_likes": [_note_fact(note, account.follower_count) for note in by_likes],
            "by_collections": [_note_fact(note, account.follower_count) for note in by_collections],
            "by_interaction_rate": [
                _note_fact(note, account.follower_count) for note in by_interaction_rate
            ],
        },
        "first_observed_product_terms": first_observed,
        "publishing_rhythm": {
            "weekly_counts": dict(sorted(weekly.items())),
            "monthly_counts": monthly_counts,
            "statistical_phases": phases,
            "notice": "阶段标签是基于当前采集数据发文数量的统计结果。",
        },
        "keyword_relations": related,
        "data_completeness": {
            "crawled_note_count": len(notes),
            "detail_crawled_count": sum(note.detail_crawled_at is not None for note in notes),
            "earliest_date": dated[0].publish_time if dated else None,
            "latest_date": dated[-1].publish_time if dated else None,
            "missing_field_counts": missing,
            "possibly_incomplete": any(note.detail_crawled_at is None for note in notes),
            "notice": "仅反映本次可访问页面和当前采集结果，可能不代表账号全部历史。",
        },
    }


def render_markdown(report: dict[str, object]) -> str:
    account = report["account"]
    overview = report["overview"]
    assert isinstance(account, dict)
    assert isinstance(overview, dict)
    follower_display = (
        overview.get("follower_count") if overview.get("follower_count") is not None else "缺失"
    )
    date_range = (
        f"{overview.get('earliest_publish_time') or '缺失'} ～ "
        f"{overview.get('latest_publish_time') or '缺失'}"
    )
    lines = [
        f"# {account.get('nickname') or account.get('account_id')} 账号运营报告",
        "",
        f"> 生成时间：{report['generated_at']}。本报告只陈述当前采集数据与规则统计结果。",
        "",
        "## 账号概况",
        "",
        f"- 昵称：{overview.get('nickname') or '缺失'}",
        f"- 粉丝：{follower_display}",
        f"- 总笔记：{overview.get('total_notes')}",
        f"- 可获取时间跨度：{date_range}",
        f"- 数据来源：{report['source_url']}",
        "",
        "## 运营时间线",
        "",
        "| 月份 | 笔记数量 | 平均点赞 | 最高点赞 | 主题关键词 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for item in report["timeline_by_month"]:
        topics = "、".join(f"{key}({value})" for key, value in item["topic_keywords"].items())
        average_likes = item["average_likes"] if item["average_likes"] is not None else "缺失"
        highest_likes = item["highest_likes"] if item["highest_likes"] is not None else "缺失"
        lines.append(
            f"| {item['month']} | {item['note_count']} | {average_likes} | "
            f"{highest_likes} | {topics or '无 seed 命中'} |"
        )

    lines.extend(
        [
            "",
            "## 起号阶段",
            "",
            "以下为当前采集数据中时间最早的最多 20 篇笔记，不推断未采集历史。",
            "",
            "| 日期 | 标题 | 总互动 | 关键词 |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for note in report["early_stage_notes"]:
        note_prefix = f"| {note['date'] or '缺失'} | {note['title'] or '缺失'}"
        lines.append(
            f"{note_prefix} | {note['total_engagement']} | "
            f"{'、'.join(note['keywords']) or '无 seed 命中'} |"
        )

    lines.extend(["", "## 内容主题变化", ""])
    lines.append("采用固定 seed 的大小写不敏感关键词匹配；命中只代表文本出现，不代表内容结论。")
    lines.extend(["", "| 月份 | 主题占比 |", "| --- | --- |"])
    for item in report["timeline_by_month"]:
        shares = "、".join(f"{key}: {value:.1%}" for key, value in item["topic_share"].items())
        lines.append(f"| {item['month']} | {shares or '无 seed 命中'} |")

    lines.extend(["", "## 爆款", ""])
    lines.append("互动率按当前采集到的单篇互动总数 ÷ 当前账号粉丝数计算，不代表笔记发布时互动率。")
    lines.append("")
    for title, key in (
        ("按点赞 Top 20", "by_likes"),
        ("按收藏 Top 20", "by_collections"),
        ("按互动率 Top 20", "by_interaction_rate"),
    ):
        lines.extend(
            [
                f"### {title}",
                "",
                "| 日期 | 标题 | 点赞 | 收藏 | 总互动 | 互动率 |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for note in report["top_notes"][key]:
            rate = (
                f"{note['interaction_rate']:.2%}"
                if note["interaction_rate"] is not None
                else "不可计算"
            )
            lines.append(
                f"| {note['date'] or '缺失'} | {note['title'] or '缺失'} | "
                f"{note['like_count'] if note['like_count'] is not None else '缺失'} | "
                f"{note['collect_count'] if note['collect_count'] is not None else '缺失'} | "
                f"{note['total_engagement']} | {rate} |"
            )
        lines.append("")

    lines.extend(["## 产品出现时间", ""])
    if report["first_observed_product_terms"]:
        lines.extend(["| 关键词 | 首次观察时间 | 笔记 | 口径 |", "| --- | --- | --- | --- |"])
        for item in report["first_observed_product_terms"]:
            lines.append(
                f"| {item['term']} | {item['first_observed_at']} | "
                f"[{item['note_id']}]({item['note_url']}) | {item['statement_scope']} |"
            )
    else:
        lines.append("当前采集数据中未观察到 seed 关键词。")

    lines.extend(
        [
            "",
            "## 发布节奏",
            "",
            "以下阶段均为统计标签。",
            "",
            "| 月份 | 笔记数 | 统计阶段 | 规则 |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for item in report["publishing_rhythm"]["statistical_phases"]:
        phase_prefix = f"| {item['month']} | {item['note_count']}"
        lines.append(f"{phase_prefix} | {item['statistical_label']} | {item['rule']} |")

    lines.extend(["", "### 按周发文数量", "", "| ISO 周 | 笔记数 |", "| --- | ---: |"])
    for week, count in report["publishing_rhythm"]["weekly_counts"].items():
        lines.append(f"| {week} | {count} |")

    lines.extend(["", "## 关键词关系", ""])
    if report["keyword_relations"]:
        lines.extend(["| 关键词 | 日期 | 标题 | 笔记 |", "| --- | --- | --- | --- |"])
        for item in report["keyword_relations"]:
            lines.append(
                f"| {item['keyword']} | {item['date'] or '缺失'} | {item['title'] or '缺失'} | "
                f"[{item['note_id']}]({item['url']}) |"
            )
    else:
        lines.append("当前数据库没有该账号的关键词发现关系。")

    completeness = report["data_completeness"]
    missing_fields = json.dumps(completeness["missing_field_counts"], ensure_ascii=False)
    lines.extend(
        [
            "",
            "## 数据完整性",
            "",
            f"- 抓取笔记数量：{completeness['crawled_note_count']}",
            f"- 已完成详情采集：{completeness['detail_crawled_count']}",
            f"- 最早日期：{completeness['earliest_date'] or '缺失'}",
            f"- 最近日期：{completeness['latest_date'] or '缺失'}",
            f"- 缺失字段计数：`{missing_fields}`",
            f"- 可能未抓完整：{'是' if completeness['possibly_incomplete'] else '否'}",
            f"- 说明：{completeness['notice']}",
            "",
        ]
    )
    return "\n".join(lines)


def generate_account_report(
    database: Database, account_id: str, output_dir: Path
) -> tuple[Path, Path]:
    account = database.get_account(account_id)
    if account is None:
        raise ValueError(f"数据库中不存在账号：{account_id}")
    notes = database.list_notes(account_id)
    report = build_report(account, notes, database.keyword_notes(account_id))
    markdown = render_markdown(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{account_id}.md"
    json_path = output_dir / f"{account_id}.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    database.save_report(account_id, report, markdown, account.profile_url)
    return markdown_path, json_path
