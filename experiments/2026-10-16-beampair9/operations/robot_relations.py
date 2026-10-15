"""GCP-only evaluator relationship timeline for all15 original failures/caps."""
import json,math,hashlib
from pathlib import Path
from analyze_before import ROOT,OPS,read,data,write

if __name__=='__main__':
    before=read(OPS/'before-summary.json');runs=[]
    for entry in before['runs']:
        raw=Path(entry['raw']);rows=[json.loads(x) for x in data(raw/'eval-only.jsonl').splitlines()]
        result=read(raw/'result.json');t0=rows[0]['t'];dist=[];same=[]
        for row in rows:
            dist.append(math.dist(row['robots']['r1']['pose'][:2],row['robots']['r2']['pose'][:2]))
            nearest={r:min(row['beam']['ends'],key=lambda e:math.dist(row['robots'][r]['pose'][:2],row['beam']['ends'][e][:2])) for r in ('r1','r2')}
            same.append(len(set(nearest.values()))==1)
        phases={}
        for r,t in result['teachers'].items():
            phases[r]={phase:next((e['t']-t0 for e in t['events'] if e.get('to')==phase),None) for phase in ('align','ready','pick','complete')}
        i=min(range(len(rows)),key=dist.__getitem__)
        runs.append(dict(seed=entry['seed'],category=entry['category'],assigned_ends=entry['roles'],
            min_robot_distance_m=dist[i],closest_elapsed_sim_s=rows[i]['t']-t0,
            same_nearest_end_frames=sum(same),frames_N=len(rows),nearest_end_scope='evaluator distance, not task intent',
            first_phase_elapsed_sim_s=phases,configured_grasp_start_delays_s=result.get('grasp_start_delays_s'),
            max_stable_joint_hold_s=result.get('max_stable_hold_s'),outcomes=entry['outcomes'],raw=str(raw)))
    report=dict(runs=runs,scope=__doc__,evaluator_only=True,control_input=False,
        reproduce=str(Path(__file__).resolve()),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write(OPS/'robot-relations.json',report)
    lines=['# 두 로봇 관계: 원래 실패9 + cap_end6','', '|시드|담당 r1/r2|최소 로봇 간 거리 m (SIM초)|같은 최근접 끝 프레임/전체|첫 READY r1/r2 (SIM초)|첫 pick r1/r2 (SIM초)|','|---|---|---|---|---|---|']
    def fmt(x):return f'{x:.1f}' if x is not None else '없음'
    for r in runs:
        p=r['first_phase_elapsed_sim_s'];lines.append(f"|{r['seed']}|{r['assigned_ends']['r1']}/{r['assigned_ends']['r2']}|{r['min_robot_distance_m']:.3f} ({r['closest_elapsed_sim_s']:.1f})|{r['same_nearest_end_frames']}/{r['frames_N']}|{fmt(p['r1']['ready'])}/{fmt(p['r2']['ready'])}|{fmt(p['r1']['pick'])}/{fmt(p['r2']['pick'])}|")
    lines+=['','최근접 끝은 평가 거리이며 담당 끝이나 의도의 변경이 아니다. 거리가 작다는 사실만으로 접촉/충돌로 분류하지 않는다. 원본 고정 역할은 모든 실행에서 서로 다른 끝이다. 모든 계산은 평가 전용이며 교사 입력에 넣지 않았다.']
    (OPS/'robot-relations.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps([dict(seed=r['seed'],min_peer=r['min_robot_distance_m'],same_N=r['same_nearest_end_frames']) for r in runs]))
