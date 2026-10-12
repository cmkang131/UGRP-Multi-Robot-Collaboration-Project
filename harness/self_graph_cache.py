"""Own-submap matcher/result reuse, default off (egomap48).

Cartographer DispatchScanMatcherConstruction retains immutable submap matchers;
its node/submap lifecycle retains constraints. Here RBPF lineage can change, so
exact input content (not IDs alone) invalidates cached fields and pair results.
No search pruning, solver/objective changes, approximation or peer-map sharing.
"""
from collections import OrderedDict,Counter
import copy,hashlib
from dataclasses import astuple
import numpy as np

OPTION='match_cache_v1'


def array_key(value):
    a=np.ascontiguousarray(value,dtype=np.float64)
    return a.shape,a.tobytes()


class Prepared:
    def __init__(self,submap,owner):
        self.grid=copy.copy(submap['grid']);self.grid.cells=dict(submap['grid'].cells)
        self.segments=np.array(submap['segments'],copy=True);self.owner=owner
        self.occupied=self.grid.occupied_points()
        self._probability=self._distance=None
    def probability(self):
        if self._probability is None:
            from harness.self_pose_graph import ProbabilityField
            self._probability=ProbabilityField(self.grid);self.owner.counts['probability_builds']+=1
        return self._probability
    def distance(self):
        if self._distance is None:
            from harness.self_pose_graph import DistanceField
            self._distance=DistanceField(self.segments,.05,1.);self.owner.counts['distance_builds']+=1
        return self._distance


class GraphCache:
    def __init__(self,robot_id,*,max_pairs=8192,max_fields=64):
        if max_pairs<1 or max_fields<1:raise ValueError('POSITIVE_GRAPH_CACHE_LIMIT_REQUIRED')
        self.robot_id=robot_id;self.max_pairs=max_pairs;self.max_fields=max_fields
        self.pairs=OrderedDict();self.fields=OrderedDict();self.counts=Counter()
    @staticmethod
    def submap_key(submap):
        g=submap['grid']
        # Sort is conservative and exact: fields use cell values, independent of
        # dictionary insertion order. Segment order is retained for distance ties.
        h=hashlib.sha256();h.update(np.float64(g.resolution_m).tobytes())
        h.update(np.asarray(sorted((x,y,v) for (x,y),v in g.cells.items()),np.float64).tobytes())
        shape,data=array_key(submap['segments']);h.update(repr(shape).encode());h.update(data)
        return h.digest()
    def prepare(self,submaps,robot_id):
        if robot_id!=self.robot_id:raise ValueError('POSE_GRAPH_PEER_CACHE_FORBIDDEN')
        for submap in submaps:
            key=self.submap_key(submap)
            if key not in self.fields:
                self.fields[key]=Prepared(submap,self);self.counts['field_misses']+=1
                if len(self.fields)>self.max_fields:self.fields.popitem(last=False)
            else:self.counts['field_hits']+=1
            self.fields.move_to_end(key)
            submap['_cached_key']=key;submap['_prepared']=self.fields[key]
    def match(self,submap,row,initial,options):
        from harness.self_pose_graph import match_loop
        if row.get('robot_id')!=self.robot_id:raise ValueError('POSE_GRAPH_PEER_CACHE_FORBIDDEN')
        key=(submap['_cached_key'],array_key(row['segments']),array_key(initial),astuple(options))
        if key in self.pairs:
            self.counts['pair_hits']+=1;self.pairs.move_to_end(key)
            return copy.deepcopy(self.pairs[key])
        self.counts['pair_misses']+=1
        event=match_loop(submap,row,initial,options,prepared=submap['_prepared'])
        self.pairs[key]=copy.deepcopy(event)
        if len(self.pairs)>self.max_pairs:self.pairs.popitem(last=False)
        return event
    def stats(self):
        return dict(self.counts,pair_entries=len(self.pairs),field_entries=len(self.fields),
                    max_pairs=self.max_pairs,max_fields=self.max_fields)


def install(memory,*,graph_acceleration='off'):
    if graph_acceleration=='off':return memory
    if graph_acceleration!=OPTION:raise ValueError('UNKNOWN_GRAPH_ACCELERATION')
    if memory.pose_graph!='own_submap_v1':raise ValueError('CACHE_REQUIRES_OWN_SUBMAP')
    memory.graph_cache=GraphCache(memory.robot_id)
    return memory
