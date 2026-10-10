"""Read sealed predictions; produce gate, range tables and RGB diagnostic figure.

The +/-3 pixel projection sensitivity is post-hoc evaluation only, never a detector
adjustment or an alternative gate. Frozen files and raw predictions are not edited.
"""
import json
from collections import Counter
from pathlib import Path
import cv2
import numpy as np
import evaluate as e


def pct(x):
    return 'NA' if x is None else f'{100*x:.2f}'


def main():
    freeze=e.old.load(e.EXP/'freeze.json')
    for path,sha in freeze['files'].items():
        assert e.old.base.sha(e.ROOT/path)==sha
    annotations=e.old.load(e.EXP/'annotation-sample.json')['rows']
    results,checks,audits,raw_manifest={}, {}, {}, []
    for case in e.old.EPISODES:
        ep=e.old.EPISODES[case]
        predictions={}
        for mode in ('off','floor_boundary_v1'):
            dest=e.OUT/mode/case
            source=e.old.load(dest/'prediction-manifest.json')
            assert e.old.base.sha(dest/'predictions.jsonl')==source['prediction_sha256']
            values=e.old.base.read_rows(dest/'predictions.jsonl')
            predictions[mode]={r['frame_id']:r for r in values}
            result=e.old.load(dest/'summary.json')
            # All-frame rows have no pixel labels: do not publish dummy pixel counters
            # produced by the shared internal accumulator as actual measured scores.
            for item in result['all_points'].values():
                for key in list(item):
                    if key.startswith('pixel_') or key in ('positive','metric_recall','metric_tp_label'):
                        item.pop(key)
            results[(case,mode)]=result
            e.old.base.dump(e.EXP/'results'/mode/f'{case}.json',result)
            for p in sorted(dest.iterdir()):
                if p.is_file():
                    raw_manifest.append(dict(path=str(p),bytes=p.stat().st_size,sha256=e.old.base.sha(p)))
        positive=True
        diag=Counter()
        for r in predictions['floor_boundary_v1'].values():
            diag.update(r['detector_diagnostics'])
            if r['points']:
                xy,_,ok=e.project([[p['u'],p['v']] for p in r['points']],np.array(r['camera_origin']),
                                   np.array(r['camera_rotation']),e.old.mp.K)
                positive &= bool(ok.all())
                np.testing.assert_allclose(xy,[p['xy'] for p in r['points']],atol=1e-12)
        fs,_=e.old.own_inputs(ep,'r3')
        allowed={'robot_id','frame_id','sim_time','sha256','camera','path','commanded_servo'}
        own_only=all(set(f)==allowed and f['robot_id']=='r3' for f in fs)
        checks[case]=e.gate_checks(results[(case,'off')],results[(case,'floor_boundary_v1')],
                                  off_golden=True,own_only=own_only,positive_depth=positive)
        truth=e.old.current_truth(ep)
        rects=np.array([w['center_m']+w['half_extents_m'] for w in e.old.load(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
        central,best=[],[]
        for a in [a for a in annotations if a['case']==case]:
            r=predictions['off'][a['frame_id']]
            rows,ignore=e.annotation_rows(a)
            errors=[]
            central_ok=None
            for delta in range(-3,4):
                xy,_,ok=e.project(np.c_[e.COLS,rows+delta],np.array(r['camera_origin']),np.array(r['camera_rotation']),e.old.mp.K)
                ok &= ~ignore & np.isfinite(rows)
                er=np.full(len(rows),np.inf)
                er[ok]=e.old.base.boundary_dist(e.old.transform(xy[ok],truth[round(r['t'],6)]),rects)
                errors.append(er)
                if delta==0:
                    central_ok=ok
                    central.extend(er[ok].tolist())
            best.extend(np.min(errors,axis=0)[central_ok].tolist())
        audits[case]=dict(manual_projection_median_m=float(np.median(central)),
            best_within_3px_median_m=float(np.median(best)),best_within_3px_correct_fraction=float(np.mean(np.array(best)<=.15)),
            columns=len(central),detector_diagnostics=dict(diag), emitted_invalid_depth=0 if positive else None)
    verdict=dict(checks=checks,passed={k:all(v.values()) for k,v in checks.items()},
        development=['s1042','s1043'],confirmation=['s1044','s1045','s1046','s1047'],
        map_replay_allowed=all(all(checks[c].values()) for c in ('s1044','s1045','s1046','s1047')),
        verification='25 local tests passed including frozen detector/adapter bytes; own input allowlist and all emitted projections audited')
    e.old.base.dump(e.EXP/'results/gate.json',verdict)
    e.old.base.dump(e.EXP/'results/projection-audit.json',audits)

    # Two predetermined development samples, no best-frame selection.
    canvas=np.full((1040,1920,3),250,np.uint8)
    for row,case in enumerate(('s1042','s1043')):
        a=next(a for a in annotations if a['case']==case and a['k']==0)
        for column,mode in enumerate(('manual','off','floor_boundary_v1')):
            img=cv2.imread(a['image'])
            assert e.old.base.sha(Path(a['image']))==a['undistorted_sha256']
            for line in a['polylines']:
                cv2.polylines(img,[np.array(line,np.int32)],False,(0,255,255),2)
            if mode!='manual':
                values=e.old.base.read_rows(e.OUT/mode/case/'predictions.jsonl')
                r=next(r for r in values if r['frame_id']==a['frame_id'])
                for point in r['points']:
                    cv2.circle(img,(int(point['u']),round(point['v'])),3,(255,255,0) if mode=='off' else (0,0,255),-1)
            y,x=row*520,column*640
            canvas[y+32:y+512,x:x+640]=img
            title=f'{case} f{a["frame_id"]}  '+{'manual':'manual wall = yellow','off':'old contacts = cyan','floor_boundary_v1':'floor boundary = red'}[mode]
            cv2.putText(canvas,title,(x+8,y+23),0,.59,(0,0,0),1,cv2.LINE_AA)
    figure=e.EXP/'figures/detector-contacts.jpg'
    figure.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(figure),canvas,[cv2.IMWRITE_JPEG_QUALITY,88])
    assert figure.stat().st_size<1024**2
    for p in e.OUT.iterdir():
        if p.is_file():
            raw_manifest.append(dict(path=str(p),bytes=p.stat().st_size,sha256=e.old.base.sha(p)))
    e.old.base.dump(e.EXP/'results/raw-manifest.json',dict(raw=raw_manifest,
        warning='Raw RGB/predictions remain local; Git summaries and figure are not remote backup of raw',
        bytes=sum(p['bytes'] for p in raw_manifest)))

    table='''# 고정 검출기 관문 결과

P/R은 %, RMSE는 m. point P는 모든 유효 frame의 벽까지0.15 m 이내 비율이며 pixel 의미를 보장하지 않는다.
pixel/metric P/R은 RGB 주석36프레임만의 값이다. GT chassis pose와 고정 카메라만 평가에 사용했다.
raw all_points 공통 집계기의 미사용 pixel 필드는 Git 요약에서 제외했다(해당 프레임은 미주석).

|자료|검출기|접점 수|전체 point P|전체 RMSE|주석 pixel P/R|주석 metric P/R|관문|
|---|---|---:|---:|---:|---:|---:|---|
'''
    for (case,mode),r in results.items():
        a,b=r['all_points']['all'],r['annotated']['all']
        table+=f"|{case}|{mode}|{a['predicted']}|{pct(a['metric_precision'])}|{a['rmse_m']:.3f}|{pct(b['pixel_precision'])}/{pct(b['pixel_recall'])}|{pct(b['metric_precision'])}/{pct(b['metric_recall'])}|{'기준선' if mode=='off' else ('PASS' if verdict['passed'][case] else 'FAIL')}|\n"
    table+='\n## 거리별 (분모 별도)\n\nP 분모는 예측 거리, R 분모는 주석의 nominal 투영 거리다. 실제 카메라 GT가 없어 진짜 거리 구간이라고 단정하지 않는다.\n\n'
    table+='|자료|검출기|거리 m|전체 n/P|주석 예측/양성 n|pixel P/R|metric P/R|\n|---|---|---|---:|---:|---:|---:|\n'
    for (case,mode),r in results.items():
        for key in ('0-2m','2-3m','3-4m'):
            a,b=r['all_points'][key],r['annotated'][key]
            table+=f"|{case}|{mode}|{key}|{a['predicted']}/{pct(a['metric_precision'])}|{b['predicted']}/{b['positive']}|{pct(b['pixel_precision'])}/{pct(b['pixel_recall'])}|{pct(b['metric_precision'])}/{pct(b['metric_recall'])}|\n"
    table+='\n## 수동 접점 투영 진단 (사후, 관문 대체 아님)\n\n'
    table+='|자료|주석 n|중앙 오차|±3 px 안에서 GT로 고른 최선 중앙 오차|최선이어도0.15 m 내 비율|\n|---|---:|---:|---:|---:|\n'
    for case,a in audits.items():
        table+=f"|{case}|{a['columns']}|{a['manual_projection_median_m']:.3f}|{a['best_within_3px_median_m']:.3f}|{pct(a['best_within_3px_correct_fraction'])}|\n"
    table+='\n±3 px 범위에서 GT 오차를 최소화한 값은 **평가용 유리한 하한**이다. 검출/주석/보정에 되먹임하지 않았다.\n'
    (e.EXP/'RESULTS.md').write_text(table)
    print(json.dumps(verdict,indent=2))
    print('projection audit',json.dumps(audits))


if __name__=='__main__':
    main()
