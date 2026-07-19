cmake_minimum_required(VERSION 3.8)
project(nova_xtainer_control_description)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY urdf meshes
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
