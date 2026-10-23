# 评估、姿态诊断与本地视频渲染

**简体中文** | [English](evaluation.en.md)

评估工具只操作执行机器上已有的文件。运行前，请将 `SUPERMIMIC_EXPERIMENT_ROOT` 设置为可写的持久化目录。新模型、经验回放、归档、已记录轨迹和视频保留在训练服务器持久盘，工具不会下载或传输这些产物。完整性检查在该机器上执行；监控仅可获取少量文本指标和元数据。已有授权的关机不等待下载。用户已明确授权将唯一的已测试策略 `checkpoints/g1_29dof/policy_098000.pt` 发布到 Git；此例外不授权获取或发布其他训练产物。

仓库中的两种机器人均采用 Unitree SDK 的 29 关节顺序：

- `g1_29dof` 为默认模型，与现有已评估权重匹配。
- `g1_29dof_rev_1_0` 为另一种原始修订模型。评估该机器人训练出的权重时，必须选择同一模型。物理约束一致性检查会拒绝其他模型的权重。

默认控制配置为 `upstream`，观测模式为 `legacy99`，后者表示第三方基线采用的 99 维观测。控制配置 `paper` 与观测模式 `paper93` 是历史实验选项，并非本项目报告结果所用的复现基线。仅改变安装路径无需修改权重；评估器会比较 XML 内容、模型选择、控制器参数和求解器设置。仓库附带策略中的 XML 哈希已在编译后模型严格等价检查通过后，更新为重建资产的哈希。携带旧 XML 哈希的历史权重仍会被严格拒绝；安装路径可迁移不代表可跳过资产版本检查。

## 记录评估轨迹

请先按照[环境配置指南](installation.md)安装项目及视频依赖。仓库包含公开 LAFAN 和 100STYLE 结果所用的固定 98,000 次迭代策略。该文件包含策略权重和推理配置，不包含恢复训练所需的世界模型、critic、优化器状态或经验回放，仅兼容默认的 `g1_29dof`。

在仓库根目录执行，并显式指定已有的本地动作数据：

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic_results
python -m supermimic.evaluate \
  --ckpt checkpoints/g1_29dof/policy_098000.pt \
  --motion_dir /path/to/local_motions \
  --run_dir "$SUPERMIMIC_EXPERIMENT_ROOT/eval" \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz" \
  --backend mjlab --device cuda:0 \
  --robot g1_29dof \
  --profile upstream --observation_mode legacy99 --network_size paper
```

小规模原生 MuJoCo 评估可使用 `--backend mujoco --device cpu`。每条源动作均从第一帧开始评估，不添加动作或观测噪声，也不使用域随机化。评估器以 50 Hz 在每个物理步之前记录状态。归一化回报和失败标签以 `evaluation.json` 为准。`rollout.npz` 保存供后续分析和渲染使用的状态与参考动作，不包含策略或经验回放缓冲区。

请使用新的评估目录。完整动作轨迹可能占用较大空间，尤其是批量处理时长不同的片段时：已完成片段会以冻结状态填充，直到最长片段结束。记录轨迹为可选功能，不影响回报计算。

## 计算姿态诊断指标

```bash
python tools/analyze_rollout.py \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz" \
  --evaluation "$SUPERMIMIC_EXPERIMENT_ROOT/eval/evaluation.json" \
  --output "$SUPERMIMIC_EXPERIMENT_ROOT/eval/tracking_metrics.json" \
  --robot g1_29dof
```

`--record` 与 `--output` 为必填参数。分析程序拒绝写入 `SUPERMIMIC_EXPERIMENT_ROOT` 之外的路径，也不会覆盖已有 JSON。可选的 `--evaluation` 会在核对片段集合后，关联权威回报和失败标签。`--chunk` 限制每批正向运动学计算的规模，不会对帧采样降频。若需显式指定与原评估相符的本地资产，可使用 `--xml-path`。

输出 JSON 保留已报告的分析约定：

- 将时刻 `t` 的记录状态与记录帧索引 `f[t]` 对应的参考状态比较，不做一帧偏移。
- 仅纳入物理步之前 `alive=True` 的样本。包含重置帧，排除冻结填充帧以及使片段完成或终止的最后一个步后状态。
- 关节 MAE/RMSE 使用 29 个有限位铰链关节角的直接差值，不做周期角度折返；同时报告弧度和角度。
- 根部位置误差为世界坐标系中的欧氏距离；根部姿态误差为 SO(3) 测地角。根部四元数使用 `wxyz` 顺序。
- 刚体 MPJPE 对 14 个跟踪刚体的连杆原点距离取平均。世界坐标版本保留漂移；对齐版本严格采用奖励函数中的 XY 平移与偏航角对齐，不进行 Procrustes 拟合，也不对齐根部高度。
- `frame_weighted` 汇总所有有效样本；`clip_equal_weighted` 先计算每条片段的指标再平均，使长短片段权重相同。其中 RMSE 字段是**各片段 RMSE 的算术平均值**，沿用原 LAFAN 分析约定，不是先平均各片段 MSE 再开平方。

这些姿态指标仅描述仍在运行的有效样本。它们不会从 NPZ 重构奖励，也不是新增的论文验收标准。应结合完成情况、片段时长、动作重定向约定和姿态误差共同判断；完成率高本身不能证明模仿准确。

## 并排渲染预测与参考动作

列出轨迹文件中的动作名称，或使用 `evaluation.json` 中的名称：

```bash
python -c 'import numpy as np, sys; z=np.load(sys.argv[1], allow_pickle=False); print("\n".join(z["names"].tolist()))' \
  "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz"

python tools/render_rollout.py \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz" \
  --clip EXACT_CLIP_NAME \
  --output "$SUPERMIMIC_EXPERIMENT_ROOT/eval/clip.mp4" \
  --robot g1_29dof --side-by-side
```

渲染器回放已记录的姿态，不会重新仿真轨迹。左侧为预测，右侧为参考。两侧相机分别跟随各自根部，因此累积漂移应通过世界坐标指标判断。默认以 50 fps 输出所有有效帧。`--max-seconds 10` 可生成明确标记的预览。`--width` 和 `--height` 指定每个画面的尺寸，均须能被 16 整除。默认离屏后端为 EGL；`--gl osmesa` 需要已有可用的 OSMesa 安装。

同目录的 `.video.json` 记录输入/输出 SHA-256 哈希、所选机器人/XML、帧数、完整参考长度、是否提前结束以及预览是否截断。视频不是独立的成功指标。渲染失败后的部分输出会保留用于诊断，但不会生成表示成功的元数据记录。

视频依赖包括 `imageio`、`imageio-ffmpeg`、`Pillow`，以及可用的 MuJoCo 离屏图形后端。MP4、NPZ 和其他训练权重不进入 Git；唯一明确授权发布的 98k 策略为例外。静态结果网站可以引用单独托管的视频；在此生成视频不会自动发布视频。
