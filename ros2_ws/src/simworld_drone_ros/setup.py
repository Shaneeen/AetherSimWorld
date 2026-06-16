from setuptools import find_packages, setup

package_name = "simworld_drone_ros"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="you",
    maintainer_email="you@example.com",
    description="ROS 2 bridge and brain for SimWorld drone control",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "ue_bridge = simworld_drone_ros.bridge.ue_bridge:main",
            "brain = simworld_drone_ros.control.brain:main",
            "target_brain = simworld_drone_ros.duel.target_brain:main",
            "chaser_brain = simworld_drone_ros.duel.chaser_brain:main",
            "start_signal = simworld_drone_ros.control.start_signal:main",
            "chase_watch = simworld_drone_ros.watch.chase_watch:main",
            "team_coordinator = simworld_drone_ros.team.coordinator:main",
            "team_drone_controller = simworld_drone_ros.team.drone_controller:main",
            "team_panel = simworld_drone_ros.panel.team_panel:main",
            "visual_observer = simworld_drone_ros.vision.visual_observer:main",
            "vision_check = simworld_drone_ros.vision.check_vision_stack:main",
            "vision_prepare_ollama = simworld_drone_ros.vision.prepare_ollama:main",
            "run_report = simworld_drone_ros.analysis.run_report:main",
        ],
    },
)
