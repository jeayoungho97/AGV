#pragma once

#include <string>
#include <vector>
#include "agv_types.hpp"

// Build a simple path by visiting POIs that match item names, starting at entrance and ending at checkout if present.
Path build_path(const std::vector<Item>& items, const std::vector<Poi>& poi_list, const std::string& frame);
