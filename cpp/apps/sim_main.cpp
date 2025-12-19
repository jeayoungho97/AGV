#include <iostream>
#include <vector>

#include "agv_types.hpp"
#include "io.hpp"

int main() {
  Path path;
  path.frame = "map";
  path.created_ms = now_ms();
  path.waypoints = {{0.0, 0.0}, {1.0, 1.0}, {2.0, 1.5}, {3.0, 2.0}};
  path.total_cost = 3.5;

  std::cout << path_to_json(path);
  return 0;
}
