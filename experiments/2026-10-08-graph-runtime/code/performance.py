"""Measured equality plus explicitly conditional whole-run cost model."""
import copy
import profile_graph as p


def main():
    b=p.load(p.RAW/'benchmark.json');audit=p.load(p.RAW/'reuse-audit.json')
    off,cold,warm,combined=b['graph'];fo,fn=b['frames']
    identical=[]
    for row in b['graph']:
        checks={name:p.sha(p.RAW/row['name']/name)==p.sha(p.RAW/'off-profile'/name) for name in ('graph.json','grid.json')}
        assert all(checks.values())
        identical.append(dict(condition=row['name'],files_identical=checks,
            max_pose_difference=0.,max_cell_difference=0.,max_constraint_difference=0.))
    # Add the final graph to a 360-SIM-s run; physical HOST_ERROR remains.
    # Cost model, not new execution: per-pair cost from final graph; nonmatcher
    # cost proportional to scan count. Warm full-input repeat is NOT extrapolated.
    receipts=audit['receipts'];scans=sum(r['scans'] for r in receipts)/204
    matches=sum(r['matches'] for r in receipts);misses=sum(r['pair_misses'] for r in receipts)
    g_off=off['stage_s']['match_loop']*matches/3751+(off['wall_s']-off['stage_s']['match_loop'])*scans
    g_on=combined['stage_s']['match_loop']*misses/3751+(combined['wall_s']-combined['stage_s']['match_loop'])*scans
    non_graph_ratio=(fn['measured_wall_s']-fn['inclusive_graph_s'])/(fo['measured_wall_s']-fo['inclusive_graph_s'])
    acquisition=p.load(p.EP/'result.json')
    # The interrupted final call may already account for some unknown fraction
    # of its full cost; do not count that fraction twice.
    baseline_interval=[acquisition['wall_s'],acquisition['wall_s']+off['wall_s']]
    scenarios=[]
    for fixed_fraction in (0.,.25,.5,1.):
        times=[]
        for total in baseline_interval:
            residual=total-g_off
            assert residual>=0
            fixed=residual*fixed_fraction
            times.append(fixed+(residual-fixed)*non_graph_ratio+g_on)
        scenarios.append(dict(non_graph_fixed_fraction=fixed_fraction,estimated_wall_s_interval=times,estimated_wall_per_sim_interval=[t/360 for t in times]))
    result=dict(equality=identical,frame_sha256=fo['all_outputs_sha256'],frame_comparisons=141,
        graph_speedup=dict(cold=off['wall_s']/cold['wall_s'],warm=off['wall_s']/warm['wall_s'],combined_cold=off['wall_s']/combined['wall_s']),
        frame_speedup=fo['measured_wall_s']/fn['measured_wall_s'],non_graph_ratio=non_graph_ratio,
        estimate=dict(sim_s=360,physical_measured_wall_s=acquisition['wall_s'],baseline_completion_wall_s_interval=baseline_interval,
            modeled_graph_off_s=g_off,modeled_graph_on_s=g_on,matched_pairs=matches,uncached_pairs=misses,
            scan_equivalents=scans,scenarios=scenarios,
            assumptions='Per-pair cost and per-scan rebuild cost calibrated on final graph. 30s non-graph ratio extrapolated only to nonfixed residual. Physics/render fixed fraction unknown. Sensitivity scenarios, NOT confidence bounds or verified wall time. Cache hit repeat speedup not applied to all graphs.'),
        qualification='Sequential locked single observations; no timing significance claim. cProfile excluded from speed ratios. No physics.')
    p.dump(p.EXP/'results/performance.json',result);p.dump(p.RAW/'performance.json',result)
    print(p.json.dumps(result,indent=2))

if __name__=='__main__':main()
