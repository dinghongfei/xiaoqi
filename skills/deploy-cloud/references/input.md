# 输入

必须同时具备：

- 用户明确要发布，并提供 `--sk`
- 工作区已有 `preview/`（官网 + 可选 `_wechat/`）
- `.env` 中 `PUBLISH_SECRET_KEY` 与 `--sk` 一致

`OSS_BUCKET` 为空时本步返回「未开通」，不是去猜 bucket。
