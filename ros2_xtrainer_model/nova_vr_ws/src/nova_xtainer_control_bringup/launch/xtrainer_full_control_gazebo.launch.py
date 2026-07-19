from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
import os


def generate_launch_description():
    model = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_description"),
        "urdf",
        "generated",
        "xtrainer_full_control.urdf.xacro",
    ])
    rviz_config = PathJoinSubstitution([
        FindPackageShare("nova_xtainer_control_bringup"),
        "config",
        "xtrainer_full_control.rviz",
    ])

    robot_description = ParameterValue(
        Command([
            "xacro ",
            LaunchConfiguration("model"),
            " hardware_plugin:=gazebo_ros2_control/GazeboSystem",
        ]),
        value_type=str,
    )

    gazebo_home = os.path.join(os.environ.get("NOVA_VR_WS", os.getcwd()), "logs", "gazebo_home")
    os.makedirs(gazebo_home, exist_ok=True)
    gazebo_env = {
        "HOME": gazebo_home,
        "GAZEBO_MODEL_DATABASE_URI": "",
        "GAZEBO_MODEL_PATH": "/usr/share/gazebo-11/models",
        "GAZEBO_RESOURCE_PATH": "/usr/share/gazebo-11",
        "GAZEBO_PLUGIN_PATH": "/usr/lib/x86_64-linux-gnu/gazebo-11/plugins:/opt/ros/humble/lib",
        "GAZEBO_MASTER_URI": LaunchConfiguration("gazebo_master_uri"),
        "GAZEBO_IP": "127.0.0.1",
    }

    return LaunchDescription([
        DeclareLaunchArgument("model", default_value=model),
        DeclareLaunchArgument("gui", default_value="true"),
        DeclareLaunchArgument("rviz", default_value="true"),
        DeclareLaunchArgument("gazebo_master_uri", default_value="http://127.0.0.1:11347"),
        ExecuteProcess(
            cmd=[
                "gzserver",
                "/opt/ros/humble/share/gazebo_ros/worlds/empty.world",
                "-s",
                "/opt/ros/humble/lib/libgazebo_ros_init.so",
                "-s",
                "/opt/ros/humble/lib/libgazebo_ros_factory.so",
                "-s",
                "/opt/ros/humble/lib/libgazebo_ros_force_system.so",
            ],
            output="screen",
            additional_env=gazebo_env,
        ),
        ExecuteProcess(
            cmd=["gzclient", "--gui-client-plugin=/opt/ros/humble/lib/libgazebo_ros_eol_gui.so"],
            output="screen",
            additional_env=gazebo_env,
            condition=IfCondition(LaunchConfiguration("gui")),
        ),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),
        Node(
            package="gazebo_ros",
            executable="spawn_entity.py",
            arguments=["-topic", "robot_description", "-entity", "xtrainer_full_control"],
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
            arguments=["xtrainer_full_joint_controller", "--controller-manager", "/controller_manager"],
            output="screen",
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            output="screen",
            arguments=["-d", rviz_config],
            condition=IfCondition(LaunchConfiguration("rviz")),
        ),
    ])
