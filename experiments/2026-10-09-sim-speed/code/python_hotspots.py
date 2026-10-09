from pathlib import Path
import json,pstats
root=Path('/Users/changmin/projects/ugrp/outputs/simspeed-20261009')
stats=pstats.Stats(str(root/'physical-abba-v2/physics.prof'))
functions=sorted(((k,v) for k,v in stats.stats.items() if k[0]!='~'),key=lambda x:x[1][2],reverse=True)[:10]
result=[dict(function=f'{k[0]}:{k[1]}:{k[2]}',calls=v[1],self_s=v[2],percent=100*v[2]/stats.total_tt,cumulative_s=v[3]) for k,v in functions]
(root/'python-hotspots.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['\n### Python 함수 상위 10개 (동기 재생)','', '분모는 cProfile 전체 self time(C 확장·렌더 대기 포함), Python 함수만 정렬했다.', '|함수|호출 수|self s|전체 대비|','|---|---:|---:|---:|']
for r in result:
    name=r['function'].replace('/Users/changmin/projects/ugrp-wt/sim-speed/','').replace('/Users/changmin/Project-Runtimes/ugrp/.venv-sim-worker-mac/lib/python3.12/site-packages/','')
    lines.append(f"|`{name}`|{r['calls']:,}|{r['self_s']:.4f}|{r['percent']:.2f}%|")
with (root/'results.md').open('a') as out:out.write('\n'.join(lines)+'\n')
print(json.dumps(result[:3],indent=2))
