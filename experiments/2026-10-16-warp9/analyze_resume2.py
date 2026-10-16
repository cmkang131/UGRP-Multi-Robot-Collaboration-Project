"""Finite gcp2 CPU recount; originals remain on gcp4. No simulation/model calls."""
import argparse,datetime,hashlib,json,math,os,platform,subprocess,sys
from pathlib import Path
import numpy as np


def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def playback(raw,out):
    out.mkdir()
    f=raw/'failure-rgb/manifest.json'
    if not f.exists():return dict(status='NO_FRAMES',raw=str(raw))
    m=read(f);frames=m['frames'];n=len(frames)
    if not n:return dict(status='NO_FRAMES',raw=str(raw))
    for row in frames:
        assert sha(raw/'failure-rgb'/row['path'])==row['sha256']
    source=str(raw/'failure-rgb/%04d.jpg')
    cols=min(4,n);rows=math.ceil(n/cols)
    # Display layout only; no controller or acceptance constants.
    subprocess.run(['ffmpeg','-loglevel','error','-y','-framerate','10','-i',source,
        '-vf',f'scale=240:180,tile={cols}x{rows}','-frames:v','1',str(out/'tail-10hz.jpg')],check=True)
    subprocess.run(['ffmpeg','-loglevel','error','-y','-framerate','40','-i',source,
        '-frames:v',str(n),'-vf','scale=480:360','-c:v','libx264','-crf','28','-pix_fmt','yuv420p',
        str(out/'own-only-4x.mp4')],check=True)
    video=out/'own-only-4x.mp4'
    assert video.stat().st_size<=8*1024**2  # User's playback export limit.
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)],text=True))
    overview=raw/'playback/manifest.json'
    value=dict(status='PARTIAL_OWN_ONLY',raw=str(raw),frame_N=n,range=[frames[0]['t'],frames[-1]['t']],
        hz=10,speed=4,camera=frames[0]['camera'],recording_only=True,training_rgb=False,
        whole_2hz_N=len(read(overview)['frames']) if overview.exists() else 0,
        missing='no saved overview/r2/r3 frames in this 0.3 SIM s profile; no composite or successful mission comparison',
        probe=probe,files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.iterdir() if p.is_file()},
        directly_viewed=False)
    write(out/'manifest.json',value);return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--retrieved',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):p.error('gcp2 CPU analysis only')
    a.output.mkdir(parents=True,exist_ok=False)
    lease=Path('/home/ugrp/ugrp-sim/leases/warp9-analysis.json')
    with lease.open('x') as f:json.dump(dict(task='warp9',pid=os.getpid(),started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite profile/state/playback recount',concurrency=0),f)
    try:
        sys.path.insert(0,str(a.source));from scripts.analyze_warp9_profile import collect,markdown
        base=a.retrieved/'profile-gcp4-r1';r2=a.retrieved/'trace-gcp4-r2';r3=a.candidate
        runs=[('R1',base),('R2_trace',r2),('R3_scratch_graph',r3)]
        baseline=collect(base);write(a.output/'scaling.json',baseline)
        (a.output/'timing-table.md').write_text(markdown(baseline))
        variants=[];integrity=[]
        for name,root in runs:
            row=collect(root)['rows'][2];progress=read(root/'n16/progress.json')
            row.update(round=name,loop_wall_s=progress['wall_s'],fixed_work_wall_per_sim=progress['wall_s']/progress['sim_s'])
            variants.append(row)
            for n in (1,4,16,64):
                folder=root/f'n{n}';manifest=folder/'SHA256SUMS.json'
                if not manifest.exists():continue
                hashes=read(manifest);present=[key for key in hashes if (folder/key).is_file()]
                integrity.append(dict(round=name,nworld=n,verified_available_n=len(present),
                    not_retrieved=[key for key in hashes if key not in present],
                    mismatches=[key for key in present if sha(folder/key)!=hashes[key]]))
        aa,bb=(np.load(root/'n16/group-0-final-state.npz') for root in (r2,r3))
        parity={k:dict(exact=bool(np.array_equal(aa[k],bb[k],equal_nan=True)),
            max_abs=float(np.max(np.abs(aa[k].astype(float)-bb[k].astype(float)))) if aa[k].size else 0,
            coordinates='native mixed coordinates; not a position error in metres',
            reference_replica_span=float(np.max(np.ptp(aa[k].astype(float),axis=0))) if aa[k].size else 0)
            for k in aa.files}
        settings=[read(root/'n16/physics-settings.json')['groups'][0] for root in (r2,r3)]
        keys=('dt','noslip_iterations','solver','iterations','ls_iterations','numerics')
        config_equal={key:settings[0][key]==settings[1][key] for key in keys}
        initial_equal=read(r2/'n16/initial-state.json')==read(r3/'n16/initial-state.json')
        audit=[]
        for name,root in runs:
            for i in range(16):
                raw=root/f'n16/world-{i:03d}/raw';d=read(raw/'result.json')
                audit.append(dict(round=name,world=i,status=d['status'],input_audit=d.get('input_audit'),
                    scope='initial start/fold only; no held/carry audit qualification',raw=str(raw),sha256=sha(raw/'result.json')))
        write(a.output/'variants.json',variants);write(a.output/'state-comparison.json',dict(initial_equal=initial_equal,
            physics_settings_equal=config_equal,fields=parity,adopted=False,
            interpretation='not bit-identical; allocator/capture effect vs normal GPU nondeterminism not isolated; no equivalence claim'))
        write(a.output/'integrity.json',integrity);write(a.output/'input-audits.json',audit)
        videos={}
        for name,root in runs[1:]:videos[name]=playback(root/'n16/world-000/raw',a.output/name)
        write(a.output/'playback.json',videos)
        trace=next((r2/'n16/groups').rglob('physics-event-trace.json'));write(a.output/'physics-event-trace.json',read(trace))
        stages=[dict(stage='submitted_N16_diagnostic_rounds',cumulative_pass_n=3,rejected_n=0),
            dict(stage='fixed_0.3_SIM_work_complete',cumulative_pass_n=3,rejected_n=0),
            dict(stage='throughput_defect_resolved',cumulative_pass_n=0,rejected_n=3)]
        rejection=dict(unit='diagnostic_configuration; not task trials',stages=stages,
            rejections=[dict(category='throughput',reason='NoSlip dominated physical interval remains after round3',blocked_object='MJWarp NoSlip execution',minimum_gap_m=None,gap_scope='timing_not_physical_gap',n=3),
                dict(category='HOST_ERROR',reason='N64 kernel global OOM SIGKILL',blocked_object='gcp4 host RAM',minimum_gap_m=None,gap_scope='memory_not_physical_gap',n=1),
                dict(category='state_comparison',reason='R3 final integration state not bit-identical',blocked_object='R3 scratch/full-period candidate',minimum_gap_m=None,gap_scope='mixed_state_coordinates_not_physical_gap',n=1)],
            task_funnel=dict(valid_trials=0,first30=0,lift_carry=0,transport=0,destination=0,place=0,complete=0,cap_end=0,LLM=0),
            raw=[str(x[1]) for x in runs],reproduction=sys.argv)
        write(a.output/'rejection-table.json',rejection)
        summary=dict(status='NOT_READY_STOP_REPEATED_3',physics_host='gcp4',analysis_host=platform.node(),
            source_shas=sorted({read(root/'n16/summary.json')['source_sha'] for _,root in runs}),
            model_calls=0,first30='NOT_RUN',task_trials=0,candidate_adopted=False,
            N64='HOST_ERROR_kernel_OOM_no_phase_timings',n4_control_L4_separation='not_implemented',
            coreweave_registration='offline fixed; actual Mac relay/E2E not verified',
            raw=[str(x[1]) for x in runs],rejection_table=str(a.output/'rejection-table.json'),
            analysis_script_sha256=sha(Path(__file__)),utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        write(a.output/'summary.json',summary)
        write(a.output/'SHA256SUMS.json',{str(x.relative_to(a.output)):sha(x) for x in a.output.rglob('*') if x.is_file()})
        print(json.dumps(summary))
    finally:
        if read(lease)['pid']!=os.getpid():raise RuntimeError('lease ownership changed')
        lease.unlink()


if __name__=='__main__':main()
