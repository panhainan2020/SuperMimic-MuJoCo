# 评估结果

**简体中文** | [English](README.en.md) · **[在线查看](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**

本目录保存固定 **98,000 次迭代**策略的指标、评估条件和来源记录。原始轨迹、完整训练检查点、动作数据及视频保存在 Git 之外。

| 文件 | 内容 |
| --- | --- |
| [REPORT.md](098000/REPORT.md) | 评估结论与局限 |
| [summary.json](098000/summary.json) | 完整精度汇总指标及评估条件 |
| [training_coverage.json](098000/training_coverage.json) | 40 条 G1 LAFAN 发布动作与原始 77 条序列的覆盖关系 |
| [lafan_per_clip.csv](098000/lafan_per_clip.csv) | 40 条 LAFAN 动作的逐条结果 |
| [100style_per_clip.csv](098000/100style_per_clip.csv) | 3,573 条 100STYLE 片段的逐条结果 |
| [100style_per_style.csv](098000/100style_per_style.csv) | 100 种风格的汇总结果 |
| [trajectory_mae.public.json](098000/trajectory_mae.public.json) | 整段已记录轨迹 MAE、覆盖率、汇总口径及来源哈希 |
| [trajectory_mae.per_clip.csv](098000/trajectory_mae.per_clip.csv) | 全部 3,613 条轨迹的 MAE |
| [media_manifest.json](098000/media_manifest.json) | 视频选择、展示范围、大小及哈希 |
| [provenance.json](098000/provenance.json) | 原始指标元数据的 SHA-256 |

在线网页展示实体策略与青色参考虚影叠加视频，共 20 条：7 条 LAFAN 预览、1 条概览和 12 条 100STYLE 记录。960×540、25 fps 的演示文件合计约 38 MiB，独立托管；构建及媒体配置见[网页说明](../website/README.md)。

MAE 使用全部有效的 50 Hz 步前记录，失败片段仅计算终止前部分。逐片等权与逐帧加权结果均提供，关节角 MAE、根 XYZ 分量 MAE 和根位置 L2 分开定义，详见[评估指南](../docs/evaluation.md)。

[环境验证记录](release_validation.json)及[机器人等价性记录](robot_asset_equivalence.json)单独保存；上表保留原评估运行指标。

训练产物保留在服务器持久盘，完整性和恢复检查在服务器完成；仅获取少量文本指标与元数据，不自动回传、预取或镜像大文件。已授权关机不等待下载。网页导出工具不执行网络操作。
