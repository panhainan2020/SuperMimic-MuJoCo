# 评估网页

**简体中文** | [English](README.en.md) · **[在线查看](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**

网页展示固定 98k 策略的 LAFAN 与 100STYLE 评估结果：

- 同一世界坐标和相机下，实体策略机器人与青色参考虚影叠加，保留位置偏差。
- 7 条 LAFAN 预览、1 条概览和 12 条 100STYLE 视频，分别标注视频长度、参考时长与失败状态。
- 整段已记录轨迹的关节角 MAE、根 XYZ 分量 MAE，以及原有回报和姿态指标；支持逐片等权、逐帧加权汇总和 JSON/CSV 下载。

MAE 使用全部有效的 50 Hz 步前记录，独立于视频截取范围。失败片段仅计算终止前记录，并报告覆盖率。计算口径与渲染命令见[评估指南](../docs/evaluation.md)。

## 构建与预览

无需外部 JavaScript 依赖。可直接打开 `index.html`，或将构建目录交给静态网站服务：

```sh
# 使用仓库内的小体积指标和媒体清单。
python website/build.py

# 生成独立部署目录，不复制视频。
python website/build.py --output-dir /tmp/supermimic-site
```

使用已有实验的指标和媒体清单生成预览：

```sh
python website/build.py \
  --mae-dir "$SUPERMIMIC_EXPERIMENT_ROOT/trajectory_mae" \
  --media-manifest "$SUPERMIMIC_EXPERIMENT_ROOT/media/media_manifest.json" \
  --output-dir "$SUPERMIMIC_EXPERIMENT_ROOT/site_preview"
```

维护者可用 `--experiment-dir "$SUPERMIMIC_EXPERIMENT_ROOT"` 刷新基础结果快照。导出器仅选择公开 JSON/CSV 字段并记录元数据哈希，拒绝私有机器路径；不读取或传输权重、数据集、轨迹和视频。原始实验产物保留在服务器持久盘。

## 视频托管

视频文件保存在独立媒体存储中，媒体键、展示范围及文件哈希见 [`media_manifest.json`](../results/098000/media_manifest.json)。在 `media-config.js` 配置媒体地址：

```js
window.MEDIA_CONFIG = {
  enabled: true,
  baseUrl: "https://supermimic-mujoco-results.zippyaspen7.chatgpt.site/media",
  overrides: {},
  repositoryUrl: "https://github.com/panhainan2020/SuperMimic-MuJoCo"
};
```

`baseUrl` 与清单中的媒体键拼接；`overrides` 可为个别键指定其他地址。离线预览可用相对 `media` 路径，并自行放入已有视频或软链接。网页仅在点击播放后请求视频，不预取视频或封面。

媒体服务需支持 `video/mp4` 和字节范围请求，推荐 H.264/yuv420p、启用 `faststart` 的 MP4。远端地址须为 HTTPS；本地开发允许 localhost HTTP。令牌和私有凭据不得写入配置。Sites / R2 部署方法见[托管说明](hosting/README.md)。构建源码、Git 推送与在线部署是独立步骤，构建器不会自动发布。

## 浏览器检查

使用已安装的 Playwright 与 Chromium：

```sh
python website/check_site.py --browser /path/to/chromium
```

检查覆盖指标导航、视频数量、搜索排序、移动布局和无预取行为。可选 `--experiment-dir` 使用已有本地视频验证播放；不会下载浏览器或远端产物。
