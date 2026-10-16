"""Actual frozen planner regression. No keychain/network/provider calls."""
import importlib.util
import sys
from pathlib import Path
import pytest
from scripts.warp9_planner import install_coreweave_rate_v1

ROOT=Path(__file__).parent/'fixtures/warp9'


def load(name,filename,monkeypatch):
    # .txt fixture is the exact legacy module; loader reads ordinary source.
    from importlib.machinery import SourceFileLoader
    spec=importlib.util.spec_from_loader(name,SourceFileLoader(name,str(ROOT/filename)))
    module=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,name,module)
    spec.loader.exec_module(module)
    return module


def test_actual_coreweave_registration_failure_and_fixed_pinned_config(monkeypatch,tmp_path):
    import scripts
    models=load('harness.task_planner_model','harness__task_planner_model.py.txt',monkeypatch)
    policy=load('scripts.openrouter_ling_policy','scripts__openrouter_ling_policy.py.txt',monkeypatch)
    monkeypatch.setattr(scripts,'openrouter_ling_policy',policy,raising=False)
    upstream=load('warp9_legacy_upstream','scripts__openrouter_upstream.py.txt',monkeypatch)
    # The real config hashes its sibling policy file. Preserve that layout in
    # scratch space without changing any frozen fixture bytes.
    (tmp_path/'openrouter_ling_policy.py').write_bytes((ROOT/'scripts__openrouter_ling_policy.py.txt').read_bytes())
    upstream.__file__=str(tmp_path/'openrouter_upstream.py')
    choice=models.ModelSelection()
    with pytest.raises(ValueError,match='REGISTERED_RATE_POLICY_REQUIRED'):
        upstream.config(selection=choice,rate_limit_policy='planner_rate_limit_v1')
    old=upstream.config(selection=models.GEMMA_FP4,rate_limit_policy='planner_rate_limit_v1')
    audit=install_coreweave_rate_v1(upstream,models)
    fixed=upstream.config(selection=choice,rate_limit_policy='planner_rate_limit_v1')
    assert fixed['provider_order']==['CoreWeave']
    assert fixed['quantizations']==['fp4'] and fixed['allow_fallbacks'] is False
    assert fixed['rate_limit_parameters']==old['rate_limit_parameters']
    assert upstream.config(selection=models.GEMMA_FP4,rate_limit_policy='planner_rate_limit_v1')==old
    assert install_coreweave_rate_v1(upstream,models)==audit
    for provider in ('CoreWeave','coreweave/fp4'):
        for fmt in ('off','json_object'):
            c=models.ModelSelection(provider=provider,response_format=fmt)
            assert upstream.config(selection=c,rate_limit_policy='planner_rate_limit_v1')['tag']=='coreweave/fp4'
    with pytest.raises(ValueError):
        upstream.config(selection=choice,rate_limit_policy='unregistered')
    body=dict(max_tokens=768,messages=[])
    import json
    expected=(len(json.dumps(body,ensure_ascii=True).encode())+4096)*.1/1e6+768*.34/1e6
    assert policy.reserve_cost(body,choice)==pytest.approx(expected)
