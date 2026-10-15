"""VM-only ffmpeg playback/strips. Never opens a desktop app or rerenders physics."""
import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image,ImageDraw


def make(run,out):
    out.mkdir(parents=True,exist_ok=False)
    raw=run/'raw';files=sorted((raw/'eval-own/r1').glob('*release-*.jpg'))
    frames=[(int(p.name.split('-')[0])*.1,p) for p in files]
    ring=raw/'failure-rgb'
    if ring.exists():
        for p in (ring/'r1').glob('*.jpg'):
            frames.append((float(p.stem),p))
    frames.sort(key=lambda x:x[0]);times=[t for t,p in frames]
    if not frames:raise ValueError('no own-camera evidence')
    # Existing raw release filenames index elapsed release ticks; failure ring
    # uses the same release-relative SIM seconds, never frame number as clock.
    def compose(t):
        j=max(0,bisect_right(times,t+1e-6)-1);at,p=frames[j]
        image=Image.new('RGB',(960,264),(22,22,22));draw=ImageDraw.Draw(image)
        top=raw/'eval-overview'/p.name
        if top.exists():image.paste(Image.open(top).resize((320,240)),(0,24))
        else:draw.text((8,80),'overview unavailable in saved raw',fill='white')
        for i,rid in enumerate(('r1','r2'),1):
            peer=p.parent.parent/rid/p.name
            if peer.exists():image.paste(Image.open(peer).resize((320,240)),(320*i,24))
        draw.text((4,6),f'{run.name} release SIM {t:.1f}s; source {at:.1f}s',fill='white')
        return image
    end=times[-1];fps=2;N=int(end*fps)+1
    movie=out/'playback-4x.mp4'
    proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','960x264','-framerate','8','-i','-','-an','-c:v','libx264','-preset','fast','-crf','30','-pix_fmt','yuv420p',str(movie)],stdin=subprocess.PIPE)
    for i in range(N):proc.stdin.write(compose(i/fps).tobytes())
    proc.stdin.close()
    if proc.wait():raise RuntimeError('ffmpeg failed')
    assert movie.stat().st_size<=8*1024**2
    strips=[]
    # Every 2Hz sample is represented; pages of 80 readable own-camera pairs.
    for start in range(0,N,80):
        page=Image.new('RGB',(1280,1400));draw=ImageDraw.Draw(page)
        for j,i in enumerate(range(start,min(start+80,N))):
            src=compose(i/fps);pair=src.crop((320,24,960,264)).resize((320,120))
            x=(j%4)*320;y=(j//4)*70
            page.paste(pair.resize((320,60)),(x,y+10));draw.text((x+2,y),f'{i/fps:.1f}s',fill='white')
        p=out/f'full-2hz-{start:04d}.jpg';page.save(p,quality=88);strips.append(str(p))
    page=Image.new('RGB',(1600,1400));draw=ImageDraw.Draw(page)
    for i in range(101):
        t=max(0,end-10)+i*.1;x=i%5*320;y=i//5*66
        src=compose(t);page.paste(src.crop((320,24,960,264)).resize((320,56)),(x,y+10));draw.text((x+2,y),f'{t:.1f}s',fill='white')
    p=out/'last10-10hz.jpg';page.save(p,quality=88)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(movie)]))
    rec=dict(run=str(run),release_range_s=[0,end],sample_hz=2,last10_sample_hz=10,
        source_max_gap_s=max(b-a for a,b in zip(sorted(set(times)),sorted(set(times))[1:])),
        warning='Repeated frames are explicitly timestamped; sampling does not restore missing 10Hz evidence.',
        overview_available=any((raw/'eval-overview').glob('*.jpg')),strips=strips,probe=probe,
        movie=dict(path=str(movie),bytes=movie.stat().st_size,sha256=hashlib.sha256(movie.read_bytes()).hexdigest()))
    (out/'playback.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(dict(run=run.name,range_s=rec['release_range_s'],max_gap_s=rec['source_max_gap_s'],movie_bytes=movie.stat().st_size,strips=len(strips))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('out',type=Path);a=p.parse_args();make(a.run,a.out)
