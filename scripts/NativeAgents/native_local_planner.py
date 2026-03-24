"""Experimental planner that reuses SimWorld LocalPlanner with live pose syncing."""

import math
import time
from typing import Optional

import numpy as np

from simworld.local_planner.local_planner import LocalPlanner
from simworld.traffic.base.traffic_signal import TrafficSignalState
from simworld.utils.vector import Vector


class NativeHumanoidPlanner(LocalPlanner):
    """LocalPlanner variant that keeps the native agent pose synced from UnrealCV."""

    def sync_agent_pose(self):
        try:
            info = self.communicator.get_position_and_direction(humanoid_ids=[self.agent.id])
            pos_dir = info.get(('humanoid', self.agent.id))
            if pos_dir:
                pos, yaw = pos_dir
                self.agent.position = pos
                self.agent.direction = float(yaw)
                return pos, float(yaw)
        except Exception:
            pass

        name = self.communicator.get_humanoid_name(self.agent.id)
        loc = self.communicator.unrealcv.get_location(name)
        ori = self.communicator.unrealcv.get_orientation(name)
        pos = Vector(loc[0], loc[1])
        yaw = float(ori[1]) if len(ori) > 1 else 0.0
        self.agent.position = pos
        self.agent.direction = yaw
        return pos, yaw

    def navigate_rule_based(self, point: Vector) -> None:
        self.sync_agent_pose()
        self.logger.info(f'Agent {self.agent.id} is navigating to {point}, current position: {self.agent.position}, native rule based mode')
        if self.map.traffic_signals:
            current_node = self.map.get_closest_node(self.agent.position)
            if current_node.type == 'intersection':
                traffic_light = None
                min_distance = self.agent.config['traffic.sidewalk_offset'] * 2
                for signal in self.map.traffic_signals:
                    distance = self.agent.position.distance(signal.position)
                    if distance < min_distance:
                        min_distance = distance
                        traffic_light = signal

                if traffic_light is not None:
                    while self.exit_event is None or not self.exit_event.is_set():
                        state = traffic_light.get_state()
                        left_time = traffic_light.get_left_time()
                        if state[1] == TrafficSignalState.PEDESTRIAN_GREEN and left_time > min(15, self.agent.config['traffic.traffic_signal.pedestrian_green_light_duration']):
                            break
                        time.sleep(self.dt)

        time.sleep(0.5)
        self.communicator.humanoid_move_forward(self.agent.id)
        while not self._walk_arrive_at_waypoint(point) and (self.exit_event is None or not self.exit_event.is_set()):
            while not self._align_direction(point) and (self.exit_event is None or not self.exit_event.is_set()):
                self.communicator.humanoid_stop(self.agent.id)
                angle, turn = self._get_angle_and_direction(point)
                if turn is not None:
                    self.communicator.humanoid_rotate(self.agent.id, angle, turn)
                time.sleep(self.dt)
            self.communicator.humanoid_move_forward(self.agent.id)
            time.sleep(self.dt)
        self.communicator.humanoid_stop(self.agent.id)
        self.sync_agent_pose()

    def _walk_arrive_at_waypoint(self, waypoint: Vector) -> bool:
        self.sync_agent_pose()
        threshold = self.agent.config['user.waypoint_distance_threshold']
        if self.agent.position.distance(waypoint) < threshold:
            self.logger.info(f'Agent {self.agent.id} Arrived at {waypoint}')
            return True
        return False

    def _get_angle_and_direction(self, waypoint: Vector) -> tuple[float, Optional[str]]:
        self.sync_agent_pose()
        to_wp = waypoint - self.agent.position
        angle = math.degrees(math.acos(np.clip(self.agent.direction.dot(to_wp.normalize()), -1, 1)))
        cross = self.agent.direction.cross(to_wp)
        turn_direction = 'left' if cross < 0 else 'right'
        if angle < 2:
            return 0.0, None
        return angle, turn_direction

    def _align_direction(self, waypoint: Vector) -> bool:
        self.sync_agent_pose()
        to_wp = waypoint - self.agent.position
        angle = math.degrees(math.acos(np.clip(self.agent.direction.dot(to_wp.normalize()), -1, 1)))
        return angle < 5
