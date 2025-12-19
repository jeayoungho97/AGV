#pragma once

#include <string>
#include <vector>
#include "agv_types.hpp"

std::vector<Item> parse_items_file(const std::string& path);
std::vector<Poi> parse_poi_file(const std::string& path);
std::string path_to_json(const Path& path);
long long now_ms();
