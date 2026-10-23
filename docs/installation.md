# 环境配置

**简体中文** | [English](installation.en.md)

本项目可独立安装，无需 Isaac Lab、Isaac Sim、Newton 或 USD。仓库已包含两种 G1 机器人模型及其许可证。请为本项目创建单独的 Python 环境。

## 已验证的软件版本

| 组件 | 版本或适用范围 |
| --- | --- |
| 操作系统 | Linux x86_64；服务器部署使用 Ubuntu 22.04 |
| Python | 3.10；独立本地环境已验证 3.10.20 |
| PyTorch | 2.7.1，CUDA 12.6 构建版本 |
| MJLab | 1.4.0 |
| MuJoCo / MuJoCo-Warp | 3.8.1 / 3.8.1 |
| Warp | 1.14.0 |
| NumPy | 1.26.4 |

完整的已验证依赖版本见 [`requirements.lock.txt`](../requirements.lock.txt)。软件包声明支持 Python 3.10–3.12，但完整锁定依赖和复现环境仅验证了 Python 3.10。Windows 和 macOS 尚未作为复现平台验证。

- **CUDA 训练与并行评估：** 使用 `--backend mjlab --device cuda:0`，需要 NVIDIA GPU 和正常工作的主机驱动。已记录的服务器部署使用驱动 580.126.09；这是经过验证的版本，**不代表最低驱动版本要求**。
- **CPU 调试与小规模评估：** 使用 `--backend mujoco --device cpu`。该模式仍会导入 MJLab 构建场景，然后在 CPU 上使用原生 MuJoCo 推进物理仿真，因此可使用同一套环境。即使选择 CPU 后端，完整锁定依赖仍包含 CUDA 运行时软件包。
- **视频渲染：** 除 Python 依赖外，还需要 OpenGL 后端。纯数值训练和评估无需桌面会话，也不依赖视频渲染。

## 安装独立环境

请先安装 Python 3.10 及其 `venv` 模块。仓库已公开，克隆无需 GitHub 身份认证：

```bash
git clone https://github.com/panhainan2020/SuperMimic-MuJoCo.git
cd SuperMimic-MuJoCo
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt -e '.[video]'
python -m pip check
```

上述安装命令包含视频扩展依赖 `imageio`、`imageio-ffmpeg` 和 Pillow。锁定依赖包含已验证 PyTorch 构建所用的 CUDA 12.6 依赖。如果所用软件源提供的是其他 PyTorch 构建版本，请在安装锁定依赖**之前**显式选择官方 CUDA 12.6 安装包：

```bash
python -m pip install torch==2.7.1 torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r requirements.lock.txt -e '.[video]'
python -m pip check
```

版本选择依据 [PyTorch 2.7.1 官方安装说明](https://pytorch.org/get-started/previous-versions/#v271)。`nvidia-smi` 显示的 `CUDA Version` 与 `torch.version.cuda` 报告的运行时版本含义不同；请检查后者，确认实际安装的 PyTorch 构建版本。对照已发布评估结果时，请勿单独升级仿真器相关软件包。

## 检查导入与 GPU 可见性

激活环境后执行：

```bash
python - <<'PY'
import importlib.metadata as metadata
import sys
import torch
import mujoco
import mjlab
import mujoco_warp
import warp
import supermimic

print("Python:", sys.version.split()[0])
print("Package:", supermimic.__file__)
for name in ("torch", "mjlab", "mujoco", "mujoco-warp", "warp-lang", "numpy"):
    print(f"{name}: {metadata.version(name)}")
print("PyTorch CUDA build:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
PY

python -m supermimic.train --help
python -m supermimic.evaluate --help
```

使用 MJLab/CUDA 时，预期看到 `CUDA available: True`，CUDA 构建版本为 `12.6`。若 CUDA 不可用，请检查 `nvidia-smi`、容器是否能访问 GPU、当前 Python 解释器和已安装的 PyTorch 构建版本。在仅使用 CPU 原生后端的机器上，显示 `False` 属于正常情况。导入成功本身不能证明物理仿真或训练正确。

## 可选的实现检查

请将输出目录设为执行机器持久盘上的可写目录，运行前替换示例路径：

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic
mkdir -p "$SUPERMIMIC_EXPERIMENT_ROOT"

# CPU contract, motion, kinematics and native-backend checks.
OMP_NUM_THREADS=2 python -m unittest discover -s tests -v

# Tiny CPU train -> resume -> evaluate pipeline, using synthetic standing motions.
python tools/smoke.py --backend mujoco --device cpu --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cpu"
```

上述命令先检查 CPU 物理约束、动作、运动学和原生后端，再使用合成站立动作运行小规模的训练、续训和评估流程。

在 GPU 机器上，还可检查 CUDA 后端：

```bash
SUPERMIMIC_TEST_CUDA=1 OMP_NUM_THREADS=2 \
  python -m unittest discover -s tests -v
python tools/smoke.py --backend mjlab --device cuda:0 --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cuda"
```

每次冒烟测试均应使用新的 `--out` 目录。这些检查采用小网络和合成参考动作，不衡量已发布策略的性能。检查另一种模型时，使用 `--robot g1_29dof_rev_1_0` 并另设输出目录。已发布的 98k 策略仅适用于默认的 `g1_29dof`。

## 无桌面视频渲染

`tools/render_rollout.py` 默认使用 EGL。在最小化 Ubuntu 22.04 服务器镜像中，除 NVIDIA 驱动和 Python 环境外，还需要以下系统库：

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends libegl1 libgl1 libopengl0 libglib2.0-0
```

安装这些库不会安装或修复 NVIDIA 主机驱动。在容器中，还必须能访问主机的图形/EGL 驱动库。只有已正确安装 OSMesa 时，才使用渲染器的 `--gl osmesa`；有可用显示环境时可使用 `--gl glfw`。切换图形后端只影响视频生成，不改变已保存的数值轨迹。

[评估指南](evaluation.md)提供已发布策略的评估命令、轨迹分析和并排 MP4 渲染命令。动作数据须通过 `--motion_dir` 指向现有本地文件，本项目不会下载数据集。仓库附带的策略仅供推理，无法恢复世界模型、critic 或优化器的完整训练状态。

## 存储与网络范围

安装命令执行时会获取软件依赖，但不会获取动作数据集、远端训练归档、经验回放或额外权重。用户已明确授权本仓库发布唯一的已测试策略 `checkpoints/g1_29dof/policy_098000.pt`；此授权不涵盖其他产物的获取或发布。

训练输出、经验回放、已记录轨迹、视频和其他大体积产物保留在训练服务器持久盘上，不得自动下载、预取、镜像、断点续传或流式传输。只可获取少量文本状态、指标和必要元数据；完整性与恢复检查在服务器上执行。已有授权的关机应在训练、持久盘保存核验和授权测试完成后执行，保留持久盘，不等待下载。
