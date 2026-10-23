# SuperMimic on MuJoCo / MJLab

**简体中文** | [English](README.en.md)

基于 [zita-ch/supermimic_vibed@a1508d4](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9) 的 **SuperMimic 非官方 MuJoCo/MJLab 移植**，支持两套 G1 模型、GPU 并行训练、动作跟踪评估和视频渲染，无需 Isaac Lab 或 Isaac Sim。

**[在线评估结果](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**：实体策略机器人与青色参考虚影同场景对比，包含 LAFAN 示例、12 条 100STYLE 视频、整段已记录轨迹 MAE 和完整指标表。视频独立托管，不占用 Git 仓库。

<a id="install"></a>

## 环境安装

已验证：Linux x86_64、Python 3.10、PyTorch 2.7.1、MJLab 1.4.0、MuJoCo / MuJoCo-Warp 3.8.1、Warp 1.14.0。MJLab 并行训练需要 CUDA；小规模评估可使用原生 MuJoCo CPU 后端。

```bash
git clone https://github.com/panhainan2020/SuperMimic-MuJoCo.git
cd SuperMimic-MuJoCo
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt -e '.[video]'
```

环境检查和依赖说明见[安装指南](docs/installation.md)。两套机器人资产随包提供；动作数据需自行准备，脚本不会自动下载。

<a id="evaluation-and-videos"></a>

## 评估已有策略

仓库包含已测试的 [`policy_098000.pt`](checkpoints/g1_29dof/policy_098000.pt)（34.8 MiB），适用于默认 `g1_29dof`、`upstream` 控制配置和 `legacy99` 观测。这是推理策略，不能用于 `--resume` 恢复完整训练；哈希和兼容性见[权重说明](checkpoints/g1_29dof/README.md)。

在仓库根目录检查权重并评估已有动作数据：

```bash
python tools/verify_checkpoint.py

export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic
export SUPERMIMIC_MOTION_PATH=/path/to/lafan_csv_directory_or_joblib.pkl

python -m supermimic.evaluate \
  --backend mjlab --device cuda:0 \
  --robot g1_29dof --profile upstream \
  --observation_mode legacy99 --network_size paper \
  --motion_dir "$SUPERMIMIC_MOTION_PATH" \
  --run_dir "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/policy_098000" \
  --ckpt checkpoints/g1_29dof/policy_098000.pt
```

每次使用新的输出目录，结果写入其中的 `evaluation.json`。CPU 评估改为 `--backend mujoco --device cpu`；增加 `--record "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/policy_098000/rollout.npz"` 可记录轨迹。MAE 计算和虚影视频命令见[评估指南](docs/evaluation.md)。

## 评估结果

以下为固定 **98,000 次迭代**策略的结果。训练集为第三方 G1 LAFAN 发布版全部 40 条动作（约 2.45 小时），并非原始 LAFAN1 的全部 77 条序列。100STYLE 测试覆盖 100 种风格、3,573 条未见片段，未作微调。

| 指标 | LAFAN 训练动作 | 100STYLE 分布外动作 |
| --- | ---: | ---: |
| 平均归一化回报 | 0.8713 | 0.8045 |
| 完成动作数 | 40 / 40 | 3569 / 3573 |
| 整段关节角 MAE | 4.40° | 6.99° |
| 整段根位置 XYZ 分量 MAE | 27.29 cm | 21.68 cm |
| XY 与偏航对齐后的身体 MPJPE | 2.61 cm | 5.23 cm |
| 平均动作时长 | 220.55 s | 18.77 s |

误差按动作等权汇总。MAE 使用全部有效的 50 Hz 步前记录，包含初始帧，排除未记录的终止步后状态；失败动作仅计算终止前部分，并报告覆盖率。根 XYZ MAE 不做位置对齐，与根位置 L2 距离不同。网页另提供逐帧加权结果。

“完成”表示未触发终止条件；动作时长及重定向流程不同，两个数据集的指标不能直接等同比较。本结果不代表完整 320k 训练或论文的全部实验。详见[完整报告](results/098000/REPORT.md)和[指标文件](results/README.md)。

<a id="choose-a-robot"></a>

## 选择机器人

| `--robot` | 模型 | 权重状态 |
| --- | --- | --- |
| `g1_29dof` **（默认）** | 5010 腕部、MJLab 碰撞基本体 | 提供上述 98k 策略 |
| `g1_29dof_rev_1_0` | 第三方实现使用的 G1 revision 1.0，由固定 URDF 转换 | 训练接口已验证，暂无已训练权重 |

两者均有 29 个驱动关节，腕部几何、惯性和碰撞表示不同，检查点不能混用，详见[机器人资产说明](ASSETS.md)。默认 `upstream` / `legacy99` 保留第三方控制器及 99 维观测；`paper` / `paper93` 仅为实验选项。

<a id="motion-data-and-persistent-outputs"></a>

## 数据与输出

`--motion_dir` 接受已有的重定向 CSV 目录、单个 CSV 或兼容的 joblib `.pkl`。CSV 列为根 xyz、xyzw 四元数和 Unitree SDK 顺序的 29 个关节角，源频率为 30 Hz；joblib 每条动作需包含 `root_trans_offset`、`root_rot`（xyzw）、`dof`、`fps`。加载器重采样至 50 Hz。100STYLE 原始数据需先转换格式。

将 `SUPERMIMIC_EXPERIMENT_ROOT` 设为服务器持久盘目录，运行输出必须在其内；未设置时默认为 `./outputs`。

**训练产物保留在服务器持久盘。** 禁止自动下载、预取、镜像、断点续传或流式传输权重、回放、归档及其他大文件；仅获取少量文本状态、指标和必要元数据。完整性及恢复检查在服务器完成。训练、持久盘核验和授权测试完成后，按已有授权关机并保留持久盘，不等待下载。

<a id="training"></a>

## 训练

以下使用第三方基线配置。替换数据路径，并选择新的运行目录：

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic

python -m supermimic.train \
  --backend mjlab --device cuda:0 --robot g1_29dof \
  --profile upstream --observation_mode legacy99 \
  --motion_dir /path/to/lafan_csv_or_joblib \
  --num_envs 4096 --iterations 320000 --buffer_steps 1000 \
  --network_size paper --amp bf16 --compile \
  --last_every 100 --ckpt_every 2000 --seed 0 \
  --log_dir "$SUPERMIMIC_EXPERIMENT_ROOT/runs/lafan_g1"
```

另一套模型改为 `--robot g1_29dof_rev_1_0`，并使用不同运行目录。显存需求随并行环境数和回放容量变化。

添加 `--resume /path/to/run/last.pt` 可恢复网络和优化器，随后重新填充回放。SIGINT/SIGTERM 会在迭代边界保存；关机前等待退出并核验持久盘检查点。完整参数见 `python -m supermimic.train --help`。

<a id="validation"></a>

## 验证

```bash
OMP_NUM_THREADS=2 python -m unittest discover -s tests -v
python tools/smoke.py --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cpu"
```

冒烟检查验证小规模训练、恢复和评估流程，不用于判断收敛。

<a id="repository-layout"></a>

## 代码与文档

[算法与后端](supermimic/) · [工具](tools/) · [测试](tests/) · [评估结果](results/098000/) · [网页构建与托管](website/README.md)

<a id="acknowledgments-and-citation"></a>

## 致谢与引用

SuperMimic 由 Qiayuan Liao、Yiyang Shao、Junfeng Long、Kevin Zakka、Roberto Horowitz、Pieter Abbeel 和 Koushil Sreenath 在[原论文](https://arxiv.org/abs/2610.28480)中提出。感谢论文作者和 **Chong Zhang** 开源的[第三方实现](https://github.com/zita-ch/supermimic_vibed)，本项目基线固定为 `a1508d42c9d1699a52e8233ab16d08c488441ab9`。

本移植保留上游网络和核心学习循环，提供 MuJoCo/MJLab 接入、两套 G1 配置及训练评估工具，未覆盖论文完整 BONES-SEED 语料、多 GPU 扩展和全部目标接口。实现差异见 [UPSTREAM.md](UPSTREAM.md)。使用时请引用原论文、上游实现及本项目版本；引用信息见 [references.bib](references.bib) 和 [CITATION.cff](CITATION.cff)。

<a id="attribution-and-scope"></a>

## 许可证

[LICENSE](LICENSE) 保留 `Copyright (c) 2026 ETH Zurich, Chong Zhang` 及 MIT 条款。机器人资产、依赖、数据集和媒体分别遵循其原许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
