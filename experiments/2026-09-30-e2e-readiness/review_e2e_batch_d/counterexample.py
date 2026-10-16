import sys,os,copy,json,itertools,math,importlib.abc,socket
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in {'mujoco','torch','openai','anthropic','google','glfw'}:raise RuntimeError(fullname)
sys.meta_path.insert(0,Block())
def refuse(*a,**kw):raise RuntimeError('no network')
socket.socket.connect=refuse
sys.path.insert(0,os.getcwd())
mode=sys.argv[1]
if mode=='314':
 from harness import zone_static_door_routes as dr,static_keepouts as ko
 from harness.zone_team_footprint_v3 import team_footprint
 static=json.loads(Path('maps/zones_final/zone_wide_two_doors_final_v1.json').read_text())
 original=dr._formation
 def bad(*a,**kw):
  team=original(*a,**kw);team.parts=team.item_parts+team.carrier_parts['end_pos'];return team
 kw=dict(cargo_kind='long_beam',roles=('end_neg','end_pos'),robot_model='masterpi_v3',passage_id='door_narrow')
 good=dr.plan_door_routes(static,(1.,-1.2,0.),(3.5,-1.2,0.),**kw).selected
 dr._formation=bad
 route=dr.plan_door_routes(static,(1.,-1.2,0.),(3.5,-1.2,0.),**kw).selected
 full=team_footprint({'robot_model':'masterpi_v3'},'long_beam',margin=.03)
 hits=[]
 for pose in route.poses_m_rad:
  for role,parts in full.carrier_parts.items():
   for row in static['obstacles']:
    rect=(*row['center_m'],*row['half_extents_m'],row.get('yaw_rad',0))
    if any(not ko.pose_clear(pose,p,[rect]) for p in parts):hits.append({'pose':pose,'role':role,'wall':row['id']})
 print(json.dumps({'mutant_route':route.poses_m_rad,'original_route':good.poses_m_rad,'full_carrier_collisions_on_mutant_waypoints':hits},indent=2))
 assert hits
else:
 from harness import beam_initial_pose_plan as bp,static_keepouts as ko
 from harness.zone_team_footprint_v3 import TeamFootprintV3
 static=json.loads(Path('maps/zones/zone_wide_door_geometry_v2.json').read_text())
 scenario=json.loads(Path('configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json').read_text())
 order=next(o for o in scenario['orders'] if o['kind']=='long_beam')
 coarse={'beam_xyyaw':[1.3,.4,1.570796],'grid':dict(bp.GRID),'source':bp.SOURCE}
 real=bp.make_initial_pose_plan(static,bp.freeze_public_sheet(static,coarse,order),order)
 class Bad(TeamFootprintV3):
  def __init__(self,*a,**kw):
   super().__init__(*a,**kw);self.carrier_parts={r:[] for r in self.carrier_parts}
 bp.TeamFootprintV3=Bad
 bad=bp.make_initial_pose_plan(static,bp.freeze_public_sheet(static,coarse,order),order)
 def outside(point,box):
  x,y=point;x0,x1,y0,y1=box;return x<x0-.003 or x>x1+.003 or y<y0-.003 or y>y1+.003
 found=None
 for role in bp.ROLES:
  polys=real['roles'][role]['local_parts_at_endpoints'];n=len(polys)//2
  for t in (0,.25,.5,.75,1):
   for a,b in zip(polys[:n],polys[n:]):
    local=[(x*(1-t)+u*t,y*(1-t)+v*t) for (x,y),(u,v) in zip(a,b)]
    for dx,dy,da in itertools.product((-.05,0,.05),(-.05,0,.05),(-math.radians(5),0,math.radians(5))):
     pose=[1.3+dx,.4+dy,1.570796+da]
     world=ko.polygon_at(pose,local)
     for p in world:
      if all(outside(p,box) for box in bad['swept_bounds_m'].values()):found={'role':role,'t':t,'actual_pose':pose,'wall_point':p};break
     if found:break
    if found:break
   if found:break
  if found:break
 assert found
 row={'id':'omitted_carrier_corner','center_m':list(found['wall_point']),'half_extents_m':[.001,.001]}
 static['obstacles'].append(row)
 mutant=bp.make_initial_pose_plan(static,bp.freeze_public_sheet(static,coarse,order),order)
 bp.TeamFootprintV3=TeamFootprintV3
 try:bp.make_initial_pose_plan(static,bp.freeze_public_sheet(static,coarse,order),order)
 except bp.PlanRefusal as e:original={'code':e.code,'detail':e.detail}
 else:raise AssertionError('original should refuse')
 print(json.dumps({'counterexample':found,'static_wall':row,'original':original,'mutant':mutant['verdict'],'original_bounds':real['swept_bounds_m'],'mutant_bounds':bad['swept_bounds_m']},indent=2))
