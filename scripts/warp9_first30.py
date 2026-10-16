"""Existing project speed gate, evaluated over fixed SIM work (not a wall cap)."""
from statistics import median


def summarize(samples, *, shared_load,nworld=1,per_execution=False):
    if isinstance(nworld,bool) or not isinstance(nworld,int) or nworld<1:raise ValueError('positive world count required')
    if not samples or samples[-1]['sim_s']<30:
        raise ValueError('first30 SIM work incomplete')
    rates=[s['wall_s']/s['delta_sim_s'] for s in samples if s['sim_s']<=30 and s['delta_sim_s']>0]
    if not rates:raise ValueError('no completed SIM intervals')
    batch=median(rates);value=batch/nworld if per_execution else batch
    # AGENTS 2026-10-15 user speed flexibility: 3.5 warns, only >6 blocks.
    # These inherited coordinator thresholds are not new fitted constants.
    return dict(sim_s=30,median_wall_per_sim=value,samples=len(rates),shared_load=shared_load,
        batch_median_wall_per_sim=batch,per_execution_median_wall_per_sim=batch/nworld,nworld=nworld,
        gate_unit='wall/(SIM*nworld)' if per_execution else 'batch wall/SIM',
        warning=value>3.5,status='SPEED_GATE_FAIL' if value>6 else 'PASS',
        basis='inherited >3.5 warning/>6 stop; per-execution denominator is warp10 coordinator interpretation, user unconfirmed' if per_execution else 'project AGENTS speed gate: median>3.5 warning; median>6 stops')
