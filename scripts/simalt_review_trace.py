"""gcp1-only saved-state review: top + r1 + idle r2, no stepping or policy."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','plan','states','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source))
    import cv2
    import mujoco
    import numpy as np
    from PIL import Image,ImageDraw
    from simalt_pilot import runtime,world_for
    runtime(a.source,'legacy');a.out.mkdir(exist_ok=False)
    plan=json.loads(a.plan.read_text());index=json.loads((a.states/'state-index.json').read_text())
    states=np.load(a.states/'states.npz');world,scene=world_for(plan,True);m,d=world.model,world.data
    cid=m.camera(index['camera']).id;top=scene.config['static_map']['top_cameras'][0]['name'];frames=[]
    try:
        for i in range(0,len(index['rows']),5):
            mujoco.mj_setState(m,d,states['states'][i],int(states['spec']));mujoco.mj_forward(m,d)
            d.cam_xpos[cid]=index['rows'][i]['camera_pos'];d.cam_xmat[cid]=index['rows'][i]['camera_rot']
            def render():
                r=world.renderer;images=[]
                for camera in (top,'r1__robot_cam','r2__robot_cam'):
                    opts=mujoco.MjvOption() if camera==top else world.controllers[camera[:2]]._robot_sensor_scene_option
                    if camera==top:opts.geomgroup[:]=1
                    r.update_scene(d,camera=camera,scene_option=opts);rgb=r.render().copy()
                    if camera!=top:
                        mx,my=world.controllers[camera[:2]]._robot_fisheye_map
                        rgb=cv2.remap(rgb,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                    images.append(cv2.resize(rgb,(320,240)))
                return np.concatenate(images,axis=1)
            rgb=world._render_executor.submit(render).result(timeout=30)
            im=Image.fromarray(rgb);ImageDraw.Draw(im).text((5,5),f'SIM {i*.1:.1f}s {index["rows"][i]["phase"]} | top / r1 / r2 (idle)',fill='white',stroke_width=1,stroke_fill='black')
            im.save(a.out/f'{len(frames):04d}.jpg',quality=85);frames.append(im)
    finally:world.close()
    # 2 Hz sampled timeline, displayed at 8fps = 4x SIM time, no fabricated frames.
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate','8','-i',str(a.out/'%04d.jpg'),'-c:v','libx264','-crf','28','-pix_fmt','yuv420p',str(a.out/'review-4x.mp4')],check=True)
    probe=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size','-of','json',str(a.out/'review-4x.mp4')],text=True)
    for page in range(2):
        selected=frames[page*44:(page+1)*44];sheet=Image.new('RGB',(1920,((len(selected)+3)//4)*132),'white')
        for j,im in enumerate(selected):sheet.paste(im.resize((480,120)),((j%4)*480,(j//4)*132))
        sheet.save(a.out/f'whole-2hz-{page}.jpg',quality=90)
    phases={}
    for row in index['rows']:
        phase=phases.setdefault(row['phase'],{'first_sim_s':row['index']*.1,'last_sim_s':0.,'frames':0})
        phase['last_sim_s']=row['index']*.1;phase['frames']+=1
    (a.out/'review.json').write_text(json.dumps({'scope':'complete successful command trace, saved-state replay; no new task success judgment',
        'sample_hz':2,'playback_sim_speed':4,'range_sim_s':[0,len(index['rows'])*.1],
        'frames':len(frames),'ffprobe':json.loads(probe),'timeline':phases,
        'failure_review':'No executed task failure; C stopped before physics, pre-import HOST_ERROR has no video',
        'raw_paths':[str(a.states)],'reproduce':sys.argv},indent=2)+'\n')


if __name__=='__main__':main()
