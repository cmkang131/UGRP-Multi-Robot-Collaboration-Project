// UGRP ABI adapter only. The upstream search/planning algorithms are unmodified.
#include <navfn/navfn.h>
#include <explore/frontier_search.h>
extern "C" {
int ugrp_navfn(unsigned char* data,int nx,int ny,int sx,int sy,int gx,int gy,float* out,int capacity) {
  if (sx<0||sy<0||gx<0||gy<0||sx>=nx||gx>=nx||sy>=ny||gy>=ny) return 0;
  navfn::NavFn nav(nx,ny);
  int start[2]={sx,sy},goal[2]={gx,gy};
  nav.setCostmap(data,true,false);
  nav.setStart(start); nav.setGoal(goal);
  // NavFn public primitives, full finite-grid propagation budget. The upstream
  // convenience wrapper caps cycles at max(nx*ny/20,nx+ny), which can exhaust
  // before a short U-shaped detour on small highly inflated maps. No cost/search
  // kernel changes; never treat budget exhaustion as a proven unreachable goal.
  nav.setupNavFn(true);
  nav.propNavFnDijkstra(nx*ny,true);
  if (!nav.calcPath(capacity)) return 0;
  int n=nav.getPathLen();
  if(n>capacity) return -1;
  for(int i=0;i<n;++i){out[2*i]=nav.getPathX()[i];out[2*i+1]=nav.getPathY()[i];}
  return n;
}
int ugrp_frontiers(unsigned char* data,int nx,int ny,double r,double ox,double oy,
                   double x,double y,double* out,int capacity) {
  costmap_2d::Costmap2D map(nx,ny,r,ox,oy,data);
  frontier_exploration::FrontierSearch search(&map,1.,1.,.1);
  geometry_msgs::Point p; p.x=x;p.y=y;
  auto frontiers=search.searchFrom(p);
  int n=std::min(int(frontiers.size()),capacity);
  for(int i=0;i<n;++i){auto& f=frontiers[i];
    out[7*i]=f.centroid.x;out[7*i+1]=f.centroid.y;
    out[7*i+2]=f.middle.x;out[7*i+3]=f.middle.y;
    out[7*i+4]=f.min_distance;out[7*i+5]=f.size;out[7*i+6]=f.cost;}
  return n;
}
}
