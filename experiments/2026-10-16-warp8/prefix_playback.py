"""gcp2 CPU preview of an unfinished prefix; never a success/failure verdict."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path('/home/ugrp/ugrp-sim')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--receive', action='store_true')
    p.add_argument('--label', default='v1')
    p.add_argument('--worlds', default='0,1')
    p.add_argument('--terminal', action='store_true')
    p.add_argument('--host-error', action='store_true')
    p.add_argument('--origin-proof', type=Path)
    p.add_argument('--batch', default='beam40-r1')
    p.add_argument('--tail-preview', action='store_true')
    a = p.parse_args()
    assert a.snapshot.is_absolute() and a.snapshot.parent == ROOT / 'runs'
    assert a.batch not in ('.', '..') and Path(a.batch).name == a.batch
    lease = ROOT / 'leases/warp8-prefix-playback.json'
    assert not lease.exists()
    now = dt.datetime.now(dt.timezone.utc)
    lease.write_text(json.dumps(dict(task='warp8-prefix-playback', pid=os.getpid(), started_at=now.isoformat(),
        expected_end=(now+dt.timedelta(minutes=15)).isoformat(), purpose='CPU-only kinematic preview; no physics/model')))
    try:
        if a.receive:
            a.snapshot.mkdir(exist_ok=False)
            with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
                for member in archive:
                    assert member.name.startswith(a.batch + '/')
                    archive.extract(member, a.snapshot, filter='data')
            return
        import numpy as np
        import mujoco
        original = a.snapshot / a.batch
        source_summary = json.loads((original/'summary.json').read_text())
        for world_id in map(int,a.worlds.split(',')):
            world = original / f'world-{world_id:03d}'
            rows = []
            eval_path=world/'raw/eval-only.jsonl'
            text=eval_path.read_text() if eval_path.exists() else subprocess.check_output(
                ['zstd','-qdc',str(eval_path)+'.zst'],text=True)
            for line in text.splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # Preserve original bytes; only complete rows enter this preview.
            index = {round(r['t']*10):np.asarray(r['joints']) for r in rows}
            velocities={};overlap=0
            native=original/f'world-{world_id:03d}-states.npz'
            if native.exists():
                states=np.load(native)
                for tick,qpos,qvel in zip(states['ticks'],states['qpos'],states['qvel']):
                    tick=int(tick)
                    if tick in index:
                        assert np.array_equal(qpos,index[tick]), 'NPZ/evaluator state disagreement'
                        overlap+=1
                    index[tick]=qpos;velocities[tick]=qvel
            proof=json.loads(a.origin_proof.read_text()) if a.origin_proof else source_summary
            if a.origin_proof:
                assert proof['source_sha']==source_summary['source_sha'] and proof['cases_sha256']==source_summary['cases_sha256']
                assert proof['world_indices']==source_summary['world_indices']
            if 'native_initialization_only_sim_s' in proof:
                origin=proof['native_initialization_only_sim_s'][world_id]
            elif (world/'tail-ring-10hz/journal.jsonl').exists():
                origin=json.loads((world/'tail-ring-10hz/journal.jsonl').read_text().splitlines()[0])['world_t']
            else:
                raise ValueError('authoritative GPU origin required; first evaluator row follows startup commands')
            # Drop RGB times whose exact saved evaluator row is not yet flushed.
            # Source snapshot stays immutable; derived inputs use symlinks.
            derived = a.snapshot / f'derived-{a.label}-world-{world_id:03d}'
            folder = derived / 'world-000'
            (folder/'review-2hz').mkdir(parents=True, exist_ok=False)
            (folder/'raw').symlink_to(world/'raw', target_is_directory=True)
            for rid in ('r1','r2'):
                out = folder/'review-2hz'/rid
                out.mkdir()
                for image in sorted((world/'review-2hz'/rid).glob('*.jpg')):
                    if round((origin+int(image.stem)/10)*10) in index:
                        (out/image.name).symlink_to(image)
            # scene-v5 textures belong to the frozen adapter, not its older
            # grasp dependency. Same verified asset root as warp6 playback.
            asset = ROOT / 'src/835ccef26aa84b08cc8f7e256fd0f43aa1583ef9'
            os.chdir(asset)
            model = mujoco.MjModel.from_xml_string((world/'raw/scene.xml').read_text())
            order=sorted(index)
            np.savez_compressed(derived/'world-000-states.npz', ticks=order,
                qpos=[index[t] for t in order],qvel=[velocities.get(t,np.zeros(model.nv)) for t in order])
            # qvel is unused by mj_kinematics and rendering. No C step is called.
            summary = dict(source_summary, native_initialization_only_sim_s=[origin])
            (derived/'summary.json').write_text(json.dumps(summary))
            terminal_rows=[]
            tail_jpeg_pairs=0
            tail_missing_state_times=[]
            ring=world/'tail-ring-10hz'
            if a.terminal or a.tail_preview:
                # Existing ring is100 samples=10 SIM seconds at10Hz. Older
                # identical JPEGs may still hash-match an overwritten slot.
                for line in (ring/'journal.jsonl').read_text().splitlines()[-100:]:
                    record=json.loads(line);files={}
                    for rid,item in record['files'].items():
                        image=ring/Path(item['path']).name
                        if image.exists() and hashlib.sha256(image.read_bytes()).hexdigest()==item['sha256']:
                            files[rid]=str(image)
                    if len(files)==len(record['files']):
                        tail_jpeg_pairs+=1
                        if round(record['world_t']*10) in index:
                            terminal_rows.append(dict(world_t=record['world_t'],files=files))
                        else:
                            tail_missing_state_times.append(record['world_t'])
                if a.terminal:
                    assert len(terminal_rows)==100, 'terminal last10 SIM/10Hz evidence incomplete'
            (folder/'tail-10hz.json').write_text(json.dumps(terminal_rows))
            playback = ROOT/'ops-reviews/warp8/playback'/a.snapshot.name/f'{a.label}-world-{world_id:03d}'
            subprocess.run([str(ROOT/'ugrp/.venv-sim/bin/python'),
                str(ROOT/'ops-reviews/warp6/make_playback.py'), '--run',str(derived),
                '--out',str(playback),'--asset-root',str(asset)], check=True,
                cwd=asset, env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
            meta = playback/'playback-meta.json'
            info = json.loads(meta.read_text())
            info.update(playback_helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='unfinished prefix sanity preview, not failure/success or root-cause evidence; no physics step',
                original_world=world_id, source_snapshot=str(original), simulation_host='gcp3', analysis_host='gcp2_CPU',
                reconstruction='native NPZ + exact evaluator qpos for missing terminal states; missing qvel=0 unused by renderer',
                native_state_file=str(native) if native.exists() else None,
                native_evaluator_overlap_exact_N=overlap,authoritative_backend_origin=origin,
                terminal_10hz_scope='not included in this nonterminal preview; native recording rings remain on gcp3')
            if a.tail_preview:
                info['terminal_10hz_scope']=f'{len(terminal_rows)} hash-verified native JPEG pairs with exact saved evaluator states; live prefix, not a terminal outcome'
                info['live_tail_evidence']=dict(JPEG_pairs_verified_N=tail_jpeg_pairs,
                    synchronized_N=len(terminal_rows),missing_saved_state_times=tail_missing_state_times)
            if a.terminal:
                counter_path=ROOT/'ops-reviews/warp8-collect_gate.py'
                spec=importlib.util.spec_from_file_location('counter',counter_path)
                counter=importlib.util.module_from_spec(spec);spec.loader.exec_module(counter)
                raw=counter.data(world/'raw/result.json')
                if a.host_error:
                    assert source_summary['status']=='HOST_ERROR'
                    recount=dict(success=None,status='HOST_ERROR',physical_outcome_unknown=True,
                        error=source_summary.get('error'),source_world_status=raw.get('status'))
                else:
                    assert raw['status']=='complete'
                    recount=counter.beam_recount(raw,world/'raw')
                    assert recount['agrees'], recount
                # Early full frames are2Hz, terminal native frames10Hz. Display
                # at3x, holding early samples on a30fps output; no new evidence.
                full_times=info['sim_world_range'][0]
                prefix=[path for i,path in enumerate(sorted((playback/'full').glob('*.jpg')))
                        if full_times+i*.5 < terminal_rows[0]['world_t']-1e-8]
                concat=playback/'full-tail.ffconcat'
                lines=['ffconcat version 1.0']
                for image in prefix:
                    lines += ["file '"+str(image)+"'",'duration '+str(.5/3)]
                for image in sorted((playback/'tail').glob('*.jpg')):
                    lines += ["file '"+str(image)+"'",'duration '+str(.1/3)]
                concat.write_text('\n'.join(lines)+'\n')
                video=playback/'playback-full-tail-3x.mp4'
                subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(concat),
                    '-r','30','-fps_mode','cfr','-c:v','libx264','-crf','30','-pix_fmt','yuv420p',str(video)],check=True)
                assert video.stat().st_size<=8_000_000
                probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(video)]))
                info.update(scope='completed individual beam teacher world; whole40-world gate still pending; evaluator-only reconstruction, no physics step',
                    recount=recount,counter_sha256=hashlib.sha256(counter_path.read_bytes()).hexdigest(),
                    terminal_10hz_scope='100 hash-verified native JPEG pairs at exact evaluator times',
                    representative_video=dict(path=str(video),bytes=video.stat().st_size,
                        sha256=hashlib.sha256(video.read_bytes()).hexdigest(),ffprobe=probe),
                    display_sampling='full prefix2Hz then terminal10Hz,3x playback; early images held on30fps display')
                if a.host_error:
                    info['scope']='HOST_ERROR: last valid pre-overflow RGB/evaluator states; not physical failure; no physics step'
            meta.write_text(json.dumps(info,indent=2)+'\n')
            print(str(playback),flush=True)
    finally:
        assert json.loads(lease.read_text())['pid'] == os.getpid()
        lease.unlink()


if __name__ == '__main__':
    main()
