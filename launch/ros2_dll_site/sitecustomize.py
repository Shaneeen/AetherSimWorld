"""Make ROS 2 Windows binary DLL loading reliable for launch scripts."""

import os

for path in (
    r"C:\pixi_ws\ros2-windows\bin",
    r"C:\pixi_ws\ros2-windows\Scripts",
    r"C:\pixi_ws\.pixi\envs\default",
    r"C:\pixi_ws\.pixi\envs\default\Library\bin",
    r"C:\pixi_ws\.pixi\envs\default\Scripts",
):
    if os.path.isdir(path):
        os.add_dll_directory(path)
