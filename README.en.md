# SuperMimic on MuJoCo / MJLab

[简体中文](README.md) | **English**

Independent motion-tracking reproduction of **SuperMimic**, using native MuJoCo
and MJLab / MuJoCo-Warp. Based on the third-party implementation
[zita-ch/supermimic_vibed@a1508d4](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9).
This is not official author code and does not reproduce the paper's entire
BONES-SEED training corpus, multi-GPU scaling, or every goal interface.

**[Live results](https://supermimic-mujoco-results.zippyaspen7.chatgpt.site)** —
frozen 98k policy, 40 LAFAN training motions and 3,573 unseen 100STYLE segments.
Both the results page and this code repository are public. Videos use separate
object storage and are not included in GitHub.

The [updated website source](website/README.en.md) adds solid-policy/reference-ghost overlays, 12 indexed 100STYLE videos and whole-record MAE. This update publishes source and small result text files only. New videos have not been uploaded, and the live site remains at its previous version.

**A standalone MuJoCo/MJLab project: no Isaac Lab, Isaac Sim, Newton or USD required.**
The package includes XML files, meshes and licenses for both G1 models. The
defaults retain the trained and evaluated robot, the third-party controller
and its 99-dimensional observation. PyTorch trains the world model, policy
and critic; policy gradients propagate through the learned world model.

## Repository layout

| Path | Contents |
| --- | --- |
| `supermimic/` | Algorithm, motion library, robot contracts, CPU/CUDA backends |
| `supermimic/assets/robots/` | Two G1 models, shared meshes, provenance and licenses |
| `tools/` | Train/resume smoke check, trajectory analysis and video rendering |
| `tests/` | Contract, kinematics, motion, replay and backend checks |
| `checkpoints/g1_29dof/` | Tested 98k inference policy and integrity/provenance manifest |
| `results/098000/` | Portable evaluation snapshot: reports, CSV metrics, evidence hashes |
| `website/` | Results webpage, reproducible export and external-media configuration |
| `requirements.lock.txt` | Validated Linux / Python 3.10 dependency versions |

The explicitly published 98k inference policy is included in Git. Other weights,
full training checkpoints, raw motion datasets, replay, videos and Python
environments are excluded. Result media is served separately; see
[website guide](website/README.en.md).

## Install

See the **[installation guide](docs/installation.en.md)** for complete setup
instructions and environment checks.

Validated on Linux x86_64 with Python 3.10, PyTorch 2.7.1, MJLab 1.4.0,
MuJoCo / MuJoCo-Warp 3.8.1 and Warp 1.14.0. CUDA is required for the MJLab
parallel backend. The CPU backend uses the same MJLab scene compiler and
native `mujoco.mj_step` for simulation; it does not require Isaac software.

```bash
git clone https://github.com/panhainan2020/SuperMimic-MuJoCo.git
cd SuperMimic-MuJoCo
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt -e '.[video]'
python -m supermimic.train --help
```

The repository is public and can be cloned without authentication.
For a compatible installation without the complete environment lock, use
`python -m pip install -e '.[video]'`. The package metadata pins simulation
versions to prevent accidental changes in physics. No script fetches robot
assets, motion data, policies or training archives automatically.

## Choose a robot

| `--robot` | Description | Existing evaluated policy |
| --- | --- | --- |
| `g1_29dof` **(default)** | Current trained G1; 5010 wrists and MJLab collision primitives | 98k LAFAN / 100STYLE results below |
| `g1_29dof_rev_1_0` | G1 revision 1.0 selected by the third-party reproduction, converted from its pinned URDF | Training interface verified; no convergence result claimed |

Both have 29 actuated joints, but wrist geometry, inertial parameters and
collision representation differ. See [ASSETS.md](ASSETS.md). Select the robot
when training **and** evaluating; a checkpoint from one robot is rejected for
the other. `--xml_path` is available for an explicit custom asset.

The default `--profile upstream --observation_mode legacy99` preserves the
third-party controller and observation encoding. `legacy99` is this port's
name for the third-party 99D observation. The `paper` and
`paper93` options remain experimental ablations, not claims of a faithful
reconstruction of undisclosed paper details.

## Motion data and persistent outputs

Provide data already present on the executing machine using `--motion_dir`:

- A directory of LAFAN retargeted CSV files, or one CSV: root xyz, quaternion
  **xyzw**, then 29 joint angles in Unitree SDK order; source rate 30 Hz.
- A compatible joblib `.pkl` mapping clip names to `root_trans_offset`,
  `root_rot` (xyzw), `dof` and `fps`.

The loader resamples to 50 Hz, recomputes velocity/FK and sorts clip names.
It does not apply additional height correction or heading augmentation.
Raw 100STYLE files require an explicit format conversion; the OOD result
snapshot documents the exact converted release used in that evaluation.
Dataset licenses are separate from the implementation license.

Set an output root on **server persistent storage** before training:

```bash
export SUPERMIMIC_EXPERIMENT_ROOT=/path/to/persistent/supermimic
```

Without this variable, outputs default to `./outputs`. All run directories
must be inside the configured root. Keep machine-specific output paths in
your shell environment rather than committed configuration files.

**Storage rule:** training artifacts stay on the training server's persistent
disk. Do not automatically download, prefetch, mirror, resume-transfer or
stream weights, replay, archives or other large artifacts. Only small text
status, metrics and necessary metadata may be retrieved. Verify integrity
and recovery on the server. Previously authorized shutdown follows training,
persistent-storage verification and authorized tests without waiting for a
download, and retains the persistent disk.

## Training

The current 4090 experiment uses the third-party settings below. This starts
a new run; choose a fresh output directory and a data path appropriate to
your server. Resource use depends on parallel count and replay size.

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

For the second model, change `--robot g1_29dof_rev_1_0` and use a **new** run
folder, e.g. `runs/lafan_g1_rev1`. Defaults retain H=32, world-model window=8,
10-frame goals/history, UTD=0.4, world-model batch=2048 and policy batch=4096.

Use `--resume /path/to/run/last.pt` with the same configuration to restore
networks and optimizers, then refill replay. This is not bitwise replay
continuation. `last.pt` is resumable; numbered snapshots may omit optimizer
state. SIGINT/SIGTERM saves at the next iteration boundary. Wait for process
exit and verify the persistent checkpoint before an authorized shutdown;
SIGKILL or a power loss cannot guarantee a final save.

## Evaluation and videos

**The repository includes the 98k policy evaluated on the results webpage:**
[`checkpoints/g1_29dof/policy_098000.pt`](checkpoints/g1_29dof/policy_098000.pt)
(about 34.8 MiB). It uses the default `g1_29dof` robot, the third-party
`upstream` controller and `legacy99` observations. Publication removed server
paths and updated the XML hash metadata after verifying compiled-model
equivalence. Every policy tensor is bitwise identical to the model used for
the LAFAN / 100STYLE evaluations. See the accompanying
[`manifest.json`](checkpoints/g1_29dof/manifest.json) for hashes and provenance,
and the [checkpoint guide](checkpoints/g1_29dof/README.en.md) for its scope.

This is an **inference policy**. It does not include the world model, critic,
optimizers or replay and cannot be passed to `--resume` as a complete training
checkpoint. No trained weights are available for the second G1 model.

After installation, run this loading and inference check from the repository
root; no motion data is required:

```bash
source .venv/bin/activate
python tools/verify_checkpoint.py
```

Then evaluate motion tracking using LAFAN data already available on the
executing machine. Replace both paths below with your local or server paths.
The dataset is neither included nor downloaded automatically. To compare with
the in-distribution results below, use the complete third-party release of
40 G1 LAFAN clips.

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

Results are written to `evaluation/policy_098000/evaluation.json`. This command
evaluates the bundled weights directly. For small CPU checks, use
`--backend mujoco --device cpu`; CUDA is recommended for the full dataset.
Use a fresh output directory for each evaluation.

Add trajectory recording for subsequent pose analysis or video rendering:

```bash
python -m supermimic.evaluate \
  --backend mjlab --device cuda:0 --robot g1_29dof \
  --motion_dir /path/to/lafan_csv_or_joblib \
  --run_dir "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/g1" \
  --ckpt checkpoints/g1_29dof/policy_098000.pt \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/evaluation/g1/rollout.npz"
```

Evaluation starts each clip at its first reference frame, disables noise and
domain randomization, and freezes finished environments. Normalized return
uses the **full reference length**; training-log return per surviving step is
not an equivalent metric. The bundled policy remains portable across install
paths: asset identity and control parameters are checked, while absolute
machine paths are not. Older checkpoints carrying a different XML hash are
rejected; the bundled policy metadata was updated only after verifying the
rebuilt model's exact equivalence. See [evaluation guide](docs/evaluation.en.md)
for analysis and video commands.

The published snapshot uses a **fixed 98,000-iteration policy**, not a claim
that the full 320k run is complete. Training used all 40 clips of the third-party
G1 LAFAN release (~2.45 h), not all 77 original LAFAN1 sequences (~4.6 h).

| Metric | LAFAN training motions | 100STYLE OOD |
| --- | ---: | ---: |
| Mean normalized return | 0.8713 | 0.8045 |
| Completed clips | 40 / 40 | 3569 / 3573 |
| Joint MAE | 4.40° | 6.99° |
| XY+yaw-aligned body MPJPE | 2.61 cm | 5.23 cm |
| Mean clip duration | 220.55 s | 18.77 s |

100STYLE covers 100 styles in a pinned G1 converted release with no finetuning.
Completion means no original termination trigger, not precise motion matching.
Shorter clips and a different retargeting pipeline limit direct comparisons.
The webpage includes representative and failed examples; full metrics include
all evaluated clips. See the [results guide](results/README.en.md) and
[full report](results/098000/REPORT.md).

## Validation

```bash
OMP_NUM_THREADS=2 python -m unittest discover -s tests -v
python tools/smoke.py --robot g1_29dof \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_cpu"
python tools/smoke.py --backend mjlab --device cuda:0 \
  --robot g1_29dof_rev_1_0 \
  --out "$SUPERMIMIC_EXPERIMENT_ROOT/validation/g1_rev1_gpu"
```

Smoke checks use synthetic standing references and tiny networks to test train,
resume and evaluate. They do not measure motion-tracking convergence.

## Acknowledgments and citation

The SuperMimic method was introduced by **Qiayuan Liao, Yiyang Shao, Junfeng
Long, Kevin Zakka, Roberto Horowitz, Pieter Abbeel and Koushil Sreenath** in
[SuperMimic: Scaling Humanoid Whole-Body Control with One Differentiable World
Model](https://arxiv.org/abs/2610.28480).

This project is based on **Chong Zhang's third-party implementation**,
[zita-ch/supermimic_vibed](https://github.com/zita-ch/supermimic_vibed), pinned to
commit `a1508d42c9d1699a52e8233ab16d08c488441ab9`. We thank the paper authors for
the method and Chong Zhang for releasing the implementation. This repository
retains the upstream world model, policy/critic architecture and core learning
loop. Our contributions focus on the independent MuJoCo/MJLab integration,
two G1 model configurations, implementation fixes, and reproducible training,
evaluation and result presentation. This is an unofficial port, with no
implied endorsement by the paper authors or the upstream implementation author.

When using this port, please cite the **original paper**, acknowledge the
**upstream implementation and its pinned commit**, and identify the version
of this port used in your experiment. Copyable BibTeX entries are in
[references.bib](references.bib); [CITATION.cff](CITATION.cff) provides structured
citation metadata for this port and references both prior works.

## Attribution and scope

[UPSTREAM.md](UPSTREAM.md) records the implementation baseline and changes.
The original `Copyright (c) 2026 ETH Zurich, Chong Zhang` notice and MIT terms
are preserved in [LICENSE](LICENSE). [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
records separate licenses for MJLab and Unitree robot assets, dependencies,
external datasets and media. The implementation's MIT license does not
relicense these other materials.

The port preserves the third-party differentiable model, analytical rewards,
soft termination, reset sampling and single-GPU training structure. It fixes
motion-boundary/replay edge cases and repeated-bin reward updates, and replaces
the simulator integration. Matching simulator behavior or passing code tests
alone does not establish the paper's performance or training-time claims.
