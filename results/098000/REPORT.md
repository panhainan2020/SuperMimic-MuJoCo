# SuperMimic / MuJoCo evaluation — checkpoint 98,000

Evaluated 2026-10-23. This snapshot uses the trained default G1 model, upstream control settings and the third-party baseline's 99-dimensional observation. It does not report results for the alternative G1 asset. No policy fine-tuning or data-dependent controller changes were made for 100STYLE.

| Metric, equal weight per clip | LAFAN1 training motions | 100STYLE OOD |
| --- | ---: | ---: |
| Mean normalized return ↑ | 0.8713219762 | 0.8045164074 |
| Completed segments | 40 / 40 | 3569 / 3573 |
| Completion rate ↑ | 100% | 99.8880% |
| Joint mean absolute error ↓ | 4.3967° | 6.9898° |
| World root XYZ component MAE ↓ | 27.2866 cm | 21.6817 cm |
| XY/yaw-aligned 14-body MPJPE ↓ | 2.6122 cm | 5.2332 cm |
| Mean segment duration | 220.55 s | 18.7688 s |

## 数据范围与结论

训练仅使用 LAFAN1，包含第三方采用的 G1 重定向发布版全部 40 条序列、264,705 个 30 Hz 源帧，约 2.45 小时。完整片段重采样为 50 Hz；没有按短窗裁掉其余输入。原始 LAFAN1 是 77 条序列、496,672 帧、约 4.6 小时，因此这里不是原始全集。训练包含 subject5；40 条评估属于训练动作集内评估，不是原始 LAFAN1 的留出划分。

100STYLE 测试覆盖固定公开 G1 转换版的全部 3,573 个分段、100 种风格，约 18.63 小时的参考转换步。策略固定为 98k，没有微调。大多数未见来源的短动作可以完整运行，但关节与身体姿态误差高于训练集内结果。

四个提前终止片段为：

- `Flapping__Flapping_FR__000000_001000`
- `LimpLeft__LimpLeft_BR__003000_004000`
- `LimpLeft__LimpLeft_BR__004000_004966`
- `WhirlArms__WhirlArms_BR__003000_003751`

完成率只表示未触发训练时定义的高度/倾角终止条件，不代表精确动作复现。100STYLE 平均 18.77 秒，LAFAN1 平均 220.55 秒，两者重置频率和连续跟踪难度不同。源机器人资产和重定向处理也不同，本测试包含风格、来源和预处理变化，不能把误差差值全部归因于风格泛化。未做跨来源语义重复检测，不能仅以文件名不同证明运动内容完全无重合。

身体 MPJPE 消除了水平位移和朝向差异，不是全局路径精度。LAFAN1 世界坐标根位置平均 L2 误差仍为 64.31 cm，末个记录状态平均误差约 1.08 m。100STYLE 的较短片段不能用来证明全局漂移改善。新版视频在同一世界坐标、同一相机下显示实体策略与青色参考虚影，保留位置偏差；旧版分屏各自跟随根部的画面不能用于判断全局漂移。

## 整段已记录轨迹 MAE

新增根位置 XYZ MAE 对每帧世界坐标 x、y、z 的绝对误差取平均，不做平移或朝向对齐；它不同于先计算欧氏距离的根位置 L2。关节 MAE 对 29 个关节和全部有效记录帧平均。指标使用完整 50 Hz 记录，不依赖视频是否截取为预览或降到 25 fps。

统计沿用步前 `alive=True` 口径：包含初始状态，不包含未记录的最后步后状态。提前终止片段仅计算已记录前缀，缺失帧不补零。LAFAN 记录覆盖率为 100%，100STYLE 为 99.9615%；完成率另计为 3569/3573。

`trajectory_mae.public.json` 提供全部、完整完成、失败三组的逐片等权和逐帧加权汇总，以及公式与来源哈希；`trajectory_mae.per_clip.csv` 提供全部 3,613 条轨迹。历史关节 MAE 的重算差异不超过 5.56e-17 rad，未重新运行策略或修改冻结评估。

## Evaluation and interpretation

The policy trained only on the complete **40-clip G1-retargeted LAFAN1 release**, not all 77 original LAFAN1 sequences. These 40 evaluations are in-training-distribution results. The OOD evaluation covers all **3,573 segments / 100 styles** of the pinned public G1 conversion, not a verified exhaustive mapping to every raw original 100STYLE recording.

Most unseen-source short segments complete, with lower pose-tracking accuracy than LAFAN1. Completion measures absence of termination, not precise tracking. This is a descriptive comparison: the same frozen policy and metrics, but different horizons, retargeting and inputs. LAFAN1's third-party target return of 0.82 is not an OOD acceptance threshold.

Each clip starts at its first reference frame; domain randomization, observation noise and action noise are disabled. Pose errors use recorded pre-step `alive=True` states, including reset states, excluding frozen padding and the final post-step state. Errors are survival-conditioned and must be read with the four failures.

Global mean returns use full-precision batch aggregates. The baseline stores per-clip returns to four decimals; per-style returns inherit that rounding. RMSE aggregates in `summary.json`'s comparison use square-weight-average-square-root pooling; this differs from the raw baseline's arithmetic mean of clip RMSE. This report focuses on mean absolute errors. The unchanged float-based resampler omits one last reference frame in 58 OOD segments (1.16 s total); no source motion or joint limits were adjusted.

## Media selection

- All 20 indexed videos now use one camera and world frame: solid policy plus translucent cyan reference, without independent root recentering.
- LAFAN overview: the first 10 seconds from each of seven categories, concatenated into 70 seconds.
- Seven LAFAN previews: the first 12 seconds of the original lowest-return motion selected within each category. Their MAE still uses the entire recorded trajectory.
- Four retained OOD examples: 10th, 50th and 90th successful-return percentiles, plus the longest-surviving failure, Flapping (17.76 s recorded / 19.98 s reference).
- Eight additional styles: exclude the original four styles, alphabetically sort the 96 remaining styles with completed segments of at least 10 seconds, and take ranks 0, 14, 27, 41, 54, 68, 81 and 95. Within each style, sort eligible clips by return then name and select the lower median. The resulting styles are Aeroplane, Cat, FlickLegs, LeftHop, OnToesCrouched, ShieldedRight, SwingArmsRound and Zombie.
- All 12 OOD videos show their complete valid recording; failed examples never imply completion of the full reference. Delivery encoding uses 960×540, 25 fps, H.264; a 19.98-second record may have a 20.00-second container duration after frame-rate conversion.

`media_manifest.json` contains the new ghost delivery-file hashes and presentation metadata, without raw recording paths. `media_delivery.json` is historical metadata for the five previously hosted split-screen files. This source update does not upload the ghost videos or deploy the live site; media is disabled in the checkout by default. Videos and trajectories stay outside Git. The separately authorized 98k inference policy remains bundled under `checkpoints/`.

## Provenance

- Baseline: [zita-ch/supermimic_vibed](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9).
- LAFAN source: [Ubisoft official dataset](https://github.com/ubisoft/ubisoft-laforge-animation-dataset#data).
- G1 training release: [lvhaidong/LAFAN1_Retargeting_Dataset](https://huggingface.co/datasets/lvhaidong/LAFAN1_Retargeting_Dataset/tree/ce1572906efe6157840e8474d5a0d7aa87481e74/g1).
- OOD conversion: [elijahgalahad/any4hdmi-g1-100style](https://huggingface.co/datasets/elijahgalahad/any4hdmi-g1-100style/tree/bb3cd09a89dd804a1d8c383690161f594416ecb2).

See `provenance.json` for original metadata hashes, `summary.json` for policy identity and source code revision, and the CSVs for all clips. The export removes machine paths and operational credentials. Raw training artifacts remain on server persistent storage; this report and its exporter do not authorize or perform remote artifact downloads.
