from pathlib import Path
import json,sys,cv2,numpy as np,hashlib,subprocess
import argparse
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
src=Path(__file__).resolve().parents[2];sys.path.insert(0,str(src))
from harness.active_wall_vision import modules,observe
from harness.strict_wall_motion import balanced_corners
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D,CAMERA_CALIBRATION_ID
mp,_,_=modules();K=mp.K;D=np.array(CAMERA_FISHEYE_D,float);base=args.input;out=args.output;out.mkdir(exist_ok=True)
rows=[json.loads(s) for s in (base/'frames.jsonl').read_text().splitlines()];records=[];line_reports=[];sheet=np.full((650,1600,3),(23,27,35),np.uint8)
video=subprocess.Popen(['/opt/homebrew/bin/ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s','1280x620','-r','15','-i','-','-an','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'scan-raw-undistorted.mp4')],stdin=subprocess.PIPE)
def text(im,s,x,y,scale=.52,color=(235,235,235)):cv2.putText(im,s,(x,y),cv2.FONT_HERSHEY_SIMPLEX,scale,color,1,cv2.LINE_AA)
def straightness(p):
 p=np.asarray(p,float);c=p.mean(0);_,_,vt=np.linalg.svd(p-c,full_matrices=False);res=(p-c)@vt[-1];span=np.ptp((p-c)@vt[0]);return dict(n=len(p),rms_px=float(np.sqrt(np.mean(res*res))),p95_abs_px=float(np.quantile(abs(res),.95)),span_px=float(span),normalized_rms=float(np.sqrt(np.mean(res*res))/span))
def compare(points,name,raw,image_id):
 p=np.asarray(points,float);u=cv2.fisheye.undistortPoints(p.reshape(-1,1,2),K,D,P=K).reshape(-1,2);report=dict(image=image_id,edge=name,raw=straightness(p),undistorted=straightness(u));line_reports.append(report)
 canvas=np.hstack([raw,mp.undistort(raw)])
 for j,points2 in enumerate((p,u)):
  for pt in points2:cv2.circle(canvas,tuple(np.rint(pt+[j*640,0]).astype(int)),2,(50,220,245),-1)
  fit=straightness(points2);text(canvas,f'{["Raw","PR405 corrected"][j]} RMS {fit["rms_px"]:.2f}px',12+j*640,25,.6,(40,80,245))
 cv2.imwrite(str(out/f'line-{image_id}-{name}.png'),canvas)
 return report
for i,r in enumerate(rows):
 assert hashlib.sha256((base/r['image']).read_bytes()).hexdigest()==r['sha256']
 if r['replicate']!=1:continue
 raw=cv2.imread(str(base/r['image']));und=mp.undistort(raw);servo={int(k):v for k,v in r['commanded_pose'].items()};ob=observe(cv2.cvtColor(raw,cv2.COLOR_BGR2RGB),servo,body_settling=.7)
 # The candidate overlay is intentionally separate from user semantic labels.
 display=und.copy();o=np.array(ob['camera_origin']);R=np.array(ob['camera_rotation'])
 for seg in ob['segments']:
  xyz=np.c_[seg,np.zeros(2)];q=(xyz-o)@R;h=q@K.T;uv=h[:,:2]/h[:,2,None]
  if np.isfinite(uv).all():cv2.line(display,tuple(np.rint(uv[0]).astype(int)),tuple(np.rint(uv[1]).astype(int)),(70,80,245),3,cv2.LINE_AA)
 rec=dict(image=r['image'],commanded_pose=r['commanded_pose'],candidates=len(ob['segments']),observation=ob,raw_corners=len(balanced_corners(cv2.cvtColor(raw,cv2.COLOR_BGR2GRAY))),undistorted_corners=len(balanced_corners(cv2.cvtColor(und,cv2.COLOR_BGR2GRAY))))
 # Conservative labelled floor interiors at the same pan. Evaluation-only,
 # not masks supplied to the detector, and not exact user-confirmed pixels.
 if servo[6]==1900:
  polygon=np.array([[0,323],[0,479],[225,479]],np.int32) if servo[3]==858 else np.array([[0,254],[0,479],[369,479],[365,454]],np.int32)
  mask=np.zeros((480,640),np.uint8);cv2.fillPoly(mask,[polygon],255)
  corners=balanced_corners(cv2.cvtColor(raw,cv2.COLOR_BGR2GRAY));idx=np.rint(corners).astype(int);in_floor=mask[idx[:,1],idx[:,0]]>0
  rec['conservative_floor_annotation']=dict(provenance='assistant-drawn interior polygon using user scene semantics; evaluation-only',polygon=polygon.tolist(),image_fraction=float((mask>0).mean()),corner_count=int(in_floor.sum()))
  # Wall material seam (white/gray), used only for lens straightness.
  gray=cv2.GaussianBlur(cv2.cvtColor(raw,cv2.COLOR_BGR2GRAY),(3,3),0).astype(float);pts=[]
  for x in range(12,350,3):
   y0=round((260+.60*x) if servo[3]==858 else (178+.55*x));lo=max(3,y0-20);hi=min(477,y0+20);ys=np.arange(lo,hi);response=gray[ys-2,x]-gray[ys+2,x];yy=ys[np.argmax(response)]
   if response.max()>25:pts.append([x,float(yy)])
  if len(pts)>60:compare(pts,'wall-material-seam',raw,r['image'].replace('.jpg',''))
  if servo[3]==740:
   # Two independently visible floor tile seams, no claim they are wall contacts.
   for name,a,b in [('floor-seam-A',[10,326],[115,458]),('floor-seam-B',[140,465],[257,377])]:
    a=np.array(a,float);b=np.array(b,float);tangent=(b-a)/np.linalg.norm(b-a);normal=np.array([-tangent[1],tangent[0]]);points=[]
    for center in np.linspace(a,b,60):
     offsets=np.arange(-7,7.01,.25);values=np.zeros(len(offsets))
     for shift in (-2,0,2):
      p=center[None,:]+offsets[:,None]*normal+shift*tangent;values+=cv2.remap(gray.astype(np.float32),p[:,0].astype(np.float32).reshape(1,-1),p[:,1].astype(np.float32).reshape(1,-1),cv2.INTER_LINEAR).ravel()
     j=int(np.argmin(values));points.append(center+offsets[j]*normal)
    compare(points,name,raw,r['image'].replace('.jpg',''))
 records.append(rec)
 # Undistorted overview in same pan order and two tilt rows.
 column=[1900,1700,1500,1300,1100].index(servo[6]);row=0 if servo[3]==858 else 1;x=column*320;y=40+row*280
 sheet[y:y+240,x:x+320]=cv2.resize(und,(320,240));text(sheet,f's3 {servo[3]} / pan {servo[6]}',x+8,y+262,.48)
 canvas=np.full((620,1280,3),(22,26,34),np.uint8);canvas[:480,:640]=raw;canvas[:480,640:]=display
 for x0 in (0,640):cv2.rectangle(canvas,(x0,0),(x0+639,38),(22,26,34),-1)
 text(canvas,'RAW camera',12,25,.65);text(canvas,f'PR405 correction + candidates: {len(ob["segments"])}',652,25,.58)
 text(canvas,f'ras1 camera-only scan | pan {servo[6]} / s3 {servo[3]} (commands, not measured angles)',12,510,.58)
 text(canvas,'Brown region = BOX, white/gray region = right WALL, patterned light gray = FLOOR.',12,539,.53)
 text(canvas,'Red = unverified PR405 candidates. Color seams / box edges are not floor contacts.',12,567,.53,(120,180,255))
 text(canvas,'No chassis movement. Rotation scan checks visibility, not triangulated depth.',12,597,.53)
 for _ in range(21):video.stdin.write(canvas.tobytes())
text(sheet,'PR405 undistorted views | same five pans; top s3=858, bottom s3=740 | chassis stationary',12,26,.64)
text(sheet,'Center views are occluded by the brown box. At pan1900, looking down exposes more patterned floor.',12,628,.6,(130,205,250))
cv2.imwrite(str(out/'undistorted-views-contactsheet.png'),sheet);video.stdin.close();assert video.wait()==0
# Quantify remap crop in raw sensor coordinates, and round-trip consistency.
mapx,mapy=mp._UNDISTORT;boundary=np.vstack([np.c_[mapx[0],mapy[0]],np.c_[mapx[-1],mapy[-1]],np.c_[mapx[:,0],mapy[:,0]],np.c_[mapx[:,-1],mapy[:,-1]]]).astype(np.float32);hull=cv2.convexHull(boundary)
grid=np.array([[x,y] for y in range(20,461,40) for x in range(20,621,40)],float);u=cv2.fisheye.undistortPoints(grid.reshape(-1,1,2),K,D).reshape(-1,2);dist=cv2.fisheye.distortPoints(u.reshape(-1,1,2),K,D).reshape(-1,2)
report=dict(physical_host='ras1',source_calibration=CAMERA_CALIBRATION_ID,K=K.tolist(),D=D.tolist(),input_resolution=[640,480],correction_applied=True,calibrated_for_ras1=False,correction_model='OpenCV fisheye; same output K; exactly one remap per detector input',new_pinhole_hfov_deg=float(np.degrees(np.arctan((640-K[0,2])/K[0,0])+np.arctan(K[0,2]/K[0,0]))),new_pinhole_vfov_deg=float(np.degrees(np.arctan((480-K[1,2])/K[1,1])+np.arctan(K[1,2]/K[1,1]))),raw_sampling_hull_fraction=float(cv2.contourArea(hull)/(640*480)),roundtrip_max_error_px=float(np.linalg.norm(dist-grid,axis=1).max()),line_straightness=line_reports,views=records,training_performed=False,view_scan_proves_depth=False,new_wall_map_generated=False)
(out/'camera-diagnosis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('views',)},indent=2));print('VIEW SUMMARY',json.dumps([{k:v for k,v in r.items() if k!='observation'} for r in records],indent=2))
