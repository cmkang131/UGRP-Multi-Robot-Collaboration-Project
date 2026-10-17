// UGRP bridge only. The included BSD-3-Clause header is unmodified upstream.
#include <algorithm>
#include <iostream>
#include <map>
#include "FeatureStatistics.hpp"

using Statistics = rovio::FeatureStatistics<1>;
extern "C" {
void* rovio_statistics_create(double time) {
  return new Statistics(time);
}
void rovio_statistics_destroy(void* ptr) {
  delete static_cast<Statistics*>(ptr);
}
void rovio_statistics_set(void* ptr, int status) {
  static_cast<Statistics*>(ptr)->status_[0] = static_cast<rovio::TrackingStatus>(status);
}
void rovio_statistics_advance(void* ptr, double time) {
  static_cast<Statistics*>(ptr)->increaseStatistics(time);
}
void rovio_statistics_values(void* ptr, double* values) {
  const auto& s = *static_cast<Statistics*>(ptr);
  values[0] = s.getLocalQuality(0);
  values[1] = s.getLocalVisibility(0);
  values[2] = s.getGlobalQuality();
  values[3] = s.countTot();
  values[4] = s.countTracked();
}
int rovio_statistics_good(void* ptr, double upper, double lower) {
  return static_cast<Statistics*>(ptr)->isGoodFeature(upper, lower);
}
}
