"""Post-run supervisor audit: exact own-input replay, no retuning or GT input."""
from pathlib import Path
import ctypes,hashlib,json,sys,subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/frontier-duration-v1')
EP=RAW/'A/new-seed';OUT=RAW/'exhaustion-audit-v2'
from harness.active_wall_recovery import RecoveryMapper
from harness.active_camera import SEARCH
from harness.public_navigation.native import VENDOR,HERE
from scripts.run_active_wall_rotleft import install_profile,dump

def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]

def replay():
    import cv2
    OUT.mkdir(parents=True,exist_ok=False)
    cutoff=next(e['t'] for e in load(EP/'navigation.json') if e['reason']=='exploration_finished_no_frontier')
    actor=RecoveryMapper('r3',load(EP/'result.json')['start_sim_s'],SEARCH,
        active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=46001,
        navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
    install_profile(actor.memory.self_map,profile='egomap27_wide')
    original_select=actor.navigator.select_frontier
    def select(costmap,pose,t):
        before=[p.tolist() for p in actor.navigator.blacklist]
        n=len(actor.navigator.events)
        result=original_select(costmap,pose,t)
        if any(e['reason']=='exploration_finished_no_frontier' for e in actor.navigator.events[n:]):
            np.savez_compressed(OUT/'costmap.npz',raw=costmap.raw,costs=costmap.costs,
                origin=costmap.origin,resolution=costmap.resolution,pose=pose)
            dump(OUT/'state.json',dict(t=t,epoch=actor.navigation_epoch,
                blacklist_before=before,blacklist_after=actor.navigator.blacklist,
                events=actor.navigator.events[n:],grid_cells=len(actor.grid.odds),finished=actor.navigator.finished))
        return result
    actor.navigator.select_frontier=select
    frames={r['frame_id']:r for r in rows(EP/'robots/r3/frames.jsonl')}
    oldrows=rows(EP/'own-controller.jsonl');contacts=rows(EP/'own-contacts.jsonl')
    with (OUT/'traces.jsonl').open('x') as stream:
        for i,(old,contact) in enumerate(zip(oldrows,contacts)):
            if old['t']>cutoff+1e-8:break
            rgb=cv2.cvtColor(cv2.imread(str(EP/frames[old['frame_id']]['path'])),cv2.COLOR_BGR2RGB)
            obs={k:v for k,v in contact.items() if k not in ('t','frame_id')}
            _,trace=actor.receive(robot_id='r3',t=old['t'],frame_id=old['frame_id'],rgb=rgb,servo=SEARCH,observation=obs)
            assert json.dumps(trace)==json.dumps(old),('REPLAY_DIFFERENCE',i,old['t'])
            stream.write(json.dumps(trace,allow_nan=False)+'\n')
            if old['t']<cutoff:actor.command(old['command'])
            if i%100==0:print('exact replay',i+1,flush=True)
    dump(OUT/'replay.json',dict(n=sum(r['t']<=cutoff for r in oldrows),cutoff=cutoff,
        trace_bytes_equal=True,gt_read=False,input_sha256={name:hashlib.sha256((EP/name).read_bytes()).hexdigest()
            for name in ('own-controller.jsonl','own-contacts.jsonl','robots/r3/frames.jsonl')}))

def upstream_clusters(raw,origin,res,pose):
    # Unmodified upstream search; min_size=0 exposes clusters BEFORE the native .75m filter.
    bridge=OUT/'cluster_audit.cpp';library=OUT/'cluster_audit.so'
    bridge.write_text('''#include <explore/frontier_search.h>
extern "C" int clusters(unsigned char* d,int nx,int ny,double r,double ox,double oy,double x,double y,double* out,int cap) {
 costmap_2d::Costmap2D map(nx,ny,r,ox,oy,d);
 frontier_exploration::FrontierSearch search(&map,3.,1.,0.);
 geometry_msgs::Point p; p.x=x;p.y=y;
 auto fs=search.searchFrom(p);int n=std::min(int(fs.size()),cap);
 for(int i=0;i<n;++i){auto& f=fs[i];out[7*i]=f.centroid.x;out[7*i+1]=f.centroid.y;
 out[7*i+2]=f.middle.x;out[7*i+3]=f.middle.y;out[7*i+4]=f.min_distance;out[7*i+5]=f.size;out[7*i+6]=f.cost;}return n;
}
''')
    subprocess.run(['c++','-std=c++17','-O2','-shared','-fPIC','-I'+str(HERE/'shim'),
        '-I'+str(VENDOR/'m-explore/explore/include'),str(VENDOR/'m-explore/explore/src/frontier_search.cpp'),
        str(bridge),'-o',str(library)],check=True,capture_output=True)
    lib=ctypes.CDLL(str(library));lib.clusters.argtypes=[np.ctypeslib.ndpointer(dtype=np.uint8,flags='C_CONTIGUOUS'),
        ctypes.c_int,ctypes.c_int,*([ctypes.c_double]*5),np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS'),ctypes.c_int]
    result=np.zeros((raw.size,7));n=lib.clusters(np.ascontiguousarray(raw),raw.shape[1],raw.shape[0],res,*origin,*pose[:2],result,len(result))
    return result[:n]

def audit():
    from scipy.ndimage import binary_dilation,label
    from harness.public_navigation_unknown import UnknownCostmap
    from harness.active_wall_recovery import ExplorationRecoveryNavigator
    n=ExplorationRecoveryNavigator();state=load(OUT/'state.json');d=np.load(OUT/'costmap.npz')
    costmap=UnknownCostmap(d['raw'],d['origin'],float(d['resolution']));pose=d['pose'];res=costmap.resolution
    clusters=upstream_clusters(costmap.raw,costmap.origin,res,pose)
    accepted=clusters[clusters[:,5]*res>=.75]
    native=n.core.frontiers(costmap.raw,costmap.origin,res,pose[:2])
    assert np.array_equal(accepted,native),'Native .75m frontier filter mismatch'
    n.blacklist=[np.array(p) for p in state['blacklist_before']]
    candidates=[]
    for row in native:
        blocked=n.blocked(row[:2],res);path=n.plan_to(costmap,pose,row[:2])
        cell=costmap.world_to_map(row[:2])
        start=costmap.world_to_map(pose[:2]);native_path=n.core.plan(costmap.costs,start,cell)
        first=costmap.map_to_world(native_path[0]) if len(native_path) else None
        sweep=None if first is None else costmap.sweep_clear(pose,[*first,pose[2]])
        hit_cells=[]
        if first is not None:
            from harness.public_navigation_persistent import raytrace_cells
            _,polygon=costmap.footprint_mask(np.r_[first,pose[2]])
            corners=[costmap.world_to_map(p) for p in polygon]
            edge={p for a,b in zip(corners,corners[1:]+corners[:1]) for p in raytrace_cells(a,b)}
            hit_cells=sorted(p for p in edge if costmap.costs[p[1],p[0]]==254)
        candidates.append(dict(center=row[:2],size=int(row[5]),blacklisted=blocked,path_points=len(path),
            goal_cost=None if cell is None else int(costmap.costs[cell[1],cell[0]]),
            native_path_points=len(native_path),start_pose_clear=costmap.pose_clear(pose),
            first_point=first,start_to_cell_center_m=None if first is None else float(np.linalg.norm(first-pose[:2])),
            start_sweep_clear=sweep,first_footprint_lethal_cells=hit_cells))
    cross=np.array([[0,1,0],[1,1,1],[0,1,0]])
    free=costmap.raw==0;unknown=costmap.raw==255
    boundary=unknown&binary_dilation(free,structure=cross)
    ray_ranges={}
    for kind in ('floor','wall'):
        from harness.self_map_csm import sample_segments
        distances=[]
        for row in rows(EP/'own-contacts.jsonl'):
            if row['t']>state['t']:break
            pts=np.array(row['floor_xy']).reshape(-1,2) if kind=='floor' else sample_segments(row['segments'])
            if len(pts):distances.extend(np.linalg.norm(pts-np.array(row['camera']),axis=1).tolist())
        ray_ranges[kind]=dict(n=len(distances),max_m=max(distances),above_4m=sum(x>4 for x in distances))
    result=dict(replay=load(OUT/'replay.json'),state=state,
        free_cells=int(free.sum()),unknown_cells=int(unknown.sum()),occupied_cells=int((costmap.raw==254).sum()),
        unknown_boundary_cells=int(boundary.sum()),free_boundary_cells=int((free&binary_dilation(unknown,structure=cross)).sum()),
        free_components=label(free,structure=cross)[1],all_clusters=len(clusters),all_cluster_cells=int(clusters[:,5].sum()),
        min_size_rejected_clusters=int((clusters[:,5]*res<.75).sum()),min_size_rejected_cells=int(clusters[clusters[:,5]*res<.75,5].sum()),
        size_accepted_clusters=len(native),size_accepted_cells=int(native[:,5].sum()),
        blacklist_rejected=sum(x['blacklisted'] for x in candidates),
        new_unreachable=sum(not x['blacklisted'] and not x['path_points'] for x in candidates),
        native_path_exists=sum(bool(x['native_path_points']) for x in candidates),
        adapter_start_sweep_rejected=sum(x['start_sweep_clear'] is False for x in candidates),
        usable=sum(not x['blacklisted'] and bool(x['path_points']) for x in candidates),
        candidates=candidates,ray_ranges=ray_ranges,native_filter_equal=True,
        bounds_policy='unbounded own map; dynamic extent +1m unknown padding; no GT arena clip',
        ray_policy='measured finite floor/wall endpoints only; clear to endpoint, mark wall last; no max-range extrapolation')
    dump(EXP/'results/exhaustion.json',result)
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    fig,ax=plt.subplots(figsize=(8,6));raw=costmap.raw;lo=costmap.origin;hi=lo+res*np.array(raw.shape[::-1])
    display=np.where(raw==255,0,np.where(raw==254,3,np.where(costmap.costs>=253,2,1)))
    ax.imshow(display,origin='lower',extent=[lo[0],hi[0],lo[1],hi[1]],cmap=ListedColormap(['#eeeeee','#cfdfed','#eaba70','#a32a28']),vmin=0,vmax=3)
    yy,xx=np.where(boundary);ax.scatter(lo[0]+(xx+.5)*res,lo[1]+(yy+.5)*res,s=2,c='green',label='unknown/free boundary')
    for i,c in enumerate(candidates):ax.scatter(*c['center'],marker='x',s=60,c='purple');ax.text(*c['center'],str(i+1))
    ax.scatter(*pose[:2],c='black',s=45,label='own estimated pose')
    ax.set(title=f'A exhaustion t={state["t"]-1.3:.1f}s | own navigation costmap only',xlabel='Own start X (m)',ylabel='Own start Y (m)',aspect='equal')
    ax.legend();fig.tight_layout();fig.savefig(EXP/'figures/exhaustion.png',dpi=140);plt.close(fig)
    dump(OUT/'seal.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='seal.json'})
    print(json.dumps({k:v for k,v in result.items() if k not in ('state','replay','candidates')},indent=2))

if __name__=='__main__':
    if '--audit-only' not in sys.argv:replay()
    audit()
