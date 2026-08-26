---
name: enrich-doc
description: 读取已拉取的飞书正文线索，由当前 Agent 生成属性表和封面提示词，写入本地 processed.md 与 enrich.xml。写回云文档由 Agent 用 lark-cli 完成。脚本不调用 LLM、不调用 lark-cli。不写 Hugo、不部署。
---

# 补全元数据

用户能听懂的名字：**补全元数据**。

本目录是完整 Skill，拷到其他 Agent 的 skills 下即可用，**不要**依赖宿主项目的 CLI 包。

```
enrich-doc/
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

用户说「补全」「enrich」并给出文档链接。不要顺带转换或部署。

编排方已经是带模型的 Agent：**不要**再配 `LLM_*`，**不要** curl OpenAI / 其它补全接口。脚本只负责读本地稿、校验字段、写本地文件。

## 你来执行 lark-cli（脚本不会调）

调用时**不要**加 `--profile` 或 `--as`。

inspect 之前若还没有 `data/jobs/<token>/raw.md`，先 fetch markdown：

```bash
lark-cli docs +fetch --api-version v2 --doc 'DOC' --doc-format markdown
```

知识库 wiki 先：`lark-cli drive +inspect --url '…'`，用返回的 `data.token` 作为 docx token。

apply 之后脚本会写出 `data/jobs/<token>/enrich.xml`。若用户要写回云文档，你再执行：

```bash
lark-cli docs +update --doc 'DOC' --command append --doc-format xml --content "$(cat 'data/jobs/<token>/enrich.xml')"
lark-cli docs +fetch --api-version v2 --doc 'DOC' --doc-format xml --detail with-ids
```

把 with-ids XML 存成 `data/jobs/<token>/after.xml`，取出属性区块 id：

```bash
uv run python <本Skill目录>/scripts/run.py enrichment-ids --xml 'data/jobs/<token>/after.xml'
```

再用返回的 id 列表（逗号分隔）移到文档顶部（`--block-id` 用 `document_id` / page id）：

```bash
lark-cli docs +update --doc 'PAGE_ID' --command block_move_after --block-id 'PAGE_ID' --src-block-ids 'id1,id2,…'
```

写回若报没有编辑权限，只保留本地 `processed.md`，不要假装已写回云文档。

## 命令

必须分两步。先 inspect，再由你生成字段，最后 apply。

```mermaid
flowchart LR
  fetch[你 lark-cli fetch] --> inspect[enrich-doc inspect]
  inspect --> gen[Agent 生成字段]
  gen --> apply[enrich-doc apply]
  apply --> write[你 lark-cli 写回云文档]
```

```bash
uv run python <本Skill目录>/scripts/run.py inspect --url 'https://xxx.feishu.cn/docx/TOKEN'
uv run python <本Skill目录>/scripts/run.py apply --url 'https://xxx.feishu.cn/docx/TOKEN' \
  --slug demo-article --lang zh --title '标题' --date 2026-08-22 \
  --author '内容编辑' --categories '具身智能' --summary '摘要' \
  --cover-prompt '封面提示词'
```

`inspect` 成功时标准输出是 JSON（含 `article_text`、`doc_title`、`need_cover_prompt`、`default_date` 等）。失败则打印中文原因并退出码 1，此时不要 apply。`can_edit` 恒为 `null`（是否可写回由你执行 lark-cli 时看结果）。没有本地稿时先 fetch 或先跑 `download-feishu-doc`。

也可用 `--json '{...}'` 或 `--json-file path.json` 把字段一次传给 apply。可用 `--markdown` 指向已保存的 fetch 结果。

## 依赖

- 环境已登录的 `lark-cli`（豆包工作 Agent 已内置）；由**你**调用，不要让 Python 去 subprocess
- `scripts/requirements.txt`（`httpx`、`pydantic-settings`）
- 不需要飞书 App ID / Secret

## 你来生成字段

读完 inspect 的 JSON 后，**你自己**根据正文生成下面字段，再交给 apply。只输出将写入文档的值。

必填：`slug`、`lang`、`title`、`date`、`author`、`categories`、`summary`。

1. **语言（必须先判）** 文章有中文版与英文版。正文以中文为主 → `lang=zh`，title / summary / categories / cover_prompt 都用中文。正文以英文为主 → `lang=en`，对应字段都用英文。不要把中文稿写成英文标题摘要，反之亦然。
2. **title** 结合 `doc_title`（飞书文档标题）与正文。若 `doc_title` 非空、与主题高度吻合且语言一致，则直接用它（可只做空白/标点规范化）。否则按正文总结一个简洁准确的 title，语言与正文一致。
3. **slug** 英文 kebab-case（小写字母、数字、连字符），必须能从 title 的核心主题联想到；中文 title 用意译英文词，英文 title 提炼关键词。不要用与 title 无关的泛化词。
4. **date** `YYYY-MM-DD`，不得晚于今天。正文无明显日期时用 inspect 里的 `default_date`。
5. **author** 默认「内容编辑」（inspect 的 `default_author`）；正文明确写了作者则用正文作者。英文稿未写作者时仍可用「内容编辑」。
6. **categories** 1～3 个。中文稿用中文分类、中文逗号「，」分隔；英文稿用英文分类、英文逗号 `", "` 分隔。
7. **summary** 约 100 字/词以内，概括核心，语言与正文一致。
8. 若 `need_cover_prompt` 为 true：必须给 `--cover-prompt`（画面主体、风格、色调；语言与正文一致；不要出现网址）。为 false 时不要传封面提示词。

`doc_title` 与正文语言不一致时，以正文语言为准。

## 行为

- `inspect`：读本地稿（或 `--markdown`）；云文档对应的本地稿已有可解析属性表则拒绝；几乎没有文字则拒绝。
- `apply`：同样检查后校验字段，写入本地 `processed.md`（不改 `raw.md`）和 `data/jobs/<token>/enrich.xml`。`processed.md` 结构为：第一行是由 `raw.md` 开头 `<title>` 转成的 markdown 一级标题，下面是属性/图片，再然后是文章正文。
- 脚本**不**写回飞书；写回步骤见上文 lark-cli。
- 正文插图不算封面：仅当「图片」区已有图时才跳过封面提示词。
- 不写 Hugo、不压缩、不部署。
