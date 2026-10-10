#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <mutex>
#include <queue>
#include <vector>
#include <geometry_msgs/Point.h>
#include <ros/console.h>
// Standalone storage shim. Conversion bodies match ROS Costmap2D (BSD-3-Clause).
// Original copyright/license: third_party/mapfree_navigation/navigation/costmap_2d/src/costmap_2d.cpp.
namespace costmap_2d {
class Costmap2D {
 public:
  using mutex_t=std::mutex;
  unsigned int size_x_,size_y_; double resolution_,origin_x_,origin_y_;
  unsigned char* data_; mutex_t mutex_;
  Costmap2D(unsigned int x,unsigned int y,double r,double ox,double oy,unsigned char* d)
   :size_x_(x),size_y_(y),resolution_(r),origin_x_(ox),origin_y_(oy),data_(d){}
  unsigned int getSizeInCellsX() const{return size_x_;}
  unsigned int getSizeInCellsY() const{return size_y_;}
  double getResolution() const{return resolution_;}
  unsigned char* getCharMap() const{return data_;}
  mutex_t* getMutex(){return &mutex_;}
  unsigned int getIndex(unsigned int x,unsigned int y) const{return y*size_x_+x;}
  void indexToCells(unsigned int i,unsigned int& x,unsigned int& y) const{x=i%size_x_;y=i/size_x_;}
  void mapToWorld(unsigned int mx, unsigned int my, double& wx, double& wy) const {
    wx = origin_x_ + (mx + 0.5) * resolution_;
    wy = origin_y_ + (my + 0.5) * resolution_;
  }
  bool worldToMap(double wx, double wy, unsigned int& mx, unsigned int& my) const {
    if (wx < origin_x_ || wy < origin_y_) return false;
    mx = (int)((wx-origin_x_)/resolution_);
    my = (int)((wy-origin_y_)/resolution_);
    return mx < size_x_ && my < size_y_;
  }
};
}
