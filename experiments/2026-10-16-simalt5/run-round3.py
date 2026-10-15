"""Last round: preserve the complete C312 compiled geometry representation."""
import json
import os
from pathlib import Path
import signal
import subprocess

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt5')
OLD=ROOT.parent/'simalt3'
SOURCE=Path('/home/ugrp/ugrp-sim/src/62563f51')
PY=OLD/'warp-env/bin/python'
SHA=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
ENV={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'}


def main():
    records=json.loads((ROOT/'round1-summary.json').read_text())
    corrected=[x for x in records if x['name'].startswith('corrected-')]
    reject={'stage':'R1/R2 complete; before final compiled geometry transfer',
      'distribution':[{'reason':'base_endpoint_over_5mm','count':1,'blocking_object':'r1__robot / floor',
        'minimum_gap_m':None,'gap_note':'trajectory discrepancy; not a clearance rejection',
        'observed_m':next(x['base_endpoint_m'] for x in corrected if x['case']=='grip')},
        {'reason':'unloaded_endpoint_pass','count':3,'blocking_object':'none',
         'minimum_gap_m':None,'gap_note':'trajectory gate'},
        {'reason':'compiled_mesh_principal_axis_representation_differs','count':1,
         'blocking_object':'roller mesh geometry and compiled caches','minimum_gap_m':None,
         'gap_note':'simalt4 same-shape body-frame Hausdorff maximum8.883e-10m; C312 arrays transferred exactly, no shape tuning'}],
      'funnel':[{'gate':'complete corrected tapes','entered':4,'passed':4,'rejected':0},
        {'gate':'endpoint_5mm_2deg','entered':4,'passed':3,'rejected':1},
        {'gate':'hold_bilateral_time_samples','entered':30,'passed':30,'rejected':0},
        {'gate':'small_scene_complete','entered':1,'passed':0,'rejected':1}],
      'raw':str(ROOT/'warp-compiled312-grip/steps.npz'),
      'geometry_reference':str(ROOT/'compiled-geometry312.npz'),
      'geometry_layout_check':str(ROOT/'geometry-layout-check.json')}
    (ROOT/'rejection-before-round3.json').write_text(json.dumps(reject,indent=2)+'\n')
    def command(name,engine,case):
        return list(map(str,[PY,'-u',SOURCE/'scripts/simalt_step_probe.py','--enabled',
            '--fixture',OLD/'fixture','--out',ROOT/name,'--engine',engine,'--case',case,
            '--sha',SHA,'--capacity-reference',ROOT.parent/'simalt4/rev5/dense-capacity.json',
            '--dense-capacity-v1','--backend-mode','legacy-plane-v1',
            '--compiled-reference-v1',ROOT/'compiled-312.json',
            '--compiled-geometry-312-v1',ROOT/'compiled-geometry312.npz',
            '--record-own-rgb',OLD/'runtime/source']))
    jobs=[('c316-geometry312-grip',command('c316-geometry312-grip','cpu','grip'))]
    jobs += [('warp-geometry312-'+case,command('warp-geometry312-'+case,'warp',case))
             for case in ('forward','side','turn','grip')]
    plan={'round':3,'last_round':True,'source_sha':SHA,'rejection_table':str(ROOT/'rejection-before-round3.json'),
          'jobs':jobs,'new_physical_parameters':False}
    assert Path(plan['rejection_table']).is_file()
    (ROOT/'round3-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    native_log=(ROOT/(jobs[0][0]+'.log')).open('x')
    native=subprocess.Popen(jobs[0][1],stdout=native_log,stderr=subprocess.STDOUT,env=ENV,start_new_session=True)
    try:
        for name,cmd in jobs[1:]:
            with (ROOT/(name+'.log')).open('x') as log:
                subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=ENV,check=True)
            info=json.loads((ROOT/name/'result.json').read_text())
            print(name,info['status'],info.get('error',''),flush=True)
            if info['status']!='complete':raise RuntimeError(name+' incomplete')
        if native.wait()!=0:raise RuntimeError('native control process failed')
        if json.loads((ROOT/jobs[0][0]/'result.json').read_text())['status']!='complete':
            raise RuntimeError('native control incomplete')
    finally:
        if native.poll() is None:
            os.killpg(native.pid,signal.SIGINT)
            native.wait()
        native_log.close()
    summaries=[]
    pairs=[('geometry312-'+case,ROOT.parent/('simalt4/c312-'+case),ROOT/('warp-geometry312-'+case))
           for case in ('forward','side','turn','grip')]
    pairs += [('geometry-native-vs-c312',ROOT.parent/'simalt4/c312-grip',ROOT/'c316-geometry312-grip'),
              ('geometry-backend',ROOT/'c316-geometry312-grip',ROOT/'warp-geometry312-grip')]
    for name,reference,candidate in pairs:
        out=ROOT/('analysis-'+name)
        with (ROOT/('analysis-'+name+'.log')).open('x') as log:
            subprocess.run(list(map(str,[PY,SOURCE/'scripts/simalt_step_analysis.py','--fixture',OLD/'fixture',
                '--reference',reference,'--candidate',candidate,'--out',out])),stdout=log,stderr=subprocess.STDOUT,check=True)
        summaries.append({'name':name,**json.loads((out/'summary.json').read_text())})
    (ROOT/'round3-summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    print('ROUND3_COMPLETE',flush=True)


if __name__=='__main__':main()
