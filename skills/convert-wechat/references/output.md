# 输出

```
公众号预览已生成 preview/_wechat/zh-cn/<slug>/index.html
公众号预览=http://127.0.0.1:1314/_wechat/zh-cn/<slug>/
```

产物：

- `preview/_wechat/{lang}/{slug}/index.html`
- `preview/_wechat/index.json`（首页公众号列表）

预览页左侧文章、右侧调样式，可切手机/电脑。有封面时最上方是封面图（裁切展示，悬停可看完整原图）、提示和横线。点「复制正文」会带上当前样式和内嵌图片；图片按原图像素大小粘贴，不跟预览宽度走。「复制封面图」默认勾选，会带上封面、提示和横线；取消勾选则只复制正文。高亮块用 `section` 写出，复制时也会把 `aside`/`div` 转成 `section`，避免公众号编辑器丢掉背景色。不要单独复制图片（本机地址公众号拉不到）。
