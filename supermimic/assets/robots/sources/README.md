# 默认机器人的固定版本输入

**简体中文** | [English](README.en.md)

这些小体积源文件按原始字节保留。生成工具会在使用前检查其 SHA-256 哈希，且不会访问网络。

| 文件 | 来源 | 许可证 |
| --- | --- | --- |
| `mjlab_g1_1.4.0.xml` | [MJLab v1.4.0，提交 4360096](https://github.com/mujocolab/mjlab/blob/4360096b49c1bcc478668c11ce7d458db747e49d/src/mjlab/asset_zoo/robots/unitree_g1/xmls/g1.xml) | Apache-2.0，Copyright 2025 The mjlab Developers |
| `unitree_g1_29dof_mode_15.urdf` | [Unitree ROS，提交 15ebe53](https://github.com/unitreerobotics/unitree_ros/blob/15ebe53f4cd77e7d745ae83b9d7ff90e685e8998/robots/g1_description/g1_29dof_mode_15.urdf) | BSD-3-Clause，Copyright 2016–2022 HangZhou YuShu TECHNOLOGY CO., LTD. |

完整许可证文本位于 `../licenses/`。文件哈希及源路径同时记录于 `../manifest.json`。

Unitree 输入仅提供六个腕部网格文件名、两个腕部俯仰关节惯量和两个腕部偏航关节偏移。生成模型的其余部分使用 MJLab 模型。此处收录完整 mode-15 URDF 是为了追溯来源；它不是第三种受支持的机器人，也不作为运行时输入。

在仓库根目录中使用 MuJoCo 3.8.1 重新构建：

```bash
python tools/build_default_robot.py
python tools/build_default_robot.py --check
```
