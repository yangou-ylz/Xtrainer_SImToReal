from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("session_name", default_value=""),
        Node(
            package="nova_vr_common",
            executable="logging_smoke_test",
            name="nova_vr_logging_smoke_test",
            output="screen",
            parameters=[{"session_name": LaunchConfiguration("session_name")}],
        ),
    ])
