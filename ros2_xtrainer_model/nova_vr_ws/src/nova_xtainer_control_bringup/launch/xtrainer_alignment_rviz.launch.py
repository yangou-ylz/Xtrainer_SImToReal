from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    reference_model = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_description"),
        "urdf",
        "generated",
        "xtrainer_full_visual.urdf.xacro",
    ])
    control_model = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_description"),
        "urdf",
        "xtrainer_control.urdf.xacro",
    ])
    initial_joints = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_bringup"),
        "config",
        "xtrainer_alignment_initial_joints.yaml",
    ])
    rviz_config = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_bringup"),
        "config",
        "xtrainer_alignment.rviz",
    ])

    reference_description = ParameterValue(
        Command(["xacro ", LaunchConfiguration("reference_model")]),
        value_type=str,
    )
    control_description = ParameterValue(
        Command(["xacro ", LaunchConfiguration("control_model")]),
        value_type=str,
    )

    return LaunchDescription([
        DeclareLaunchArgument("reference_model", default_value=reference_model),
        DeclareLaunchArgument("control_model", default_value=control_model),
        DeclareLaunchArgument("initial_joints", default_value=initial_joints),
        DeclareLaunchArgument("rviz_config", default_value=rviz_config),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            namespace="xtrainer_reference",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": reference_description}],
        ),
        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            namespace="xtrainer_control",
            name="xtrainer_control_joint_state_publisher",
            output="screen",
            parameters=[
                {"robot_description": control_description},
                LaunchConfiguration("initial_joints"),
            ],
        ),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            namespace="xtrainer_control",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": control_description}],
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="xtrainer_control_root_to_reference",
            output="screen",
            arguments=[
                "--x", "0",
                "--y", "0",
                "--z", "0",
                "--roll", "0",
                "--pitch", "0",
                "--yaw", "0",
                "--frame-id", "xtrainer_root",
                "--child-frame-id", "xtrainer_control_root",
            ],
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            output="screen",
            arguments=["-d", LaunchConfiguration("rviz_config")],
        ),
    ])
