"""Versioned recording admission for the four fields in the pinned warp3 gate.

Adapted from claude/act16w scripts/act16w_runtime.py, execution source
813b9113b16e382712a00b911a9dcc7c06fbd77d. No historical host fields are invented.
The existing >=95%/40 and two inspected pilots requirements remain unchanged.
"""
import hashlib
import json
from pathlib import Path


def validate(path, *, source_sha, gate, current_host):
    proof=json.loads(Path(path).read_text())
    approved_gate=proof.get('corrected_teacher_gate',{})
    checks=proof.get('pilot_checks',[])
    host=gate['cohort']['host']
    keys=('project_id','instance','machine_type','zone')
    if (current_host.get('project_id')!='ugrp-sim-b-1014'
            or current_host.get('instance') not in ('ugrp-act-l4-gcp2','ugrp-act-l4-gcp2b')
            or current_host.get('machine_type')!='g2-standard-8'
            or not current_host.get('zone','').startswith('asia-northeast3-')
            or any(not host.get(k) or host[k]!=current_host.get(k)
                   or host[k]!=approved_gate.get('execution_host',{}).get(k) for k in keys)):
        raise ValueError('recorded gate / approval / live host mismatch')
    n,N=approved_gate.get('n'),approved_gate.get('N')
    if (gate.get('source_sha')!=source_sha or gate.get('passed') is not True
            or proof.get('approved') is not True or proof.get('source_sha')!=source_sha
            or proof.get('gate_promotion_authorized_if_all_conditions_pass') is not False
            or approved_gate.get('source_sha')!=source_sha
            or approved_gate.get('solo_truth_free_lookaround_v1') is not True
            or type(n) is not int or type(N) is not int or N<40 or not 0<=n<=N or n/N<.95
            or (n,N)!=(gate['n'],gate['N'])
            or len(checks)!=2 or len({c.get('path') for c in checks})!=2):
        raise ValueError('uncorrected gate / missing inspected pilots / source mismatch')
    for check in checks:
        try:
            actual=hashlib.sha256(Path(check['path']).read_bytes()).hexdigest()
        except (KeyError,TypeError,OSError) as error:
            raise ValueError('inspected pilot evidence unavailable') from error
        if check.get('passed') is not True or actual!=check.get('sha256'):
            raise ValueError('inspected pilot evidence hash mismatch')
    return proof
