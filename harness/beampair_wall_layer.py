"""Default-off teacher wall obstacle layer: log odds + observed free rays.

OctoMap defaults: p_hit=.7, p_miss=.4, clamps .1192/.971, occupancy .5.
The 25mm grid is the pinned search23 grid, not a fitted clearance. Known wall
rectangles mark cells; only camera-visible rays clear them. No time decay.
See experiments/2026-10-16-beampair5/README.md for observation scope/sources.
"""
from collections import defaultdict
from copy import deepcopy
import math

MODE = 'beampair_wall_clear_v1'
GRID_M = .025  # pinned sim.grasp_act_search23.GRID_M
HIT = math.log(.7/.3)
MISS = math.log(.4/.6)
LOW, HIGH = math.log(.1192/(1-.1192)), math.log(.971/(1-.971))


def ray_cells(a, b):
    """Amanatides/Woo 2-D grid traversal, endpoint excluded (hit wins)."""
    x,y = [math.floor(v/GRID_M) for v in a]
    end = tuple(math.floor(v/GRID_M) for v in b)
    dx,dy = b[0]-a[0],b[1]-a[1]
    sx,sy = (1 if dx>0 else -1),(1 if dy>0 else -1)
    tx = ((x+(dx>0))*GRID_M-a[0])/dx if dx else math.inf
    ty = ((y+(dy>0))*GRID_M-a[1])/dy if dy else math.inf
    ix,iy = GRID_M/abs(dx) if dx else math.inf,GRID_M/abs(dy) if dy else math.inf
    while (x,y) != end:
        yield x,y
        if tx < ty:x+=sx;tx+=ix
        elif ty < tx:y+=sy;ty+=iy
        else:x+=sx;y+=sy;tx+=ix;ty+=iy


def rectangle_cells(m):
    """Cell squares intersecting the observed oriented wall, with SAT."""
    import numpy as np
    x,y = m['xyz'][:2];hx,hy = m['half_extents'];a=m['yaw'];c,s=math.cos(a),math.sin(a)
    ex,ey=abs(c)*hx+abs(s)*hy,abs(s)*hx+abs(c)*hy;h=GRID_M/2
    xs=np.arange(math.floor((x-ex)/GRID_M),math.floor((x+ex)/GRID_M)+1)
    ys=np.arange(math.floor((y-ey)/GRID_M),math.floor((y+ey)/GRID_M)+1)
    xx,yy=np.meshgrid(xs,ys);dx=(xx+.5)*GRID_M-x;dy=(yy+.5)*GRID_M-y
    # Separating axes of both the observed rectangle and grid cell square.
    hit=(abs(dx)<=ex+h)&(abs(dy)<=ey+h)&(abs(c*dx+s*dy)<=hx+h*(abs(c)+abs(s)))&(abs(-s*dx+c*dy)<=hy+h*(abs(c)+abs(s)))
    return set(zip(map(int,xx[hit]),map(int,yy[hit])))


class WallLayer:
    def __init__(self):
        self.active=False;self.odds={};self.owners={};self.events=[];self.last_t=None

    def update(self, world, rid, measurements, rays):
        now=world['t'];pose=world['robots'][rid]['pose'];c,s=math.cos(pose[2]),math.sin(pose[2])
        def transform(q):return (pose[0]+c*q[0]-s*q[1],pose[1]+s*q[0]+c*q[1])
        occupied=set();names={}
        for m in world['visibility'][rid]['observations'].values():
            if m['kind']=='wall' and m['seen_t']>=now-1e-8:
                cells=rectangle_cells(m);occupied|=cells
                for k in cells:names[k]=m['id']
        free=set()
        for ray in rays:
            free.update(ray_cells(transform(ray['origin']),transform(ray['end'])))
            if ray['hit_wall']:
                k=tuple(math.floor(v/GRID_M) for v in transform(ray['end']));occupied.add(k);names[k]=ray['hit_wall']
        free-=occupied  # same scan's observed occupied support always wins
        cleared=[]
        for k in free:
            before=self.odds.get(k,0.);self.odds[k]=max(LOW,before+MISS)
            if before>=0 and self.odds[k]<0 and k in self.owners:cleared.append(k)
        for k in occupied:
            self.odds[k]=min(HIGH,self.odds.get(k,0.)+HIT);self.owners[k]=names[k]
        self.events.append(dict(t=now,event='wall_scan',ray_N=len(rays),miss_cell_N=len(free),hit_cell_N=len(occupied),
            cleared_cell_N=len(cleared),cleared_by_object=dict(__import__('collections').Counter(self.owners[k] for k in cleared)),
            occupied_cell_N=sum(v>=0 and k in self.owners for k,v in self.odds.items()),active=self.active,
            reason_category='observed_hit_miss_update',blocked_object='wall_layer',min_gap_m=None,gap_scope='sensor update; no clearance decision'))
        if not self.active:return world
        w=deepcopy(dict(world));obs=w['visibility'][rid]['observations'];w['walls']=[]
        # Keep original observation names for active gaze; planning geometry is
        # exclusively the updated occupied cells. Loss of gaze never clears.
        runs=defaultdict(list)
        for (x,y),value in self.odds.items():
            if value>=0 and (x,y) in self.owners:runs[(y,self.owners[(x,y)])].append(x)
        for (y,owner),xs in sorted(runs.items()):
            xs=sorted(xs);start=previous=xs[0]
            for x in xs[1:]+[None]:
                if x is not None and x==previous+1:previous=x;continue
                key=f'{owner}:grid:{start}:{previous}:{y}'
                rect=((start+previous+1)*GRID_M/2,(y+.5)*GRID_M,(previous-start+1)*GRID_M/2,GRID_M/2,0.)
                w['walls'].append(rect)
                # Occupancy posterior accounts for hit/miss uncertainty. Hard
                # 2m odometry confidence discs are not cells' collision geometry.
                # Keep the pinned fresh geometric 5mm envelope for these cells.
                obs[key]=dict(id=key,kind='wall',xyz=[*rect[:2],0.2],half_extents=list(rect[2:4]),yaw=0.,seen_t=now,
                    wall_layer_owner=owner)
                if x is not None:start=previous=x
        return w
