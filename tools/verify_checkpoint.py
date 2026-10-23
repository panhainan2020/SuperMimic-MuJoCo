"""Verify the explicitly published policy without downloading data or running training.

Reads only local files and prints a small text receipt. Other training artifacts
remain on server persistent storage; this tool never transfers them.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def tensor_digest(state):
    """SHA256 of sorted tensor names, dtypes, shapes and contiguous CPU bytes."""
    digest = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        header = json.dumps([name, str(tensor.dtype), list(tensor.shape)],
                            separators=(",", ":")).encode()
        digest.update(len(header).to_bytes(8, "little"))
        digest.update(header)
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path,
                        default=REPO / "checkpoints/g1_29dof/policy_098000.pt")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    checkpoint = args.checkpoint.expanduser().resolve()
    manifest_path = args.manifest or checkpoint.with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text())
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if sha != manifest["sha256"] or checkpoint.stat().st_size != manifest["bytes"]:
        raise ValueError("Checkpoint file does not match the manifest")

    import torch
    import supermimic.networks as networks
    from supermimic.networks import Policy
    from supermimic.robot_contract import assert_contract_compatible, load_contract
    from supermimic.runtime import network_shapes

    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = saved["args"]
    if saved["iteration"] != 98000:
        raise ValueError("Expected the published 98k policy")
    expected = {"robot": "g1_29dof", "profile": "upstream",
                "observation_mode": "legacy99", "network_size": "paper"}
    for key, value in expected.items():
        if config.get(key) != value or manifest.get(key) != value:
            raise ValueError(f"Unexpected checkpoint/manifest {key}")
    assert_contract_compatible(saved["contract"], load_contract("upstream", robot="g1_29dof"))
    digest = tensor_digest(saved["pi"])
    if digest != manifest["policy_tensor_sha256"]:
        raise ValueError("Policy tensors do not match the manifest")
    if set(saved) & {"wm", "critic", "wm_opt", "pi_opt", "critic_opt", "replay"}:
        raise ValueError("The published artifact must contain only the inference policy")
    torch.set_num_threads(2)
    networks.AMP_DTYPE = None
    policy = Policy(99, 73 * config["goal_frames"], hist=config["hist"],
                    hidden=network_shapes("paper")[1]).eval()
    policy.load_state_dict(saved["pi"], strict=True)
    with torch.inference_mode():
        action = policy(torch.zeros(2, config["hist"], 99),
                        torch.zeros(2, 73 * config["goal_frames"]))
    if action.shape != (2, 29) or not torch.isfinite(action).all():
        raise ValueError("Policy forward pass produced invalid actions")
    print(json.dumps({"status": "PASS", "iteration": saved["iteration"],
                      "robot": "g1_29dof", "bytes": checkpoint.stat().st_size,
                      "sha256": sha, "policy_tensor_sha256": digest,
                      "state_tensors": len(saved["pi"]),
                      "inference_action_shape": list(action.shape),
                      "motion_tracking_evaluated": False,
                      "note": "Integrity/load/forward check only; use supermimic.evaluate with motion data for tracking metrics."}, indent=2))


if __name__ == "__main__":
    main()
