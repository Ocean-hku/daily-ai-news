# -*- coding: utf-8 -*-
"""Build HTML/PDF outputs from WorkBuddy's structured issue JSON."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime"
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"
TEMPLATE_PATH = ROOT / "templates" / "issue_template.html"
ITEMS_JSONL = DATA_DIR / "items.jsonl"
SUMMARY_TXT = ROOT / "已收录简表.txt"
MAKE_PDF = ROOT / "make_pdf.py"
UPDATE_DASHBOARD = ROOT / "scripts" / "update_dashboard.py"

WEEKDAYS = "一二三四五六日"
ALLOWED_BADGES = {"", "再度爆火", "追踪更新"}
SEARCH_URL_PATTERNS = ("/search?", "google.com/search", "bing.com/search", "baidu.com/s?")


def parse_date(value: str | None) -> date:
    if not value or value == "today":
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def zh_date(d: date) -> str:
    return f"{d.year} 年 {d.month} 月 {d.day} 日"


def zh_issue(issue: int) -> str:
    return f"{issue:03d}"


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid JSON: {path}: {exc}") from exc


def load_items() -> list[dict[str, Any]]:
    if not ITEMS_JSONL.is_file():
        return []
    items = []
    for line_no, line in enumerate(ITEMS_JSONL.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            raise SystemExit(f"ERROR: invalid JSONL at {ITEMS_JSONL}:{line_no}")
    return items


def validate_issue(issue: dict[str, Any], target: date, existing_items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if issue.get("date") != target.isoformat():
        errors.append(f"date must be {target.isoformat()}, got {issue.get('date')!r}")
    if not isinstance(issue.get("issue"), int):
        errors.append("issue must be an integer")
    if not issue.get("window"):
        errors.append("window is required")
    if not issue.get("deadline"):
        errors.append("deadline is required")
    sections = issue.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections must be a non-empty list")
        return errors, warnings

    existing_by_event = {
        str(item.get("event_id")): item
        for item in existing_items
        if item.get("event_id") and item.get("date") != target.isoformat() and item.get("status") == "included"
    }
    seen_event_ids: set[str] = set()
    total_items = 0

    for s_idx, section in enumerate(sections, 1):
        if not section.get("name"):
            errors.append(f"sections[{s_idx}].name is required")
        if not section.get("lead"):
            warnings.append(f"sections[{s_idx}] has no lead")
        items = section.get("items")
        if not isinstance(items, list) or not items:
            warnings.append(f"section {section.get('name')!r} has no items and will render empty")
            continue
        main_count = 0
        for i_idx, item in enumerate(items, 1):
            total_items += 1
            prefix = f"section {section.get('name')!r} item {i_idx}"
            level = item.get("level")
            if level not in {"main", "sub"}:
                errors.append(f"{prefix}: level must be main/sub")
            if level == "main":
                main_count += 1
            for field in ("title", "body", "url", "source", "event_id", "why"):
                if not item.get(field):
                    errors.append(f"{prefix}: {field} is required")
            badge = item.get("badge", "") or ""
            if badge not in ALLOWED_BADGES:
                errors.append(f"{prefix}: badge must be one of {sorted(ALLOWED_BADGES)}")
            url = str(item.get("url", ""))
            if not url.startswith(("http://", "https://", "来源 ", "来源", "未取回")):
                errors.append(f"{prefix}: url must be http(s) or an explicit source note")
            if any(pattern in url for pattern in SEARCH_URL_PATTERNS):
                warnings.append(f"{prefix}: URL looks like a search result: {url}")
            event_id = str(item.get("event_id", ""))
            if event_id:
                if event_id in seen_event_ids:
                    errors.append(f"{prefix}: duplicated event_id in this issue: {event_id}")
                seen_event_ids.add(event_id)
                old = existing_by_event.get(event_id)
                if old and badge not in {"再度爆火", "追踪更新"}:
                    errors.append(f"{prefix}: event_id already exists on {old.get('date')}; use badge 再度爆火/追踪更新 or exclude it")
        if main_count > 1:
            warnings.append(f"section {section.get('name')!r} has {main_count} main items; recommended maximum is 1")

    if total_items == 0:
        errors.append("no news items found")
    if total_items < 8:
        warnings.append(f"only {total_items} items; recommended range is 8-16")
    if total_items > 16:
        warnings.append(f"{total_items} items; recommended range is 8-16")

    gaps = issue.get("gaps", [])
    if not isinstance(gaps, list) or not gaps:
        errors.append("gaps must contain at least one item")
    if len(gaps) > 5:
        warnings.append("gaps contains more than 5 items; footer may be too long")

    return errors, warnings


def render_paragraphs(body: Any) -> str:
    if isinstance(body, str):
        paragraphs = [body]
    elif isinstance(body, list):
        paragraphs = [str(p) for p in body if str(p).strip()]
    else:
        paragraphs = []
    return "\n".join(f"    <p>{esc(p)}</p>" for p in paragraphs)


def render_figure(item: dict[str, Any]) -> str:
    svg = item.get("figure_svg") or item.get("svg")
    if not svg:
        return ""
    svg_text = str(svg).strip()
    if not svg_text.startswith("<svg"):
        return ""
    caption = esc(item.get("figure_caption", ""))
    caption_html = f"\n      <figcaption>{caption}</figcaption>" if caption else ""
    return f"\n    <figure>\n      {svg_text}{caption_html}\n    </figure>"


def render_item(item: dict[str, Any]) -> str:
    level = item.get("level")
    title_cls = "mainhead" if level == "main" else "subhead"
    tag = "h2" if level == "main" else "h3"
    item_cls = "item main-item" if level == "main" else "item sub-item"
    badge = item.get("badge", "") or ""
    badge_html = f"<span class=\"badge\">{esc(badge)}</span>" if badge else ""
    meta = f"{esc(item.get('language', '中文'))} <span class=\"dot\">·</span> {esc(item.get('read_time', '约 2 分钟'))}"
    source = esc(item.get("source", "原文"))
    url = str(item.get("url", ""))
    link_html = f"<a href=\"{esc(url)}\">{source}</a>" if url.startswith(("http://", "https://")) else esc(url or source)
    return "\n".join(
        [
            f"  <article class=\"{item_cls}\">",
            f"    <{tag} class=\"{title_cls}\">{esc(item.get('title'))}{badge_html}</{tag}>",
            f"    <div class=\"meta\">{meta}</div>",
            f"    <div class=\"why\"><strong>为什么值得读：</strong>{esc(item.get('why'))}</div>",
            render_paragraphs(item.get("body")),
            render_figure(item),
            f"    <p>原文：{link_html}</p>",
            "  </article>",
        ]
    )


def render_sections(issue: dict[str, Any]) -> str:
    blocks: list[str] = []
    for section in issue.get("sections", []):
        items_html = "\n".join(render_item(item) for item in section.get("items", []))
        blocks.append(
            "\n".join(
                [
                    "<section class=\"section\">",
                    f"  <div class=\"section-tag\">{esc(section.get('name'))}</div>",
                    f"  <p class=\"section-lead\">{esc(section.get('lead'))}</p>",
                    items_html,
                    "</section>",
                ]
            )
        )
    return "\n\n".join(blocks)


def render_html(issue: dict[str, Any], target: date) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    issue_no = int(issue["issue"])
    title = f"昨日 AI 重点资讯 · {target.isoformat()} · 第 {issue_no:03d} 期"
    subline = f"{zh_date(target)} · 星期{WEEKDAYS[target.weekday()]} · 第 {issue_no:03d} 期 · 收录窗口：{issue.get('window')}"
    gaps = issue.get("gaps", []) or ["暂无需要额外提示的信息缺口。"]
    gaps_html = "\n".join(f"    <li>{esc(gap)}</li>" for gap in gaps)
    return (
        template.replace("{{TITLE}}", esc(title))
        .replace("{{SUBLINE}}", esc(subline))
        .replace("{{SECTIONS}}", render_sections(issue))
        .replace("{{DEADLINE}}", esc(issue.get("deadline")))
        .replace("{{GAPS}}", gaps_html)
        .replace("{{ISSUE_ZH}}", zh_issue(issue_no))
        .replace("{{DATE_ZH}}", esc(zh_date(target)))
    )


def validate_html_text(html_text: str, issue: dict[str, Any], target: date) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    issue_no = int(issue["issue"])
    required = [
        f"AI日报-{target.isoformat()}",
        f"第 {issue_no:03d} 期",
        "检索截止时间",
        "会影响阅读判断的信息缺口",
        "为什么值得读",
    ]
    if f"昨日 AI 重点资讯 · {target.isoformat()} · 第 {issue_no:03d} 期" not in html_text:
        errors.append("HTML title does not contain date and issue number")
    for token in required[1:]:
        if token not in html_text:
            errors.append(f"HTML missing required token: {token}")
    for bad in ("TODO", "待补充", "链接待补", "原文链接待补"):
        if bad in html_text:
            errors.append(f"HTML contains placeholder: {bad}")
    if html_text.count("<svg") > 3:
        warnings.append("more than 3 SVG charts; review whether charts are necessary")
    return errors, warnings


def output_paths(target: date) -> dict[str, Path]:
    month_dir = ROOT / "outputs" / target.strftime("%Y-%m")
    basename = f"AI日报-{target.isoformat()}"
    return {
        "month_dir": month_dir,
        "html": month_dir / f"{basename}.html",
        "pdf": month_dir / f"{basename}.pdf",
    }


def ensure_outputs_available(paths: dict[str, Path], overwrite: bool, skip_pdf: bool) -> None:
    targets = [paths["html"]]
    if not skip_pdf:
        targets.append(paths["pdf"])
    existing = [str(p) for p in targets if p.exists()]
    if existing and not overwrite:
        raise SystemExit("ERROR: output already exists; use --overwrite for an intentional rerun:\n" + "\n".join(existing))


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys: set[tuple[str, str, str]] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing_keys.add((str(item.get("date")), str(item.get("event_id")), str(item.get("status", "included"))))
    new_lines = []
    for record in records:
        key = (str(record.get("date")), str(record.get("event_id")), str(record.get("status", "included")))
        if key in existing_keys:
            continue
        new_lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        existing_keys.add(key)
    if new_lines:
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for line in new_lines:
                f.write(line + "\n")
    return len(new_lines)


def item_records(issue: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    common = {"date": issue["date"], "issue": issue["issue"]}
    for section in issue.get("sections", []):
        for item in section.get("items", []):
            records.append(
                {
                    **common,
                    "title": item.get("title"),
                    "event_id": item.get("event_id"),
                    "category": section.get("name"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "status": "included",
                    "badge": item.get("badge", "") or "",
                }
            )
    for item in issue.get("excluded", []) or []:
        records.append(
            {
                **common,
                "title": item.get("title"),
                "event_id": item.get("event_id") or "excluded-" + hashlib.sha1(f"{item.get('title', '')}|{item.get('url', '')}".encode("utf-8")).hexdigest()[:10],
                "category": "剔除",
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "status": "excluded",
                "badge": "",
                "reason": item.get("reason", ""),
            }
        )
    return records


def append_summary(issue: dict[str, Any], records: list[dict[str, Any]]) -> int:
    SUMMARY_TXT.parent.mkdir(parents=True, exist_ok=True)
    if not SUMMARY_TXT.exists():
        SUMMARY_TXT.write_text("《昨日 AI 重点资讯》已收录简表\n格式：日期 | 标题 | 核心事件关键词 | 链接\n", encoding="utf-8")
    text = SUMMARY_TXT.read_text(encoding="utf-8")
    lines_to_add: list[str] = []
    date_s = str(issue["date"])
    if f"本期说明：第 {int(issue['issue']):03d} 期" not in text and date_s not in text:
        lines_to_add.extend([f"本期说明：第 {int(issue['issue']):03d} 期，收录窗口 {issue.get('window')}", "----------------------------------------"])
    for record in records:
        title = str(record.get("title", ""))
        if not title or title in text:
            continue
        if record.get("status") == "excluded":
            reason = record.get("reason") or "同一传播周期已收录或证据不足"
            line = f"【剔除】{date_s} | {title} | 剔除理由：{reason} | {record.get('url', '')}"
        else:
            bits = [str(record.get("category", "")), str(record.get("event_id", ""))]
            if record.get("badge"):
                bits.append(str(record.get("badge")))
            keywords = " / ".join(bit for bit in bits if bit)
            line = f"{date_s} | {title} | {keywords} | {record.get('url', '')}"
        lines_to_add.append(line)
    if lines_to_add:
        with SUMMARY_TXT.open("a", encoding="utf-8", newline="\n") as f:
            if not text.endswith("\n"):
                f.write("\n")
            f.write("\n".join(lines_to_add) + "\n")
    return len(lines_to_add)


def run_make_pdf(html_path: Path, pdf_path: Path, log_path: Path, retries: int, timeout: int) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(MAKE_PDF),
        str(html_path),
        str(pdf_path),
        "--retries",
        str(retries),
        "--timeout",
        str(timeout),
        "--log",
        str(log_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise SystemExit("ERROR: PDF build failed\n" + completed.stdout + completed.stderr)
    if log_path.exists():
        return json.loads(log_path.read_text(encoding="utf-8"))
    return {"ok": True, "stdout": completed.stdout}


def run_update_dashboard() -> tuple[bool, str]:
    completed = subprocess.run([sys.executable, str(UPDATE_DASHBOARD)], capture_output=True, text=True)
    if completed.returncode != 0:
        return False, (completed.stdout + completed.stderr).strip()
    return True, (completed.stdout + completed.stderr).strip()


def summarize(issue: dict[str, Any], paths: dict[str, Path], warnings: list[str], pdf_result: dict[str, Any] | None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    badges: dict[str, list[str]] = {"再度爆火": [], "追踪更新": []}
    top_title = ""
    top_why = ""
    for section in issue.get("sections", []):
        items = section.get("items", [])
        counts[str(section.get("name"))] = len(items)
        for item in items:
            if not top_title and item.get("level") == "main":
                top_title = str(item.get("title", ""))
                top_why = str(item.get("why", ""))
            badge = item.get("badge") or ""
            if badge in badges:
                badges[badge].append(str(item.get("title", "")))
    if not top_title:
        first = next((i for s in issue.get("sections", []) for i in s.get("items", [])), {})
        top_title = str(first.get("title", ""))
        top_why = str(first.get("why", ""))
    return {
        "ok": True,
        "date": issue.get("date"),
        "issue": issue.get("issue"),
        "top": {"title": top_title, "why": top_why},
        "counts": counts,
        "badges": {k: v for k, v in badges.items() if v},
        "html": str(paths["html"]),
        "pdf": str(paths["pdf"]),
        "warnings": warnings,
        "pdf_result": pdf_result,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build daily AI news HTML/PDF from structured JSON.")
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today")
    parser.add_argument("--issue-json", help="Explicit issue JSON path")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing HTML/PDF for intentional reruns")
    parser.add_argument("--skip-pdf", action="store_true", help="Only render and validate HTML; do not create PDF")
    parser.add_argument("--dry-run", action="store_true", help="Validate JSON and render HTML in memory only; write no outputs")
    parser.add_argument("--pdf-retries", type=int, default=2)
    parser.add_argument("--pdf-timeout", type=int, default=120)
    args = parser.parse_args()

    target = parse_date(args.date)
    issue_path = Path(args.issue_json).resolve() if args.issue_json else RUNTIME_DIR / f"issue-{target.isoformat()}.json"
    if not issue_path.is_file():
        raise SystemExit(f"ERROR: issue JSON not found: {issue_path}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    paths = output_paths(target)
    if not args.dry_run:
        paths["month_dir"].mkdir(parents=True, exist_ok=True)
        ensure_outputs_available(paths, args.overwrite, args.skip_pdf)

    existing = load_items()
    issue = load_json(issue_path)
    errors, warnings = validate_issue(issue, target, existing)
    if errors:
        raise SystemExit("ERROR: issue validation failed:\n" + "\n".join(f"- {e}" for e in errors))

    html_text = render_html(issue, target)
    html_errors, html_warnings = validate_html_text(html_text, issue, target)
    warnings.extend(html_warnings)
    if html_errors:
        raise SystemExit("ERROR: HTML validation failed:\n" + "\n".join(f"- {e}" for e in html_errors))

    if args.dry_run:
        print(f"OK: dry run passed for {target.isoformat()} ({sum(len(s.get('items', [])) for s in issue.get('sections', []))} items)")
        if warnings:
            print("WARNINGS:")
            for warning in warnings:
                print(f"- {warning}")
        return

    paths["html"].write_text(html_text, encoding="utf-8")

    pdf_result = None
    if not args.skip_pdf:
        pdf_log = LOGS_DIR / f"pdf-{target.isoformat()}.json"
        pdf_result = run_make_pdf(paths["html"], paths["pdf"], pdf_log, args.pdf_retries, args.pdf_timeout)
        pdf_warnings = ((pdf_result.get("pdf") or {}).get("warnings") or []) if isinstance(pdf_result, dict) else []
        warnings.extend(str(w) for w in pdf_warnings)

    records = item_records(issue)
    jsonl_added = append_jsonl(ITEMS_JSONL, records)
    summary_added = append_summary(issue, records)
    dashboard_ok, dashboard_message = run_update_dashboard()
    if not dashboard_ok:
        warnings.append(f"Dashboard update failed: {dashboard_message}")

    latest = summarize(issue, paths, warnings, pdf_result)
    latest["items_jsonl_added"] = jsonl_added
    latest["summary_lines_added"] = summary_added
    latest["issue_json"] = str(issue_path)
    latest["dashboard"] = str(ROOT / "outputs" / "index.html")
    latest["dashboard_update"] = dashboard_message
    latest_path = REPORTS_DIR / "latest.json"
    latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

    run_log = LOGS_DIR / f"{target.isoformat()}.log"
    run_log.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: HTML {paths['html']}")
    if not args.skip_pdf:
        print(f"OK: PDF {paths['pdf']}")
    print(f"OK: latest report {latest_path}")


if __name__ == "__main__":
    main()
