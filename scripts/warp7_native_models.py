"""Opt-in exact native-model batching; no C3.12 reference or numeric fit."""
import ast,dataclasses,hashlib,inspect,json,textwrap
import numpy as np


def layout_digest(arrays,scalars,batchable):
    """A group shares every unsupported value and every supported layout."""
    h=hashlib.sha256(json.dumps(scalars,sort_keys=True).encode())
    for name,value in sorted(arrays.items()):
        a=np.asarray(value)
        h.update(json.dumps([name,a.dtype.str,a.shape,name in batchable]).encode())
        if name not in batchable:h.update(a.tobytes())
    return h.hexdigest()


def group_key(model):
    import copy,mujoco,warp as wp,mujoco_warp as mjw
    from scripts.warp_act_core import runtime_sleep_policy
    model=copy.copy(model)
    enum=mujoco.mjtSleepPolicy
    model.tree_sleep_policy[:]=runtime_sleep_policy(model.tree_sleep_policy,auto=int(enum.mjSLEEP_AUTO),
        auto_never=int(enum.mjSLEEP_AUTO_NEVER),auto_allowed=int(enum.mjSLEEP_AUTO_ALLOWED),
        never=int(enum.mjSLEEP_NEVER),allowed=int(enum.mjSLEEP_ALLOWED))
    arrays={};scalars={};batchable=set()
    def visit(obj,prefix=''):
        for field in dataclasses.fields(obj):
            value=getattr(obj,field.name);name=prefix+field.name
            if dataclasses.is_dataclass(value):visit(value,name+'.')
            elif isinstance(value,wp.array):
                arrays[name]=value.numpy()
                if getattr(field.type,'shape',())[:1]==('*',):batchable.add(name)
            elif isinstance(value,(int,float,bool,str,type(None))):scalars[name]=value
    visit(mjw.put_model(model))
    # Existing pinned warp_act_sleep adapter indexes the exact native array by
    # world*nv+dof. It changes one lookup, with no sleep predicate/threshold fit.
    batchable.add('dof_length')
    # Renderer uses these native arrays outside MJWarp's batched field API.
    # Keep them identical even if the corresponding GPU field is batchable.
    for name in ('geom_rgba','geom_matid','geom_group','light_type','light_cutoff','cam_pos','cam_quat'):
        arrays['renderer.'+name]=getattr(model,name)
    from scripts.warp5_render import rgba_values
    rgba=rgba_values(model);transparent=np.flatnonzero((rgba[:,3]>0)&(rgba[:,3]<.995)&(model.geom_group<4))
    # Renderer reads native rbound only for ordering transparent layers;
    # opaque cargo bounds remain world-specific in wm.geom_rbound.
    arrays['renderer.transparent_rbound']=model.geom_rbound[transparent]
    return layout_digest(arrays,scalars,batchable)


def initialize(transport,contexts,**kwargs):
    """Reuse the shared verified combiner without forging C3.12 asset refs.

    Only two AST branches change: native per-world models skip copying the
    first model's geometry and select the existing exact-field combiner.
    All unsupported arrays/scalars still fail closed in combine_models.
    """
    from scripts import warp_act_backend as backend
    source=textwrap.dedent(inspect.getsource(backend.WarpTransport.initialize))
    tree=ast.parse(source);counts=dict(native_branch=0,combine=0)
    class Rewrite(ast.NodeTransformer):
        def visit_If(self,node):
            self.generic_visit(node)
            if isinstance(node.test,ast.Name) and node.test.id=='refs' and any(isinstance(n,ast.Attribute) and n.attr=='combine_models' for n in ast.walk(node)):
                node.test=ast.Constant(True);counts['combine']+=1
            if isinstance(node.test,ast.Compare) and any(isinstance(n,ast.Name) and n.id=='model_key' for n in ast.walk(node.test)):
                # Preserve per-world native model exactly; no first-world
                # geometry copy and no unrelated compiled-reference assets.
                node.test=ast.Constant(True)
                node.body=ast.parse('actuator_asset=geometry_asset=None').body
                counts['native_branch']+=1
            return node
    Rewrite().visit(tree)
    if counts!={'native_branch':1,'combine':1}:raise ValueError('native initialization AST changed: '+str(counts))
    namespace=backend.__dict__.copy();exec(compile(ast.fix_missing_locations(tree),'<warp7-native-model-batch>','exec'),namespace)
    transport.native_model_adapter=dict(edits=counts,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        ast_sha256=hashlib.sha256(ast.dump(tree).encode()).hexdigest(),basis='pinned MJWarp dataclass batchable * fields; exact unsupported arrays/scalars, no numeric tolerance')
    return namespace['initialize'](transport,contexts,**kwargs)
