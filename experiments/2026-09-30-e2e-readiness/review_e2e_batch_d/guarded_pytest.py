import importlib.abc,sys,socket,os
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in {'mujoco','torch','openai','anthropic','google','glfw'}:
   raise RuntimeError('REVIEW NO PHYSICS / MODEL IMPORT: '+fullname)
sys.meta_path.insert(0,Block())
def refuse(*a,**kw):raise RuntimeError('REVIEW NO NETWORK')
socket.socket.connect=refuse
socket.create_connection=refuse
sys.path.insert(0,os.getcwd())
mode=sys.argv.pop(1)
if mode in ('315_drop_arms','315_drop_carriers'):
 import harness.beam_initial_pose_plan as bp
 Orig=bp.TeamFootprintV3
 class NoArms(Orig):
  def __init__(self,*a,**kw):
   super().__init__(*a,**kw)
   self.carrier_parts={r:(parts[:1] if mode=='315_drop_arms' else []) for r,parts in self.carrier_parts.items()}
 bp.TeamFootprintV3=NoArms
elif mode=='314_drop_trailing':
 import harness.zone_static_door_routes as dr
 orig=dr._formation
 def bad(*a,**kw):
  team=orig(*a,**kw)
  if team.kind=='long_beam':team.parts=team.item_parts+team.carrier_parts['end_pos']
  return team
 dr._formation=bad
elif mode=='313_flip_pivot_report':
 sys.path.insert(0,str(Path.cwd()/'experiments/2026-09-30-s6-order-design'))
 import audit
 orig=audit.pivot_report
 def bad(*a,**kw):
  rows=orig(*a,**kw)
  for r in rows:
   if r['pivot']=='end_pos_contact':r['delta_deg']=-r['delta_deg']
  return rows
 audit.pivot_report=bad
import pytest
sys.exit(pytest.main(sys.argv[1:]))
