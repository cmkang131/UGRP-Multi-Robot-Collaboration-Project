import hashlib,json,subprocess,sys
from pathlib import Path
raw=Path(sys.argv[1]);dest=raw/'motion.mp4'
if dest.exists():raise ValueError('preserve existing video')
rows=[json.loads(x) for x in (raw/'robots/r3/frames.jsonl').read_text().splitlines()];selected=rows[::4]
p=subprocess.Popen(['ffmpeg','-v','error','-f','image2pipe','-vcodec','mjpeg','-framerate','20','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(dest)],stdin=subprocess.PIPE)
for q in selected:
 data=(raw/q['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==q['sha256'];p.stdin.write(data)
p.stdin.close();assert p.wait()==0
subprocess.run(['ffmpeg','-v','error','-i',str(dest),'-f','null','-'],check=True)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,r_frame_rate,nb_frames','-of','json',str(dest)]))
record=dict(path=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),source_frames=len(rows),output_frames=len(selected),speed=4,input_frame_interval_s=.05,full_decode=True,probe=probe)
(raw/'motion-4x.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
