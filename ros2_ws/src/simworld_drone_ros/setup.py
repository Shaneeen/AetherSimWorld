from setuptools import setup

package_name = "simworld_drone_ros"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
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
            "ue_bridge = simworld_drone_ros.ue_bridge:main",
            "brain = simworld_drone_ros.brain:main",
        ],
    },
)