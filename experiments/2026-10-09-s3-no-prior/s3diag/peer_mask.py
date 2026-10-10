"""Eval-only RGB annotation bounds; no semantic GT segmentation was recorded.
Orange robot surface pixels are a lower bound. Padded enclosing box is a
conservative exclusion mask, NOT an exact robot-pixel count. No controller thresholds change.
"""
import cv2,json,pathlib,hashlib,copy
import numpy as np
from harness import vision_loc_protocol as vp
B=pathlib.Path(__file__).parent;RAW=B.parent/'s3-no-prior-6c657124-s14201-v142';mp=vp.load_vis3()[0].mp;K=np.linalg.inv(mp.K_INV)
rows=[];summaries={};mask_receipts={}
visibility={(q['robot'],round(q['t'],3)):q for q in [json.loads(x) for x in (B/'peer-visibility.jsonl').read_text().splitlines()]}
for r,folder in [('r1','baseline-r1-v3'),('r2','baseline-r2'),('r3','baseline-r3')]:
 frames=[json.loads(x) for x in (RAW/f'robots/{r}/frames.jsonl').read_text().splitlines()];annotations={}
 for f in frames:
  im=mp.undistort(cv2.imread(str(RAW/f['path'])));h,s,v=np.moveaxis(cv2.cvtColor(im,cv2.COLOR_BGR2HSV),-1,0)
  roi=np.zeros((480,640),bool);geometry=visibility[r,round(f['sim_time'],3)]
  for peer in geometry['peer_geometry']:
   if peer.get('rectangle') is not None:
    x0,y0,x1,y1=peer['rectangle'];roi[int(y0):int(np.ceil(y1)),int(x0):int(np.ceil(x1))]=True
  orange=roi&(h>=5)&(h<=35)&(s>=120)&(v>=80);yy,xx=np.where(orange);box=None
  if len(xx):box=[max(0,int(xx.min())-20),max(0,int(yy.min())-20),min(640,int(xx.max())+21),min(480,int(yy.max())+21)]
  q=dict(robot=r,t=f['sim_time'],orange_pixels=int(len(xx)),orange_fraction=float(len(xx)/307200),exclusion_box=box,exclusion_fraction=0. if box is None else float((box[2]-box[0])*(box[3]-box[1])/307200),camera_geometry_available=bool(geometry['peer_geometry']),definition='orange surface lower bound / padded box area; eval-only annotation, not exact segmentation')
  rows.append(q);annotations[round(f['sim_time'],3)]=q
 packets=json.loads((B/folder/'packets.json').read_text());replacement={};edits=[]
 for p in packets:
  q=copy.deepcopy(p);box=annotations[round(p['t'],3)]['exclusion_box'];before=(len(q['wall_points']),len(q['features']))
  if box is not None:
   x0,y0,x1,y1=box;points=np.array(q['wall_points']).reshape(-1,2);cam=(np.c_[points,np.zeros(len(points))]-q['origin'])@np.array(q['rotation']);uv=cam@K.T
   with np.errstate(divide='ignore',invalid='ignore'):uv=uv[:,:2]/uv[:,2,None]
   inside=(uv[:,0]>=x0)&(uv[:,0]<x1)&(uv[:,1]>=y0)&(uv[:,1]<y1);q['wall_points']=points[~inside].tolist()
   keep=[]
   for feature in q['features']:
    a,b=np.array(feature['pixels']);samples=a+(b-a)*np.linspace(0,1,101)[:,None];hit=(samples[:,0]>=x0)&(samples[:,0]<x1)&(samples[:,1]>=y0)&(samples[:,1]<y1)
    if not hit.any():keep.append(feature)
   q['features']=keep
  replacement[str(round(q['t'],3))]=q;edits.append(dict(t=q['t'],before=before,after=(len(q['wall_points']),len(q['features'])),box=box))
 own=[z for z in rows if z['robot']==r];visible=[z for z in own if z['orange_pixels']];summaries[r]=dict(frames=len(own),frames_with_visible_orange=len(visible),first_visible=None if not visible else visible[0]['t'],max_orange_fraction=max(z['orange_fraction'] for z in own),max_exclusion_fraction=max(z['exclusion_fraction'] for z in own),critical=annotations.get(13.75),masked_packet_changes=[z for z in edits if z['before']!=z['after']])
 (B/f'peer-mask-{r}.json').write_text(json.dumps(replacement,indent=2)+'\n');mask_receipts[r]=dict(packet_count=len(packets),changed=sum(q['before']!=q['after'] for q in edits),identity_if_unchanged=all(q['before']==q['after'] for q in edits))
(B/'peer-pixel-bounds.jsonl').write_text(''.join(json.dumps(q)+'\n' for q in rows));(B/'peer-mask-summary.json').write_text(json.dumps(dict(robots=summaries,receipts=mask_receipts,method='eval-only peer sphere ROI restricts annotation to other robots; saved undistorted own RGB; orange HSV[5,35],S>=120,V>=80 annotation plus20px box; real pixel GT unavailable',gt_use='offline eval_only causal exclusion; never production perception',mask_scope='discard existing endpoints/features intersecting box; never synthesize background or introduce black-image boundaries'),indent=2)+'\n');print(json.dumps(summaries,indent=2))
