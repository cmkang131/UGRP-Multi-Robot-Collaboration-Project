"""Fail-closed teacher input capability: a visual mapping, never a World handle.

held_world_reads counts attempted access to nonvisual world fields at this
boundary. It is not a count of evaluator/measurement-adapter simulator reads.
"""
from collections.abc import Mapping

FIELDS=frozenset(('t','robots','objects','walls','beam','visibility','scope'))


class AuditedTeacherInput(Mapping):
    def __init__(self, visible, audit):
        self.audit=audit
        if set(visible)-FIELDS:
            audit['held_world_reads']+=1
            raise ValueError('nonvisual world field delivered to teacher')
        self.visible=visible

    def __getitem__(self,key):
        if key not in FIELDS:
            self.audit['held_world_reads']+=1
            raise ValueError('held world read forbidden: '+str(key))
        return self.visible[key]

    def __iter__(self):return iter(self.visible)
    def __len__(self):return len(self.visible)


def new_input_audit(enabled,pose_source):
    return {'scope':'visual measurement admission and nonvisual-field access guard; evaluator/adapter reads excluded',
            'enabled':enabled,'measurement_rows':0,'invisible_measurements':0,
            'held_world_reads':0,'gt_self_pose_comparison':pose_source!='issued'}
