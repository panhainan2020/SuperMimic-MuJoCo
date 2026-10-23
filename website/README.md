# 可移植评估网页

**简体中文** | [English](README.en.md)

可直接打开 `index.html`，也可通过静态网站服务托管此目录。指标展示无需服务器或外部 JavaScript 依赖。按照仓库目录结构访问时，报告通过相对链接指向 `../results/098000/`。

```sh
# 仅使用已提交的小体积文本快照重新构建。
python website/build.py

# 生成独立部署目录：包含 HTML 和小体积文本结果，不包含媒体文件。
python website/build.py --output-dir /tmp/supermimic-site

# 仅限维护者：从明确指定且已存在的实验目录刷新结果。
python website/build.py --experiment-dir "$EXPERIMENT_ROOT"
```

导出时仅选取可公开的 JSON 字段和 CSV 指标，记录原始元数据哈希，并拒绝包含私有机器路径的内容。导出工具不读取检查点、数据集、轨迹或视频，也不下载或上传远端产物。原始实验证据应单独保存在持久存储中；发布网页不构成传输大体积训练产物的隐含授权。

## 独立托管视频

演示网站目前通过 R2 提供五个选定示例；`media-config.js` 使用公开 HTTPS 地址，因此在检出的仓库中也可以播放。完整结果表始终可用。尚未发布的视频位置会显示未公开提示。只有访问者点击播放时，页面才设置视频源地址；页面加载时不会请求封面图片。当 `baseUrl` 为空时，未配置的媒体键保持不可用。将 `enabled` 设为 `false` 可得到完全离线、仅展示元数据的页面。

```js
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "",
  overrides: {
    "lafan/overview.mp4": "https://media.example.org/supermimic/overview.mp4",
    "100style/ood_low.mp4": "https://media.example.org/supermimic/ood_low.mp4",
    "100style/ood_median.mp4": "https://media.example.org/supermimic/ood_median.mp4",
    "100style/ood_high.mp4": "https://media.example.org/supermimic/ood_high.mp4",
    "100style/ood_failure.mp4": "https://media.example.org/supermimic/ood_failure.mp4"
  },
  repositoryUrl: "https://github.com/OWNER/REPOSITORY"
};
```

若媒体托管服务包含全部文件，可将 `baseUrl` 设为其公开 HTTPS 前缀。媒体键及原始文件相对于实验目录的路径列于 `results/098000/media_manifest.json`。请使用稳定的公开媒体地址，并确保服务支持 `Content-Type: video/mp4` 和字节范围请求。推荐使用 H.264/yuv420p 编码、启用 `faststart` 的 MP4 文件。用于发布的压缩副本保存在 Git 之外；保留原始哈希，并单独记录发布文件的哈希。

不得提交令牌、私有凭据或有时限的签名地址。网页仅允许 HTTPS 远端媒体地址、相对地址，以及开发时使用的 localhost HTTP 地址。源码已在 [GitHub 仓库](https://github.com/panhainan2020/SuperMimic-MuJoCo)公开。仓库可见性与静态网站托管独立管理。

使用已安装的 Playwright/Chromium 运行浏览器冒烟检查：

```sh
python website/check_site.py --browser /path/to/chromium
```

该检查验证禁用媒体时的页面、结果导航、数量、搜索、排序、移动端布局，以及启动时没有媒体请求。它不会安装浏览器或下载产物。可选的 `--experiment-dir` 参数通过临时的本机回环服务器使用已有本地视频验证播放；此过程只读取本地媒体，不会复制或发布它们。
