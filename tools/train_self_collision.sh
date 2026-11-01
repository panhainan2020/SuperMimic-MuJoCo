#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: bash tools/train_self_collision.sh MOTION_PATH RUN_NAME" >&2
  exit 2
fi

: "${SUPERMIMIC_EXPERIMENT_ROOT:?Set SUPERMIMIC_EXPERIMENT_ROOT to persistent storage}"
motion_path="$1"
run_name="$2"
if [[ ! -e "$motion_path" ]]; then
  echo "Motion data must already exist locally: $motion_path" >&2
  exit 2
fi
if [[ ! "$run_name" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]]; then
  echo "RUN_NAME must contain only letters, digits, underscores or hyphens" >&2
  exit 2
fi

export CUDA_VISIBLE_DEVICES="${SUPERMIMIC_GPU:-0}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
export TORCHINDUCTOR_COMPILE_THREADS="${TORCHINDUCTOR_COMPILE_THREADS:-4}"

exec python -u -m supermimic.train \
  --backend mjlab --device cuda:0 --robot g1_29dof \
  --profile upstream --self_collision --observation_mode legacy99 \
  --motion_dir "$motion_path" \
  --num_envs 4096 --buffer_steps 1000 --network_size paper \
  --amp bf16 --compile --wm_batch 2048 --pi_batch 4096 --wm_batches 10 \
  --iterations 320000 --wm_only_iters 500 --seed 0 \
  --log_every 10 --last_every 100 --ckpt_every 2000 \
  --log_dir "$SUPERMIMIC_EXPERIMENT_ROOT/runs/$run_name"
