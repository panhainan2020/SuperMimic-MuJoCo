# SuperMimic on MuJoCo / MJLab

[简体中文](README.md) | **English**

An **unofficial MuJoCo/MJLab port of SuperMimic**, based on [zita-ch/supermimic_vibed@a1508d4](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9). Supports two G1 models, parallel GPU training, motion-tracking evaluation and video rendering, without Isaac Lab or Isaac Sim.

**[Live results](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)**: solid policy and cyan reference ghost in one scene, with LAFAN examples, 12 100STYLE videos, whole-record trajectory MAE and full metric tables. Videos are hosted separately from Git.

## Install

Validated on Linux x86_64 with Python 3.10, PyTorch 2.7.1, MJLab 1.4.0, MuJoCo / MuJoCo-Warp 3.8.1 and Warp 1.14.0. MJLab parallel training requires CUDA; small evaluations can use the native MuJoCo CPU backend.

```bash
git clone https://github.com/panhainan2020/SuperMimic-MuJoCo.git
cd SuperMimic-MuJoCo
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt -e '.[video]'
```

See the [installation guide](docs/installation.en.md) for environment checks and dependencies. Both robot assets are included; prepare motion data separately. Scripts do not download it automatically.

<a id="evaluation-and-videos"></a>

## Evaluate the bundled policy

The tested [`policy_098000.pt`](checkpoints/g1_29dof/policy_098000.pt) (34.8 MiB) uses the default `g1_29dof`, `upstream` control profile and `legacy99` observations. This is an inference policy, not a complete checkpoint for `--resume`. See the [checkpoint guide](checkpoints/g1_29dof/README.en.md) for hashes and compatibility.

From the repository root, verify the policy and evaluate existing motion data:

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

Use a fresh output directory for each evaluation; results are written to its `evaluation.json`. For CPU evaluation, use `--backend mujoco --device cpu`. Add `--record "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/policy_098000/rollout.npz"` to record trajectories. See the [evaluation guide](docs/evaluation.en.md) for MAE and ghost-video commands.

## Results

Results use the fixed **98,000-iteration policy**. Training used all 40 clips in the third-party G1 LAFAN release (~2.45 hours), not all 77 original LAFAN1 sequences. The 100STYLE evaluation covers 100 styles and 3,573 unseen segments, without finetuning.

| Metric | LAFAN training motions | 100STYLE OOD |
| --- | ---: | ---: |
| Mean normalized return | 0.8713 | 0.8045 |
| Completed clips | 40 / 40 | 3569 / 3573 |
| Whole-record joint MAE | 4.40° | 6.99° |
| Whole-record root XYZ component MAE | 27.29 cm | 21.68 cm |
| XY+yaw-aligned body MPJPE | 2.61 cm | 5.23 cm |
| Mean clip duration | 220.55 s | 18.77 s |

Errors use equal clip weighting. MAE includes all valid 50 Hz pre-step records, including the initial frame and excluding the unrecorded terminal post-step state. Failed clips include only their observed prefix, with coverage reported separately. Root XYZ MAE uses no position alignment and differs from root L2 distance. The website also provides frame-weighted results.

Completion means no termination condition was triggered. Different durations and retargeting pipelines limit comparisons between datasets. These results do not represent a completed 320k run or all paper experiments. See the [full report](results/098000/REPORT.md) and [metric files](results/README.en.md).

## Choose a robot

| `--robot` | Model | Policy availability |
| --- | --- | --- |
| `g1_29dof` **(default)** | 5010 wrists, MJLab collision primitives | Bundled 98k policy |
| `g1_29dof_rev_1_0` | Third-party G1 revision 1.0, converted from a pinned URDF | Training interface verified; no trained policy |

Both have 29 actuated joints but differ in wrist geometry, inertias and collisions. Their checkpoints are not interchangeable; see [robot assets](ASSETS.md). The default `upstream` / `legacy99` preserves the third-party controller and 99D observations. `paper` / `paper93` are experimental options.

## Data and outputs

`--motion_dir` accepts an existing retargeted CSV directory, a single CSV or a compatible joblib `.pkl`. CSV columns are root xyz, an xyzw quaternion and 29 joint angles in Unitree SDK order, at 30 Hz. Each joblib motion requires `root_trans_offset`, `root_rot` (xyzw), `dof` and `fps`. The loader resamples to 50 Hz. Raw 100STYLE data requires format conversion.

Set `SUPERMIMIC_EXPERIMENT_ROOT` to server persistent storage; all run outputs must be inside it. The default is `./outputs` when unset.

**Training artifacts stay on the server's persistent disk.** Do not automatically download, prefetch, mirror, resume-transfer or stream weights, replay, archives or other large files. Retrieve only small text status, metrics and necessary metadata. Run integrity and recovery checks on the server. After training, storage checks and authorized tests, perform previously authorized shutdown while retaining the persistent disk, without waiting for downloads.

## Training

Use the third-party baseline settings below, replacing the data path and choosing a fresh run directory:

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

For the second model, select `--robot g1_29dof_rev_1_0` and a different run directory. GPU memory use depends on parallel environment count and replay capacity.

Add `--resume /path/to/run/last.pt` to restore networks and optimizers, then refill replay. SIGINT/SIGTERM saves at an iteration boundary; wait for exit and verify the persistent checkpoint before shutdown. See `python -m supermimic.train --help` for all options.

## Validation

```bash
OMP_NUM_THREADS=2 python -m unittest discover -s tests -v
python tools/smoke.py --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cpu"
```

The smoke check validates small-scale training, resume and evaluation, not convergence.

## Code and documentation

[Algorithm and backends](supermimic/) · [Tools](tools/) · [Tests](tests/) · [Results](results/098000/) · [Website build and hosting](website/README.en.md)

## Acknowledgments and citation

SuperMimic was introduced by Qiayuan Liao, Yiyang Shao, Junfeng Long, Kevin Zakka, Roberto Horowitz, Pieter Abbeel and Koushil Sreenath in the [original paper](https://arxiv.org/abs/2610.28480). We thank the paper authors and **Chong Zhang** for the [third-party implementation](https://github.com/zita-ch/supermimic_vibed), pinned here to `a1508d42c9d1699a52e8233ab16d08c488441ab9`.

This port preserves the upstream networks and core learning loop, adding MuJoCo/MJLab integration, two G1 configurations and training/evaluation tools. It does not cover the full BONES-SEED corpus, multi-GPU scaling or all goal interfaces. See [UPSTREAM.md](UPSTREAM.md) for implementation differences. Cite the original paper, upstream implementation and this port's version; citation entries are in [references.bib](references.bib) and [CITATION.cff](CITATION.cff).

## License

[LICENSE](LICENSE) preserves `Copyright (c) 2026 ETH Zurich, Chong Zhang` and the MIT terms. Robot assets, dependencies, datasets and media retain their respective licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
