"""Seal all old-detector actual contact columns before semantic GT diagnosis."""
from common import *

def predict(seed):
    ep=EPISODES[seed];out=RAW/seed/'off'
    if out.exists():raise FileExistsError(out)
    expected=load(ep/'artifacts.sha256.json')
    names=['robots/r3/frames.jsonl','own-contacts.jsonl','graph.json','frontend-covariances.jsonl','grid.json']
    for n in names:assert sha(ep/n)==expected[n]
    frames={f['frame_id']:f for f in rows(ep/'robots/r3/frames.jsonl')}
    contact_frames=rows(ep/'own-contacts.jsonl')
    out.mkdir(parents=True)
    with (out/'points.jsonl').open('w') as stream:
        for ix,own in enumerate(contact_frames):
            f=frames[own['frame_id']];servo={int(k):v for k,v in f['commanded_servo'].items()}
            points=contact_points(rgb(ep,f),servo)
            # Stored pixels, actual column measurements, no interpolated segments.
            points.update(frame_id=f['frame_id'],t=f['sim_time'],uv=uv_of(points['points'],servo).tolist())
            stream.write(json.dumps(points,allow_nan=False)+'\n')
            if ix%200==0:print(seed,ix,'/',len(contact_frames),flush=True)
    assert 'mujoco' not in sys.modules
    dump(out/'seal.json',dict(source_sha=head(),seed=seed,gt_parsed=False,physics=0,
        input_hashes={n:expected[n] for n in names},rgb_hashes={frames[r['frame_id']]['path']:frames[r['frame_id']]['sha256'] for r in contact_frames},
        files={'points.jsonl':sha(out/'points.jsonl')},frames=len(contact_frames)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('seed',choices=EPISODES);a=p.parse_args();predict(a.seed)
