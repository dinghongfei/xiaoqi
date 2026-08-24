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

已运行 `download-feishu-doc`（或 `data/last-job.json` 指向有效 processed.md）之后。官网预览链路：

```mermaid
flowchart LR
  dl[download-feishu-doc] --> cw[convert-website]
  cw --> cm[compress-media]
  cm --> loc[deploy-local]
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
- 去掉正文开头的文档标题（页面标题用 front matter）。
- 写入 `site/content/{lang}/blog/{slug}.md`。
- 更新 last-job 的 `content_path` / `site_preview`。
- **不**构建 Hugo（交给 `deploy-local`）。

## 注意

工作区必须已有 Hugo 工程（`site/hugo.toml`）。本 Skill 不会 `hugo new site`。
