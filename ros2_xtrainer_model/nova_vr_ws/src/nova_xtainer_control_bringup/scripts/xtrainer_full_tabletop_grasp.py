#!/usr/bin/env python3
from __future__ import annotations

import argparse

import rclpy
from gazebo_msgs.msg import ContactsState
from gazebo_msgs.srv import SpawnEntity

from xtrainer_full_grasp_smoke import GazeboGraspSmoke, Vec3, pose_position


class GazeboTabletopGrasp(GazeboGraspSmoke):
    def __init__(self, session_name: str) -> None:
        super().__init__(session_name)
        self.contact_pairs: set[tuple[str, str]] = set()
        self.contact_samples = 0
        self.create_subscription(ContactsState, "/xtrainer_grasp_block/contacts", self._on_contacts, 10)

    def _on_contacts(self, msg: ContactsState) -> None:
        if msg.states:
            self.contact_samples += 1
        for state in msg.states:
            self.contact_pairs.add((state.collision1_name, state.collision2_name))

    def contact_summary(self) -> str:
        pairs = sorted(f"{a}<->{b}" for a, b in self.contact_pairs)
        preview = "; ".join(pairs[:8])
        if len(pairs) > 8:
            preview += f"; ...(+{len(pairs) - 8})"
        return f"samples={self.contact_samples} pairs={len(pairs)} [{preview}]"

    def spawn_static_support(self, name: str, center: Vec3, size: tuple[float, float, float]) -> None:
        sx, sy, sz = size
        sdf = f"""<?xml version='1.0'?>
<sdf version='1.6'>
  <model name='{name}'>
    <static>true</static>
    <link name='body'>
      <collision name='collision'>
        <geometry><box><size>{sx:.5f} {sy:.5f} {sz:.5f}</size></box></geometry>
        <surface>
          <friction><ode><mu>0.08</mu><mu2>0.08</mu2></ode></friction>
          <contact><ode><kp>1000000</kp><kd>10</kd></ode></contact>
        </surface>
      </collision>
      <visual name='visual'>
        <geometry><box><size>{sx:.5f} {sy:.5f} {sz:.5f}</size></box></geometry>
        <material><ambient>0.1 0.35 0.9 1</ambient><diffuse>0.1 0.35 0.9 1</diffuse></material>
      </visual>
    </link>
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

    def spawn_gravity_box(self, name: str, center: Vec3, size: float, mass: float) -> None:
        sdf = f"""<?xml version='1.0'?>
<sdf version='1.6'>
  <model name='{name}'>
    <link name='body'>
      <gravity>true</gravity>
      <inertial>
        <mass>{mass:.6f}</mass>
        <inertia>
          <ixx>1e-5</ixx><iyy>1e-5</iyy><izz>1e-5</izz>
          <ixy>0</ixy><ixz>0</ixz><iyz>0</iyz>
        </inertia>
      </inertial>
      <collision name='collision'>
        <geometry><box><size>{size:.5f} {size:.5f} {size:.5f}</size></box></geometry>
        <max_contacts>20</max_contacts>
        <surface>
          <friction><ode><mu>12.0</mu><mu2>12.0</mu2></ode></friction>
          <contact><ode><kp>1000000</kp><kd>20</kd></ode></contact>
        </surface>
      </collision>
      <sensor name='contact_sensor' type='contact'>
        <always_on>true</always_on>
        <update_rate>100</update_rate>
        <contact>
          <collision>collision</collision>
        </contact>
        <plugin name='bumper' filename='libgazebo_ros_bumper.so'>
          <ros>
            <namespace>/xtrainer_grasp_block</namespace>
            <remapping>bumper_states:=contacts</remapping>
          </ros>
          <frame_name>world</frame_name>
        </plugin>
      </sensor>
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

    def run_tabletop(
        self,
        object_name: str,
        support_name: str,
        object_size: float,
        object_mass: float,
        support_xy: float,
        support_z: float,
        close_grip: float | None,
        min_motion: float,
        max_follow_distance: float,
    ) -> bool:
        self.wait_for_services()
        for name in (object_name, support_name):
            try:
                self.delete_object(name)
            except Exception:
                pass

        self.send_gripper(0.0, duration=0.6)
        self.sleep_spin(1.2)
        _, _, open_gap, open_mid = self.finger_centers()
        if close_grip is None:
            # Finger-center gap is roughly 0.10 - 0.08 * grip. Avoid forcing
            # full close on wider tabletop objects; a small preload is enough
            # to verify contact without launching the object.
            target_gap = max(0.021, object_size * 0.92)
            close_grip = max(0.0, min(1.0, (open_gap - target_gap) / 0.08))
        close_grip = max(0.0, min(1.0, float(close_grip)))

        support_size = (support_xy, support_xy, support_z)
        support_center = Vec3(open_mid.x, open_mid.y, open_mid.z - object_size * 0.5 - support_size[2] * 0.5)
        object_center = Vec3(open_mid.x, open_mid.y, support_center.z + support_size[2] * 0.5 + object_size * 0.5 + 0.002)
        self.spawn_static_support(support_name, support_center, support_size)
        self.spawn_gravity_box(object_name, object_center, object_size, object_mass)
        self.project_logger.info(
            "adapter",
            f"tabletop_spawn open_gap={open_gap:.5f} support={support_center.as_tuple()} "
            f"object_request={object_center.as_tuple()} object_size={object_size:.5f} mass={object_mass:.5f}",
        )
        self.project_logger.info("adapter", f"tabletop_close_grip={close_grip:.4f}")

        self.sleep_spin(1.0)
        object_settled = pose_position(self.get_object_pose())
        settle_error = (object_settled - object_center).norm()
        self.project_logger.info(
            "adapter",
            f"tabletop_after_settle object={object_settled.as_tuple()} settle_error={settle_error:.5f}",
        )
        if object_settled.z < support_center.z:
            self.project_logger.error("safety", "tabletop_grasp_result=FAIL reason=object_fell_before_grasp")
            return False

        self.send_gripper(close_grip, duration=1.4)
        self.sleep_spin(1.6)
        _, _, closed_gap, closed_mid = self.finger_centers()
        object_after_close = pose_position(self.get_object_pose())
        close_dist = (object_after_close - closed_mid).norm()
        self.project_logger.info(
            "adapter",
            f"tabletop_after_close closed_gap={closed_gap:.5f} closed_mid={closed_mid.as_tuple()} "
            f"object={object_after_close.as_tuple()} dist_to_mid={close_dist:.5f} "
            f"contacts={self.contact_summary()}",
        )

        self.send_arm_shift(close_grip, delta_j2=0.12, duration=0.9)
        self.sleep_spin(1.4)
        _, _, moved_gap, moved_mid = self.finger_centers()
        object_after_move = pose_position(self.get_object_pose())
        object_motion = (object_after_move - object_after_close).norm()
        follow_dist = (object_after_move - moved_mid).norm()
        fell_after_move = object_after_move.z < support_center.z
        self.project_logger.info(
            "adapter",
            f"tabletop_after_arm_shift moved_gap={moved_gap:.5f} moved_mid={moved_mid.as_tuple()} "
            f"object={object_after_move.as_tuple()} object_motion={object_motion:.5f} "
            f"follow_dist={follow_dist:.5f} fell_after_move={fell_after_move} "
            f"contacts={self.contact_summary()}",
        )
        success = object_motion >= min_motion and follow_dist <= max_follow_distance and not fell_after_move
        if success:
            self.project_logger.info("safety", "tabletop_grasp_result=PASS")
        else:
            self.project_logger.error("safety", "tabletop_grasp_result=FAIL")
        return success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gazebo gravity/tabletop grasp test for full X-Trainer.")
    parser.add_argument("--session-name", default="session_full_control_tabletop_grasp")
    parser.add_argument("--object-name", default="xtrainer_grasp_block")
    parser.add_argument("--support-name", default="xtrainer_grasp_support")
    parser.add_argument("--object-size", type=float, default=0.030)
    parser.add_argument("--object-mass", type=float, default=0.010)
    parser.add_argument("--support-xy", type=float, default=0.024)
    parser.add_argument("--support-z", type=float, default=0.010)
    parser.add_argument("--close-grip", type=float, default=None)
    parser.add_argument("--min-motion", type=float, default=0.018)
    parser.add_argument("--max-follow-distance", type=float, default=0.095)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = GazeboTabletopGrasp(args.session_name)
    try:
        ok = node.run_tabletop(
            object_name=args.object_name,
            support_name=args.support_name,
            object_size=args.object_size,
            object_mass=args.object_mass,
            support_xy=args.support_xy,
            support_z=args.support_z,
            close_grip=args.close_grip,
            min_motion=args.min_motion,
            max_follow_distance=args.max_follow_distance,
        )
        raise SystemExit(0 if ok else 2)
    finally:
        node.commander.destroy_node()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
