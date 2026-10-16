import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('contact_score',Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/score_look_ahead_contacts.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_continuity_and_positive_force_not_contact_manifold_size():
    rows=[dict(t=i*.05,contacts=[dict(category='wheel',normal_force_n=f) for f in fs]) for i,fs in enumerate(([0],[1,2],[3],[],[1]))]
    result=m.summary(rows)['wheel']
    assert result['continuous_episodes']==2 and result['contact_samples']==3
    assert result['positive_force_geom_pair_samples']==4
    assert result['episode_start_times']==[.05,.2]
