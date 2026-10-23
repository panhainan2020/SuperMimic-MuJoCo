# 使用独立 R2 媒体存储的 Sites Worker

**简体中文** | [English](README.en.md)

Worker 仅嵌入小体积的静态 HTML、JS、CSS、JSON、CSV 和报告文件。视频保存在 Site 的 R2 绑定 `BUCKET` 中，不进入 Git 或部署包。该 Worker 没有 npm 依赖，也不使用 D1。

```sh
node --test website/hosting/test_worker.mjs
python website/hosting/build_host.py --checkout "$REGISTERED_SITE_CHECKOUT" --node node
```

指定的检出目录必须已有 `.openai/hosting.json`，其中包含现有 Site 的项目 ID。构建工具保留清单中的其他字段，移除静态网站声明，设置 `r2: "BUCKET"` 和 `d1: null`，并生成源码、`dist/server/index.js` 及 `dist/.openai/hosting.json`。在生成的检出目录中使用 `node scripts/build.mjs` 重新构建，使用 `node scripts/validate-artifact.mjs` 验证。仓库中的可移植网页引用公开 HTTPS 媒体地址；托管版本仅使用五个同源演示视频地址，并省略仓库链接。源码仓库现已公开；更改仓库可见性不会重新部署现有网站。

公开路由 `GET`/`HEAD /media/<key>` 支持单个字节范围、后缀范围和开放范围、`206` 响应、无法满足范围时的 `416` 响应、ETag 验证及 `If-Range`。路由白名单中仅包含以下媒体键：

- `lafan/overview.mp4`
- `100style/ood_low.mp4`
- `100style/ood_median.mp4`
- `100style/ood_high.mp4`
- `100style/ood_failure.mp4`

发布所有者已授权的媒体时，应通过 Sites 临时配置运行时密钥 **`MEDIA_UPLOAD_TOKEN`** 和运行时开关 **`MEDIA_UPLOAD_ENABLED="true"`**。两者缺一不可：开关缺失、值为 `"false"` 或其他值时，路由均保持禁用，即使运行时仍残留旧令牌。`PUT /admin/media/<key>` 要求 `Authorization: Bearer …`、准确的 `Content-Length`、`Content-Type: video/mp4`、非空请求体，且**每个文件不超过 25 MiB**。请求体通过定长流写入 R2；响应返回 R2 保存的大小和 ETag。构建过程不会写入令牌，也不会向访问者返回令牌。上传并验证后，必须显式设置 **`MEDIA_UPLOAD_ENABLED="false"`**、移除令牌、部署新的源码及环境版本，并确认匿名空 PUT 请求返回 `404`。不得将密钥放入命令行参数、源码、清单、浏览器配置或日志。

构建工具和单元测试均不会上传、下载或访问网络，也不会把媒体复制到代码仓库。训练产物保存在服务器持久盘；此托管实现不构成下载远端权重、动作数据集、回放或完整归档的授权。媒体发布单独执行，仅使用本地已有且明确获准发布的演示编码文件。
