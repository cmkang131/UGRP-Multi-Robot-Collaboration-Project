"""gcp2: compress playback time by input30fps, retain all10Hz source frames."""
import json,hashlib,shutil,subprocess,sys
from pathlib import Path
raw,old,out=map(Path,sys.argv[1:]);out.mkdir(exist_ok=False);rows=[]
for case in ('drive-off','high-off'):
 folder=out/case;folder.mkdir();ins=[]
 for camera in ('overview','r1','r2'):ins+=['-framerate','30','-i',str(raw/case/(camera+'-%04d.jpg'))]
 cmd=['ffmpeg','-nostdin','-loglevel','error',*ins,'-filter_complex','[0:v][1:v][2:v]hstack=inputs=3[v]','-map','[v]','-frames:v','41','-fps_mode','vfr','-an','-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-threads','1',str(folder/'review-3x.mp4')]
 subprocess.run(cmd,check=True)
 for f in (old/case).glob('*.jpg'):shutil.copyfile(f,folder/f.name)
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(folder/'review-3x.mp4')]))
 assert int(probe['streams'][0]['nb_frames'])==41 and (folder/'review-3x.mp4').stat().st_size<=8*1024**2
 rows.append(dict(case=case,sim_range=[0,4],video_probe=probe,reproduction=cmd,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.iterdir()},scope='input rate30fps gives3x playback of source10Hz; all41 frames retained; montage hashes unchanged'))
(out/'receipts.json').write_text(json.dumps(rows,indent=2)+'\n');print([(r['case'],r['video_probe']['streams'][0]['nb_frames'],r['video_probe']['format']['duration']) for r in rows])
