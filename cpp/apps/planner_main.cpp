#include <filesystem>
#include <iostream>
#include <string>

#include "io.hpp"
#include "planner.hpp"

int main(int argc, char* argv[]) {
  std::string items_path = argc > 1 ? argv[1] : "data/samples/items_example.json";
  std::string poi_path = argc > 2 ? argv[2] : "data/poi/store_A_poi.json";
  std::string frame = "map";

  try {
    const auto items = parse_items_file(items_path);
    const auto poi = parse_poi_file(poi_path);
    const Path path = build_path(items, poi, frame);
    std::cout << path_to_json(path);
  } catch (const std::exception& e) {
    std::cerr << "[planner_main] error: " << e.what() << std::endl;
    std::cerr << "Usage: planner_main [items.json] [poi.json]" << std::endl;
    return 1;
  }

  return 0;
}
