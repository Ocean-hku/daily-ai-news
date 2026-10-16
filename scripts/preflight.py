# -*- coding: utf-8 -*-
"""Generate a short WorkBuddy context package for the daily AI news task."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RUNTIME_DIR = ROOT / "runtime"
REPORTS_DIR = ROOT / "reports"
ITEMS_JSONL = DATA_DIR / "items.jsonl"
SUMMARY_TXT = ROOT / "已收录简表.txt"

WEEKDAYS = "一二三四五六日"


def parse_date(value: str | None) -> date:
    if not value or value == "today":
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def zh_date(d: date) -> str:
    return f"{d.year} 年 {d.month} 月 {d.day} 日"


def window_text(d: date) -> str:
    y = d - timedelta(days=1)
    before = d - timedelta(days=2)
    return f"{y.month} 月 {y.day} 日（含 {before.month} 月 {before.day} 日晚间）"


def stable_event_id(title: str, url: str = "", category: str = "") -> str:
    domain = urlparse(url).netloc.replace("www.", "") if url.startswith(("http://", "https://")) else "source"
    domain = re.sub(r"[^a-zA-Z0-9]+", "-", domain).strip("-").lower() or "source"
    category_key = re.sub(r"[^a-zA-Z0-9]+", "-", category).strip("-").lower() or "ai"
    digest = hashlib.sha1(f"{title}|{url}".encode("utf-8")).hexdigest()[:10]
    return f"{category_key}-{domain}-{digest}"


def parse_summary_txt() -> list[dict]:
    if not SUMMARY_TXT.is_file():
        return []
    records: list[dict] = []
    issue = None
    for raw in SUMMARY_TXT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        issue_match = re.search(r"第\s*(\d+)\s*期", line)
        if issue_match:
            issue = int(issue_match.group(1))
        status = "excluded" if line.startswith("【剔除】") else "included"
        clean = line.replace("【剔除】", "", 1).strip()
        parts = [p.strip() for p in clean.split(" | ")]
        if len(parts) < 4 or not re.match(r"\d{4}-\d{2}-\d{2}", parts[0]):
            continue
        item_date, title, keywords, url = parts[:4]
        badge = ""
        if "再度爆火" in title or "再度爆火" in keywords:
            badge = "再度爆火"
        elif "追踪更新" in title or "追踪更新" in keywords:
            badge = "追踪更新"
        records.append(
            {
                "date": item_date,
                "issue": issue,
                "title": title,
                "category": keywords.split("/")[0].strip(),
                "keywords": keywords,
                "url": url,
                "status": status,
                "badge": badge,
                "event_id": stable_event_id(title, url, keywords.split("/")[0].strip()),
            }
        )
    return records


def load_items() -> list[dict]:
    if ITEMS_JSONL.is_file():
        items: list[dict] = []
        for line in ITEMS_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if items:
            return items
    return parse_summary_txt()


def infer_issue(target: date, items: list[dict]) -> int:
    target_s = target.isoformat()
    same_day = [i.get("issue") for i in items if i.get("date") == target_s and i.get("issue")]
    if same_day:
        return int(min(same_day))
    unique_dates = sorted({i.get("date") for i in items if re.match(r"\d{4}-\d{2}-\d{2}", str(i.get("date", ""))) and i.get("date") < target_s})
    return len(unique_dates) + 1


def compact_recent_items(items: list[dict], target: date, days: int, limit: int) -> list[dict]:
    start = target - timedelta(days=days)
    recent = []
    for item in items:
        try:
            d = datetime.strptime(str(item.get("date")), "%Y-%m-%d").date()
        except ValueError:
            continue
        if start <= d < target and item.get("status") != "excluded":
            recent.append(item)
    recent.sort(key=lambda x: (x.get("date", ""), x.get("title", "")), reverse=True)
    return recent[:limit]


def write_context(target: date, recent_days: int, recent_limit: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    items = load_items()
    issue = infer_issue(target, items)
    month_dir = ROOT / "outputs" / target.strftime("%Y-%m")
    recent = compact_recent_items(items, target, recent_days, recent_limit)

    lines = [
        "# WorkBuddy 今日执行上下文（低 token 版）",
        "",
        "你只负责检索、判断、写结构化内容 JSON；不要写完整 HTML，不要写 CSS，不要手动追加简表。",
        "脚本会负责 HTML 渲染、PDF 生成、校验、日志、归档和简表同步。",
        "",
        "## 今日参数",
        f"- 日期：{target.isoformat()}",
        f"- 星期：星期{WEEKDAYS[target.weekday()]}",
        f"- 期号：{issue:03d}",
        f"- 收录窗口：{window_text(target)}",
        f"- 输出 HTML：{month_dir / f'AI日报-{target.isoformat()}.html'}",
        f"- 输出 PDF：{month_dir / f'AI日报-{target.isoformat()}.pdf'}",
        f"- 内容 JSON：{RUNTIME_DIR / f'issue-{target.isoformat()}.json'}",
        "",
        "## 近期去重索引（只用于避免同传播周期重复）",
    ]
    if recent:
        for item in recent:
            lines.append(f"- {item.get('date')} | {item.get('event_id')} | {item.get('title')}")
    else:
        lines.append("- 暂无近期结构化索引；必要时参考已收录简表。")

    schema = {
        "date": target.isoformat(),
        "issue": issue,
        "window": window_text(target),
        "deadline": f"{zh_date(target)}上午（北京时间）",
        "sections": [
            {
                "name": "大模型与 AI 产品进展",
                "lead": "一句栏目导语",
                "items": [
                    {
                        "level": "main",
                        "title": "标题",
                        "badge": "",
                        "language": "中文/英文",
                        "read_time": "约 4 分钟",
                        "why": "读懂这件事：用 1—2 句讲清背景、重要性和它说明了什么，不要只写“值得关注”",
                        "body": ["段落 1：谁在何时何地做了什么，证据来自哪里", "段落 2：主流看法、争议、限制或后续影响"],
                        "url": "https://...",
                        "source": "来源名称",
                        "event_id": "稳定事件ID，如 openai-model-release-2026-10",
                    }
                ],
            }
        ],
        "gaps": ["影响阅读判断的信息缺口，最多 5 条"],
        "excluded": [{"title": "剔除标题", "reason": "剔除原因", "url": "https://...", "event_id": "..."}],
    }
    lines.extend(
        [
            "",
            "## 必须输出的 JSON Schema",
            "将最终内容保存为上面的 `runtime\\issue-YYYY-MM-DD.json`，严格 JSON，不要 Markdown 包裹。",
            "```json",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 内容规则",
            "- 总条数建议 8—16 条；没有达标内容的栏目省略，不为凑数降低质量。",
            "- 每个栏目最多 1 条 main，其余为 sub；main 建议 450—700 字，sub 建议 180—320 字。",
            "- 核心目标不是堆“值得看/重点读”，而是把事情说清楚。",
            "- 每条正文必须回答：谁发现/发布/起诉/回应？证据或报告在哪里？谁对谁做了什么？目前主流看法是什么？还有哪些不确定？",
            "- `why` 字段用来解释这件事反映了什么变化或风险；禁止只写“更值得留意”“先例更重要”而不解释原因。",
            "- 避免同一句式重复，例如反复写“比 X 更值得看的是 Y”“不在于分数，而在于用量”。",
            "- 同一事件同传播周期且无实质新进展：放入 excluded。",
            "- 再次登顶或重新大量讨论：保留，badge 写 `再度爆火`，正文交代前情和这次为什么又热。",
            "- 有实质新进展：保留，badge 写 `追踪更新`，正文交代旧事件和新增信息。",
            "- 每条必须有直达来源 URL；没有稳定直链时，url 写来源说明，并在 gaps 说明。",
            "- 不要编造链接、数据、标题或引用。",
            "",
            "## 生成后执行",
            f"保存 JSON 后运行：python {ROOT / 'scripts' / 'build_issue.py'} --date {target.isoformat()}",
        ]
    )

    context_path = RUNTIME_DIR / "today_context.md"
    context_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = {
        "ok": True,
        "date": target.isoformat(),
        "issue": issue,
        "context": str(context_path),
        "issue_json": str(RUNTIME_DIR / f"issue-{target.isoformat()}.json"),
        "recent_items": len(recent),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (REPORTS_DIR / "preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return context_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate short context for WorkBuddy daily AI news task.")
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today")
    parser.add_argument("--recent-days", type=int, default=14)
    parser.add_argument("--recent-limit", type=int, default=80)
    args = parser.parse_args()

    target = parse_date(args.date)
    context_path = write_context(target, args.recent_days, args.recent_limit)
    print(f"OK: context written to {context_path}")


if __name__ == "__main__":
    main()
