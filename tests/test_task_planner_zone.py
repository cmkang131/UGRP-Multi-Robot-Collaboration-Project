from types import SimpleNamespace
from harness.task_planner_zone import ZonePort
from harness.task_planner import candidate
from scripts.run_task_planner import planner_option


def port():
    ex=SimpleNamespace(robot_id='r1',stopped=None,job=None,door_id='door',door_xy=[1,0],
        slots={'P1-1':{'center_m':[0,0]}},
        map={'zone_slots':{'A':[{'slot_id':'A1','center_m':[2,0]},{'slot_id':'A2','center_m':[2,1]}]},'passages':[{'id':'door','center_m':[1,0]}]},
        orders={'cyan':dict(order_id='cyan',kind='cyan',required_robots=1,destination_zone='A',initial_location={'slot':'P1-1'})})
    calls=[]
    p=ZonePort(ex,lambda *args:calls.append(args) or {'accepted':True})
    return p,calls


def test_native_choice_exact_or_refused_no_ignored_route():
    p,calls=port()
    c=candidate('carry',dict(cargo='cyan',to='A2',via='door',approach='west',mode='solo'))
    assert p.start(c)['accepted'] and calls==[('deliver','cyan','A2')]
    for k,v in [('via','another'),('approach','north'),('to','B1'),('cargo','red')]:
        c['args'][k]=v;assert not p.start(c)['accepted'];c['args'][k]={'via':'door','approach':'west','to':'A2','cargo':'cyan'}[k]
    assert len(calls)==1


def test_search_sequences_selected_area_then_own_sweep():
    p,calls=port();assert p.start(candidate('search',{'area':'P1-1'}))['accepted']
    assert p.event({'event':'job_done'}) is None
    assert calls==[('goto','P1-1'),('look_around',)]
    assert p.event({'event':'job_done'})['kind']=='job_done'


def test_default_planner_off():
    assert planner_option({})=='off'
    assert planner_option({'planner':'gemma_v1'})=='gemma_v1'


def test_real_native_event_envelope_and_report_do_not_finish_carry():
    p,calls=port();c=candidate('carry',dict(cargo='cyan',to='A2',via='door',approach='west',mode='solo'))
    p.start(c);p.start(candidate('report',{'fact':'I am carrying cyan.'}))
    assert p.active==c and p.immediate is None
    event={'event':'job_done','detail':{'confirmation':'own_camera_confirmed','outcome':'done'}}
    assert p.event(event)['kind']=='job_done' and p.completed_orders==['cyan']
    assert p.event({'event':'job_failed','detail':{'reason':'TARGET_NOT_FOUND'}})['reason']=='TARGET_NOT_FOUND'
