cmake_minimum_required(VERSION 3.16)
project(agv_planner LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(agv_core STATIC
  src/io.cpp
  src/planner.cpp
)
target_include_directories(agv_core PUBLIC ${PROJECT_SOURCE_DIR}/include)

add_executable(sim_main apps/sim_main.cpp)
target_link_libraries(sim_main PRIVATE agv_core)

add_executable(planner_main apps/planner_main.cpp)
target_link_libraries(planner_main PRIVATE agv_core)
