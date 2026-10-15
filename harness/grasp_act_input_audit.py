"""Fail-closed teacher input capability: a visual mapping, never a World handle.

held_world_reads counts attempted access to nonvisual world fields at this
boundary. It is not a count of evaluator/measurement-adapter simulator reads.
"""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass

FIELDS=frozenset(('t','robots','objects','walls','beam','visibility','scope'))
ALLOWED_SOURCES=frozenset(('own_rgb','issued_commands','visible_teacher_measurement','static_map','known_shape','clock','fixed_rule'))


@dataclass(frozen=True)
class Sourced:
    value: object
    sources: frozenset


def sourced(value, *sources):
    """Tag at the producer, retaining dependencies through every derived value.

    This is a runtime provenance contract, not a detector for a producer lying
    about its source. Untagged or evaluation-tagged payloads fail closed.
    """
    return Sourced(deepcopy(value),frozenset(sources))


def admit(value, audit):
    if isinstance(value,Sourced):
        if not value.sources or not value.sources<=ALLOWED_SOURCES:
            audit['held_world_reads']+=1
            raise ValueError('forbidden value provenance: '+repr(sorted(value.sources)))
        counts=audit.setdefault('admitted_source_tags',{})
        for source in sorted(value.sources):counts[source]=counts.get(source,0)+1
        # A parent source cannot launder a nested tagged GT value.
        def nested(v):
            if isinstance(v,Sourced):return admit(v,audit)
            if isinstance(v,Mapping):return {k:nested(x) for k,x in v.items()}
            if isinstance(v,(list,tuple)):return [nested(x) for x in v]
            return deepcopy(v)
        return nested(value.value)
    if isinstance(value,Mapping):return {k:admit(v,audit) for k,v in value.items()}
    audit['held_world_reads']+=1
    raise ValueError('untagged value at strict teacher boundary')


class AuditedTeacherInput(Mapping):
    def __init__(self, visible, audit, *, provenance='off'):
        self.audit=audit
        if provenance not in ('off','value_sources_v1'):raise ValueError('unknown provenance mode')
        self.provenance=provenance
        if provenance!='off':visible=admit(visible,audit)
        if set(visible)-FIELDS:
            audit['held_world_reads']+=1
            raise ValueError('nonvisual world field delivered to teacher')
        self.visible=visible

    def __getitem__(self,key):
        if key not in FIELDS:
            self.audit['held_world_reads']+=1
            raise ValueError('held world read forbidden: '+str(key))
        return deepcopy(self.visible[key]) if self.provenance!='off' else self.visible[key]

    def __iter__(self):return iter(self.visible)
    def __len__(self):return len(self.visible)


def new_input_audit(enabled,pose_source):
    return {'scope':'visual measurement admission and nonvisual-field access guard; evaluator/adapter reads excluded',
            'enabled':enabled,'measurement_rows':0,'invisible_measurements':0,
            'held_world_reads':0,'gt_self_pose_comparison':pose_source!='issued'}
