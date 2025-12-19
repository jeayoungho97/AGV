#include <mosquitto.h>

#include <atomic>
#include <csignal>
#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>

#include "io.hpp"
#include "planner.hpp"

namespace {
std::atomic<bool> g_should_exit{false};

void on_signal(int) { g_should_exit.store(true); }

std::string read_all(const std::string& path) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("Failed to open file: " + path);
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

std::string json_get_string(const std::string& json, const std::string& key, const std::string& default_value) {
  std::regex re("\\\"" + key + "\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");
  std::smatch m;
  if (std::regex_search(json, m, re)) return m[1].str();
  return default_value;
}

int json_get_int(const std::string& json, const std::string& key, int default_value) {
  std::regex re("\\\"" + key + "\\\"\\s*:\\s*(\\d+)");
  std::smatch m;
  if (std::regex_search(json, m, re)) return std::stoi(m[1].str());
  return default_value;
}

std::string json_get_topic(const std::string& json, const std::string& topic_key, const std::string& default_value) {
  // crude nested lookup: "topics": { "items": "..." }
  std::regex re("\\\"topics\\\"\\s*:\\s*\\{[^}]*\\\"" + topic_key + "\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"");
  std::smatch m;
  if (std::regex_search(json, m, re)) return m[1].str();
  return default_value;
}

struct Runtime {
  std::string items_topic;
  std::string path_topic;
  std::string frame;
  std::vector<Poi> poi;
  int qos{1};
};

void on_message(struct mosquitto* mosq, void* userdata, const struct mosquitto_message* msg) {
  auto* rt = static_cast<Runtime*>(userdata);
  if (!rt || !msg || !msg->payload || msg->payloadlen <= 0) return;

  try {
    const std::string payload(static_cast<const char*>(msg->payload), static_cast<size_t>(msg->payloadlen));
    const auto items = parse_items_json(payload);
    const Path path = build_path(items, rt->poi, rt->frame);
    const std::string out = path_to_json(path);
    mosquitto_publish(mosq, nullptr, rt->path_topic.c_str(), static_cast<int>(out.size()), out.c_str(), rt->qos, false);
    std::cerr << "[planner_mqtt] published global_path (" << rt->path_topic << ")" << std::endl;
  } catch (const std::exception& e) {
    std::cerr << "[planner_mqtt] failed to handle message: " << e.what() << std::endl;
  }
}
}

int main(int argc, char* argv[]) {
  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);

  const std::string mqtt_config_path = argc > 1 ? argv[1] : "config/dev/mqtt.json";
  const std::string planner_config_path = argc > 2 ? argv[2] : "config/dev/planner.json";

  try {
    const std::string mqtt_cfg = read_all(mqtt_config_path);
    const std::string planner_cfg = read_all(planner_config_path);

    const std::string broker = json_get_string(mqtt_cfg, "broker", "localhost");
    const int port = json_get_int(mqtt_cfg, "port", 1883);

    Runtime rt;
    rt.items_topic = json_get_topic(mqtt_cfg, "items", "agv/ai/items");
    rt.path_topic = json_get_topic(mqtt_cfg, "global_path", "agv/planner/global_path");
    rt.frame = json_get_string(planner_cfg, "frame", "map");
    const std::string poi_file = json_get_string(planner_cfg, "map_file", "data/poi/store_A_poi.json");
    rt.poi = parse_poi_file(poi_file);

    mosquitto_lib_init();
    mosquitto* mosq = mosquitto_new(nullptr, true, &rt);
    if (!mosq) throw std::runtime_error("mosquitto_new failed");

    mosquitto_message_callback_set(mosq, on_message);

    const int rc_conn = mosquitto_connect(mosq, broker.c_str(), port, 60);
    if (rc_conn != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error(std::string("mosquitto_connect failed: ") + mosquitto_strerror(rc_conn));
    }

    const int rc_sub = mosquitto_subscribe(mosq, nullptr, rt.items_topic.c_str(), rt.qos);
    if (rc_sub != MOSQ_ERR_SUCCESS) {
      throw std::runtime_error(std::string("mosquitto_subscribe failed: ") + mosquitto_strerror(rc_sub));
    }

    std::cerr << "[planner_mqtt] connected to " << broker << ":" << port << "\n";
    std::cerr << "[planner_mqtt] subscribed: " << rt.items_topic << " -> publishes: " << rt.path_topic << "\n";

    while (!g_should_exit.load()) {
      const int rc_loop = mosquitto_loop(mosq, 200 /*ms*/, 1);
      if (rc_loop != MOSQ_ERR_SUCCESS) {
        std::cerr << "[planner_mqtt] loop error: " << mosquitto_strerror(rc_loop) << ", retrying..." << std::endl;
        mosquitto_reconnect(mosq);
      }
    }

    mosquitto_disconnect(mosq);
    mosquitto_destroy(mosq);
    mosquitto_lib_cleanup();
  } catch (const std::exception& e) {
    std::cerr << "[planner_mqtt] error: " << e.what() << std::endl;
    std::cerr << "Usage: planner_mqtt_main [config/dev/mqtt.json] [config/dev/planner.json]" << std::endl;
    return 1;
  }

  return 0;
}
