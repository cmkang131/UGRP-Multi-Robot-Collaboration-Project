// Diagnostic port of C3.12 Plane–Mesh support/neighbor selection to C3.16.
// Source: google-deepmind/mujoco 3.12.0 engine_collision_convex.c:966-1103.
// Same maxplanemesh=3, tolplanemesh=.3; no model parameter changes.
#include <mujoco/mujoco.h>
#include <math.h>

static mjtNum dot(const mjtNum *a, const mjtNum *b) {
  return mju_dot3(a,b);
}
static void transform(mjtNum *p, const float *v, const mjtNum *r, const mjtNum *x) {
  // Preserve C312's operation order: matvec first, add translation second.
  // Adding x inside the scalar dot changed the long contact trajectory.
  mjtNum vertex[3]={v[0],v[1],v[2]};
  mju_mulMatVec3(p,r,vertex);mju_addTo3(p,x);
}
static void contact(mjPreContact *c, const mjtNum *p, const mjtNum *normal, const mjtNum *plane) {
  mjtNum delta[3];mju_sub3(delta,p,plane);
  c->dist=dot(normal,delta);
  mju_copy3(c->pos,p);mju_addToScl3(c->pos,normal,-.5*c->dist);
  mju_copy3(c->normal,normal);mju_zero3(c->tangent);
}
int simalt_legacy_plane_mesh(const mjModel *m, mjData *d, mjPreContact *con, int g1, int g2, mjtNum margin) {
  int mesh=m->geom_dataid[g2], count=m->mesh_vertnum[mesh];
  const float *vertices=m->mesh_vert+3*m->mesh_vertadr[mesh];
  const mjtNum *plane=d->geom_xpos+3*g1, *x=d->geom_xpos+3*g2;
  const mjtNum *r=d->geom_xmat+9*g2, *pr=d->geom_xmat+9*g1;
  mjtNum normal[3]={pr[2],pr[5],pr[8]}, direction[3], p[3];
  mjtNum negative[3]={-normal[0],-normal[1],-normal[2]};
  mju_mulMatTVec3(direction,r,negative);
  int adr=m->mesh_graphadr[mesh], best=-1, local=0;
  mjtNum maximum=-1.e10;
  const int *edges=0,*globals=0,*neighbors=0;
  if(adr<0) {
    for(int i=0;i<count;i++) {
      mjtNum v[3]={vertices[3*i],vertices[3*i+1],vertices[3*i+2]}, value=dot(direction,v);
      if(value>maximum){maximum=value;best=i;}
    }
  } else {
    int n=m->mesh_graph[adr];edges=m->mesh_graph+adr+2;globals=edges+n;neighbors=globals+n;
    best=globals[0];mjtNum v[3]={vertices[3*best],vertices[3*best+1],vertices[3*best+2]};maximum=dot(direction,v);
    int change=1;
    while(change) {
      change=0;
      for(int e=edges[local];neighbors[e]>=0;e++) {
        int candidate=globals[neighbors[e]];
        mjtNum vertex[3]={vertices[3*candidate],vertices[3*candidate+1],vertices[3*candidate+2]};
        mjtNum value=dot(direction,vertex);
        if(value>maximum){maximum=value;local=neighbors[e];change=1;}
      }
    }
    best=globals[local];
  }
  if(best<0)return 0;
  transform(p,vertices+3*best,r,x);contact(con,p,normal,plane);
  if(con[0].dist>margin)return 0;
  mjtNum delta[3];for(int k=0;k<3;k++)delta[k]=x[k]-plane[k];
  mjtNum threshold=dot(normal,delta)-margin;
  int n=1,begin=adr<0?0:edges[local];
  for(int e=begin;n<3 && (adr<0?e<count:neighbors[e]>=0);e++) {
    int i=adr<0?e:globals[neighbors[e]];
    mjtNum vertex[3]={vertices[3*i],vertices[3*i+1],vertices[3*i+2]};
    if(dot(direction,vertex)>threshold && (adr>=0 || i!=best)) {
      transform(p,vertices+3*i,r,x);
      for(int k=0;k<3;k++)delta[k]=p[k]-con[0].pos[k];
      if(mju_dist3(p,con[0].pos)>=.3*m->geom_rbound[g2])contact(con+n++,p,normal,plane);
    }
  }
  return n;
}
