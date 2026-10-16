"""Default-off persistent NoSlip workspaces; original kernels and arithmetic.

Pinned MJWarp solver.noslip allocates L/Y/A on every captured physics tick.
Warp's stream-ordered allocation guide permits allocation in graphs, but a
serial solver can also retain scratch across calls. The original kernels
initialize every row they consume. All steps use one stream; these buffers
are private to one transport and retained for its captured graph's lifetime.
NoSlip iterations/tolerance, dt and solver selection are unchanged.
"""
import ast
from contextlib import contextmanager
import hashlib
import inspect
import textwrap


def rewrite(function, workspace):
    source=textwrap.dedent(inspect.getsource(inspect.unwrap(function)))
    tree=ast.parse(source)
    expected={
        'noslip_L':'wp.empty((d.nworld, m.nv, m.nv), dtype=float)',
        'noslip_Y':'wp.empty((d.nworld, d.njmax, m.nv), dtype=float)',
        'noslip_A':'wp.empty((d.nworld, d.njmax), dtype=types.vec5)',
    }
    counts={key:0 for key in expected}
    class Replace(ast.NodeTransformer):
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                key=node.targets[0].id
                if key in expected:
                    if ast.dump(node.value)!=ast.dump(ast.parse(expected[key],mode='eval').body):
                        raise ValueError('pinned NoSlip allocation changed: '+key)
                    counts[key]+=1
                    node.value=ast.parse(f'__warp9_workspace__(m,d)[{key!r}]',mode='eval').body
            return node
    tree=ast.fix_missing_locations(Replace().visit(tree))
    if counts!={key:1 for key in expected}:raise ValueError('expected exactly three NoSlip allocations')
    ns=dict(inspect.unwrap(function).__globals__,__warp9_workspace__=workspace)
    exec(compile(tree,'<warp9-persistent-noslip-workspace>','exec'),ns)
    return ns[function.__name__],dict(profile='warp9_noslip_scratch_v1',allocation_edits=counts,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        ast_sha256=hashlib.sha256(ast.dump(tree).encode()).hexdigest(),
        basis='pinned NoSlip source; private persistent buffers, unchanged original kernels and math')


@contextmanager
def scope(owner):
    from mujoco_warp._src import solver
    import warp as wp
    original=solver.noslip
    cache={}
    def workspace(m,d):
        key=(d.nworld,m.nv,d.njmax)
        if key not in cache:
            cache[key]=dict(noslip_L=wp.empty((d.nworld,m.nv,m.nv),dtype=float),
                noslip_Y=wp.empty((d.nworld,d.njmax,m.nv),dtype=float),
                noslip_A=wp.empty((d.nworld,d.njmax),dtype=solver.types.vec5))
        return cache[key]
    replacement,audit=rewrite(original,workspace)
    owner.warp9_scratch_buffers=cache
    owner.warp9_scratch_audit=audit
    solver.noslip=replacement
    try:
        yield
    finally:
        if solver.noslip is not replacement:raise RuntimeError('NoSlip scope ownership changed')
        solver.noslip=original
        audit['workspaces']=[dict(nworld=k[0],nv=k[1],njmax=k[2],
            # Warp float is float32; pinned types.vec5 has five float32s.
            bytes=4*k[0]*(k[1]*k[1]+k[2]*k[1]+5*k[2]))
            for k,v in cache.items()]
