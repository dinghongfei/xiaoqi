# 输出

`output/<token>/`：

- `raw.md` / `raw.xml`：lark-cli 原始输出
- `body.md`：正文（媒体已改为本地文件名）
- `summary.txt`：Agent 根据正文总结的摘要（≤100 字）
- 图片/视频文件：与上述文件同目录（hash 文件名）
- `<文章标题>.html`：公众号预览页

stdout 示例：

```
title=文章标题
summary=不超过一百字的摘要…
预览文件=/abs/path/to/文章标题.html
正文稿=/abs/path/to/body.md
```
