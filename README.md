# 飞书内容助手

把一篇飞书云文档，变成**官网文章预览**和**公众号排版预览**。对着助手说话即可，不必自己敲命令、也不必懂网站或排版软件。

支持中文和英文稿。文档里的图片、视频、表格、代码、引用、高亮颜色都会尽量带上。仓库里自带一个演示站，装好后就能先看到效果。

---

## 第一次使用

大约几分钟。准备好两样东西：**本项目已经用 Trae 或 Cursor 打开**，以及一个**飞书企业自建应用**。

### 1. 创建一个飞书应用

打开 [飞书开放平台](https://open.feishu.cn/app)，创建**企业自建应用**，并开通机器人。

事件与回调用**长连接**，不要去填 Webhook 网址。事件和权限都要开全，漏了后面出预览时会提示不足。

**事件订阅**

在应用详情里打开 **事件与回调**，搜索并订阅：

| 在开放平台里搜索 | 对应事件 |
| --- | --- |
| 接收消息 | `im.message.receive_v1` |

**权限**

本助手用应用身份（机器人）收消息、回卡片、读写文档。在应用详情里打开 **权限管理**，点 **批量导入导出权限**，把下面整段 JSON 粘贴进去再申请开通。用户身份不用开，`user` 保持空列表即可。

```json
{
  "scopes": {
    "tenant": [
      "application:application:self_manage",
      "application:bot.basic_info:read",
      "application:bot.menu:write",
      "board:whiteboard:node:read",
      "cardkit:card:read",
      "cardkit:card:write",
      "contact:contact.base:readonly",
      "docs:document.comment:create",
      "docs:document.comment:delete",
      "docs:document.comment:read",
      "docs:document.comment:update",
      "docs:document.comment:write_only",
      "docs:document.media:download",
      "docx:document.block:convert",
      "docx:document:readonly",
      "docx:document:write_only",
      "drive:drive.metadata:readonly",
      "im:chat.members:bot_access",
      "im:chat:create",
      "im:chat:read",
      "im:chat:update",
      "im:message.group_at_msg.include_bot:readonly",
      "im:message.group_at_msg:readonly",
      "im:message.p2p_msg:readonly",
      "im:message.pins:read",
      "im:message.pins:write_only",
      "im:message.reactions:read",
      "im:message.reactions:write_only",
      "im:message:readonly",
      "im:message:send_as_bot",
      "im:message:send_multi_users",
      "im:message:send_sys_msg",
      "im:message:update",
      "im:resource",
      "wiki:node:read",
      "wiki:wiki:readonly"
    ],
    "user": [
      "offline_access"
    ]
  }
}
```

应用建好后，还要把这个机器人加进目标云文档或知识库的**协作者**。只看预览时，只读即可。希望助手把标题、摘要等信息写回飞书文档时，再给它「可编辑」。没有编辑权限也可以继续出预览，助手会把信息留在本地，不会去改你的云文档。

记下应用的 **App ID** 和 **App Secret**。只要这两项。不要从别的文件夹拷密钥，也不要自己编。

### 2. 让助手帮你安装

回到 Trae 或 Cursor，对助手说 **安装环境**，把 App ID 和 Secret 发给它。

它会在本机把环境装好、写出配置、打开演示站。成功后，用浏览器打开 [http://127.0.0.1:1314/](http://127.0.0.1:1314/) ，能看到演示站就算通了。

如果助手说还缺某样东西（例如本机还没装 Node，或 Mac 上还没有 Homebrew），按它的中文提示做最少的一步，再说 **「继续安装」**。

### 3. 试一篇自己的文档

把一篇飞书云文档链接发给助手，说 **「帮我看看这篇官网效果」**。对话里会出现预览地址，打开就是第一篇成品。

知识库里的文档链接也可以。要公众号排版时，再说 **「出一版公众号预览」**。

---

## 平时怎么说

对着助手说话即可。在编辑器里说，或在飞书里找机器人说，意思一样。

| 你可以说 | 你会得到 |
| --- | --- |
| 「帮我看看这篇官网效果」+ 文档链接 | 一篇官网预览。标题、摘要、封面、图片和视频都会排进演示站风格的页面里。 |
| 「出一版公众号预览」 | 一张可调样式的预览页：左侧是文章（可切换手机 / 电脑宽度），右侧可选主题、字体、字号和主题色。调好后在**浏览器里**点「一键复制」，再贴进公众号后台。 |
| 只丢一个文档链接 | 默认官网和公众号两路都做。飞书里会回一张带两个按钮的卡片。 |
| 「补全一下元数据」+ 文档链接 | 助手根据正文补标题、日期、作者、分类、摘要，必要时再写封面图提示词。有编辑权限会写回飞书文档；没有则只留在本地，照样能继续出预览。 |
| 「发布」并附上你的口令 | 把已经做好的预览传到云端。没开通云存储时，助手会明确告诉你「未开通」，不会擅自上传。 |
| 「清掉预览稿」 | 清掉这次生成的预览和中间稿，演示站和原文都还在。 |
| 「启动 / 停止 / 看看日志」 | 助手帮你开关本机预览和飞书机器人，不必自己找开关。 |

文档顶部如果还没有标题、日期、分类这些属性，官网转换会做不下去。这时先说「补全」，再看出预览。

公众号预览**不会改你的原文**，只是换一层样式。飞书对话里没法写入电脑剪贴板，所以复制一定要在浏览器预览页完成。也不要单独存图再往公众号里插：预览里的图是给这台电脑看的，公众号后台往往拉不到。

---

## 两种用法

**在 Trae / Cursor 里打开本项目说话。** 适合先在电脑上出预览。装好后，预览地址就是 [http://127.0.0.1:1314/](http://127.0.0.1:1314/) 。这个地址只在**这台电脑**上打得开。

**在飞书里直接找机器人说话。** 适合丢链接、收卡片。需要同时满足：

1. 本机已经登录一套对话式编程助手，三选一即可：[Claude Code](https://code.claude.com/docs/en/quickstart)、[OpenCode](https://opencode.ai)、[Codex](https://github.com/openai/codex)。
2. 装好并完成登录后，用这套助手打开本项目。
3. 飞书机器人和这套助手必须在**同一台电脑、同一个项目**里。不要指望云上的机器人去驱动你笔记本里的助手。

只用 Trae / Cursor、不在飞书里找机器人时，走上面的第 3 步也能出预览。

---

## 使用时请留意

- 目标文档或知识库要把应用机器人加为协作者，否则助手读不到正文和图片。
- 开放平台的事件和权限请一次勾全；漏开会在预览时报权限错误，把缺的那一项补上即可。
- 预览是给本机看的。换电脑、或把链接发给别人，对方打不开 `127.0.0.1` 这种地址。要给别人看，需要你明确说「发布」并提供口令，且工作区已经开通云存储。
- 不要把别的项目里的密钥拷进这里，也不要让助手去编造飞书或云存储口令。
- 清理预览稿不会删掉飞书原文，也不会动你电脑上的项目原稿。

---

## 开源声明

本项目以 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) 开源。你可以自由使用、修改和分享，完整条款见仓库里的 `LICENSE` 文件。
