---
name: convert-wechat-lite
description: 把飞书云文档转成公众号预览 HTML。用户给出飞书文档链接或说转公众号时使用。
---

# 飞书转公众号（轻量）

```
convert-wechat-lite/
├── SKILL.md
├── scripts/run.py
├── references/
└── output/<token>/
    ├── raw.md / raw.xml / body.md
    ├── summary.txt
    ├── <hash>.png / <hash>.mp4
    └── <文章标题>.html
```

## 何时调用

用户发了飞书 docx / wiki 链接，或说「转公众号」「出公众号预览」。

## 流程

### 1. 拉取并转换

```bash
python3 <本Skill目录>/scripts/run.py --url '用户给的链接'
# 或
python3 <本Skill目录>/scripts/run.py --token 'TOKEN'
# wiki：
python3 <本Skill目录>/scripts/run.py --token 'WIKI_TOKEN' --kind wiki
```

依赖由脚本预检；缺包时会 `python3 -m pip install -r scripts/requirements.txt`。

有图片/视频时下载到与 `raw.md` / `raw.xml` **同一目录**（HTTP 失败则用 `lark-cli docs +media-download`），再嵌入预览 HTML。正文有图时用第一张作封面；无图则跳过封面。

### 2. 总结摘要（必须）

1. 阅读 `output/<token>/body.md` 与 `title=`
2. **根据全文内容总结**一条公众号摘要，**不超过 100 字**（概括主题与要点，不要大段照搬原文）
3. 写入 `output/<token>/summary.txt`
4. 再生成带摘要的最终预览：

```bash
python3 <本Skill目录>/scripts/run.py --token 'TOKEN' \
  --reuse-raw \
  --summary-file '<本Skill目录>/output/<token>/summary.txt'
```

成功时 stdout 含：`title=`、`summary=`、`预览文件=`、`正文稿=`。

## 回复用户

给出预览 HTML 的绝对路径，说明打开即可预览，并可点「复制正文」贴进公众号。
