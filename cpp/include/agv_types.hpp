#pragma once

#include <string>
#include <vector>

struct Item {
  std::string name;
  int qty{};
};

struct Poi {
  std::string id;
  double x{};
  double y{};
};

struct Waypoint {
  double x{};
  double y{};
};

struct Path {
  std::string frame;
  std::vector<Waypoint> waypoints;
  double total_cost{};
  long long created_ms{};
};
