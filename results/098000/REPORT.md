# SuperMimic / MuJoCo evaluation — checkpoint 98,000

Evaluated 2026-10-23. This snapshot uses the trained default G1 model, upstream control settings and the third-party baseline's 99-dimensional observation. It does not report results for the alternative G1 asset. No policy fine-tuning or data-dependent controller changes were made for 100STYLE.

| Metric, equal weight per clip | LAFAN1 training motions | 100STYLE OOD |
| --- | ---: | ---: |
| Mean normalized return ↑ | 0.8713219762 | 0.8045164074 |
| Completed segments | 40 / 40 | 3569 / 3573 |
| Completion rate ↑ | 100% | 99.8880% |
| Joint mean absolute error ↓ | 4.3967° | 6.9898° |
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

身体 MPJPE 消除了水平位移和朝向差异，不是全局路径精度。LAFAN1 世界坐标根位置平均误差仍为 64.31 cm，末个记录状态平均误差约 1.08 m。100STYLE 的较短片段不能用来证明全局漂移改善。左右视频镜头分别跟随机器人，也不能凭画面对齐判断全局误差。

## Evaluation and interpretation

The policy trained only on the complete **40-clip G1-retargeted LAFAN1 release**, not all 77 original LAFAN1 sequences. These 40 evaluations are in-training-distribution results. The OOD evaluation covers all **3,573 segments / 100 styles** of the pinned public G1 conversion, not a verified exhaustive mapping to every raw original 100STYLE recording.

Most unseen-source short segments complete, with lower pose-tracking accuracy than LAFAN1. Completion measures absence of termination, not precise tracking. This is a descriptive comparison: the same frozen policy and metrics, but different horizons, retargeting and inputs. LAFAN1's third-party target return of 0.82 is not an OOD acceptance threshold.

Each clip starts at its first reference frame; domain randomization, observation noise and action noise are disabled. Pose errors use recorded pre-step `alive=True` states, including reset states, excluding frozen padding and the final post-step state. Errors are survival-conditioned and must be read with the four failures.

Global mean returns use full-precision batch aggregates. The baseline stores per-clip returns to four decimals; per-style returns inherit that rounding. RMSE aggregates in `summary.json`'s comparison use square-weight-average-square-root pooling; this differs from the raw baseline's arithmetic mean of clip RMSE. This report focuses on mean absolute errors. The unchanged float-based resampler omits one last reference frame in 58 OOD segments (1.16 s total); no source motion or joint limits were adjusted.

## Media selection

- LAFAN overview: seven 10-second middle excerpts; a 70-second montage, not full rollouts.
- Seven complete LAFAN examples: lowest-return motion within each displayed category.
- OOD complete examples: 10th, 50th and 90th return percentiles among successful segments of at least 10 s, with distinct styles where available.
- OOD failure: the longest-surviving failed segment, Flapping; recorded 17.76 s of its 19.98 s reference.

Public playback may use separately hosted compact encodings. Original recording SHA256 values are in `media_manifest.json`; transcoded delivery files have distinct hashes and must not be represented as byte-identical originals. Videos, trajectories and policies are not stored in this repository.

## Provenance

- Baseline: [zita-ch/supermimic_vibed](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9).
- LAFAN source: [Ubisoft official dataset](https://github.com/ubisoft/ubisoft-laforge-animation-dataset#data).
- G1 training release: [lvhaidong/LAFAN1_Retargeting_Dataset](https://huggingface.co/datasets/lvhaidong/LAFAN1_Retargeting_Dataset/tree/ce1572906efe6157840e8474d5a0d7aa87481e74/g1).
- OOD conversion: [elijahgalahad/any4hdmi-g1-100style](https://huggingface.co/datasets/elijahgalahad/any4hdmi-g1-100style/tree/bb3cd09a89dd804a1d8c383690161f594416ecb2).

See `provenance.json` for original metadata hashes, `summary.json` for policy identity and source code revision, and the CSVs for all clips. The export removes machine paths and operational credentials. Raw training artifacts remain on server persistent storage; this report and its exporter do not authorize or perform remote artifact downloads.
