# 评估结果快照

**简体中文** | [English](README.en.md)

本目录保存固定于 **98,000 次迭代**的策略所对应、经过筛选且可移植的文本证据。这些是历史结果快照，不代表最新训练检查点的表现。原始轨迹、训练检查点、动作数据集和视频不纳入 Git。

| 文件 | 用途 |
| --- | --- |
| [098000/REPORT.md](098000/REPORT.md) | 中英文评估结论与局限 |
| [098000/summary.json](098000/summary.json) | 完整精度的汇总指标及评估条件 |
| [098000/training_coverage.json](098000/training_coverage.json) | 40 条动作的重定向发布集与原始 LAFAN1 的 77 条序列之间的覆盖关系 |
| [098000/lafan_per_clip.csv](098000/lafan_per_clip.csv) | 40 条训练动作的逐条评估结果 |
| [098000/100style_per_clip.csv](098000/100style_per_clip.csv) | 全部 3,573 个转换后 100STYLE 片段的评估结果 |
| [098000/100style_per_style.csv](098000/100style_per_style.csv) | 100 种风格的汇总结果 |
| [098000/media_manifest.json](098000/media_manifest.json) | 媒体标识、选取规则及原始哈希，不包含媒体文件 |
| [098000/provenance.json](098000/provenance.json) | 筛选公开字段之前的源元数据 SHA-256 |

[静态结果网页](../website/index.html)读取这些已提交的快照。重新构建网页及配置独立媒体托管的说明见 [website/README.md](../website/README.md)。

[公开评估页面](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)展示同一组指标。五段完整演示视频由外部对象存储提供；[media_delivery.json](098000/media_delivery.json)记录其发布编码、大小和哈希。用于展示的 960×360、25 fps 压缩副本合计 11.93 MiB。原始评估录像保持不变，并保存在 Git 之外。

训练产物保存在服务器持久盘。评估、备份和发布请求均不隐含下载远端权重、数据集、回放或完整归档的授权。本快照来自此前已获授权的本地文本证据；导出工具不执行网络操作。

[发布验证记录](release_validation.json)记录了后续针对随仓库提供的策略及可复现生成的机器人所做的 38 项 CPU/CUDA 检查和 40 条 LAFAN 动作评估。[机器人等价性记录](robot_asset_equivalence.json)对比了编译后的模型；上面的固定 98k 结果表保留原始运行指标。本次打包调整没有重新运行 100STYLE 评估。
