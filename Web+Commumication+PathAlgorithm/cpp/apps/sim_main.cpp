#include <iostream>
#include <vector>

#include "planner.hpp"
#include "io.hpp"

int main() {
  // 샘플 입력(파일 로드 없이 하드코딩)
  std::vector<Item> items = {{"coke", 1}, {"ramen", 2}};

  // poi_list는 실제로 io.cpp에서 로드하는 게 좋지만, sim에선 하드코딩 OK
  std::vector<Poi> pois = {
      {"entrance", 0.0, 0.0},
      {"coke", 5.0, 1.0},
      {"ramen", 8.0, 4.0},
      {"checkout", 2.0, 6.0},
  };

  Path path = build_path(items, pois, "map");
  std::cout << path_to_json(path) << "\n";
  return 0;
}
