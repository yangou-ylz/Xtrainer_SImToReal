from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    model = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_description"),
        "urdf",
        "xtrainer_control.urdf.xacro",
    ])
    controllers = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_bringup"),
        "config",
        "xtrainer_mock_controllers.yaml",
    ])
    rviz_config = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_bringup"),
        "config",
        "xtrainer_control.rviz",
    ])

    robot_description = ParameterValue(
        Command(["xacro ", LaunchConfiguration("model")]),
        value_type=str,
    )

    return LaunchDescription([
        DeclareLaunchArgument("model", default_value=model),
        DeclareLaunchArgument("controllers", default_value=controllers),
        DeclareLaunchArgument("rviz_config", default_value=rviz_config),
        DeclareLaunchArgument("session_name", default_value="session_dt4_ik_rviz"),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),
        Node(
            package="controller_manager",
            executable="ros2_control_node",
            parameters=[{"robot_description": robot_description}, LaunchConfiguration("controllers")],
            output="screen",
        ),
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=["joint_state_broadcaster", "--controller-manager", "/controller_manager"],
            output="screen",
        ),
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=["xtrainer_arm_controller", "--controller-manager", "/controller_manager"],
            output="screen",
        ),
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=["xtrainer_gripper_controller", "--controller-manager", "/controller_manager"],
            output="screen",
        ),
        Node(
            package="nova_xtainer_control_bringup",
            executable="dt2_mock_bringup_logger.py",
            name="dt4_mock_bringup_logger",
            output="screen",
            parameters=[{"session_name": LaunchConfiguration("session_name")}],
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            output="screen",
            arguments=["-d", LaunchConfiguration("rviz_config")],
        ),
    ])
