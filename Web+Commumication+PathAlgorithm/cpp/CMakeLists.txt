cmake_minimum_required(VERSION 3.16)
project(agv_planner LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(agv_core STATIC
  src/io.cpp
  src/planner.cpp
)
target_include_directories(agv_core PUBLIC ${PROJECT_SOURCE_DIR}/include)

# Optional MQTT planner node (requires libmosquitto).
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(MOSQUITTO QUIET libmosquitto)
endif()

if(MOSQUITTO_FOUND)
  find_package(nlohmann_json CONFIG REQUIRED)
  add_executable(planner_mqtt_main apps/planner_mqtt_main.cpp)
  target_include_directories(planner_mqtt_main PRIVATE ${MOSQUITTO_INCLUDE_DIRS})
  target_link_directories(planner_mqtt_main PRIVATE ${MOSQUITTO_LIBRARY_DIRS})
  target_link_libraries(planner_mqtt_main PRIVATE agv_core ${MOSQUITTO_LIBRARIES} nlohmann_json::nlohmann_json)
  target_compile_options(planner_mqtt_main PRIVATE ${MOSQUITTO_CFLAGS_OTHER})
endif()

add_executable(sim_main apps/sim_main.cpp)
target_link_libraries(sim_main PRIVATE agv_core)

add_executable(planner_main apps/planner_main.cpp)
target_link_libraries(planner_main PRIVATE agv_core)
