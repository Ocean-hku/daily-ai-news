# -*- coding: utf-8 -*-
"""
make_pdf.py — stable HTML -> PDF converter for the daily AI newspaper.

Usage:
    python make_pdf.py input.html output.pdf
    python make_pdf.py input.html output.pdf --retries 2 --timeout 120 --log logs/pdf.json

The HTML owns layout and styling. This script owns only deterministic PDF
printing, retries, isolation of the browser profile, and basic PDF validation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser(explicit: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("DAILY_AI_NEWS_BROWSER"):
        candidates.append(os.environ["DAILY_AI_NEWS_BROWSER"])
    candidates.extend(BROWSER_CANDIDATES)

    for command in ("msedge", "chrome", "chrome.exe", "msedge.exe"):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(resolved)

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise SystemExit("ERROR: no headless browser found. Install Edge/Chrome or set DAILY_AI_NEWS_BROWSER.")


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


def extract_text_sample(pdf_path: Path, max_pages: int = 3) -> str | None:
    try:
        import fitz  # type: ignore

        chunks: list[str] = []
        with fitz.open(pdf_path) as doc:
            for page in doc[: min(max_pages, doc.page_count)]:
                chunks.append(page.get_text("text"))
        return "\n".join(chunks).strip()
    except Exception:
        pass

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        chunks = []
        for page in reader.pages[:max_pages]:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks).strip()
    except Exception:
        return None


def validate_pdf(pdf_path: Path, min_bytes: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(pdf_path),
        "exists": pdf_path.is_file(),
        "size": 0,
        "page_count": None,
        "text_extractable": None,
        "warnings": [],
    }
    if not pdf_path.is_file():
        result["ok"] = False
        result["error"] = "PDF was not created."
        return result

    size = pdf_path.stat().st_size
    result["size"] = size
    if size < min_bytes:
        result["ok"] = False
        result["error"] = f"PDF is too small: {size} bytes < {min_bytes} bytes."
        return result

    header = pdf_path.read_bytes()[:5]
    if header != b"%PDF-":
        result["ok"] = False
        result["error"] = "Output file is not a valid PDF header."
        return result

    page_count = count_pdf_pages(pdf_path)
    result["page_count"] = page_count
    if page_count is not None and page_count <= 0:
        result["ok"] = False
        result["error"] = "PDF page count is zero."
        return result
    if page_count is None:
        result["warnings"].append("Page count unavailable; install pymupdf or pypdf for stronger validation.")

    text_sample = extract_text_sample(pdf_path)
    if text_sample is None:
        result["text_extractable"] = None
        result["warnings"].append("Text extraction unavailable; install pymupdf or pypdf for stronger validation.")
    else:
        result["text_extractable"] = bool(text_sample.strip())
        if not text_sample.strip():
            result["ok"] = False
            result["error"] = "PDF text extraction returned empty text."
            return result

    result["ok"] = True
    return result


def write_log(path: Path | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_print(browser: str, html_path: Path, pdf_path: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    if pdf_path.exists():
        pdf_path.unlink()
    with tempfile.TemporaryDirectory(prefix="daily-ai-news-chrome-") as profile_dir:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_dir}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print local HTML to PDF with Edge/Chrome headless mode.")
    parser.add_argument("input_html")
    parser.add_argument("output_pdf")
    parser.add_argument("--browser", help="Explicit Edge/Chrome executable path.")
    parser.add_argument("--retries", type=int, default=2, help="Retry count after the first attempt.")
    parser.add_argument("--timeout", type=int, default=120, help="Per-attempt timeout in seconds.")
    parser.add_argument("--min-bytes", type=int, default=50_000, help="Minimum accepted PDF size.")
    parser.add_argument("--log", help="Write machine-readable conversion log JSON.")
    args = parser.parse_args()

    html_path = Path(args.input_html).resolve()
    pdf_path = Path(args.output_pdf).resolve()
    log_path = Path(args.log).resolve() if args.log else None

    payload: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "input_html": str(html_path),
        "output_pdf": str(pdf_path),
        "attempts": [],
    }

    if not html_path.is_file():
        payload["ok"] = False
        payload["error"] = f"HTML not found: {html_path}"
        write_log(log_path, payload)
        raise SystemExit(f"ERROR: HTML not found: {html_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    browser = find_browser(args.browser)
    payload["browser"] = browser

    last_error = "unknown error"
    for attempt in range(1, args.retries + 2):
        attempt_log: dict[str, Any] = {"attempt": attempt, "started_at": datetime.now().isoformat(timespec="seconds")}
        try:
            completed = run_print(browser, html_path, pdf_path, args.timeout)
            attempt_log["returncode"] = completed.returncode
            attempt_log["stdout_tail"] = completed.stdout[-2000:]
            attempt_log["stderr_tail"] = completed.stderr[-2000:]
            validation = validate_pdf(pdf_path, args.min_bytes)
            attempt_log["validation"] = validation
            payload["attempts"].append(attempt_log)
            if validation.get("ok"):
                payload["ok"] = True
                payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
                payload["pdf"] = validation
                write_log(log_path, payload)
                print(f"OK: {pdf_path} ({validation['size']} bytes, pages={validation.get('page_count')})")
                return
            last_error = str(validation.get("error") or "PDF validation failed.")
        except subprocess.TimeoutExpired as exc:
            attempt_log["timeout"] = args.timeout
            attempt_log["error"] = str(exc)
            payload["attempts"].append(attempt_log)
            last_error = f"Browser timed out after {args.timeout}s."
        except Exception as exc:
            attempt_log["error"] = repr(exc)
            payload["attempts"].append(attempt_log)
            last_error = repr(exc)

    payload["ok"] = False
    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    payload["error"] = last_error
    write_log(log_path, payload)
    raise SystemExit(f"ERROR: PDF conversion failed: {last_error}")


if __name__ == "__main__":
    main()
