# Sites Worker 与 R2 媒体存储

**简体中文** | [English](README.en.md)

Worker 嵌入静态网页和小体积指标文件；视频存放在 R2 绑定 `BUCKET`，不进入 Git 或部署包。无 npm 依赖，不使用 D1。

```sh
node --test website/hosting/test_worker.mjs
python website/hosting/build_host.py --checkout "$REGISTERED_SITE_CHECKOUT" --node node
```

使用 Node.js 22 或更新版本。检出目录须包含现有 Site 的 `.openai/hosting.json`。构建工具保留项目 ID，配置 R2，并生成 Worker 源码和 `dist/` 部署产物；在生成的检出目录运行 `node scripts/build.mjs` 和 `node scripts/validate-artifact.mjs` 可重新构建、验证。

媒体路由、同源视频地址、允许上传的文件大小和 SHA-256 均由 [media_manifest.json](../../results/098000/media_manifest.json) 生成，避免维护重复名单。`GET` / `HEAD /media/<key>` 支持单字节范围、`206` / `416`、ETag 和 `If-Range`。已校验对象通过 `X-Content-SHA256` 返回完整文件哈希，HEAD 无需传输视频。

发布已获授权的本地演示视频时：

1. 通过 Sites 临时设置密钥 `MEDIA_UPLOAD_TOKEN` 和开关 `MEDIA_UPLOAD_ENABLED="true"`，部署对应环境。
2. 使用 `PUT /admin/media/<key>`，附带 `Authorization: Bearer …`、准确的 `Content-Length` 和 `Content-Type: video/mp4`。单文件上限 25 MiB，大小须与清单一致；Worker 有界读取并核对 SHA-256 后才写入 R2，响应返回大小、哈希和 ETag。
3. 核对上传回执和 HEAD 元数据后，将开关设为 `"false"`、移除密钥并部署，确认匿名 PUT 返回 `404`。

密钥仅保存在运行时环境，不得进入命令行、源码、清单或日志。构建和测试均不访问网络。训练产物留在服务器持久盘；此流程不授权下载远端权重、数据集、回放或归档，仅发布本地已有且明确获准的演示视频。
