# -*- coding: utf-8 -*-
"""Generate a static local dashboard for daily AI news outputs."""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"
ITEMS_JSONL = DATA_DIR / "items.jsonl"
DASHBOARD = OUTPUTS_DIR / "index.html"


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def rel_href(path: Path) -> str:
    return path.relative_to(OUTPUTS_DIR).as_posix()


def count_pdf_pages(pdf_path: Path) -> int | None:
    try:
        import fitz  # type: ignore

        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except Exception:
        pass

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        pass

    try:
        data = pdf_path.read_bytes()
        matches = re.findall(rb"/Type\s*/Page\b", data)
        return len(matches) or None
    except Exception:
        return None


def load_items() -> list[dict[str, Any]]:
    if not ITEMS_JSONL.is_file():
        return []
    items: list[dict[str, Any]] = []
    for line in ITEMS_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def scan_outputs() -> dict[str, dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    if not OUTPUTS_DIR.is_dir():
        return issues
    pattern = re.compile(r"AI日报-(\d{4}-\d{2}-\d{2})\.(html|pdf)$", re.IGNORECASE)
    for path in OUTPUTS_DIR.glob("**/AI日报-*.*"):
        match = pattern.match(path.name)
        if not match:
            continue
        day, ext = match.group(1), match.group(2).lower()
        item = issues.setdefault(day, {"date": day})
        item[ext] = path
    return issues


def enrich_with_items(issues: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        day = str(record.get("date", ""))
        if not day:
            continue
        grouped.setdefault(day, []).append(record)
        issues.setdefault(day, {"date": day})

    for day, issue in issues.items():
        day_records = grouped.get(day, [])
        included = [r for r in day_records if r.get("status") == "included"]
        excluded = [r for r in day_records if r.get("status") == "excluded"]
        issue_numbers = [r.get("issue") for r in day_records if isinstance(r.get("issue"), int)]
        if issue_numbers:
            issue["issue"] = min(issue_numbers)
        issue["included_count"] = len(included)
        issue["excluded_count"] = len(excluded)
        issue["top_title"] = included[0].get("title") if included else ""
        counts: dict[str, int] = {}
        badges: dict[str, list[str]] = {"再度爆火": [], "追踪更新": []}
        for record in included:
            category = str(record.get("category") or "未分类")
            counts[category] = counts.get(category, 0) + 1
            badge = str(record.get("badge") or "")
            if badge in badges:
                badges[badge].append(str(record.get("title") or ""))
        issue["counts"] = counts
        issue["badges"] = {k: v for k, v in badges.items() if v}


def enrich_pdf_info(issues: dict[str, dict[str, Any]]) -> None:
    for issue in issues.values():
        pdf = issue.get("pdf")
        if isinstance(pdf, Path) and pdf.is_file():
            issue["pdf_size"] = pdf.stat().st_size
            issue["pdf_pages"] = count_pdf_pages(pdf)


def issue_sort_key(item: dict[str, Any]) -> str:
    return str(item.get("date", ""))


def render_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "<span class=\"muted\">暂无结构化栏目数据</span>"
    return "".join(f"<span class=\"pill\">{esc(k)}×{v}</span>" for k, v in counts.items())


def render_badges(badges: dict[str, list[str]]) -> str:
    if not badges:
        return ""
    blocks = []
    for badge, titles in badges.items():
        joined = "；".join(titles)
        blocks.append(f"<div class=\"badge-line\"><b>{esc(badge)}：</b>{esc(joined)}</div>")
    return "\n".join(blocks)


def render_links(issue: dict[str, Any]) -> str:
    links = []
    html_path = issue.get("html")
    pdf_path = issue.get("pdf")
    if isinstance(html_path, Path) and html_path.is_file():
        links.append(f"<a class=\"btn\" href=\"{esc(rel_href(html_path))}\">打开 HTML</a>")
    else:
        links.append("<span class=\"btn disabled\">HTML 缺失</span>")
    if isinstance(pdf_path, Path) and pdf_path.is_file():
        links.append(f"<a class=\"btn\" href=\"{esc(rel_href(pdf_path))}\">打开 PDF</a>")
    else:
        links.append("<span class=\"btn disabled\">PDF 缺失</span>")
    return "\n".join(links)


def render_issue_card(issue: dict[str, Any]) -> str:
    date_text = str(issue.get("date", ""))
    issue_no = issue.get("issue")
    issue_text = f"第 {int(issue_no):03d} 期" if isinstance(issue_no, int) else "期号未知"
    top = issue.get("top_title") or "暂无结构化头条记录"
    page_info = ""
    if issue.get("pdf_pages") is not None:
        page_info = f"<span>{issue.get('pdf_pages')} 页</span>"
    elif issue.get("pdf"):
        page_info = "<span>页数未知</span>"
    size_info = ""
    if issue.get("pdf_size"):
        size_info = f"<span>{int(issue['pdf_size']) / 1024:.0f} KB</span>"
    return f"""
<section class="card">
  <div class="card-head">
    <div>
      <h2>{esc(date_text)}</h2>
      <p>{esc(issue_text)}</p>
    </div>
    <div class="links">
      {render_links(issue)}
    </div>
  </div>
  <h3>{esc(top)}</h3>
  <div class="meta">
    <span>收录 {int(issue.get('included_count') or 0)} 条</span>
    <span>剔除 {int(issue.get('excluded_count') or 0)} 条</span>
    {page_info}
    {size_info}
  </div>
  <div class="counts">{render_counts(issue.get('counts') or {})}</div>
  {render_badges(issue.get('badges') or {})}
</section>
""".strip()


def render_dashboard(issues: list[dict[str, Any]]) -> str:
    cards = "\n\n".join(render_issue_card(issue) for issue in issues)
    latest = issues[0] if issues else {}
    latest_date = latest.get("date", "暂无")
    total = len(issues)
    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>每日 AI 新闻看板</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #faf8f4; color: #242424; font-family: "Microsoft YaHei", "Source Han Sans SC", sans-serif; }}
  .page {{ max-width: 1180px; margin: 0 auto; padding: 36px 22px 54px; }}
  header {{ border-top: 3px solid #1a1a1a; border-bottom: 1px solid #1a1a1a; padding: 22px 0 18px; margin-bottom: 24px; text-align: center; }}
  h1 {{ font-family: "SimSun", "Source Han Serif SC", serif; font-size: 34px; letter-spacing: .18em; text-indent: .18em; margin: 0 0 8px; }}
  .sub {{ color: #6b6b6b; font-size: 14px; }}
  .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 22px 0 24px; }}
  .summary div {{ background: #fffdf8; border: 1px solid #e2dbcf; padding: 14px 16px; }}
  .summary b {{ display: block; font-size: 22px; margin-bottom: 4px; }}
  .summary span {{ color: #6b6b6b; font-size: 13px; }}
  .card {{ background: #fffdf8; border: 1px solid #ded8cc; box-shadow: 0 8px 24px rgba(35, 31, 27, .06); padding: 18px 20px; margin: 0 0 16px; }}
  .card-head {{ display: flex; gap: 16px; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #e8e1d6; padding-bottom: 12px; }}
  h2 {{ font-family: "SimSun", "Source Han Serif SC", serif; font-size: 23px; margin: 0 0 4px; }}
  .card-head p {{ margin: 0; color: #8d2d25; font-weight: 700; }}
  h3 {{ font-family: "SimSun", "Source Han Serif SC", serif; font-size: 20px; margin: 16px 0 10px; line-height: 1.45; }}
  .links {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
  .btn {{ display: inline-block; color: #fff; background: #b03a2e; text-decoration: none; padding: 7px 12px; border-radius: 999px; font-size: 13px; }}
  .btn.disabled {{ color: #8b8378; background: #eee7dc; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 9px; color: #6b6b6b; font-size: 13px; margin-bottom: 12px; }}
  .meta span {{ border-left: 3px solid #c9bfb1; padding-left: 8px; }}
  .counts {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 8px 0; }}
  .pill {{ display: inline-block; border: 1px solid #d8cfc2; background: #faf6ed; color: #403b35; padding: 4px 9px; border-radius: 999px; font-size: 12px; }}
  .badge-line {{ margin-top: 8px; padding: 8px 10px; background: rgba(176, 58, 46, .06); border-left: 3px solid #b03a2e; font-size: 13px; }}
  .muted {{ color: #8b8378; font-size: 13px; }}
  footer {{ margin-top: 26px; color: #777064; font-size: 12px; text-align: center; }}
  @media (max-width: 720px) {{ .summary {{ grid-template-columns: 1fr; }} .card-head {{ display: block; }} .links {{ justify-content: flex-start; margin-top: 12px; }} }}
</style>
</head>
<body>
<div class="page">
  <header>
    <h1>每日 AI 新闻看板</h1>
    <div class="sub">本地静态索引 · 直接点击打开 HTML/PDF · 无需本地服务器</div>
  </header>
  <div class="summary">
    <div><b>{total}</b><span>已归档期数</span></div>
    <div><b>{esc(latest_date)}</b><span>最新日期</span></div>
    <div><b>{esc(updated)}</b><span>看板更新时间</span></div>
  </div>
  {cards if cards else '<p class="muted">暂无日报产物。</p>'}
  <footer>文件位置：outputs/index.html。链接均为相对路径，双击本文件即可本地浏览。</footer>
</div>
</body>
</html>
"""


def build_dashboard() -> Path:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    issues = scan_outputs()
    enrich_with_items(issues, load_items())
    enrich_pdf_info(issues)
    issue_list = sorted(issues.values(), key=issue_sort_key, reverse=True)
    DASHBOARD.write_text(render_dashboard(issue_list), encoding="utf-8")
    return DASHBOARD


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static dashboard for daily AI news outputs.")
    parser.add_argument("--open", action="store_true", help="Reserved for manual use; generation does not require a server.")
    parser.parse_args()
    path = build_dashboard()
    print(f"OK: dashboard written to {path}")


if __name__ == "__main__":
    main()
