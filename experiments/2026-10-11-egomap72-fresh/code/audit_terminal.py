"""Read-only audit of the frozen twelve runs; accepts lossless zstd JSON files."""
from pathlib import Path
import contextlib,hashlib,io,json,subprocess,sys

SOURCE='29c0c169bdfd7eff91186bb90af901393340f2a1'

@contextlib.contextmanager
def opened(path):
    if path.exists():
        with path.open() as stream:yield stream
    else:
        proc=subprocess.Popen(['zstd','-qdc','--',str(path)+'.zst'],stdout=subprocess.PIPE)
        try:
            with io.TextIOWrapper(proc.stdout) as stream:yield stream
        finally:
            if proc.wait()!=0:raise RuntimeError('decompression failed: '+str(path))

def read(path):
    with opened(path) as stream:return json.load(stream)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main(root):
    root=Path(root)
    if not (root/'EXIT').exists():raise ValueError('terminal batch required')
    output={'source_sha':SOURCE,'pairs':[],'runs':[],'all_passed':True}
    for seed in range(63001,63007):
        bundles={};warmups={}
        for cond in ('off','on'):
            name=f'egomap72-{seed}-{cond}';p=root/'data'/name
            b=read(p/'bundle.json');r=read(p/'result.json');meta=read(p/'RUN_META.json')
            frames=[digest(p/'robots/r3/rgb'/f'{i:05d}.jpg') for i in range(11)]
            warmups[cond]=hashlib.sha256(json.dumps(frames).encode()).hexdigest()
            expected={'rgb_reconfirmation':'two_view_rgb_v1' if cond=='on' else 'off',
                      'covariance_inflation':'nees_stratified_v1' if cond=='on' else 'off',
                      'fresh_home':'first_own_graph_frame_v1' if cond=='on' else 'off'}
            checks={'source':r['source_sha']==meta['sha']==SOURCE,'class_pr':meta['class']=='dev' and meta['pr']==405,
                    'fresh':r.get('resumed') is False and r['mode']=='full',
                    'toggles':all(b['options'][k]==v for k,v in expected.items())}
            n=bad=0
            with opened(p/'execution-path.jsonl') as stream:
                for line in stream:
                    if not line.strip():continue
                    x=json.loads(line);n+=1
                    bad+=not (x['valid'] and x['rgb']==expected['rgb_reconfirmation'] and x['covariance']==expected['covariance_inflation'])
            checks['execution_path']=n>0 and bad==0
            bank=read(p/'rgb-reconfirmation.json')
            checks['bank_source']=bank['source']=='same_run_own_RGB'
            checks['bank_capture']=(bank['captures']>0 if cond=='on' else bank['captures']==0)
            checks['checkpoint_absent']=not any(p.glob('checkpoints/*'))
            output['runs'].append(dict(name=name,checks=checks,execution_rows=n,invalid_execution_rows=bad,
                bank_captures=bank['captures'],bank_acquisition_count=len(bank['acquisitions']),
                first_acquisition=bank['acquisitions'][:1],initial_rgb_sha256=frames[0]))
            output['all_passed'] &= all(checks.values())
            del b['execution_bundle_id']
            for k in expected:del b['options'][k]
            bundles[cond]=b
        same=warmups['off']==warmups['on'] and bundles['off']==bundles['on']
        output['pairs'].append(dict(seed=seed,warmup_11_RGB_sha256=warmups,
                                   same_warmup=warmups['off']==warmups['on'],same_common_bundle=bundles['off']==bundles['on']))
        output['all_passed'] &= same
    output['helper_sha256']=digest(Path(__file__))
    print(json.dumps(output))

if __name__=='__main__':main(sys.argv[1])
