# Pinned public navigation sources

`SOURCES.json` records the immutable upstream revision, URL, byte count and SHA256
of each downloaded file. These files are **unmodified**. All original copyright
and license notices are retained. Native binaries are local build outputs, not
Git assets. ROS services, TF, physics, rendering and network APIs are not run.

| Upstream | License | Actual use |
|---|---|---|
| hrnr/m-explore | BSD-3-Clause (`LICENSE`) | Original `frontier_search.cpp` + headers compile into runtime; `explore.cpp` is the reference for Python goal/timeout/blacklist port |
| ros-planning/navigation | BSD-3-Clause (source headers) | Original `navfn.cpp`/header compile into runtime; costmap/inflation/footprint/ROS wrapper sources are references for documented adapter ports |
| AtsushiSakai/PythonRobotics | MIT (`LICENSE`) | Original `TargetCourse.search_target_index` and `pure_pursuit_steer_control` run in Python; vehicle simulator/main/plots are not called |
| ros-navigation/navigation2 | Apache-2.0 (`LICENSE` + source notice) | RPP rotate-to-heading and collision projection structure, reference only; no Nav2 server |

Adapters live in `harness/public_navigation/`. This is a composed standalone
integration, **not a verbatim end-to-end ROS deployment**. ROS middleware structs,
storage and logging have small C++ shims; planning/frontier algorithm bodies are
untouched. Python costmap preserves ROS floor/centre conversion, unknown=255,
inscribed costs and exponential inflation. SciPy EDT replaces the distance cache.
A rectangular padded footprint boundary/interior is rasterized with OpenCV; it is
checked on projected motion, while global NavFn uses inscribed inflation as ROS does.

NavFn's public `setupNavFn` → `propNavFnDijkstra(nx*ny, true)` → `calcPath` are called.
The convenience wrapper's `max(nx*ny/20,nx+ny)` budget ran out in the unit-test
4m U-detour with inflation; the adapter uses the finite map cell count as the
propagation budget. This is an explicit resource-budget adaptation, not a modified
search algorithm or a confirmation-result tuning. The test preserves that case.
`Costmap2D` cell centres consistently add 0.5; the older NavfnROS local mapToWorld
helper omits it. We use the actual Costmap2D centre contract for every adapter.

Pursuit's virtual rear axle is the robot body origin. WB=.24m, Lfc=.20m, k=.1;
steering becomes yaw-rate before the unchanged own-command M1 inverse. Courses
are re-created from the current path for each DR update; no upstream car dynamics
or measured/GT pose feedback is used. The upstream car demo defaults are not robot
parameters. RPP heading rotation/collision projection are separately documented ports.

explore_lite frontiers are unknown cells adjacent to free cells; the goal adapter
uses a reachable known-free standoff within .5m and turns the narrow camera toward
the centroid. Unknown traversal is disabled. The active target persists until
failure or lack of progress (30 modeled seconds); failed targets use the upstream
5-cell, axis-wise blacklist tolerance. At a reached viewing point it observes until
progress timeout, rather than inventing a new unexplored disk. No peer map merging.
