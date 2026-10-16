"""Independent raw recount/playback preparation on the original execution VM.

No simulator or model imports; nothing here changes a controller or a result.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess


def read(root, name, default=None):
    p = root/name
    return json.loads(p.read_text()) if p.exists() else default


def inspect(root):
    result = read(root, 'result.json', {})
    calls = [r for r in read(root, 'llm_ledger.json', []) if r['sim_s'] <= 30]
    decisions = [r for r in read(root, 'decisions.json', []) if r['sim_s'] <= 30]
    commands = [r for r in read(root, 'commands.json', []) if r['t'] <= 30]
    mapping = [r for r in read(root, 'localization.json', []) if r['sim_s'] <= 30]
    attempts = [v for r in calls for v in (r.get('upstream') or {}).get('attempts', [])]
    prompts = [r['usage']['prompt_tokens'] for r in calls if r.get('usage', {}).get('prompt_tokens') is not None]
    tokens = sum(r.get('usage', {}).get('total_tokens', 0) or 0 for r in calls)
    cached = sum((r.get('usage', {}).get('prompt_tokens_details') or {}).get('cached_tokens', 0) or 0 for r in calls)
    image_checks = []
    prompt_checks = []
    for call in calls:
        robot, world = call['robot'], call['world']
        file = root/f'world-{world:02d}'/'review-rgb'/f'{robot}-{round(call["sim_s"]*10):06d}.jpg'
        image_checks.append(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == call['image_sha256'])
    for file in root.glob('world-*/llm/*/*.request.json'):
        body = json.loads(file.read_text())
        msgs = body['messages']
        prompt_checks.append(len(msgs) == 3 and msgs[0]['role'] == 'system' and isinstance(msgs[1]['content'], str)
            and [v['type'] for v in msgs[-1]['content']] == ['text', 'image_url']
            and msgs[-1]['content'][-1]['image_url']['removed'] is True)
    worlds = result.get('nworld', 1)
    elapsed = min(result.get('sim_s', 0), 30)
    return dict(raw=str(root), source_sha=result.get('source_sha'), status=result.get('status'),
        inspected_sim_range=[0, elapsed], worlds=worlds,
        calls=len(calls), accepted=sum(r['accepted'] for r in calls), prompt_tokens=sum(prompts),
        prompt_tokens_per_call=prompts, median_prompt_tokens=statistics.median(prompts) if prompts else None,
        total_tokens=tokens, tokens_per_sim_world_s=tokens/(worlds*elapsed) if elapsed else None,
        cached_tokens=cached, cache_ratio=cached/sum(prompts) if sum(prompts) else None,
        http_429=sum(r['status'] == 429 for r in calls), upstream_429=sum(a['status'] == 429 for a in attempts),
        upstream_attempts=len(attempts), format_errors=sum('format_error' in r for r in calls),
        median_response_wall_s=statistics.median(r['response_wall_s'] for r in calls) if calls else None,
        image_raw_sha_verified=sum(image_checks), image_raw_sha_checks=len(image_checks),
        cache_order_checks=sum(prompt_checks), cache_order_total=len(prompt_checks),
        selections=dict(Counter(str(r.get('act')) for r in decisions)),
        timeline=[{k:r.get(k) for k in ('world', 'robot', 'sim_s', 'act', 'reason')} for r in decisions],
        stops=dict(issued_command_rows=len(commands), zero_wheels=sum(not any(r['wheels']) for r in commands),
                   interpretation='issued stop intent only; no actual motion inference'),
        localization=dict(Counter(r['status'] for r in mapping)),
        rejections=dict(Counter(r['reason'] for r in read(root, 'rejections.json', []))),
        runtime_applied=read(root, 'runtime-applied.json', None),
        success_scope='first30 integration diagnostic; no independent ACT/actual transport success',
        compatible_CPU_first30_baseline=None,
        baseline_limit='No same scene/provider/initial-state CPU first30 supplied. Historical results not pooled.')


def playback(root, output):
    from PIL import Image, ImageDraw
    rows=[]
    for tick in (0, 60, 120, 180, 240, 300):
        parts=[]
        for robot in ('r1', 'r2', 'r3'):
            path=root/'world-00/review-rgb'/f'{robot}-{tick:06d}.jpg'
            if not path.is_file():
                continue
            im=Image.open(path).convert('RGB').resize((320, 240))
            ImageDraw.Draw(im).text((5, 5),f'{robot} SIM {tick/10:g}',fill='white',stroke_width=1,stroke_fill='black')
            parts.append(im)
        if parts:
            row=Image.new('RGB',(320*3,240))
            for i, im in enumerate(parts):row.paste(im,(i*320,0))
            rows.append(row)
    if rows:
        sheet=Image.new('RGB',(960,240*len(rows)))
        for i,row in enumerate(rows):sheet.paste(row,(0,240*i))
        sheet.save(output/'first30-montage.jpg',quality=88)
    if len(rows) < 6:
        return
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
        '-framerate','3','-pattern_type','glob','-i',str(root/'world-00/review-rgb/r1-*.jpg'),
        '-framerate','3','-pattern_type','glob','-i',str(root/'world-00/review-rgb/r2-*.jpg'),
        '-filter_complex','[0:v]scale=320:240[a];[1:v]scale=320:240[b];[a][b]hstack=inputs=2',
        '-c:v','libx264','-pix_fmt','yuv420p','-crf','28',str(output/'own-r1-r2-3x.mp4')],check=True)
    probe=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size',
                                   '-of','json',str(output/'own-r1-r2-3x.mp4')],text=True)
    (output/'ffprobe.json').write_text(probe)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--playback',action='store_true');a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith('ugrp-act-l4-gcp6'):
        raise ValueError('original gcp6 CPU analysis only')
    a.output.mkdir(parents=True,exist_ok=False)
    report=inspect(a.raw)
    (a.output/'review.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    if a.playback:playback(a.raw,a.output)
    (a.output/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in a.output.iterdir() if p.is_file()},indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('runtime_applied','timeline')},ensure_ascii=False))


if __name__=='__main__':main()
