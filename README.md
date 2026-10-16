# 每日 AI 新闻自动化流水线

一个用于生成每日 AI 新闻简报的静态发布项目。流程以结构化 JSON 作为内容源，自动渲染 HTML、生成 PDF，并维护可浏览的历史看板。

项目适合以下场景：

- 每天整理 AI 领域重点新闻。
- 将日报归档为可公开访问的 HTML/PDF。
- 使用 GitHub Pages 发布静态看板。
- 需要把内容生成、版式渲染、PDF 输出和历史归档分开维护。

## 核心思路

项目把每日流程拆成两部分：

1. 内容生成：由人工或自动化助手整理新闻，并保存为结构化 JSON。
2. 确定性构建：脚本负责校验 JSON、渲染 HTML、生成 PDF、更新索引和刷新看板。

这样可以避免每天重复编写 HTML/CSS，也便于排查失败原因。

## 功能特性

- 结构化内容输入：每日内容保存在 `runtime/issue-YYYY-MM-DD.json`。
- 固定 HTML 模板：通过 `templates/issue_template.html` 统一日报版式。
- PDF 自动生成：`make_pdf.py` 使用 Edge/Chrome 无头模式输出 PDF。
- 历史索引：`data/items.jsonl` 保存机器可读的收录记录。
- 静态看板：`outputs/index.html` 汇总历史日报，可直接跳转到 HTML/PDF。
- GitHub Pages 友好：`outputs/` 可作为静态站点发布目录。

## 目录结构

```text
每日AI新闻/
  README.md
  make_pdf.py
  requirements.txt

  scripts/
    preflight.py          # 生成当天运行上下文
    build_issue.py        # 从 JSON 构建 HTML/PDF，并更新索引
    update_dashboard.py   # 生成 outputs/index.html 静态看板

  templates/
    issue_template.html   # 日报 HTML 模板

  data/
    items.jsonl           # 历史收录记录

  outputs/
    index.html            # 静态看板
    YYYY-MM/
      AI日报-YYYY-MM-DD.html
      AI日报-YYYY-MM-DD.pdf

  runtime/                # 运行中间文件，通常不提交
  logs/                   # 运行日志，通常不提交
  reports/                # 运行摘要，通常不提交
```

## 环境要求

- Python 3.10+
- Microsoft Edge 或 Google Chrome
- 可选依赖：`pymupdf`，用于更可靠地读取 PDF 页数和文本

安装依赖：

```bash
pip install -r requirements.txt
```

如果未安装 `pymupdf`，脚本仍会进行基础 PDF 校验。

## 基本用法

以下命令均在项目根目录执行。

### 1. 生成当天上下文

```bash
python scripts/preflight.py --date today
```

该命令会生成：

```text
runtime/today_context.md
```

它包含当天日期、期号、收录窗口、近期去重索引和 JSON 格式要求。

### 2. 准备日报 JSON

根据 `runtime/today_context.md` 整理当天内容，并保存为：

```text
runtime/issue-YYYY-MM-DD.json
```

核心结构示例：

```json
{
  "date": "2026-10-16",
  "issue": 3,
  "window": "10 月 15 日（含 10 月 14 日晚间）",
  "deadline": "2026 年 10 月 16 日上午（北京时间）",
  "sections": [
    {
      "name": "大模型与 AI 产品进展",
      "lead": "一句栏目导语",
      "items": [
        {
          "level": "main",
          "title": "标题",
          "badge": "",
          "language": "中文",
          "read_time": "约 4 分钟",
          "why": "为什么值得读，一句话",
          "body": ["段落 1", "段落 2"],
          "url": "https://example.com/article",
          "source": "来源名称",
          "event_id": "stable-event-id"
        }
      ]
    }
  ],
  "gaps": ["信息缺口"],
  "excluded": []
}
```

`badge` 仅允许为空、`再度爆火` 或 `追踪更新`。

### 3. 构建日报

```bash
python scripts/build_issue.py --date today
```

构建完成后会生成：

```text
outputs/YYYY-MM/AI日报-YYYY-MM-DD.html
outputs/YYYY-MM/AI日报-YYYY-MM-DD.pdf
outputs/index.html
```

同时会更新：

```text
data/items.jsonl
logs/YYYY-MM-DD.log
reports/latest.json
```

## 测试与重跑

仅校验 JSON 和模板渲染，不写入正式产物：

```bash
python scripts/build_issue.py --date YYYY-MM-DD --dry-run
```

如果当天产物已存在，默认不会覆盖。确认需要重建时使用：

```bash
python scripts/build_issue.py --date YYYY-MM-DD --overwrite
```

单独测试 PDF 生成：

```bash
python make_pdf.py input.html output.pdf --log logs/pdf-test.json
```

手动刷新看板：

```bash
python scripts/update_dashboard.py
```

## 静态看板

看板文件位于：

```text
outputs/index.html
```

它是纯静态 HTML，链接使用相对路径，例如：

```text
2026-10/AI日报-2026-10-16.html
2026-10/AI日报-2026-10-16.pdf
```

本地查看时可以直接双击打开；部署到 GitHub Pages 时，可将 `outputs/` 作为站点发布目录。

## GitHub Pages

仓库已包含 GitHub Pages 工作流：

```text
.github/workflows/pages.yml
```

该工作流会将 `outputs/` 发布为静态站点。推送到 `main` 分支后，可在仓库的 `Settings → Pages` 中选择 `GitHub Actions` 作为发布源。

## 注意事项

- 脚本不负责自动抓取新闻；新闻筛选和内容撰写需要在生成 JSON 前完成。
- PDF 渲染依赖本机 Edge/Chrome，不同系统的分页可能略有差异。
- `runtime/`、`logs/`、`reports/` 属于运行产物，通常不需要提交到仓库。
- `outputs/` 是公开归档目录，提交前请确认其中内容适合公开展示。
