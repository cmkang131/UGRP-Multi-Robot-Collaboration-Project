// Local ABI only. Original NavFn/frontier algorithms remain byte-identical.
// Separate symbol/DSO preserves the v1-v6 allow_unknown=false golden path.
#define ugrp_navfn ugrp_navfn_legacy
#include "public_navigation/bridge.cpp"
#undef ugrp_navfn
extern "C" int ugrp_navfn(unsigned char* data,int nx,int ny,int sx,int sy,int gx,int gy,float* out,int capacity) {
  if (sx<0||sy<0||gx<0||gy<0||sx>=nx||gx>=nx||sy>=ny||gy>=ny) return 0;
  navfn::NavFn nav(nx,ny);
  int start[2]={sx,sy},goal[2]={gx,gy};
  nav.setCostmap(data,true,true); // Nav2 NavFn allow_unknown default
  nav.setStart(start); nav.setGoal(goal);
  nav.setupNavFn(true);
  nav.propNavFnDijkstra(nx*ny,true);
  if (!nav.calcPath(capacity)) return 0;
  int n=nav.getPathLen();
  if(n>capacity) return -1;
  for(int i=0;i<n;++i){out[2*i]=nav.getPathX()[i];out[2*i+1]=nav.getPathY()[i];}
  return n;
}
