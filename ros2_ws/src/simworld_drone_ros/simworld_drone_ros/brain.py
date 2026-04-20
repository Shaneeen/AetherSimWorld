import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String


class Brain(Node):
    def __init__(self) -> None:
        super().__init__("brain")

        self.cmd_pub = self.create_publisher(Twist, "/drone/cmd_vel", 10)

        self.pose_sub = self.create_subscription(
            PoseStamped,
            "/drone/pose",
            self.pose_callback,
            10,
        )

        self.status_sub = self.create_subscription(
            String,
            "/drone/status",
            self.status_callback,
            10,
        )

        self.current_x = 0.0
        self.mode = "forward"

        self.timer = self.create_timer(0.1, self.control_loop)

    def pose_callback(self, msg: PoseStamped) -> None:
        self.current_x = msg.pose.position.x

    def status_callback(self, msg: String) -> None:
        self.get_logger().info(f"Bridge status: {msg.data}")

    def control_loop(self) -> None:
        cmd = Twist()

        # Very simple demo brain:
        # move forward until x > 10, then turn
        if self.mode == "forward":
            cmd.linear.x = 2.0
            if self.current_x > 10.0:
                self.mode = "turn"
        elif self.mode == "turn":
            cmd.angular.z = 1.0

        self.cmd_pub.publish(cmd)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Brain()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()