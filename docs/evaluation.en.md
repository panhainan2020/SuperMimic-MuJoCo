# Evaluation, pose diagnostics and local video rendering

[简体中文](evaluation.md) | **English**

The evaluation tools operate entirely on files that already exist on the executing machine. Set `SUPERMIMIC_EXPERIMENT_ROOT` to a writable persistent directory before running them. New models, replay, archives, recorded trajectories and videos remain on the training server's persistent disk. These tools never download or transfer them. Integrity checks run on that machine; monitoring may retrieve small text metrics and metadata. Previously authorized shutdown does not wait for downloads. The user's explicit publication request permits the single tested `checkpoints/g1_29dof/policy_098000.pt` in Git; this exception does not authorize retrieving or publishing other training artifacts.

The two packaged robots use the same 29-joint Unitree SDK order:

- `g1_29dof` is the default and matches the existing evaluated checkpoint.
- `g1_29dof_rev_1_0` is the alternate original revision. Evaluate a checkpoint trained with this robot using the same selection. A different model's checkpoint is rejected by the physical contract check.

The default controller is `upstream` and the observation mode is `legacy99`, which names the third-party baseline's 99-dimensional observation. `paper` and `paper93` are historical experimental options, not the reported reproduction baseline. Changing only the install path does not require editing checkpoints; the evaluator compares XML contents, model selection, controller parameters and solver settings. The bundled policy carries the rebuilt asset's XML hash, updated after exact compiled-model equivalence checks. Older checkpoints carrying the previous XML hash remain strictly rejected; path portability does not bypass asset-version checks.

## Record an evaluation

Install the project and its video dependencies using the [environment setup guide](installation.en.md). The repository includes the fixed 98,000-iteration policy used for the published LAFAN and 100STYLE results. It contains policy weights and inference configuration, not the world model, critic, optimizer state or replay needed to resume training. It is compatible with the default `g1_29dof` only.

From the repository root, supply your existing local motion data explicitly:

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

Use `--backend mujoco --device cpu` for small native-MuJoCo evaluations. Every source clip is evaluated from its first frame, with no action or observation noise and no domain randomization. The evaluator records the states at 50 Hz before each physics step. `evaluation.json` is the authoritative source for normalized return and failure labels. `rollout.npz` contains states and references for later analysis and rendering; it does not contain a policy or replay buffer.

Use a fresh evaluation directory. Full-motion recordings can be large, especially when batching clips with different durations: completed clips remain as frozen padding until the longest clip finishes. Recording is optional and does not affect the return computation.

## Compute pose diagnostics

```bash
python tools/analyze_rollout.py \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz" \
  --evaluation "$SUPERMIMIC_EXPERIMENT_ROOT/eval/evaluation.json" \
  --output "$SUPERMIMIC_EXPERIMENT_ROOT/eval/tracking_metrics.json" \
  --robot g1_29dof
```

`--record` and `--output` are mandatory. The analysis rejects outputs outside `SUPERMIMIC_EXPERIMENT_ROOT` and refuses to overwrite an existing JSON. The optional `--evaluation` associates the authoritative return/failure labels after checking the clip sets. `--chunk` limits each forward-kinematics batch; it does not subsample frames. `--xml-path` is available for an explicit local asset override matching the original evaluation.

The JSON preserves the reported analysis conventions:

- Compare the recorded state at time `t` with the reference at recorded frame `f[t]`, without a one-frame shift.
- Include only `alive=True` pre-step samples. Include the reset frame; exclude frozen padding and the final post-step state that completes or terminates the clip.
- Joint MAE/RMSE use direct differences of the 29 bounded hinge angles, with no angle wrapping. Both radians and degrees are reported.
- Root position error is the Euclidean world-space difference; root orientation error is the SO(3) geodesic angle. Root quaternions use `wxyz`.
- Body MPJPE averages link-origin distances over the 14 tracked bodies. The world version retains drift. The anchored version uses exactly the reward's XY translation and yaw alignment; it is not a Procrustes fit and does not align root height.
- `frame_weighted` pools all valid samples. `clip_equal_weighted` averages each clip's metric, giving short and long clips equal weight. Its RMSE fields are **the arithmetic mean of per-clip RMSE values**, preserving the original LAFAN analysis convention; they are not the square root of averaged per-clip MSE values.

These pose diagnostics are descriptive and conditional on survival. They neither reconstruct reward from the NPZ nor create a new paper acceptance criterion. Compare completion, horizon lengths, retargeting conventions and pose errors together; a high completion rate alone does not establish accurate imitation.

## Compute MAE over the full recorded trajectory

The following CPU-only command reads existing recordings without inference, downloads or uploads. Each `rollout.npz` must have its matching `evaluation.json` beside it. Directory inputs are searched recursively for recordings.

```bash
python tools/trajectory_mae.py \
  --dataset id="$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz" \
  --dataset ood="$SUPERMIMIC_EXPERIMENT_ROOT/ood/batches" \
  --output-dir "$SUPERMIMIC_EXPERIMENT_ROOT/trajectory_mae"
```

Joint MAE averages absolute errors over all valid recorded samples and 29 joints. Root XYZ MAE averages absolute errors over the world X, Y and Z components. It uses no trajectory alignment and differs from mean Euclidean root error (L2). All valid 50 Hz samples contribute, independently of video preview lengths or frame rates.

The convention includes the initial state and excludes the unrecorded final post-step state. Failed clips report only their observed prefix, together with coverage; unexecuted states are never zero-padded. Summaries include all clips, completed clips and failed clips separately, with both equal clip weighting and frame weighting.

Outputs include a raw JSON with source paths, `trajectory_mae.public.json` without machine paths, and per-clip CSV/JSON. Keep the raw JSON in the experiment directory. Public-format files are not automatically committed or published either.

## Render a solid policy with a reference ghost

List the names in the recording or use a name from `evaluation.json`:

```bash
python -c 'import numpy as np, sys; z=np.load(sys.argv[1], allow_pickle=False); print("\n".join(z["names"].tolist()))' \
  "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz"

python tools/render_rollout.py \
  --record "$SUPERMIMIC_EXPERIMENT_ROOT/eval/rollout.npz" \
  --clip EXACT_CLIP_NAME \
  --output "$SUPERMIMIC_EXPERIMENT_ROOT/eval/clip.mp4" \
  --robot g1_29dof --comparison ghost
```

Rendering replays recorded poses; it does not simulate a new rollout. Default `ghost` mode shows the solid policy and a translucent cyan reference in the same world frame and camera, retaining their actual position difference. The ghost adds visual geometry only, without changing physics or duplicating the ground. The camera follows their midpoint and expands with their separation; the trajectories are never independently recentered. Use `--reference-alpha 0.35` to adjust opacity.

`--comparison policy` shows only the policy. `--comparison side-by-side` and the old `--side-by-side` flag retain the two-panel mode. By default the output includes every alive frame at 50 fps. `--max-seconds 10` creates an explicitly marked preview. `--width` and `--height` set each panel's dimensions and must be divisible by 16. EGL is the default offscreen backend; `--gl osmesa` requires an existing OSMesa installation.

The adjacent `.video.json` records input/output SHA-256 hashes, the selected robot/XML, frame counts, full reference length, early-ending status and preview truncation. A video is not an independent success metric. Partial output from a rendering failure is retained for diagnosis and has no successful metadata receipt.

Video dependencies are `imageio`, `imageio-ffmpeg` and `Pillow`, plus a working MuJoCo offscreen graphics backend. Keep MP4, NPZ and other training weights out of Git; the single explicitly published 98k policy is the exception. The static results website can refer to videos hosted separately; generating a video here does not publish it.
