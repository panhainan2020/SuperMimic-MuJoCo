# 可移植评估网页

**简体中文** | [English](README.en.md)

可直接打开 `index.html`，也可通过静态网站服务托管此目录。指标展示无需服务器或外部 JavaScript 依赖。按照仓库目录结构访问时，报告通过相对链接指向 `../results/098000/`。

```sh
# 使用已提交的小体积文本快照重新构建，自动包含整段 MAE 和虚影视频索引。
python website/build.py

# 生成独立部署目录：包含 HTML 和小体积文本结果，不包含媒体文件。
python website/build.py --output-dir /tmp/supermimic-site

# 仅限维护者：从明确指定且已存在的实验目录刷新结果。
python website/build.py --experiment-dir "$EXPERIMENT_ROOT"
```

导出时仅选取可公开的 JSON 字段和 CSV 指标，记录原始元数据哈希，并拒绝包含私有机器路径的内容。导出工具不读取检查点、数据集、轨迹或视频，也不下载或上传远端产物。原始实验证据应单独保存在持久存储中；发布网页不构成传输大体积训练产物的隐含授权。

## 本地预览虚影对比和整段 MAE

先用[评估工具](../docs/evaluation.md)生成已有轨迹的 MAE 与虚影视频。将视频清单和指标作为显式输入，输出到实验目录，不改写仓库中已发布的结果快照：

```sh
python website/build.py \
  --mae-dir "$SUPERMIMIC_EXPERIMENT_ROOT/trajectory_mae" \
  --media-manifest "$SUPERMIMIC_EXPERIMENT_ROOT/media/media_manifest.json" \
  --output-dir "$SUPERMIMIC_EXPERIMENT_ROOT/site_preview"
```

虚影视频在同一世界坐标下显示实体策略和青色参考，保留位置偏差。页面分别标记预览视频时长、完整参考时长及失败状态。整段 MAE 使用全部有效记录，不只使用视频截取的片段；关节角 MAE、根 XYZ 分量 MAE 与根位置 L2 分开显示。可在逐片等权和逐帧加权之间切换，完整数值通过小体积 JSON/CSV 提供。

此模式只生成本地文件，不上传视频、不推送 Git、不部署网站。媒体仍由调用者放在输出目录的 `media/` 路径下，或通过本地软链接访问已有文件；构建器不复制视频。新增文件必须经过明确的文件清单与差异审阅后，才能另行批准提交或发布。

## 独立托管视频

仓库现包含 20 条虚影视频的索引：7 条 LAFAN 预览、1 条概览、12 条 100STYLE 记录。视频文件不在 Git 中，此次源码提交也不上传媒体或更新独立托管的网站。`media-config.js` 默认禁用媒体，完整指标、MAE 和视频说明仍可查看。此前线上网站的五个分屏示例属于旧版；旧版压缩记录保存在 `results/098000/media_delivery.json`，不对应新虚影文件。

单独获准托管视频后，配置新媒体键。只有访问者点击播放时，页面才设置视频源地址；页面加载时不会请求封面图片。当 `baseUrl` 为空时，未配置的媒体键保持不可用。

```js
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "",
  overrides: {
    "ghost_v1/lafan/overview.mp4": "https://media.example.org/supermimic/overview.mp4",
    "ghost_v1/100style/ood_low.mp4": "https://media.example.org/supermimic/ood_low.mp4"
  },
  repositoryUrl: "https://github.com/OWNER/REPOSITORY"
};
```

若媒体托管服务包含全部文件，可将 `baseUrl` 设为其公开 HTTPS 前缀。媒体键、展示范围与交付文件哈希列于 `results/098000/media_manifest.json`；清单不包含原始轨迹路径。请使用稳定的公开媒体地址，并确保服务支持 `Content-Type: video/mp4` 和字节范围请求。推荐使用 H.264/yuv420p 编码、启用 `faststart` 的 MP4 文件。用于发布的压缩副本保存在 Git 之外；保留原始哈希，并单独记录发布文件的哈希。

不得提交令牌、私有凭据或有时限的签名地址。网页仅允许 HTTPS 远端媒体地址、相对地址，以及开发时使用的 localhost HTTP 地址。源码已在 [GitHub 仓库](https://github.com/panhainan2020/SuperMimic-MuJoCo)公开。仓库可见性与静态网站托管独立管理。

使用已安装的 Playwright/Chromium 运行浏览器冒烟检查：

```sh
python website/check_site.py --browser /path/to/chromium
```

该检查验证禁用媒体时的页面、结果导航、数量、搜索、排序、移动端布局，以及启动时没有媒体请求。它不会安装浏览器或下载产物。可选的 `--experiment-dir` 参数通过临时的本机回环服务器使用已有本地视频验证播放；此过程只读取本地媒体，不会复制或发布它们。
