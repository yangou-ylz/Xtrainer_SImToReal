cmake_minimum_required(VERSION 3.8)
project(nova_xtainer_control_bringup)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS
    scripts/dt2_mock_bringup_logger.py
    scripts/send_dt2_mock_command.py
    scripts/send_dt4_right_ik_target.py
    scripts/send_dt5_dual_ik_command.py
    scripts/send_dt7_command14.py
    scripts/xtrainer_full_action_slider.py
    scripts/xtrainer_full_command14.py
    scripts/xtrainer_full_grasp_smoke.py
    scripts/xtrainer_full_tabletop_grasp.py
    scripts/validate_full_control_action14.sh
    scripts/validate_full_control_gazebo.sh
    scripts/validate_full_control_grasp.sh
    scripts/validate_full_control_tabletop_grasp.sh
    scripts/validate_dt6_gazebo_control.sh
    scripts/validate_dt4_to_dt7.sh
  DESTINATION lib/${PROJECT_NAME}
)

install(
  FILES
    scripts/xtrainer_backend.py
    scripts/xtrainer_kinematics.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
