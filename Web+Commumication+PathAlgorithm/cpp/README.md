# C++ Nodes

Minimal planner simulation with header-only data types and a simple POI-based planner.

## Build
```bash
cd cpp
cmake -S . -B build
cmake --build build
```

## Run
```bash
./build/sim_main
./build/planner_main ../data/samples/items_example.json ../data/poi/store_A_poi.json
```
`planner_main` parses items/POI JSON using a lightweight regex parser and outputs a JSON path (entrance -> item POIs -> checkout). Wire in MQTT and a full planner as you extend the project.
