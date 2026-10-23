# Environment setup

[简体中文](installation.md) | **English**

This repository installs independently of Isaac Lab, Isaac Sim, Newton and
USD. Both G1 models and their licenses are included. Use a separate Python
environment for this project.

## Validated software

| Component | Version / scope |
| --- | --- |
| Operating system | Linux x86_64; server deployment on Ubuntu 22.04 |
| Python | 3.10; independent local environment verified with 3.10.20 |
| PyTorch | 2.7.1, CUDA 12.6 build |
| MJLab | 1.4.0 |
| MuJoCo / MuJoCo-Warp | 3.8.1 / 3.8.1 |
| Warp | 1.14.0 |
| NumPy | 1.26.4 |

The complete validated package versions are in
[`requirements.lock.txt`](../requirements.lock.txt). The package accepts Python
3.10–3.12, but the complete lock and reproduction environment were validated
with Python 3.10. Windows and macOS are not validated reproduction platforms.

- **CUDA training and parallel evaluation:** use `--backend mjlab --device
  cuda:0` with an NVIDIA GPU and a working host driver. The recorded server
  deployment used driver 580.126.09; this is a tested version, **not a claimed
  minimum driver version**.
- **CPU debugging and small evaluations:** use `--backend mujoco --device cpu`.
  This still imports MJLab for scene construction, then advances native MuJoCo
  physics on the CPU. The same environment works for this mode. The full lock
  includes CUDA runtime packages even when you select the CPU backend.
- **Video rendering:** requires an OpenGL backend in addition to the Python
  packages. Numerical training/evaluation does not require a desktop session
  or video rendering.

## Install a dedicated environment

Start with Python 3.10 and its `venv` module available. The repository is
public; cloning requires no GitHub authentication:

```bash
git clone https://github.com/panhainan2020/SuperMimic-MuJoCo.git
cd SuperMimic-MuJoCo
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt -e '.[video]'
python -m pip check
```

The last installation command includes the video extras (`imageio`,
`imageio-ffmpeg`, and Pillow). The lock includes the CUDA 12.6 dependencies used
by the validated PyTorch build. If your package index supplies a different
PyTorch build, select the official CUDA 12.6 wheels explicitly **before** the
locked installation:

```bash
python -m pip install torch==2.7.1 torchvision==0.22.1 \
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r requirements.lock.txt -e '.[video]'
python -m pip check
```

The version/build selection follows the
[official PyTorch 2.7.1 installation instructions](https://pytorch.org/get-started/previous-versions/#v271).
The `CUDA Version` displayed by `nvidia-smi` and the runtime reported by
`torch.version.cuda` are different checks; inspect the latter to confirm the
installed PyTorch build. Do not upgrade the simulator packages independently
when comparing against the published evaluation.

## Verify imports and GPU visibility

Run from the activated environment:

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

For MJLab/CUDA runs, expect `CUDA available: True` and a CUDA build of `12.6`.
If CUDA is unavailable, check `nvidia-smi`, whether the GPU is exposed to the
container, the active Python interpreter, and the installed PyTorch build.
`False` is expected on a CPU-only machine using the native backend. An import
check alone does not validate physics or training.

## Optional implementation checks

Set a writable output directory on the executing machine's persistent storage.
Replace the example path before running:

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic
mkdir -p "$SUPERMIMIC_EXPERIMENT_ROOT"

# CPU contract, motion, kinematics and native-backend checks.
OMP_NUM_THREADS=2 python -m unittest discover -s tests -v

# Tiny CPU train -> resume -> evaluate pipeline, using synthetic standing motions.
python tools/smoke.py --backend mujoco --device cpu --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cpu"
```

On a GPU machine, optionally verify the CUDA backend as well:

```bash
SUPERMIMIC_TEST_CUDA=1 OMP_NUM_THREADS=2 \
  python -m unittest discover -s tests -v
python tools/smoke.py --backend mjlab --device cuda:0 --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cuda"
```

Use a fresh `--out` directory for each smoke run. These checks use tiny networks
and synthetic references; they do not measure the released policy's performance.
The alternate model can be checked with `--robot g1_29dof_rev_1_0` and a separate
output directory. The released 98k policy is for the default `g1_29dof` only.

## Headless video rendering

`tools/render_rollout.py` uses EGL by default. In minimal Ubuntu 22.04 server
images, the following system libraries were needed in addition to the NVIDIA
driver and Python environment:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends libegl1 libgl1 libopengl0 libglib2.0-0
```

Installing these libraries does not install or repair the NVIDIA host driver.
In containers, the host's graphics/EGL driver libraries must also be accessible.
Use the renderer's `--gl osmesa` option only when a working OSMesa installation
already exists, or `--gl glfw` with a working display. Changing the graphics
backend affects video generation, not the saved numerical rollout.

The [evaluation guide](evaluation.en.md) provides the released-policy command,
trajectory analysis and side-by-side MP4 rendering commands. Data is supplied
through an existing local `--motion_dir`; no dataset download is performed by
the project. The bundled policy is inference-only and cannot restore the full
world-model/critic/optimizer training state.

## Storage and network scope

The installation commands fetch software dependencies when executed. They do
not fetch motion datasets, remote training archives, replay or additional
checkpoints. The user's explicit publication request permits the single tested
`checkpoints/g1_29dof/policy_098000.pt` in this repository; it is not general
authorization to retrieve or publish other artifacts.

Training outputs, replay, recorded trajectories, videos and other large
artifacts stay on the training server's persistent disk. Do not automatically
download, prefetch, mirror, resume-transfer or stream them. Only small text
status, metrics and necessary metadata may be retrieved; integrity and recovery
checks run on the server. Previously authorized shutdown follows training,
persistent-storage verification and authorized tests, retains the persistent
disk, and does not wait for downloads.
