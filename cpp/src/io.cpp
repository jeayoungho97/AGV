#include "io.hpp"

#include <chrono>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace {
std::string read_all(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("Failed to open file: " + path);
  }
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}
}

std::vector<Item> parse_items_file(const std::string& path) {
  std::vector<Item> items;
  const std::string content = read_all(path);
  std::regex item_regex(R"(\{\s*\"name\"\s*:\s*\"([^\"]+)\"\s*,\s*\"qty\"\s*:\s*(\d+))");
  auto begin = std::sregex_iterator(content.begin(), content.end(), item_regex);
  auto end = std::sregex_iterator();
  for (auto it = begin; it != end; ++it) {
    Item item;
    item.name = (*it)[1].str();
    item.qty = std::stoi((*it)[2].str());
    items.push_back(item);
  }
  if (items.empty()) {
    throw std::runtime_error("No items parsed from: " + path);
  }
  return items;
}

std::vector<Poi> parse_poi_file(const std::string& path) {
  std::vector<Poi> poi;
  const std::string content = read_all(path);
  std::regex poi_regex(R"(\{\s*\"id\"\s*:\s*\"([^\"]+)\"\s*,\s*\"x\"\s*:\s*([-+]?\d*\.?\d+)\s*,\s*\"y\"\s*:\s*([-+]?\d*\.?\d+))");
  auto begin = std::sregex_iterator(content.begin(), content.end(), poi_regex);
  auto end = std::sregex_iterator();
  for (auto it = begin; it != end; ++it) {
    Poi p;
    p.id = (*it)[1].str();
    p.x = std::stod((*it)[2].str());
    p.y = std::stod((*it)[3].str());
    poi.push_back(p);
  }
  if (poi.empty()) {
    throw std::runtime_error("No POIs parsed from: " + path);
  }
  return poi;
}

std::string path_to_json(const Path& path) {
  std::ostringstream ss;
  ss << "{\n";
  ss << "  \"frame\": \"" << path.frame << "\",\n";
  ss << "  \"waypoints\": [\n";
  for (size_t i = 0; i < path.waypoints.size(); ++i) {
    const auto& wp = path.waypoints[i];
    ss << "    { \"x\": " << wp.x << ", \"y\": " << wp.y << " }";
    if (i + 1 != path.waypoints.size()) ss << ",";
    ss << "\n";
  }
  ss << "  ],\n";
  ss << "  \"total_cost\": " << path.total_cost << ",\n";
  ss << "  \"created_ms\": " << path.created_ms << "\n";
  ss << "}\n";
  return ss.str();
}

long long now_ms() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}
