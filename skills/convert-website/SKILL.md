---
name: convert-website
description: 把已下载的飞书文档解析成官网 Hugo Markdown，写入 site/content/{lang}/blog/{slug}.md。
---

# 转换为官网文章

用户能听懂的名字：**转换为官网文章**。

本目录是完整 Skill，拷到其他 Agent 的 skills 下即可用，**不要**依赖宿主项目的 CLI 包。

```
convert-website/
├── SKILL.md
├── scripts/
│   ├── run.py
│   └── requirements.txt
├── references/
│   ├── input.md
│   └── output.md
└── assets/                  # 资源文件（本 Skill 暂无）
```

## 何时调用

用户给了飞书文档链接时，先跑 `download-feishu-doc`（同一链接也要重新下载），再跑本 Skill。不要直接用上次的 `processed.md`。仅当本轮已经下载过、或用户没有给新链接时，才读 `data/last-job.json` 里的 processed.md。没有特别说明时，官网和公众号都要转换：

```mermaid
flowchart LR
  dl[download-feishu-doc] --> cw[convert-website]
  cw --> cm[compress-media]
  cm --> loc[deploy-local]
  loc --> wx[convert-wechat]
```

## 命令

```bash
uv run python <本Skill目录>/scripts/run.py
uv run python <本Skill目录>/scripts/run.py --section blog --root /path/to/workspace
uv run python <本Skill目录>/scripts/run.py --markdown path/to/processed.md
```

默认读工作区 `data/last-job.json`。栏目固定 `blog`。

## 行为

- 解析三列表格；校验 slug / lang / section（栏目固定 `blog`）。
- unescape、分栏 shortcode、有序列表修复。
- 用飞书 XML 补回颜色、下划线、高亮、代码标题、图片说明；callout 收成短代码。
- 仅当正文第一行是一级标题、且属性表上方还没有文档标题一级标题时，把它当作飞书文档标题去掉（页面标题用 front matter）。正文里其它一级标题保留。
- 写入 `site/content/{lang}/blog/{slug}.md`。
- 更新 last-job 的 `content_path` / `site_preview`。
- **不**构建 Hugo（交给 `deploy-local`）。
- 成功且已有预览 URL 时打印 `官网预览=...`

## 注意

工作区必须已有 Hugo 工程（`site/hugo.toml`）。本 Skill 不会 `hugo new site`。
