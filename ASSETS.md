# Bundled G1 robot models

Both assets are self-contained MuJoCo MJCF models, with 29 actuated joints in
Unitree SDK order. They share one `supermimic/assets/robots/meshes/` directory.
No neighbouring checkout, Isaac Lab, Isaac Sim, USD conversion, or asset
download is needed at runtime. The 41 shared meshes occupy 23,012,744 bytes
(21.95 MiB).

| CLI selection | Model | Total mass | Wrist-pitch body mass, each | Wrist-yaw joint offset |
| --- | --- | ---: | ---: | ---: |
| `--robot g1_29dof` (default) | Current trained model, 5010 wrist assets, MJLab collision primitives | 33.741042 kg | 0.684 kg | 0.051 m |
| `--robot g1_29dof_rev_1_0` | Third-party reproduction's G1 revision 1.0 URDF, converted to MJCF | 33.341143 kg | 0.48405 kg | 0.046 m |

The model selection is independent of the controller `--profile`. Both use
the third-party `upstream` control profile by default. Changing robots changes
inertial parameters, wrist geometry, fixed-body representation and collisions;
it is a separate training condition. Existing policy results describe only the
default robot and do not establish performance on the second robot.

## Current trained model

`supermimic/assets/robots/g1_29dof.xml` is reproducibly generated from two
bundled, hash-pinned primary sources:

- [MJLab v1.4.0 G1 XML, commit 4360096](https://github.com/mujocolab/mjlab/blob/4360096b49c1bcc478668c11ce7d458db747e49d/src/mjlab/asset_zoo/robots/unitree_g1/xmls/g1.xml), Apache-2.0: the base model and collision primitives, including foot capsules.
- [Unitree G1 mode-15 URDF, commit 15ebe53](https://github.com/unitreerobotics/unitree_ros/blob/15ebe53f4cd77e7d745ae83b9d7ff90e685e8998/robots/g1_description/g1_29dof_mode_15.urdf), BSD-3-Clause: six 5010 wrist mesh filenames, two wrist-pitch inertias, and two wrist-yaw offsets.

The generator diagonalizes the selected Unitree inertias using MuJoCo 3.8.1,
uses its fixed XML writer precision, and generates motors from joint order.
It sets the trained scene's lighting and sensor selection. Other mode-15
body parameters and collision shapes are not substituted into the MJLab model.
The generator reads only these primary sources; it does not read a previous
generated model or fetch any files. See [source inventory](supermimic/assets/robots/sources/README.md).

```bash
python tools/build_default_robot.py
python tools/build_default_robot.py --check
```

Generated SHA-256:
`ac0a40caa37cf38af8dcee55e4bd2cb77fa19fef796d01c3a6765b4ed669d53f`.

The serialized XML differs from the earlier training asset. The compiled
robot remains exactly equal: all 469 public model arrays, 96 scalar fields,
and all 29 option fields match without a numeric tolerance. The same checks
pass after constructing the actual upstream MJLab scene, including its PD
actuators, ground and solver options. Native MuJoCo state trajectories also
match for 128 control steps. The [equivalence record](results/robot_asset_equivalence.json)
includes both file hashes. Bundled policy metadata records the generated
asset identity; policy tensors are unchanged.

All 35 meshes referenced by this model were checked against existing Unitree
ROS `robots/g1_description/meshes` files and are byte-identical. Unitree's BSD
license applies to those meshes. The generated XML retains the MJLab Apache
and Unitree BSD notices; it is **not relicensed as MIT**.

## Third-party reference robot

The third-party [robot.py](https://github.com/zita-ch/supermimic_vibed/blob/a1508d42c9d1699a52e8233ab16d08c488441ab9/supermimic/robot.py)
selects `g1_29dof_rev_1_0.urdf` from the LAFAN1 retargeting repository.
The bundled URDF is pinned to
[`ce1572906efe6157840e8474d5a0d7aa87481e74`](https://huggingface.co/datasets/lvhaidong/LAFAN1_Retargeting_Dataset/blob/ce1572906efe6157840e8474d5a0d7aa87481e74/robot_description/g1/g1_29dof_rev_1_0.urdf).
The source SHA-256 is `824ce02c2c1e489aa8dece47a10fe02d1872289c0e6d01ba51abd291e66b7b2c`.
The bundled URDF normalizes line endings and trailing whitespace only; its
separate checksum is recorded in the manifest. XML values are unchanged.

The generated MJCF follows the third-party
[URDF conversion](https://github.com/zita-ch/supermimic_vibed/blob/a1508d42c9d1699a52e8233ab16d08c488441ab9/tools/urdf_to_mjcf.py):
remove comments, compile with `balanceinertia=true`, `discardvisual=false`,
`fusestatic=false`, `strippath=false`, then add a free pelvis joint. It was
generated with MuJoCo 3.8.1. The URDF preserves fixed link bodies and uses
convex mesh collisions and foot spheres. The scene builder supplies motors
and controller settings at runtime. This is a native MuJoCo representation
of the third-party robot; it does not assert binary identity with its
Isaac Lab/Newton/USD import pipeline.

The conversion input differs from the local Unitree URDF in inline material
definitions, ankle/waist effort and velocity limits, and two fixed-joint
attributes. We used the pinned third-party source instead of substituting
that local URDF. All referenced meshes were reused from existing local files
and verified against the pinned dataset's blob/LFS metadata; no mesh bundle,
motion dataset, weight or video was downloaded for this packaging step.

## Attribution, integrity and storage

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for license scope and the
bundled full license texts. The source and per-file SHA-256 inventory is
[`manifest.json`](supermimic/assets/robots/manifest.json).

Datasets, checkpoints and videos are not part of these robot assets. Training
artifacts remain on the training server's persistent disk; scripts must not
automatically download, mirror, prefetch or resume-transfer them. Only small
text status, metrics and necessary metadata may be retrieved. Integrity and
recovery checks run on the server, and authorized shutdown does not wait for
downloads.
