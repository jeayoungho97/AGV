#include "planner.hpp"

#include <cmath>
#include <stdexcept>
#include <unordered_map>

#include "io.hpp"

namespace {
double distance(const Poi& a, const Poi& b) {
  const double dx = a.x - b.x;
  const double dy = a.y - b.y;
  return std::hypot(dx, dy);
}

Poi find_poi(const std::unordered_map<std::string, Poi>& poi_map, const std::string& id) {
  auto it = poi_map.find(id);
  if (it == poi_map.end()) {
    throw std::runtime_error("POI not found: " + id);
  }
  return it->second;
}
}

Path build_path(const std::vector<Item>& items, const std::vector<Poi>& poi_list, const std::string& frame) {
  std::unordered_map<std::string, Poi> poi_map;
  for (const auto& p : poi_list) {
    poi_map[p.id] = p;
  }

  Path path;
  path.frame = frame;
  path.created_ms = unix_ms();

  // Start at entrance if present.
  Poi current = poi_map.count("entrance") ? poi_map["entrance"] : Poi{"start", 0.0, 0.0};
  path.waypoints.push_back({current.x, current.y});

  for (const auto& item : items) {
    const Poi target = find_poi(poi_map, item.name);
    path.total_cost += distance(current, target);
    path.waypoints.push_back({target.x, target.y});
    current = target;
  }

  // End at checkout if available.
  if (poi_map.count("checkout")) {
    const Poi checkout = poi_map["checkout"];
    path.total_cost += distance(current, checkout);
    path.waypoints.push_back({checkout.x, checkout.y});
  }

  return path;
}
