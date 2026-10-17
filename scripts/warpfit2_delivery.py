"""Format the completed source-host analysis; no simulator imports."""
import json
from pathlib import Path
import platform
from statistics import median


def main():
    if not platform.node().startswith('ugrp-act-l4-gcp6'):raise ValueError('gcp6 analysis only')
    p=Path('/home/ugrp/ugrp-sim/runs/warpfit2/analysis-final')
    rows=json.loads((p/'rows.json').read_text());summary=json.loads((p/'summary.json').read_text())
    if summary['runs']!=25 or summary['completed']!=25:raise ValueError('incomplete comparison')
    lines=['# warpfit2 — native-v1 다음 runtime 비교','',
        '3라운드25/25 고정명령 배치 완주, HOST_ERROR0·cap_end0. 기본값 변경0. 상자 선택30/30은 모든 비교에서 유지했고 빔은 각16/16 또는64/64 짧은 유지를 충족했다. 동일 reset 복제이며 독립 seed 일반화·교사/학생/E2E 관문이 아니다.','',
        '|round/N|runtime|구간|기준 GPU ms/step|후보 GPU ms/step|기준/후보|',
        '|---|---|---|---:|---:|---:|']
    for pair in summary['pairs']:
        b=next(r for r in rows if r['output']==pair['baseline']);c=next(r for r in rows if r['output']==pair['candidate'])
        lines.append(f"|R{c['round']}/N{c['nworld']}|{c['profile']}|{c['kind']} repeat{c['repeat']}|{b['physical_gpu_ms_per_step']:.6f}|{c['physical_gpu_ms_per_step']:.6f}|{pair['gpu_speedup']:.4f}×|")
    lines += ['', '## 횡펄스: 해당축 부호 있는 변위','',
        '같은 tape를 받은 세계들의 중앙값(펄스 끝/정지1초 후)이다. 원본 CSV에는 모든 XY/yaw·tilt·world를 보존한다. FOLDED/PR564 초기 겹침 제거 진단 장면이며 HIGH·생산 보정이 아니다. 400ms·warm 예측값은 미등록으로 null이다.','',
        '|round/N|runtime|cold60 mm|warm60 mm|cold400 mm|warm400 mm|','|---|---|---:|---:|---:|---:|']
    for r in rows:
        if r['kind']!='drive':continue
        values=[]
        for name in ('left-0.06','warm-left-0.06','left-0.4','warm-left-0.4'):
            values.append(' / '.join(f"{median(q['delta_xyyaw'][1]*1000 for q in r['pulses'] if q['case']==name and q['phase']==phase):.3f}"
                for phase in ('pulse','pulse_plus_stop')))
        lines.append(f"|R{r['round']}/N{r['nworld']}|{r['profile']}|"+'|'.join(values)+'|')
    lines += ['', '## 빔 상대 slip P95','', '|round/N|runtime|slip P95 mm|유지|','|---|---|---:|---:|']
    for r in rows:
        if r['kind']=='beam':lines.append(f"|R{r['round']}/N{r['nworld']}|{r['profile']}|{r['slip_p95_mm']:.6f}|{r['fully_retained_worlds']}/{r['measured_worlds']}|")
    lines += ['', '기존 교사12mm+전 손가락 양의 힘과 같은 라운드 native-v1 P05/P95로 비교했다. 백분위에서 제외된 프레임은 실제 낙하가 아니다. CUDA event 시간은 고정명령·매step 최대치 기록 커널을 포함하며 setup/JIT·RGB 기록은 제외한다. wall/SIM은 기록·평가를 포함한 배치 지연이며 세계당 상각값과 다르다.']
    (p/'delivery.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(runs=summary['runs'],completed=summary['completed'],box30=summary['box30'],
        pairs=[r for r in summary['pairs'] if r['round']==3]),ensure_ascii=False))


if __name__=='__main__':main()
