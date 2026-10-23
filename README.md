# SuperMimic on MuJoCo / MJLab

**简体中文** | [English](README.en.md)

本项目使用原生 MuJoCo 和 MJLab / MuJoCo-Warp，独立复现 **SuperMimic** 的
动作跟踪方法，代码基于第三方实现
[zita-ch/supermimic_vibed@a1508d4](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9)。
本项目并非论文作者的官方代码，也未复现论文完整的 BONES-SEED 训练语料、
多 GPU 扩展实验或全部目标接口。

**[在线评估结果](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**：
固定 98k 策略在 40 条 LAFAN 训练动作和 3,573 条未见过的 100STYLE 动作片段上的结果。
结果网页与代码仓库均已公开；视频由独立对象存储提供，不上传到 GitHub。

**独立 MuJoCo/MJLab 工程：无需 Isaac Lab、Isaac Sim、Newton 或 USD。**
两套 G1 的 XML、网格及许可证随包提供；默认保持当前已经训练并评估的机器人、
第三方控制器和 99 维观测。世界模型、策略和价值评估网络（critic）由 PyTorch 训练；
策略梯度通过学习的世界模型传播。

<a id="repository-layout"></a>

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `supermimic/` | 算法、动作库、机器人兼容性约定、CPU/CUDA 后端 |
| `supermimic/assets/robots/` | 两套 G1 模型、共享网格、来源记录和许可证 |
| `tools/` | 训练与恢复的冒烟检查、轨迹分析、视频渲染 |
| `tests/` | 兼容性约定、运动学、动作、经验回放与后端检查 |
| `checkpoints/g1_29dof/` | 已测试的 98k 推理策略，以及完整性与来源清单 |
| `results/098000/` | 可分享的评估快照：报告、CSV 指标、证据哈希 |
| `website/` | 结果网页、可复现导出流程、外部媒体配置 |
| `requirements.lock.txt` | 已验证的 Linux / Python 3.10 依赖版本 |

经明确授权发布的 98k 推理策略已纳入 Git。其他权重、完整训练检查点、
原始动作数据、经验回放、视频和 Python 环境均不纳入仓库。
结果视频由独立存储提供，详见[网页说明](website/README.md)。

<a id="install"></a>

## 环境安装

完整安装步骤和环境检查命令见 **[环境安装指南](docs/installation.md)**。

已验证环境为 Linux x86_64、Python 3.10、PyTorch 2.7.1、MJLab 1.4.0、
MuJoCo / MuJoCo-Warp 3.8.1、Warp 1.14.0。MJLab 并行后端需要 CUDA。
CPU 后端使用相同的 MJLab 场景编译器，并通过原生 `mujoco.mj_step` 仿真；
无需安装 Isaac 系列软件。

```bash
git clone https://github.com/panhainan2020/SuperMimic-MuJoCo.git
cd SuperMimic-MuJoCo
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt -e '.[video]'
python -m supermimic.train --help
```

仓库已公开，克隆无需身份验证。如果不需要完整锁定环境，可用
`python -m pip install -e '.[video]'` 安装兼容依赖。包配置固定了仿真相关版本，
防止依赖变化意外改变物理行为。项目中的脚本不会自动下载机器人资产、动作数据、
策略或训练归档。

<a id="choose-a-robot"></a>

## 选择机器人

| `--robot` | 说明 | 已有评估策略 |
| --- | --- | --- |
| `g1_29dof` **（默认）** | 当前已训练的 G1，使用 5010 腕部和 MJLab 碰撞基本体 | 下方 98k LAFAN / 100STYLE 结果 |
| `g1_29dof_rev_1_0` | 第三方复现采用的 G1 revision 1.0，由其固定版本的 URDF 转换 | 已验证训练接口，尚无收敛结果 |

两者均有 29 个驱动关节，但腕部几何、惯性参数和碰撞表示不同，详见
[机器人资产说明](ASSETS.md)。训练和评估时都必须选择对应机器人；
一个机器人的检查点会被另一套模型拒绝加载。自定义资产可通过 `--xml_path` 显式指定。

默认 `--profile upstream --observation_mode legacy99` 保留第三方控制器和观测编码。
`legacy99` 是本项目对第三方 99 维观测的命名。`paper` 和 `paper93` 选项保留为
实验性消融配置，不代表已经准确还原论文未公开的实现细节。

<a id="motion-data-and-persistent-outputs"></a>

## 动作数据与持久化输出

通过 `--motion_dir` 指定执行机器上已经准备好的数据：

- LAFAN 重定向 CSV 所在目录，或单个 CSV 文件：依次为根节点 xyz、
  **xyzw** 顺序的四元数，以及按 Unitree SDK 顺序排列的 29 个关节角；原始频率为 30 Hz。
- 兼容的 joblib `.pkl` 文件：以动作名称为键，每条动作包含 `root_trans_offset`、
  `root_rot`（xyzw）、`dof` 和 `fps`。

加载器重采样至 50 Hz，重新计算速度与前向运动学，并按动作名称排序。
它不额外修正高度或增加朝向增强。原始 100STYLE 文件需要显式转换格式；
分布外评估快照记录了当次评估所用转换版本。数据集许可证与代码许可证分别适用。

训练前，将输出根目录设置在**服务器持久盘**：

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic
```

未设置时，默认输出到 `./outputs`。所有运行目录都必须位于配置的根目录内。
机器专用的绝对路径应通过 shell 环境配置，不写入提交到仓库的配置文件。

**存储规则：**训练产物保留在训练服务器的持久盘。禁止自动下载、预取、镜像、
断点续传或流式传输权重、经验回放、归档及其他大体积产物；只获取少量文本状态、
指标和必要元数据。完整性核验与恢复检查在服务器端执行。训练、持久盘保存核验和
已授权测试完成后，按既有授权关闭计算实例并保留持久盘，不等待用户下载。

<a id="training"></a>

## 训练

当前 4090 实验使用以下第三方配置。该命令启动一次新训练，请选择新的输出目录，
并将数据路径替换为服务器上的实际路径。资源占用随并行环境数量和经验回放容量变化。

```bash
python -m supermimic.train \
  --backend mjlab --device cuda:0 --robot g1_29dof \
  --profile upstream --observation_mode legacy99 \
  --motion_dir /path/to/lafan_csv_or_joblib \
  --num_envs 4096 --iterations 320000 --buffer_steps 1000 \
  --network_size paper --amp bf16 --compile \
  --last_every 100 --ckpt_every 2000 --seed 0 \
  --log_dir "$SUPERMIMIC_EXPERIMENT_ROOT/runs/lafan_g1"
```

训练第二套模型时，改为 `--robot g1_29dof_rev_1_0`，并使用**新的**运行目录，
例如 `runs/lafan_g1_rev1`。默认参数为 H=32、世界模型窗口=8、目标与历史长度各为
10 帧、UTD=0.4、世界模型批量大小=2048、策略批量大小=4096。

使用相同配置并添加 `--resume /path/to/run/last.pt`，可恢复网络与优化器，
随后重新填充经验回放。这不保证逐位一致地延续原有经验回放状态。`last.pt` 支持恢复；
按迭代编号保存的快照可能不包含优化器状态。收到 SIGINT/SIGTERM 后会在下一个
迭代边界保存。按授权关机前，请等待进程退出并核验持久盘检查点；
SIGKILL 或断电无法保证保存最后状态。

<a id="evaluation-and-videos"></a>

## 评估与视频

**仓库已包含网页中测试过的 98k 策略权重：**
[`checkpoints/g1_29dof/policy_098000.pt`](checkpoints/g1_29dof/policy_098000.pt)
（约 34.8 MiB）。它用于默认 `g1_29dof`，采用第三方 `upstream` 控制和
`legacy99` 观测。发布时清理了服务器路径，并在编译模型等价验证后更新了
XML 哈希元数据；全部策略张量与 LAFAN / 100STYLE 评估使用的模型
逐位一致。哈希与来源见同目录
[`manifest.json`](checkpoints/g1_29dof/manifest.json)，适用范围见[权重说明](checkpoints/g1_29dof/README.md)。

这是**推理策略**，不含世界模型、价值评估网络、优化器或经验回放，不能作为完整
训练恢复点传给 `--resume`。另一套 G1 尚无已训练权重。

安装环境后，在仓库根目录先执行无需动作数据的加载与推理检查：

```bash
source .venv/bin/activate
python tools/verify_checkpoint.py
```

然后使用已经准备好的 LAFAN 数据进行正式动作跟踪评估。将以下两个路径
替换为本机/服务器的实际路径；数据集没有随仓库提供，也不会自动下载。
使用完整的第三方 40 条 G1 LAFAN 发布版才能对应下面的训练集内结果。

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic_results
export SUPERMIMIC_MOTION_PATH=/path/to/lafan_csv_directory_or_joblib.pkl

python -m supermimic.evaluate \
  --backend mjlab --device cuda:0 \
  --robot g1_29dof --profile upstream \
  --observation_mode legacy99 --network_size paper \
  --motion_dir "$SUPERMIMIC_MOTION_PATH" \
  --run_dir "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/policy_098000" \
  --ckpt checkpoints/g1_29dof/policy_098000.pt
```

结果写入 `evaluation/policy_098000/evaluation.json`。这条命令直接测试随仓库
提供的权重；CPU 小规模检查可改用 `--backend mujoco --device cpu`，全库
评估建议使用 CUDA。每次评估使用新的输出目录。

需要后续姿态分析或视频时，增加轨迹记录参数：

```bash
python -m supermimic.evaluate \
  --backend mjlab --device cuda:0 --robot g1_29dof \
  --motion_dir /path/to/lafan_csv_or_joblib \
  --run_dir "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/g1" \
  --ckpt checkpoints/g1_29dof/policy_098000.pt \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/g1/rollout.npz"
```

评估从每条动作的第一个参考帧开始，关闭噪声和域随机化，并冻结已结束的环境。
归一化回报以**完整参考动作长度**计算；训练日志中按存活步数计算的回报并非同一指标。
随仓库提供的策略可在不同安装路径下使用：加载时检查资产标识与控制参数，
不依赖机器绝对路径。携带不同 XML 哈希的旧检查点会被拒绝；当前策略元数据只在
重建模型通过严格等价验证后才更新。分析与视频命令详见[评估指南](docs/evaluation.md)。

已发布快照采用**固定的 98,000 迭代策略**，不代表完整的 320k 训练已经完成。
训练使用第三方 G1 LAFAN 发布版全部 40 条动作（约 2.45 小时），
并非原始 LAFAN1 的全部 77 条序列（约 4.6 小时）。

| 指标 | LAFAN 训练动作 | 100STYLE 分布外动作 |
| --- | ---: | ---: |
| 平均归一化回报 | 0.8713 | 0.8045 |
| 完成动作数 | 40 / 40 | 3569 / 3573 |
| 关节角平均绝对误差（MAE） | 4.40° | 6.99° |
| XY 与偏航对齐后的身体平均关节位置误差（MPJPE） | 2.61 cm | 5.23 cm |
| 平均动作时长 | 220.55 s | 18.77 s |

100STYLE 测试使用固定的 G1 转换版本，覆盖 100 种风格，未作微调。
“完成”表示未触发原有终止条件，不代表精确复现动作。动作更短、重定向流程不同，
因此两组指标不能直接等同比较。网页提供代表性与失败案例；完整指标包含全部
评估动作。详见[结果说明](results/README.md)和[完整报告](results/098000/REPORT.md)。

<a id="validation"></a>

## 验证

```bash
OMP_NUM_THREADS=2 python -m unittest discover -s tests -v
python tools/smoke.py --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cpu"
python tools/smoke.py --backend mjlab --device cuda:0 \
  --robot g1_29dof_rev_1_0 \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_rev1_gpu"
```

冒烟检查使用合成站立参考动作与小型网络，验证训练、恢复和评估流程，
不用于衡量动作跟踪是否收敛。

<a id="acknowledgments-and-citation"></a>

## 致谢与引用

SuperMimic 方法由 **Qiayuan Liao、Yiyang Shao、Junfeng Long、Kevin Zakka、
Roberto Horowitz、Pieter Abbeel 和 Koushil Sreenath** 在论文
[SuperMimic: Scaling Humanoid Whole-Body Control with One Differentiable World
Model](https://arxiv.org/abs/2610.28480) 中提出。

本项目基于 **Chong Zhang 的第三方实现**
[zita-ch/supermimic_vibed](https://github.com/zita-ch/supermimic_vibed)，
基线版本固定为 `a1508d42c9d1699a52e8233ab16d08c488441ab9`。
感谢论文作者提出该方法，感谢 Chong Zhang 开源复现代码。本项目保留上游的世界模型、
策略与价值评估网络结构以及核心学习循环，主要贡献为独立的 MuJoCo/MJLab 接入、
两套 G1 模型配置、实现修复，以及可复现的训练、评估和结果展示流程。
本项目为非官方移植，不表示获得论文作者或上游实现作者的官方背书。

使用本项目时，请引用**原论文**，注明**上游实现及其固定提交版本**，
并记录实验采用的本项目版本。可直接使用的 BibTeX 条目见
[references.bib](references.bib)；[CITATION.cff](CITATION.cff) 提供本项目的
结构化引用信息，并引用上述两项前置工作。

<a id="attribution-and-scope"></a>

## 来源、版权与复现范围

[UPSTREAM.md](UPSTREAM.md) 记录实现基线和改动。
[LICENSE](LICENSE) 保留原始 `Copyright (c) 2026 ETH Zurich, Chong Zhang`
声明及 MIT 条款。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 分别记录
MJLab、Unitree 机器人资产、依赖项、外部数据集和媒体的许可证。
代码采用的 MIT 许可证不会改变这些其他材料的许可条件。

本移植保留第三方的可微模型、解析奖励、软终止、重置采样和单 GPU 训练结构，
修复动作边界、经验回放边界情况与重复分箱奖励更新，并替换仿真器接入实现。
仅凭仿真行为匹配或代码测试通过，不能证明已经达到论文的性能或训练时长。
