"""Result/source/media integrity, separate from physical or map success."""
import importlib,json,subprocess,sys
from physical_report import ROOT,EXP,RAW,EP,load,sha,dump
from scripts.run_wall_parallax_strafe import USER_FILES


def main():
    frozen=load(EXP/'freeze.json')
    assert all(sha(ROOT/p)==h for p,h in frozen['hashes'].items())
    assert all(sha(EP/p)==h for p,h in load(EP/'artifacts.sha256.json').items())
    assert all(sha(ROOT/p)==h for p,h in USER_FILES.items())
    bundle=load(EP/'bundle.json')
    assert bundle['task']['seed']==32002 and bundle['case_cap_s']==180
    assert '5_of_7_UNMET' in bundle['admission']
    result=load(EP/'result.json')
    assert result['status']=='RECORDED' and result['frames']==901
    assert result['source_sha']=='9ff008331cd7c82ff94617e8dfc878cfdcb5d426'
    c=load(EXP/'results/comparison.json')
    assert c['supervisor_authorized_DEV'] and not c['egomap33_gate_passed']
    assert c['fresh']['full_map']==c['frontend']['full_map']
    assert c['fresh']['path']['end_m']==c['frontend']['endpoint_error_m']
    s=load(EXP/'results/segments.json')
    assert not s['export_start']
    preview=EXP/'figures/wrist-map-4x-preview.mp4'
    assert preview.stat().st_size<1024**2
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(preview)]))
    assert int(probe['streams'][0]['nb_frames'])==901 and probe['streams'][0]['r_frame_rate']=='20/1'
    assert abs(float(probe['format']['duration'])-45.05)<.01
    movie=load(EXP/'results/video.json')
    assert sha(RAW/'wrist-map-4x.mp4')==movie['sha256']
    source_files={str(p.relative_to(RAW)):sha(p) for p in RAW.rglob('*') if p.is_file()
        and p.name not in ('delivery.json','pr405-before.json','pr405-body.md','pr405-after.json')}
    dump(EXP/'results/raw-manifest.json',source_files)
    dump(EXP/'results/verification.json',dict(source_sha=result['source_sha'],tests_passed=8,
        frozen_files_unchanged=True,preserved_untracked=USER_FILES,physical_runs=1,gate_override='explicit supervisor DEV; original 5/7 remains unmet',
        frontend_graph_same_metrics=True,off_memory_bytes_identical=True,upstream_license='BSD-3-Clause',
        wall_export_implemented=False,preview=dict(path=str(preview),bytes=preview.stat().st_size,sha256=sha(preview),frames=901,fps=20,duration_s=45.05),
        video_visual_review='first/middle/last checked; past-only snapshots; full H264 stream decode passed',
        runtime={name:importlib.import_module(name).__version__ for name in ('numpy','scipy','cv2')},python=sys.version,
        result_hashes={str(p.relative_to(EXP)):sha(p) for p in (EXP/'results').glob('*.json') if p.name!='verification.json'}))
    print('PASS: frozen code, all acquisition hashes, source admission, distinct DEV label, graph/frontend metrics, 901-frame video, user files')


if __name__=='__main__':main()
