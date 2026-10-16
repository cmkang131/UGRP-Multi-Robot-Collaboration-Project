"""Opt-in host staging. Actors receive no additional simulator fields.

Warp 1.15 concurrency: pinned CPU arrays + wp.copy + one completion event
before reading NumPy views. Slots belong to one owner/stream and are reused.
The upstream evaluator is separately staged once per batch, never per world.
"""
import ast
import hashlib
import inspect
import textwrap
import numpy as np
from scripts.warp9_profile import exporter, phase


def make_gather(wp):
    @wp.kernel
    def gather(source:wp.array2d[wp.vec3],ids:wp.array[int],out:wp.array2d[wp.vec3]):
        w,j=wp.tid();out[w,j]=source[w,ids[j]]
    return gather


class Readback:
    def __init__(self, wp, owner, prefix):
        self.wp,self.owner,self.prefix=wp,owner,prefix
        self.slots={};self.pending={};self.bytes=0;self.syncs=0

    def enqueue(self, key, array):
        if key in self.pending:
            if self.pending[key][0] is not array:raise ValueError('readback key aliases different arrays')
            return
        slot=self.slots.get(key)
        if slot is None:
            slot=self.wp.empty(array.shape,dtype=array.dtype,device='cpu',pinned=True)
            self.slots[key]=slot
        elif slot.shape!=array.shape or slot.dtype!=array.dtype:
            raise ValueError('pinned slot layout changed')
        with phase(self.owner,self.prefix+'_d2h',nbytes=array.capacity):
            self.wp.copy(slot,array)
        self.pending[key]=(array,slot);self.bytes+=array.capacity

    def finish(self):
        with phase(self.owner,self.prefix+'_existing_sync',explicit_syncs=1):
            event=self.wp.Event();self.wp.record_event(event);self.wp.synchronize_event(event)
        self.syncs+=1
        values={k:slot.numpy() for k,(_,slot) in self.pending.items()}
        self.pending.clear()
        return values


def device_reads(function):
    """Fail closed on any exporter read outside its explicit d.field paths."""
    source=textwrap.dedent(inspect.getsource(function));paths=set()
    parameter=list(inspect.signature(function).parameters)[2]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='numpy':
            value=node.func.value;parts=[]
            while isinstance(value,ast.Attribute):parts.append(value.attr);value=value.value
            if not isinstance(value,ast.Name) or value.id!=parameter or node.args or node.keywords:
                raise ValueError('unsupported evaluator read')
            paths.add(tuple(reversed(parts)))
    if not paths:raise ValueError('no evaluator arrays')
    return sorted(paths),hashlib.sha256(source.encode()).hexdigest()


class EvaluationExport:
    """Same upstream CPU export/contact ordering; no whole-world rereads.

    Fields are restricted to the pinned upstream export's static read manifest.
    This broad evaluation mirror is not the actor/command buffer. Zero-sized
    and model-inapplicable optional fields carry no device bytes.
    """
    def __init__(self, owner):
        self.owner=owner;self.paths,self.source_sha=device_reads(owner.mjw.get_data_into)
        self.readback=Readback(owner.wp,owner,'evaluator');self.values={}
        self.export,self.ast_audit=exporter(owner.mjw.get_data_into,self.read)

    def read(self,array):
        try:return self.values[id(array)]
        except KeyError:raise ValueError('unregistered evaluator array') from None

    def stage(self):
        for path in self.paths:
            value=self.owner.wd
            for part in path:value=getattr(value,part)
            if value is not None:self.readback.enqueue(id(value),value)
        self.values=self.readback.finish()

    def audit(self):
        return dict(fields=['.'.join(p) for p in self.paths],
            arrays=len(self.readback.slots),total_bytes=self.readback.bytes,
            syncs=self.readback.syncs,actor_reads=0,scope='evaluation-only full upstream export',**self.ast_audit)

    def compare(self,contexts):
        """Initial same-device-state export, every world and exported field."""
        import copy
        rows=[]
        for i,c in enumerate(contexts):
            actual=c['world'].data;reference=copy.copy(actual)
            self.owner.mjw.get_data_into(reference,c['world'].model,self.owner.wd,world_id=i)
            differences=[];checked=0
            for name in dir(actual):
                if name.startswith('_'):continue
                value=getattr(actual,name)
                if isinstance(value,np.ndarray):
                    other=getattr(reference,name);checked+=1
                    if value.shape!=other.shape or value.tobytes()!=other.tobytes():differences.append(name)
            for name in dir(actual.contact):
                if name.startswith('_'):continue
                value=getattr(actual.contact,name)
                if isinstance(value,np.ndarray):
                    other=getattr(reference.contact,name);checked+=1
                    if value.shape!=other.shape or value.tobytes()!=other.tobytes():differences.append('contact.'+name)
            for name in ('time','ncon','nefc','nisland','nidof'):
                if getattr(actual,name)!=getattr(reference,name):differences.append(name)
            rows.append(dict(world=i,checked_arrays=checked,exact=not differences,differences=differences))
        return rows


def blend_staged(opaque,layers,alpha,order):
    """Convert only consumed layer pixels; preserve native float64 operations."""
    out=opaque.astype(float)*255
    for indices in (order,order[:,::-1]):
        for rank in range(indices.shape[1]):
            for w,j in enumerate(indices[:,rank]):
                colour,mask=layers[j];a=alpha[j];selected=mask[w]
                out[w][selected]=a*(colour[w][selected].astype(float)*255)+(1-a)*out[w][selected]
    return out


def command_tapes(row_groups,relays,tables,**kwargs):
    """Vectorize robot and world axes, retaining the exact tick recurrence.

    Canonical command slots have 4 wheels + 5 issued servos. Native fingers
    share a servo command, as enforced by build_lookup's joint-limit check.
    No closed-form interpolation: floating point accumulation order is kept.
    """
    from scripts.warp_act_core import control_tape
    lookup=tables[0][0];n=len(row_groups[0])
    if any(len(rows)!=n for rows in row_groups) or any(not np.array_equal(t[0],lookup) for t in tables):
        raise ValueError('matching robot command lookup and world layouts required')
    rows=[dict(row,ctrl=np.zeros(9)) for group in row_groups for row in group]
    tape,state=control_tape(rows,np.concatenate(relays),lookup=lookup,
        wheel_ids=[0,1,2,3],servo_ids=[[4],[5],[6],[7],[8]],**kwargs)
    result=[]
    for j,(original,(_,wheels,servos)) in enumerate(zip(row_groups,tables)):
        section=slice(j*n,(j+1)*n)
        # Only owned actuators are consumed by the common tape assembler.
        value=np.broadcast_to(np.stack([r['ctrl'] for r in original]),(kwargs['steps'],n,len(original[0]['ctrl']))).copy().astype(np.float32)
        value[:,:,wheels]=tape[:,section,:4]
        for k,ids in enumerate(servos):value[:,:,ids]=tape[:,section,4+k,None]
        result.append((value,{k:v[section] for k,v in state.items()}))
    return result
