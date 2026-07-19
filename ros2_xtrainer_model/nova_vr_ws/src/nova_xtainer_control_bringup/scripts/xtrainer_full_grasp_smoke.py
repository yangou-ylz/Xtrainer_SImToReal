#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass

import rclpy
from gazebo_msgs.srv import DeleteEntity, SpawnEntity
from geometry_msgs.msg import Pose, Quaternion
from nav_msgs.msg import Odometry
from rclpy.node import Node
import tf2_ros

from nova_vr_common.project_logging import ProjectLogger, create_log_session
from xtrainer_full_command14 import DEFAULT_ACTION14, FullCommand14Publisher


ROOT_FRAME = "xtrainer_full_control_root"
LEFT_FINGER_LINKS = ("J1_7_link", "J1_8_link")
LEFT_FINGER_COLLISION_CENTERS = (
    (0.0240000616, 0.0198703241, 0.012462504),
    (0.0239999377, -0.0198703241, 0.012462504),
)


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, value: float) -> "Vec3":
        return Vec3(self.x * value, self.y * value, self.z * value)

    def norm(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def quat_rotate(q: Quaternion, p: Vec3) -> Vec3:
    # Quaternion-vector rotation: q * p * q^-1.
    w, x, y, z = q.w, q.x, q.y, q.z
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-12:
        return p
    w, x, y, z = w / n, x / n, y / n, z / n
    tx = 2.0 * (y * p.z - z * p.y)
    ty = 2.0 * (z * p.x - x * p.z)
    tz = 2.0 * (x * p.y - y * p.x)
    return Vec3(
        p.x + w * tx + (y * tz - z * ty),
        p.y + w * ty + (z * tx - x * tz),
        p.z + w * tz + (x * ty - y * tx),
    )


def pose_position(pose: Pose) -> Vec3:
    return Vec3(pose.position.x, pose.position.y, pose.position.z)


def transform_point(pose: Pose, local: tuple[float, float, float]) -> Vec3:
    return pose_position(pose) + quat_rotate(pose.orientation, Vec3(*local))


class GazeboGraspSmoke(Node):
    def __init__(self, session_name: str) -> None:
        super().__init__("xtrainer_full_grasp_smoke")
        self.session = create_log_session(session_name=session_name)
        self.project_logger = ProjectLogger(self.get_logger(), self.session)
        self.spawn_client = self.create_client(SpawnEntity, "/spawn_entity")
        self.delete_client = self.create_client(DeleteEntity, "/delete_entity")
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.object_pose: Pose | None = None
        self.object_topic = "/xtrainer_grasp_block/pose"
        self.create_subscription(Odometry, self.object_topic, self._on_object_odom, 10)
        self.commander = FullCommand14Publisher(session_name=f"{session_name}_command")

    def _on_object_odom(self, msg: Odometry) -> None:
        self.object_pose = msg.pose.pose

    def wait_for_services(self) -> None:
        for name, client in (
            ("spawn_entity", self.spawn_client),
            ("delete_entity", self.delete_client),
        ):
            if not client.wait_for_service(timeout_sec=20.0):
                raise RuntimeError(f"Gazebo service not available: {name}")

    def call(self, client, request):
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if future.result() is None:
            raise RuntimeError(f"service call failed: {future.exception()}")
        return future.result()

    def sleep_spin(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def wait_for_tf(self, frames: tuple[str, ...], timeout_sec: float = 10.0) -> None:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if all(self.tf_buffer.can_transform(ROOT_FRAME, frame, rclpy.time.Time()) for frame in frames):
                return
        frames_yaml = self.tf_buffer.all_frames_as_yaml()
        raise RuntimeError(f"TF missing {frames}; available={frames_yaml[:1200]}")

    def get_tf_pose(self, frame: str) -> Pose:
        self.wait_for_tf((frame,))
        transform = self.tf_buffer.lookup_transform(ROOT_FRAME, frame, rclpy.time.Time())
        pose = Pose()
        pose.position.x = transform.transform.translation.x
        pose.position.y = transform.transform.translation.y
        pose.position.z = transform.transform.translation.z
        pose.orientation = transform.transform.rotation
        return pose

    def get_object_pose(self) -> Pose:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self.object_pose is not None:
                return self.object_pose
        raise RuntimeError(f"object odometry not received on {self.object_topic}")

    def finger_centers(self) -> tuple[Vec3, Vec3, float, Vec3]:
        self.wait_for_tf(LEFT_FINGER_LINKS)
        poses = [self.get_tf_pose(name) for name in LEFT_FINGER_LINKS]
        centers = tuple(transform_point(pose, local) for pose, local in zip(poses, LEFT_FINGER_COLLISION_CENTERS))
        gap = (centers[0] - centers[1]).norm()
        mid = (centers[0] + centers[1]) * 0.5
        return centers[0], centers[1], gap, mid

    def send_gripper(self, grip: float, duration: float = 0.5) -> None:
        cmd = list(DEFAULT_ACTION14)
        cmd[6] = float(grip)
        cmd[13] = 0.0
        self.commander.publish_action14(cmd, duration=duration)

    def send_arm_shift(self, grip: float, delta_j2: float, duration: float = 1.0) -> None:
        cmd = list(DEFAULT_ACTION14)
        cmd[1] += float(delta_j2)
        cmd[6] = float(grip)
        cmd[13] = 0.0
        self.commander.publish_action14(cmd, duration=duration)

    def delete_object(self, name: str) -> None:
        req = DeleteEntity.Request()
        req.name = name
        self.call(self.delete_client, req)

    def spawn_box(self, name: str, center: Vec3, size: float) -> None:
        sdf = f"""<?xml version='1.0'?>
<sdf version='1.6'>
  <model name='{name}'>
    <pose>0 0 0 0 0 0</pose>
    <link name='body'>
      <gravity>false</gravity>
      <inertial>
        <mass>0.015</mass>
        <inertia>
          <ixx>1e-5</ixx><iyy>1e-5</iyy><izz>1e-5</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <collision name='collision'>
        <geometry><box><size>{size:.5f} {size:.5f} {size:.5f}</size></box></geometry>
        <surface>
          <friction><ode><mu>8.0</mu><mu2>8.0</mu2></ode></friction>
          <contact><ode><kp>1000000</kp><kd>20</kd></ode></contact>
        </surface>
      </collision>
      <visual name='visual'>
        <geometry><box><size>{size:.5f} {size:.5f} {size:.5f}</size></box></geometry>
        <material><ambient>0.9 0.2 0.1 1</ambient><diffuse>0.9 0.2 0.1 1</diffuse></material>
      </visual>
    </link>
    <plugin name='pose_publisher' filename='libgazebo_ros_p3d.so'>
      <ros>
        <namespace>/xtrainer_grasp_block</namespace>
        <remapping>odom:=pose</remapping>
      </ros>
      <body_name>body</body_name>
      <frame_name>world</frame_name>
      <update_rate>50</update_rate>
      <xyz_offset>0 0 0</xyz_offset>
      <rpy_offset>0 0 0</rpy_offset>
      <gaussian_noise>0</gaussian_noise>
    </plugin>
  </model>
</sdf>"""
        req = SpawnEntity.Request()
        req.name = name
        req.xml = sdf
        req.initial_pose.position.x = center.x
        req.initial_pose.position.y = center.y
        req.initial_pose.position.z = center.z
        req.initial_pose.orientation.w = 1.0
        req.reference_frame = "world"
        res = self.call(self.spawn_client, req)
        if not res.success:
            raise RuntimeError(f"failed to spawn {name}: {res.status_message}")
        self.object_pose = None

    def run(self, object_name: str, min_follow_distance: float) -> bool:
        self.wait_for_services()
        try:
            self.delete_object(object_name)
        except Exception:
            pass

        self.send_gripper(0.0, duration=0.6)
        self.sleep_spin(1.2)
        _, _, open_gap, open_mid = self.finger_centers()
        self.project_logger.info("adapter", f"open_gap={open_gap:.5f} open_mid={open_mid.as_tuple()}")

        self.send_gripper(1.0, duration=0.6)
        self.sleep_spin(1.2)
        _, _, closed_gap, closed_mid_probe = self.finger_centers()
        self.project_logger.info(
            "adapter",
            f"closed_gap_without_object={closed_gap:.5f} closed_mid_probe={closed_mid_probe.as_tuple()}",
        )
        object_size = max(0.010, min(0.020, abs(open_gap - closed_gap) + 0.006))
        spawn_center = closed_mid_probe
        self.spawn_box(object_name, spawn_center, object_size)
        self.project_logger.info(
            "adapter",
            f"spawned object={object_name} size={object_size:.5f} requested_pose={spawn_center.as_tuple()} "
            "while_gripper_closed=true",
        )
        self.sleep_spin(0.5)
        _, _, closed_gap_object, closed_mid = self.finger_centers()
        object_clamped = pose_position(self.get_object_pose())
        dist_to_mid = (object_clamped - closed_mid).norm()
        self.project_logger.info(
            "adapter",
            f"after_close gap={closed_gap_object:.5f} closed_mid={closed_mid.as_tuple()} "
            f"object={object_clamped.as_tuple()} dist_to_mid={dist_to_mid:.5f}",
        )

        self.send_arm_shift(1.0, delta_j2=0.10, duration=0.8)
        self.sleep_spin(1.2)
        _, _, moved_gap, moved_mid = self.finger_centers()
        object_after = pose_position(self.get_object_pose())
        object_motion = (object_after - object_clamped).norm()
        dist_after = (object_after - moved_mid).norm()
        self.project_logger.info(
            "adapter",
            f"after_arm_shift gap={moved_gap:.5f} object={object_after.as_tuple()} "
            f"object_motion={object_motion:.5f} dist_to_mid={dist_after:.5f}",
        )
        success = object_motion >= min_follow_distance and dist_after <= max(0.08, object_size * 3.0)
        if success:
            self.project_logger.info("safety", "grasp_smoke_result=PASS")
        else:
            self.project_logger.error("safety", "grasp_smoke_result=FAIL")
        return success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gazebo smoke test for full X-Trainer gripper-object contact.")
    parser.add_argument("--session-name", default="session_full_control_grasp")
    parser.add_argument("--object-name", default="xtrainer_grasp_block")
    parser.add_argument("--min-follow-distance", type=float, default=0.006)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = GazeboGraspSmoke(args.session_name)
    try:
        ok = node.run(args.object_name, args.min_follow_distance)
        raise SystemExit(0 if ok else 2)
    finally:
        node.commander.destroy_node()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
