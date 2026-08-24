---
name: deploy-local
description: 对已有 site/ 跑 hugo 构建，把 public/ 拷到 preview/，供 127.0.0.1:1314 预览。不是 hugo new site。
---

# 本地部署（官网预览）

用户能听懂的名字：**本地部署 / 官网预览**。

本目录是完整 Skill，拷到其他 Agent 的 skills 下即可用，**不要**依赖宿主项目的 CLI 包。

```
deploy-local/
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

`convert-website`（建议还跑过 `compress-media`）之后。用户要看官网效果时必须跑本步。

```mermaid
flowchart LR
  cw[convert-website] --> cm[compress-media]
  cm --> loc[deploy-local]
```

## 命令

```bash
uv run python <本Skill目录>/scripts/run.py
uv run python <本Skill目录>/scripts/run.py --root /path/to/workspace
```

## 依赖

本机 `hugo`（Extended）。Python 包见 `scripts/requirements.txt`。

## 行为

- **不是** `hugo new site`，也不下载主题。
- 假定工作区 `site/` 已是完整 Hugo 工程（缺 `hugo.toml` 直接报错）。
- `hugo --minify` 生成 `site/public/`，再整目录覆盖拷到 `preview/`。
- 保留已有 `preview/_wechat/`，避免冲掉公众号页。
- 成功时打印 `SITE_PREVIEW=...`

预览 HTTP 由宿主项目的启动脚本提供（本 Skill 只负责构建和拷贝）。
