"""Select exact own-frame cohort before any parallax prediction."""
from collections import Counter
import cv2
import common as c


def main():
    c.OUT.mkdir(parents=True,exist_ok=True)
    cases={}
    annotations=[]
    for case,ep in c.EPISODES.items():
        counts=Counter()
        eligible=[]
        for f,cm,reason,_,_ in c.stream(case):
            counts[reason]+=1
            if cm is not None:eligible.append(f)
        cases[case]=dict(episode=str(ep),counts=dict(counts),eligible_frames=[f['frame_id'] for f in eligible],
            sources={str(p):c.sha(p) for p in [ep/'robots/r3/frames.jsonl',ep/'robots/r3/commands.jsonl']})
        if case in ('s1050','s1051'):
            for k in range(6):
                f=eligible[int((k+.5)*len(eligible)/6)]
                path=ep/f['path']
                assert c.sha(path)==f['sha256']
                image=c.old.mp.undistort(cv2.imread(str(path)))
                target=c.OUT/f'{case}-{k}-annotation.png'
                assert not target.exists()
                cv2.imwrite(str(target),image)
                annotations.append(dict(case=case,k=k,frame_id=f['frame_id'],t=f['sim_time'],
                    image=str(target),raw_path=str(path),sha256=f['sha256'],undistorted_sha256=c.sha(target),
                    polylines=[],ignore=[],status='needs_annotation_before_parallax'))
        print(case,'eligible',len(eligible),dict(counts),flush=True)
    c.dump(c.EXP/'cohort.json',dict(rule='all_even_settled_unloaded_registered_frames',cases=cases))
    c.dump(c.EXP/'new-annotations.json',dict(rule='six_mid_quantiles_per_case',rows=annotations))


if __name__=='__main__':main()
