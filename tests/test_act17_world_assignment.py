from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import act17_world_assignment as m


def test_independent_plans_and_exact_per_candidate_seed_sets():
    plans=[dict(seed=i,spawns={'r1':{'x':i}}) for i in [1,2]]
    expanded,assignment=m.expand_cases(plans,['M','F','S']);m.validate_assignment(expanded,assignment)
    expanded[0]['spawns']['r1']['x']=999
    assert plans[0]['spawns']['r1']['x']==1 and expanded[2]['spawns']['r1']['x']==1
    expanded[3]['seed']=1
    with pytest.raises(ValueError,match='duplicate seed'):
        m.validate_assignment(expanded,assignment)


def test_frozen_executor_gets_only_its_assigned_predictor_and_own_state():
    class Actor:
        def __init__(self,name):self.name=name
        def predict(self,value):return self.name,value
    class Executor:
        def __init__(self,predict):self.predict,self.steps=predict,0
        def step(self,value):self.steps+=1;return self.predict(value)
    create=m.executor_factory(Executor,{c:Actor(c) for c in ['M','F','S']},['M','M','F','F','S','S'])
    worlds=[create(None) for _ in range(6)]
    assert [w.step(i) for i,w in enumerate(worlds)]==[(c,i) for i,c in enumerate(['M','M','F','F','S','S'])]
    worlds[0].step('own-next')
    assert worlds[0].steps==2 and worlds[1].steps==1
    with pytest.raises(ValueError,match='too many'):
        create(None)
