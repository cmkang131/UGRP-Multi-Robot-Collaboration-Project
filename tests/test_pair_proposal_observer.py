import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from harness.pair_proposal_observer import ProposalObserver
from harness.pair_worker_audit import AuditSink


class Controller:
    def __init__(self):
        self.proposals={};self.barriers={'r1':SimpleNamespace(blocked=True)}
        self.inputs={'r1':SimpleNamespace(episode_id='ep')}
        self.cmd={'t':1.,'wheels':[.35]*4,'duration_s':[.15]*4,'pwm':{'1':1999}}
        self.previous={**self.cmd,'pwm':{'1':2000}}
        self.result={'r1':{'observation':{'robot_id':'r1','sample_id':'ep:0:r1','t':1.},'stage':'approach'}}
    def propose(self,now,robots):
        self.proposals={'r1':(self.cmd,False,self.previous)}
        return self.result
    def issue(self,now,permits):
        self.proposals={}
        return {'issued':'unchanged'}


class Sink:
    def __init__(self):self.rows=[]
    def write(self,row):self.rows.append(row)


PIN=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def observer(c,s):return ProposalObserver(c,enabled=True,source_controller=c,sink=s,expected_source_sha256=PIN)


def test_default_disabled_does_not_inspect_source():
    c=Controller();w=ProposalObserver(c);assert w.propose(1.,{}) is c.result
    assert w.capture_failures==0

def test_capture_before_issue_and_deep_independence():
    c=Controller();s=Sink();w=observer(c,s);before=copy.deepcopy(c.cmd)
    assert w.propose(1.,{}) is c.result
    row=s.rows[0]['robots']['r1'];assert row['proposal']==before and row['blocked'] is True
    assert 'origin' not in row and 'issued' not in row
    assert w.issue(1.,{})=={'issued':'unchanged'} and c.proposals=={}
    c.cmd['wheels'][0]=0.;assert row['proposal']==before
    row['previous']['pwm']['1']=3;assert c.previous['pwm']['1']==2000

def test_sink_failure_nonblocking():
    c=Controller()
    class Broken:
        def write(self,row):raise OSError('disk full')
    w=observer(c,Broken());assert w.propose(1.,{}) is c.result
    assert w.capture_failures==1 and w.last_capture_error=='OSError'
    assert w.issue(1.,{})=={'issued':'unchanged'}

@pytest.mark.parametrize('field,value',[('t',2.),('robot_id','other')])
def test_bad_binding_drops_capture_only(field,value):
    c=Controller();c.result['r1']['observation'][field]=value;s=Sink();w=observer(c,s)
    assert w.propose(1.,{}) is c.result;assert w.capture_failures==1 and s.rows==[]

def test_missing_candidate_never_fabricated():
    c=Controller();s=Sink();w=observer(c,s);original=c.propose
    def missing(*a):r=original(*a);c.proposals={};return r
    c.propose=missing;assert w.propose(1.,{}) is c.result
    assert not s.rows and w.capture_failures==1

def test_source_pin_required_and_checked():
    c=Controller()
    with pytest.raises(ValueError):ProposalObserver(c,enabled=True)
    with pytest.raises(ValueError):ProposalObserver(c,enabled=True,source_controller=c,sink=Sink(),expected_source_sha256='wrong')

def test_actual_existing_sink_envelope(tmp_path):
    import json
    c=Controller();s=AuditSink(run_id='proposal-test',output_root=tmp_path);w=observer(c,s)
    w.propose(1.,{});s.close();r=json.loads(s.path.read_text())
    assert r['run_id']=='proposal-test' and r['kind']=='raw_proposal_snapshot' and r['seq']==0
    assert 'record_digest' in r


def test_pinned_controller_retains_candidate_until_issue(tmp_path):
    """Real pinned controller/executor/barrier, fixed synthetic predictor only."""
    import json, os, subprocess, sys
    tree=Path('/home/ubuntu/UGRP/experiments/2026-11-04-joint-act-4tree-assembly-diag-v1/out/trees/worker')
    if not tree.is_dir():pytest.skip('external pinned controller unavailable')
    repo=Path(__file__).resolve().parents[1]
    code=r'''
import importlib.util,json,sys,hashlib,copy
from pathlib import Path
import numpy as np
from harness.pairact_r1_student import PairStudentController
import harness.pairact_r1_student as pc

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
repo=Path(sys.argv[1]);out=Path(sys.argv[2])
a=load(repo/'harness/pair_worker_audit.py','audit')
o=load(repo/'harness/pair_proposal_observer.py','observer')
expected='3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a54efdef77e81'
assert hashlib.sha256(Path(pc.__file__).read_bytes()).hexdigest()==expected

def predict(obs,jpegs):
 chunk=np.zeros((8,14));chunk[:,:4]=.35;chunk[:,4:8]=1.
 logits=np.zeros((8,8));logits[:,0]=1.
 return {'chunk':chunk,'stage_logits':logits}
cmd={'t':0.,'wheels':[0.]*4,'duration_s':[0.]*4,'pwm':{'1':2000,'3':1500,'4':1500,'5':1500,'6':1500}}
results=[]
for enabled in (False,True):
 raw=PairStudentController(predict,{'r1':'teal','r2':'blue'},'ep',{r:copy.deepcopy(cmd) for r in ['r1','r2']})
 sink=a.AuditSink(run_id=str(enabled),output_root=out)
 wrapped=o.ProposalObserver(raw,enabled=enabled,source_controller=raw,sink=sink,expected_source_sha256=expected)
 proposed=wrapped.propose(.1,{r:{'jpeg':b'own-'+r.encode(),'issued':copy.deepcopy(cmd)} for r in ['r1','r2']})
 assert len(raw.proposals)==2
 before=copy.deepcopy(raw.proposals)
 issued=wrapped.issue(.1,{'r1':False,'r2':False})
 assert raw.proposals=={}
 assert all(v['blocked'] and v['command']['wheels']==[0.]*4 for v in issued.values())
 assert all(v[0]['wheels']==[.35]*4 for v in before.values())
 sink.close();rows=[json.loads(x) for x in sink.path.read_text().splitlines()]
 if enabled:
  assert len(rows)==1
  for rid,s in rows[0]['robots'].items():
   assert s['proposal']==before[rid][0] and s['previous']==before[rid][2]
   assert s['sample_id']==proposed[rid]['observation']['sample_id']
   assert s['episode_id']=='ep' and s['blocked'] is True
 else:assert not rows
 assert wrapped.capture_failures==0
 results.append([proposed,issued])
assert results[0]==results[1]
print(json.dumps({'actual_controller_sha':expected,'on_off_equal':True,'raw_candidate_captured_before_issue':True,'synthetic_only':True}))
'''
    p=subprocess.run([sys.executable,'-B','-c',code,str(repo),str(tmp_path)],env={**os.environ,'PYTHONPATH':str(tree),'PYTHONDONTWRITEBYTECODE':'1'},cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)['on_off_equal'] is True


def test_other_controller_cannot_supply_snapshot():
    c=Controller();other=Controller()
    with pytest.raises(ValueError):ProposalObserver(c,enabled=True,source_controller=other,sink=Sink(),expected_source_sha256=PIN)


def test_failed_sink_has_independent_completeness_status():
    import io,json
    c=Controller();stream=io.StringIO()
    class Broken:
        def write(self,row):raise OSError('disk full')
    w=ProposalObserver(c,enabled=True,source_controller=c,sink=Broken(),expected_source_sha256=PIN,status_stream=stream)
    assert w.propose(1.,{}) is c.result
    w.finish();state=json.loads(stream.getvalue())
    assert state['finished'] and state['attempted_ticks']==1 and state['failed_ticks']==1
    assert state['captured_ticks']==0 and state['expected_robot_candidates']==1 and not state['complete']
    assert state['last_capture_error']=='OSError'


def test_success_status_and_idempotent_finish():
    import io,json
    c=Controller();sink=Sink();stream=io.StringIO()
    w=ProposalObserver(c,enabled=True,source_controller=c,sink=sink,expected_source_sha256=PIN,status_stream=stream)
    w.propose(1.,{});w.finish();w.finish()
    assert len(sink.rows)==2
    state=json.loads(stream.getvalue());assert state['complete'] and state['captured_ticks']==1
    assert state['captured_robot_candidates']==1


def test_bad_status_stream_does_not_interrupt_control():
    c=Controller();sink=Sink()
    class Broken:
        def seek(self,*a):raise OSError('status unavailable')
    w=ProposalObserver(c,enabled=True,source_controller=c,sink=sink,expected_source_sha256=PIN,status_stream=Broken())
    assert w.propose(1.,{}) is c.result;w.finish()
    assert w.status_write_failures==2 and not w.capture_status()['complete']
    assert w.issue(1.,{})=={'issued':'unchanged'}


def test_owned_worker_opt_in_wiring(tmp_path):
    import json,os,subprocess,sys,shutil
    source=Path('/home/ubuntu/UGRP/experiments/2026-11-04-joint-act-4tree-assembly-diag-v1/out/trees/worker')
    if not source.is_dir():pytest.skip('external pinned tree unavailable')
    repo=Path(__file__).resolve().parents[1];tree=tmp_path/'tree'
    shutil.copytree(source,tree,ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['pair_worker_audit.py','pair_proposal_observer.py']:
        shutil.copy2(repo/'harness'/name,tree/'harness'/name)
    code=r'''
import importlib.util,json,sys,hashlib,io
from pathlib import Path
from harness import pair_worker_audit as a
repo=Path(sys.argv[1]);root=Path(sys.argv[2]);tree=Path(sys.argv[3])
spec=importlib.util.spec_from_file_location('scenario',repo/'tests/pair_worker_audit_scenario.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
manifest=root/'sources.json';manifest.write_text(json.dumps({str(tree/'harness'/n):hashlib.sha256((tree/'harness'/n).read_bytes()).hexdigest() for n in ['pairact_r1_student.py','pair_proposal_observer.py']}))
outputs=[]
for observe in (False,True):
 capture=s.Capture();args=['--student-root',str(tree),'--geometry-worker','/home/ubuntu/ugrp-retrain-geom-20261029/received/final/extracted/scripts/geometry_pair_worker.py','--audit-run-id',str(observe),'--audit-output-root',str(root),'--audit-sources',str(manifest)]
 if observe:args.append('--observe-raw-proposals')
 a.owned_worker_main(args,predict=s.synthetic_predict_factory(),stdin=s.build_requests(6,capture),stdout=capture)
 outputs.append(capture.lines())
rows=[json.loads(x) for x in (root/'pair-audit-True.jsonl').read_text().splitlines()]
snaps=[r for r in rows if r['kind']=='raw_proposal_snapshot'];assert len(snaps)==6
assert len([r for r in rows if r['kind']=='proposal_capture_summary'])==1
assert all(len(r['robots'])==2 for r in snaps)
for r in snaps:
 before=rows[r['seq']-1];assert before['kind']=='propose_op'
 for rid,val in r['robots'].items():assert val['observation_digest']==before['robots'][rid]['observation_digest']
status=json.loads((root/'proposal-status-True.json').read_text());assert status['complete'] and status['captured_robot_candidates']==12
assert not (root/'proposal-status-False.json').exists()
assert outputs[0]==outputs[1]
print(json.dumps({'ticks':6,'captured_candidates':12,'stdout_equal':True,'complete':True}))
'''
    p=subprocess.run([sys.executable,'-B','-c',code,str(repo),str(tmp_path),str(tree)],env={**os.environ,'PYTHONPATH':str(tree),'PYTHONDONTWRITEBYTECODE':'1'},cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)['captured_candidates']==12


def test_no_attempts_not_a_complete_diagnostic():
    c=Controller();w=observer(c,Sink());w.finish()
    state=w.capture_status();assert state['finished'] and not state['complete']
    assert state['attempted_ticks']==state['captured_ticks']==0
