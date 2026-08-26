---
name: reply-preview
description: 遗留 Skill：用飞书 OpenAPI 回复预览卡片。豆包 / IDE 场景不要调用；无 App 凭证时会跳过。
---

# 回复预览卡片

用户能听懂的名字：**把预览发回飞书 / 回卡片**。

本目录是完整 Skill，拷到其他 Agent 的 skills 下即可用，**不要**依赖宿主项目的 CLI 包。

```
reply-preview/
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

豆包工作 Agent 与 IDE 预览**不要**调用本 Skill：直接在对话里回复 `官网预览=` / `公众号预览=`。

无 `.env` 飞书应用凭证时脚本会跳过（成功退出），不要为此去创建应用或编造密钥。

## 命令

```bash
uv run python <本Skill目录>/scripts/run.py --message-id 'om_xxx'
uv run python <本Skill目录>/scripts/run.py --message-id 'om_xxx' --site-preview 'http://127.0.0.1:1314/blog/slug/'
uv run python <本Skill目录>/scripts/run.py --message-id 'om_xxx' --summary '失败原因（中文）'
uv run python <本Skill目录>/scripts/run.py --message-id 'om_xxx' --root /path/to/workspace
```

未传 `--site-preview` / `--wechat-preview` 时，从 `data/last-job.json` 读取这两项。

## 行为

- 未配置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：跳过，不报错。
- 有凭证时发交互卡片：有 URL 则带「官网预览」「公众号预览」按钮。
- 卡片接口失败则回纯文本。
