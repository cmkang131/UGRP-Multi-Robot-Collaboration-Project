"""Gcp2 ffmpeg/ffprobe + saved-image strips only; never launches a viewer."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ffmpeg(args):subprocess.run(['ffmpeg','-v','error','-n',*args],check=True)
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)],text=True))
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worlds',nargs='+',type=int,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);runs=[]
    for world in a.worlds:
        raw=a.root/f'world-{world:03d}'/'raw';out=a.output/f'world-{world:03d}';out.mkdir()
        playback=raw/'playback/manifest.json';tail=raw/'failure-rgb/manifest.json';record=dict(world=world,raw=str(raw),
            scope='saved diagnostic prefix; not a completed mission or fabricated success comparison',directly_viewed=False,source_hashes={})
        if playback.exists():
            rows=json.loads(playback.read_text())['frames'];record['whole_2hz_N']=len(rows)
            if rows:
                record['whole_range_sim_s']=[rows[0]['t'],rows[-1]['t']]
                video=out/'overview-r1-r2-4x.mp4'
                ffmpeg(['-framerate','8','-i',str(raw/'playback/%05d-overview.jpg'),'-framerate','8','-i',str(raw/'playback/%05d-r1.jpg'),
                    '-framerate','8','-i',str(raw/'playback/%05d-r2.jpg'),'-filter_complex',
                    '[0:v]scale=320:240[o];[1:v]scale=320:240[a];[2:v]scale=320:240[b];[o][a][b]hstack=inputs=3,format=yuv420p',
                    '-c:v','libx264','-preset','fast','-crf','32','-threads','2','-an','-movflags','+faststart',str(video)])
                record['whole_video_probe']=probe(video)
                # Twenty sequential 2Hz samples per sheet; all samples retained.
                for page in range((len(rows)+19)//20):
                    sheet=Image.new('RGB',(2400,600),'white');draw=ImageDraw.Draw(sheet)
                    for cell,row in enumerate(rows[page*20:(page+1)*20]):
                        x=(cell%5)*480;y=(cell//5)*150
                        draw.text((x+3,y+3),f"SIM {row['t']:.2f} | overview / r1 / r2",fill='black')
                        for camera_index,camera in enumerate(('overview','r1','r2')):
                            src=raw/'playback'/row['files'][camera];record['source_hashes'][str(src)]=sha(src)
                            with Image.open(src) as im:sheet.paste(im.resize((160,120)),(x+camera_index*160,y+20))
                    sheet.save(out/f'whole-2hz-{page:02d}.jpg',quality=88)
        if tail.exists():
            value=json.loads(tail.read_text());rows=value['frames'];record['tail_10hz_N']=len(rows);record['tail_bytes']=value['bytes']
            if rows:
                record['tail_range_sim_s']=[rows[0]['t'],rows[-1]['t']]
                sheet=Image.new('RGB',(1600,140*((len(rows)+9)//10)),'white');draw=ImageDraw.Draw(sheet)
                for cell,row in enumerate(rows):
                    x=(cell%10)*160;y=(cell//10)*140;src=raw/'failure-rgb'/row['path']
                    draw.text((x+3,y+3),f"SIM {row['t']:.2f}",fill='black')
                    with Image.open(src) as im:sheet.paste(im.resize((160,120)),(x,y+20))
                    record['source_hashes'][str(src)]=sha(src)
                sheet.save(out/'tail-10hz.jpg',quality=90)
                video=out/'own-tail-4x.mp4'
                ffmpeg(['-framerate','40','-i',str(raw/'failure-rgb/%04d.jpg'),'-vf','scale=320:240,format=yuv420p',
                    '-c:v','libx264','-preset','fast','-crf','30','-threads','2','-an','-movflags','+faststart',str(video)])
                record['tail_video_probe']=probe(video)
        record['files']={str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.iterdir() if p.is_file()}
        if any(v['bytes']>8*1024**2 for k,v in record['files'].items() if k.endswith('.mp4')):raise ValueError('review video exceeds requested8MiB')
        runs.append(record)
    (a.output/'playback.json').write_text(json.dumps(dict(runs=runs,method='gcp2 ffmpeg4x, original2Hz and10Hz sequential strips; ffprobe only',
        success_comparison='verify actual outcomes separately; no mission-success substitution'),indent=2)+'\n')
if __name__=='__main__':main()
