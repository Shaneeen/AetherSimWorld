# Drone ROS 2 Starter

This is a starter project that uses:

- Unreal Engine / SimWorld for the world, rendering, collisions, and sensor simulation
- ROS 2 for message passing
- Python for drone logic and AI

It is intentionally simple. The bridge node spawns a static drone actor using:

- `/Game/V1/SM_Drone.SM_Drone`

Then it publishes pose, odometry, collision state, and RGB camera frames into ROS 2. A separate Python node consumes those topics and sends velocity commands back.

## Architecture

The split is exactly the pattern you described:

- Unreal says:
  - here is the drone pose
  - here is the camera image
  - here is the collision state
- Python says:
  - go up
  - move forward
  - turn
  - recover from collision
- ROS 2 carries messages between those pieces

## What This Scaffold Gives You

- `ros2_ws/src/simworld_drone_ros/`
  - ROS 2 Python package
- `simworld_drone_ros/ue_bridge_node.py`
  - UnrealCV to ROS 2 bridge
- `simworld_drone_ros/brain_node.py`
  - starter control logic
- `scripts/DroneROS/run_drone_ros.ps1`
  - local launcher for Windows PowerShell

## Topics

- `drone/pose` (`geometry_msgs/PoseStamped`)
- `drone/odom` (`nav_msgs/Odometry`)
- `drone/collision` (`std_msgs/Bool`)
- `drone/status` (`std_msgs/String`)
- `drone/camera/rgb` (`sensor_msgs/Image`)
- `drone/cmd_vel` (`geometry_msgs/Twist`)
- `drone/brain_status` (`std_msgs/String`)

## Install

Recommended on your machine:

1. Install ROS 2 Jazzy on Windows or use Ubuntu/WSL2 if you want the smoother ROS experience.
2. Install `colcon`.
3. Make sure your Python environment can import:
   - `rclpy`
   - `numpy`
   - `unrealcv`
4. Keep SimWorld and UnrealCV working the same way they already do in this repo.

## First Run

Open SimWorld yourself and load the map you want to use.

Then from `D:\SimWorld` run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\DroneROS\run_drone_ros.ps1
```

That launcher:

- sources ROS 2
- builds the ROS package if needed
- starts the Unreal bridge
- starts the example brain

## Environment Variables

Useful overrides:

```powershell
$env:SIMWORLD_HOST = "127.0.0.1"
$env:SIMWORLD_PORT = "9000"
$env:SIMWORLD_DRONE_ASSET = "/Game/V1/SM_Drone.SM_Drone"
$env:SIMWORLD_DRONE_NAME = "ROS_SM_Drone_0"
$env:SIMWORLD_DRONE_X = "0"
$env:SIMWORLD_DRONE_Y = "0"
$env:SIMWORLD_DRONE_Z = "250"
$env:SIMWORLD_DRONE_YAW = "0"
```

## Important Limitation

`SM_Drone.uasset` sounds like a static asset. That is fine for a first version, but it usually means:

- no built-in flight controller
- no rotor physics
- no aerodynamic model

So in this scaffold, the bridge moves the actor by setting location and rotation directly. That is enough for:

- AI experiments
- tracking
- path planning
- obstacle avoidance prototypes
- sensor pipelines

If you later want realistic flight dynamics, we should swap the actor to a Blueprint or Pawn with movement logic and keep the same ROS 2 topics.

## Next Good Upgrades

- publish depth images and segmentation
- add target detection node
- add waypoint follower
- add Nav2-style planner integration
- add an Unreal plugin for native ROS 2 in-engine publishing
