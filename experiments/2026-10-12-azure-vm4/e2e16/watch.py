from pathlib import Path
import subprocess,json,time,sys
out=Path(__file__).resolve().parent;deadline=time.time()+28000;notified=set()
while time.time()<deadline:
 p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','azure4','python3 -'],input=(out/'poll-remote.py').read_text(),capture_output=True,text=True,timeout=90)
 if p.returncode:
  with (out/'watch-errors.jsonl').open('a') as f:f.write(json.dumps(dict(unix=time.time(),ssh_exit=p.returncode,error=p.stderr[-1000:]))+'\n')
  time.sleep(30);continue
 d=json.loads(p.stdout);tmp=out/'live.json.tmp';tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');tmp.replace(out/'live.json')
 for name,a in d['alerts'].items():
  if name in notified:continue
  (out/'alerts').mkdir(exist_ok=True);(out/'alerts'/name).write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
  r=a.get('result',{});body=out/'alerts'/(name+'.md')
  if a['kind']=='execution_error':
   text=f"VM4 16차 재실행 오류: `{a['run']}` (source `{(out/'source-sha.txt').read_text().strip()}`).\n상태 {r.get('status')}, {r.get('failure_type')}: {r.get('failure')}. 해당 실행만 중지·EXIT·원본 보관하며 나머지 짝 비교는 유지합니다.\n진단 근거: {a.get('log_tail','')[-2500:]}\n"
  else:text=f"VM4 16차 재실행 종료조건 3개 동시 달성: `{a['run']}`. 정상 LLM·자기 지도 완성·평가된 시작→끝 운반 모두 true. SIM {r.get('sim_s')}초 / wall {r.get('wall_s')}초. 보관·해시 회수는 별도 진행 중입니다.\n"
  body.write_text(text);q=subprocess.run(['gh','pr','comment','450','--body-file',str(body)],capture_output=True,text=True)
  if q.returncode==0:notified.add(name);(out/'alerts'/(name+'.posted')).write_text(q.stdout)
 compact=[dict(run=x['run'],exit=x['exit'],sim_s=x['progress'].get('sim_s'),phase=x['progress'].get('phase'),health_time=x['latest'].get('unix'),archived=bool(x['archive'])) for x in d['runs']]
 with (out/'watch-history.jsonl').open('a') as f:f.write(json.dumps(dict(unix=time.time(),runs=compact))+'\n')
 if len(d['runs'])==6 and all(x['archive'] for x in d['runs']):break
 time.sleep(30)
