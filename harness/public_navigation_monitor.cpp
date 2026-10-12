// v8 local ABI; upstream NavFn/frontier and kinematics are compiled unchanged.
#define ugrp_frontiers ugrp_frontiers_legacy
#include "public_navigation_unknown.cpp"
#undef ugrp_frontiers
#include "nav2_collision_monitor/kinematics.hpp"
extern "C" int ugrp_frontiers(unsigned char* data,int nx,int ny,double r,double ox,double oy,
                              double x,double y,double* out,int capacity) {
  costmap_2d::Costmap2D map(nx,ny,r,ox,oy,data);
  frontier_exploration::FrontierSearch search(&map,3.,1.,.75); // explore.launch
  geometry_msgs::Point p; p.x=x;p.y=y;
  auto frontiers=search.searchFrom(p);
  int n=std::min(int(frontiers.size()),capacity);
  for(int i=0;i<n;++i){auto& f=frontiers[i];
    out[7*i]=f.centroid.x;out[7*i+1]=f.centroid.y;
    out[7*i+2]=f.middle.x;out[7*i+3]=f.middle.y;
    out[7*i+4]=f.min_distance;out[7*i+5]=f.size;out[7*i+6]=f.cost;}
  return n;
}
// Adapted from Nav2 geometry_utils.hpp:200-233 and polygon.cpp:339-389.
// Copyright (c) 2022 Samsung R&D Institute Russia; (c) 2019 Intel Corporation.
// Apache-2.0; full notice and
// exact originals in third_party/mapfree_navigation_monitor. Only ROS wrappers
// and polygon source-map aggregation replaced by finite own-camera arrays.
using namespace nav2_collision_monitor;
static bool inside(const Point& p, const std::vector<Point>& polygon) {
  bool res=false;
  int i=int(polygon.size())-1;
  for(int j=0;j<int(polygon.size());j++) {
    if((p.y<=polygon[i].y)==(p.y>polygon[j].y)) {
      const double x_inter=polygon[i].x+(p.y-polygon[i].y)*
        (polygon[j].x-polygon[i].x)/(polygon[j].y-polygon[i].y);
      if(x_inter>p.x) res=!res;
    }
    i=j;
  }
  return res;
}
extern "C" double ugrp_collision_time(double* xy,int n,double* footprint,int vertices,double* twist) {
  std::vector<Point> points,polygon;
  for(int i=0;i<n;i++) points.push_back({xy[2*i],xy[2*i+1]});
  for(int i=0;i<vertices;i++) polygon.push_back({footprint[2*i],footprint[2*i+1]});
  auto hit=[&polygon](const std::vector<Point>& ps){int count=0;
    for(auto& p:ps) count+=inside(p,polygon); return count>=6;};
  Pose pose={0.,0.,0.}; Velocity vel={twist[0],twist[1],twist[2]};
  if(hit(points)) return 0.;
  for(double time=0.;time<=1.2;time+=.1) {
    projectState(.1,pose,vel);
    auto moved=points;
    transformPoints(pose,moved);
    if(hit(moved)) return time;
  }
  return -1.;
}
