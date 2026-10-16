"""Default-off compatibility for the pinned legacy planner dependency.

The legacy bounded retry policy registered DeepInfra Gemma only. CoreWeave
was switched by the user on 2026-10-16 (PR #552/#553). This private module copy
adds its exact selections; old provider selections and retry limits remain.
"""
import ast
import hashlib
import inspect
import textwrap


def install_coreweave_rate_v1(upstream, models):
    if getattr(upstream, '_warp9_rate_audit', None):
        return upstream._warp9_rate_audit
    source=textwrap.dedent(inspect.getsource(upstream.config))
    tree=ast.parse(source)
    choices=tuple(models.ModelSelection(models.DEFAULT_MODEL,provider,'default',fmt)
        for provider in ('CoreWeave','coreweave/fp4') for fmt in ('off','json_object'))
    changed=0

    class Registration(ast.NodeTransformer):
        def visit_Compare(self,node):
            nonlocal changed
            if (isinstance(node.left,ast.Tuple) and ast.dump(node.left)==ast.dump(ast.parse('(rate_limit_policy,choice)',mode='eval').body)
                    and len(node.ops)==1 and isinstance(node.ops[0],ast.NotIn)
                    and len(node.comparators)==1 and isinstance(node.comparators[0],ast.Tuple)):
                old=node.comparators[0]
                if len(old.elts)!=4:raise ValueError('legacy rate registration changed')
                old.elts.extend(ast.parse("('planner_rate_limit_v1',__warp9_choices__[%d])"%i,mode='eval').body for i in range(len(choices)))
                changed+=1
            return self.generic_visit(node)

    tree=ast.fix_missing_locations(Registration().visit(tree))
    if changed!=1:raise ValueError('expected one pinned rate registration')
    namespace=dict(upstream.config.__globals__,__warp9_choices__=choices)
    exec(compile(tree,'<warp9-coreweave-rate-registration>','exec'),namespace)
    upstream.config=namespace['config']
    # Same pre-existing UTF-8 reservation formula; CoreWeave prices are from
    # configs/model_endpoints.json / user-approved 2026-10-16 endpoint snapshot.
    # This is a spend reservation, not a task acceptance or physics constant.
    from scripts import openrouter_ling_policy as policy
    original=policy.reserve_cost
    def reserve(body,selection=None):
        if selection in choices:
            import json
            return (len(json.dumps(body,ensure_ascii=True).encode())+4096)*.1/1e6+body.get('max_tokens',768)*.34/1e6
        return original(body,selection)
    policy.reserve_cost=reserve
    audit=dict(profile='warp9_coreweave_rate_v1',registration_edits=changed,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        ast_sha256=hashlib.sha256(ast.dump(tree).encode()).hexdigest(),
        choices=[vars(c) for c in choices],reserved_usd_per_million=dict(prompt=.1,completion=.34),
        basis='user-approved CoreWeave fp4; configs/model_endpoints.json; legacy reservation formula unchanged')
    upstream._warp9_rate_audit=audit
    return audit
