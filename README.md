# 每日 AI 新闻自动化流水线

这是一个由 WorkBuddy 托管的每日 AI 新闻生产项目。项目每天生成《昨日 AI 重点资讯》的静态 HTML 报纸、PDF 文件和本地 HTML 看板。

核心设计原则：**WorkBuddy 只负责检索、判断和写结构化内容；脚本负责模板渲染、PDF 生成、校验、归档、日志和看板更新。**

## 项目特性

- 低 token 每日执行：每天只向 WorkBuddy 提供短上下文 `runtime/today_context.md`。
- 结构化内容源：WorkBuddy 输出 `runtime/issue-YYYY-MM-DD.json`，不再每天重写完整 HTML/CSS。
- 固定 HTML 模板：通过 `templates/issue_template.html` 统一版式。
- 稳定 PDF 生成：`make_pdf.py` 使用 Edge/Chrome 无头模式，包含独立临时用户目录、重试和基础 PDF 校验。
- 历史去重：`data/items.jsonl` 维护机器可读的收录记录。
- 本地看板：`outputs/index.html` 汇总每日 HTML/PDF，可直接双击打开，无需本地服务器。
- 可迁移：复制项目目录并重新配置 WorkBuddy 定时任务即可恢复运行。

## 目录结构

```text
每日AI新闻/
  README.md
  提示词.txt
  已收录简表.txt
  make_pdf.py
  requirements.txt

  scripts/
    preflight.py          # 生成 WorkBuddy 每日短上下文
    build_issue.py        # 从结构化 JSON 构建 HTML/PDF，并更新历史与看板
    update_dashboard.py   # 生成 outputs/index.html 静态看板

  templates/
    issue_template.html   # 固定 HTML 报纸模板

  data/
    items.jsonl           # 机器可读历史收录与去重索引

  outputs/
    index.html            # 本地看板
    YYYY-MM/
      AI日报-YYYY-MM-DD.html
      AI日报-YYYY-MM-DD.pdf

  runtime/                # 每日运行中间文件，通常不提交
  logs/                   # 每日运行日志，通常不提交
  reports/                # latest.json 等运行摘要，通常不提交
```

## 环境要求

- Windows
- Python 3.10+
- Microsoft Edge 或 Google Chrome
- 可选依赖：`pymupdf`，用于更可靠地读取 PDF 页数和文本

安装可选依赖：

```powershell
pip install -r requirements.txt
```

如果未安装 `pymupdf`，脚本仍会做基础 PDF 校验，但页数/文本抽查能力会弱一些。

## 每日执行流程

### 1. 生成短上下文

```powershell
python D:\桌面\每日AI新闻\scripts\preflight.py --date today
```

该命令会生成：

```text
runtime/today_context.md
```

WorkBuddy 每日任务只需要阅读这个短上下文。

### 2. WorkBuddy 生成结构化内容

WorkBuddy 根据 `runtime/today_context.md` 检索新闻，并保存：

```text
runtime/issue-YYYY-MM-DD.json
```

WorkBuddy 不需要写完整 HTML，不需要写 CSS，不需要手动追加简表。

### 3. 构建日报

```powershell
python D:\桌面\每日AI新闻\scripts\build_issue.py --date today
```

构建脚本会自动完成：

- 校验 JSON
- 渲染 HTML
- 生成 PDF
- 校验 PDF
- 更新 `data/items.jsonl`
- 追加 `已收录简表.txt`
- 写入 `logs/YYYY-MM-DD.log`
- 写入 `reports/latest.json`
- 刷新 `outputs/index.html`

正式产物统一保存到：

```text
outputs/YYYY-MM/AI日报-YYYY-MM-DD.html
outputs/YYYY-MM/AI日报-YYYY-MM-DD.pdf
```

项目根目录不再保存日报副本。

## WorkBuddy 定时任务建议提示词

```text
进入 D:\桌面\每日AI新闻。先运行 scripts\preflight.py --date today，阅读 runtime\today_context.md。你只负责检索、判断、写 runtime\issue-YYYY-MM-DD.json，不要写 HTML/CSS，不要手动追加简表。保存 JSON 后运行 scripts\build_issue.py --date today。成功后读取 reports\latest.json，只输出一句重点、栏目条数、再度爆火/追踪更新、HTML/PDF/看板路径。
```

## JSON 内容格式

每日内容 JSON 的 schema 由 `runtime/today_context.md` 自动生成。核心结构如下：

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
          "url": "https://...",
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

## 本地看板

看板位置：

```text
outputs/index.html
```

它是静态 HTML，可直接双击打开。看板中的日报链接使用相对路径，例如：

```text
2026-10/AI日报-2026-10-16.html
2026-10/AI日报-2026-10-16.pdf
```

因此本机查看不需要启动本地服务器。

手动刷新看板：

```powershell
python D:\桌面\每日AI新闻\scripts\update_dashboard.py
```

## 测试方式

仅校验 JSON 和模板渲染，不写产物：

```powershell
python D:\桌面\每日AI新闻\scripts\build_issue.py --date YYYY-MM-DD --dry-run
```

如果当天产物已存在，默认不会覆盖。确认重跑时使用：

```powershell
python D:\桌面\每日AI新闻\scripts\build_issue.py --date YYYY-MM-DD --overwrite
```

单独测试 PDF 生成：

```powershell
python D:\桌面\每日AI新闻\make_pdf.py input.html output.pdf --log logs\pdf-test.json
```

## GitHub 发布方案

目标仓库：`daily-ai-news`  
可见性：Public  
归档策略：提交 `outputs/` 下的历史日报 HTML/PDF，让 GitHub 同时作为日报归档库。  
Pages 策略：通过 GitHub Actions 将 `outputs/` 目录部署为 GitHub Pages 站点。

建议提交：

- `README.md`
- `.gitignore`
- `.github/workflows/pages.yml`
- `提示词.txt`
- `已收录简表.txt`
- `make_pdf.py`
- `requirements.txt`
- `scripts/`
- `templates/`
- `data/items.jsonl`
- `outputs/index.html`
- `outputs/.nojekyll`
- `outputs/YYYY-MM/` 下的历史日报 HTML/PDF

不提交：

- `.workbuddy/`
- `.codebuddy/`
- `runtime/`
- `logs/`
- `reports/`
- Python 缓存和本地虚拟环境

GitHub Pages 已准备：

- 工作流：`.github/workflows/pages.yml`
- 发布源：`outputs/`
- 站点首页：`outputs/index.html`

首次推送后，在 GitHub 仓库中进入 `Settings → Pages`，确认 Source 使用 `GitHub Actions`。之后每次推送到 `main` 分支，都会自动发布最新看板和日报归档。

## 注意事项

- 本项目的每日调度仍由 WorkBuddy 托管。
- 脚本不会自行联网抓新闻；新闻检索和内容判断由 WorkBuddy 完成。
- PDF 渲染依赖本机 Edge/Chrome 和系统字体，不同机器可能有轻微分页差异。
- 链接、热度数据和厂商口径信息应由 WorkBuddy 在写作阶段谨慎核验。
