# Pinned inputs for the default robot

[简体中文](README.md) | **English**

These small source files are preserved byte-for-byte. The generator checks
their SHA-256 hashes before use and performs no network access.

| File | Source | License |
| --- | --- | --- |
| `mjlab_g1_1.4.0.xml` | [MJLab v1.4.0, commit 4360096](https://github.com/mujocolab/mjlab/blob/4360096b49c1bcc478668c11ce7d458db747e49d/src/mjlab/asset_zoo/robots/unitree_g1/xmls/g1.xml) | Apache-2.0, Copyright 2025 The mjlab Developers |
| `unitree_g1_29dof_mode_15.urdf` | [Unitree ROS, commit 15ebe53](https://github.com/unitreerobotics/unitree_ros/blob/15ebe53f4cd77e7d745ae83b9d7ff90e685e8998/robots/g1_description/g1_29dof_mode_15.urdf) | BSD-3-Clause, Copyright 2016–2022 HangZhou YuShu TECHNOLOGY CO., LTD. |

Full license texts are in `../licenses/`. The file hashes and source paths are
also recorded in `../manifest.json`.

The Unitree input supplies only the six wrist mesh filenames, two wrist-pitch
inertias, and two wrist-yaw offsets. The rest of the generated model uses the
MJLab model. The complete mode-15 URDF is included for source traceability; it
is not a third supported robot or a runtime input.

Rebuild from the repository root with MuJoCo 3.8.1:

```bash
python tools/build_default_robot.py
python tools/build_default_robot.py --check
```
