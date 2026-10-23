# Third-party notices

The root [MIT license](LICENSE) covers the SuperMimic implementation derived
from `zita-ch/supermimic_vibed`, Copyright (c) 2026 ETH Zurich, Chong Zhang.
The original copyright and full MIT terms are retained. The port additions
are Copyright (c) 2026 SuperMimic-MuJoCo contributors. This independent port
is not official SuperMimic author code; attribution does not imply endorsement.
The root license does not replace the licenses of bundled robot assets,
dependencies, external datasets, or result media.

| Component | Source and scope | License |
| --- | --- | --- |
| SuperMimic implementation and reference conversion procedure | [zita-ch/supermimic_vibed@a1508d4](https://github.com/zita-ch/supermimic_vibed/tree/a1508d42c9d1699a52e8233ab16d08c488441ab9) | MIT; [root LICENSE](LICENSE) |
| G1 STL meshes, revision 1.0 and mode-15 robot descriptions | [Unitree Robotics](https://github.com/unitreerobotics/unitree_ros/tree/master/robots/g1_description); third-party reference URDF distributed in [LAFAN1 retargeting robot_description](https://huggingface.co/datasets/lvhaidong/LAFAN1_Retargeting_Dataset/tree/ce1572906efe6157840e8474d5a0d7aa87481e74/robot_description/g1) | [BSD-3-Clause](supermimic/assets/robots/licenses/UNITREE-BSD-3-Clause.txt), Copyright (c) 2016–2022 HangZhou YuShu TECHNOLOGY CO., LTD. |
| MJLab G1 model used to generate the default XML and collision layout | [MJLab](https://github.com/mujocolab/mjlab), Copyright 2025, The mjlab Developers | [Apache-2.0](supermimic/assets/robots/licenses/MJLAB-Apache-2.0.txt) |

`supermimic/assets/robots/g1_29dof.xml` is generated directly from the pinned
MJLab G1 XML and Unitree mode-15 URDF. Source hashes, the reproducible build
procedure and compiled-model equivalence checks are documented in
[ASSETS.md](ASSETS.md). The generated file identifies its modifications and
retains the MJLab/Unitree attribution. The separate `g1_29dof_rev_1_0.xml`
is a generated conversion of the pinned Unitree revision-1.0 URDF.

The bundled full Apache-2.0 and BSD-3-Clause texts apply to their respective
robot sources and assets; they are not replaced by the root MIT license.
The [asset manifest](supermimic/assets/robots/manifest.json) records the source
revisions and file hashes. Generation scripts and port-specific application
code use the root MIT license, while generated robot descriptions retain the
terms of their source materials.

LAFAN1 motion data is licensed separately by Ubisoft under CC BY-NC-ND 4.0;
the robot-description BSD license does not relicense the motions. 100STYLE
and its retargeted releases also retain their source terms. No raw motion
datasets, full training checkpoints, replay buffers, or video binaries are bundled here.
The separately documented 98k inference policy is included by explicit user
request; it is an independently trained reproduction artifact, not an official
SuperMimic author checkpoint. See checkpoints/g1_29dof/README.md for its scope.
Rendered demonstrations and external media must retain their own attribution
and are not covered by the implementation's MIT license.

Runtime dependencies retain their own licenses. This project imports MuJoCo,
MuJoCo-Warp, MJLab, Warp and PyTorch rather than redistributing their source.
