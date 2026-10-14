import hashlib,json
from pathlib import Path
import pytest
from harness.grasp_act_contract import SCHEMA,RGB_HISTORY,HISTORY
from harness.grasp_act_data import read_episode,validate_splits


def episode(root,start='a',map_id='map-a',rid='r1',kind='long_beam',role='teal'):
    from PIL import Image
    root.mkdir();(root/'rgb').mkdir();image=root/'rgb/a.jpg';Image.new('RGB',(32,24),(20,200,100)).save(image)
    digest=hashlib.sha256(image.read_bytes()).hexdigest();obs=[];ys=[]
    for i in range(3):
        cmd={'t':i*.1,'wheels':[0.]*4,'duration_s':[0.]*4,'pwm':{'1':2000 if i==0 else 1500,'3':740,'4':2320,'5':1320,'6':1500}}
        x={'schema':SCHEMA,'sample_id':f'{start}:{i}:{rid}','robot_id':rid,'t':i*.1,
           'skill':'grasp','object_kind':kind,'role':role,'destination_zone':'none','skill_elapsed_s':i*.1,'pwm_elapsed_s':0.,'rgb':[{'path':'rgb/a.jpg','sha256':digest,'t':i*.1,'robot_id':rid} for _ in range(RGB_HISTORY)],'issued':[cmd]*HISTORY}
        obs.append(x);ys.append({'sample_id':x['sample_id'],'skill':'grasp','object_kind':kind,'done':i==2,'terminal_reason':'command_sequence_complete' if i==2 else None,'clean_teacher_command':cmd})
    (root/f'student-{rid}.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in obs))
    (root/f'labels-{rid}.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in ys))
    meta={'teacher_admitted':True,'robots':[rid],'episode_id':start,'start_state_id':start,'initial_state_sha256':hashlib.sha256(start.encode()).hexdigest(),'map_id':map_id}
    (root/'episode.json').write_text(json.dumps(meta));return root


def test_all_three_robots_and_cargo_task_tokens(tmp_path):
    p=episode(tmp_path/'tri',rid='r3',kind='tri_frame',role='v2')
    m,seq=read_episode(p);assert len(seq['r3'][0])==3
    data=json.loads((p/'student-r3.jsonl').read_text().splitlines()[0]);data['object_kind']='can'
    from harness.grasp_act_contract import validate_observation
    with pytest.raises(ValueError):validate_observation(data)


def test_split_and_image_integrity_fail_closed(tmp_path):
    a=episode(tmp_path/'a');b=episode(tmp_path/'b')
    with pytest.raises(ValueError,match='split leakage'):validate_splits({'train':[a],'development':[b]})
    b=episode(tmp_path/'c',start='c')
    with pytest.raises(ValueError,match='held-out map'):validate_splits({'train':[a],'heldout_map':[b]})
    (a/'rgb/a.jpg').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='hash'):read_episode(a)


def test_missing_done_cannot_be_admitted(tmp_path):
    a=episode(tmp_path/'a');p=a/'labels-r1.jsonl';xs=[json.loads(x) for x in p.read_text().splitlines()]
    for x in xs:x['done']=False;x['terminal_reason']='timeout'
    p.write_text(''.join(json.dumps(x)+'\n' for x in xs))
    with pytest.raises(ValueError,match='termination'):read_episode(a)


def test_large_manifest_is_losslessly_compressed_and_still_readable(tmp_path):
    from scripts.run_grasp_act_teacher import compress_logs
    from harness.grasp_act_data import read
    # Long distinct names create a large inventory without large raw test data.
    for i in range(600):(tmp_path/(f'{i:04d}-'+'x'*70+'.txt')).write_text('evidence')
    compress_logs(tmp_path)
    assert not (tmp_path/'manifest.json').exists()
    manifest=read(tmp_path/'manifest.json');assert len(manifest)==600
    assert all(x['bytes']==8 for x in manifest.values())
    receipt=read(tmp_path/'manifest-compression.json')
    assert receipt['sha256']==hashlib.sha256((tmp_path/'manifest.json.zst').read_bytes()).hexdigest()
