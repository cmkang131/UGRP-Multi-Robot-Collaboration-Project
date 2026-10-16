"""Private evaluation-only same-kind object scores; actor observations unchanged.

Uses the qualified backend's existing contact-force kernel with separate
scratch outputs. No shared backend/model/scene file or physics option changes.
"""
from copy import deepcopy
import json
import math


class InstanceMetrics:
    def __init__(self, owner):
        import numpy as np
        from warp_act_scene import make_scene
        from warp_act_visibility import BatchVisibility
        self.owner, self.np, self.items, self.last = owner, np, [], {}
        self.log = (owner.out / 'same-kind-evaluation-only.jsonl').open('x')
        self.samples, self.checks = 0, 0
        contexts = []
        for i, (plan, ctx) in enumerate(zip(owner.plans, owner.contexts)):
            scene = make_scene({**plan, 'end_color_scene': 'off'})
            index = {iid: dict(body_name=value['body_name'], kind=iid.rsplit('_', 1)[0])
                     for iid, value in scene.config['setup_only']['objects'].items()}
            rows = []
            model = ctx['world'].model
            for iid, value in sorted(index.items()):
                if value['kind'] != plan['kind']:
                    continue
                bid = model.body(value['body_name']).id
                gids = [g for g in range(model.ngeom)
                        if model.geom_bodyid[g] == bid and model.geom_contype[g]]
                if len(gids) != 1:
                    raise ValueError('qualified same-kind BOX requires one collision geom')
                rows.append(dict(item_id=iid, body=bid, gids=gids,
                                 initial_xy=ctx['world'].data.xpos[bid, :2].copy()))
            if plan['item_id'] not in {row['item_id'] for row in rows}:
                raise ValueError('assigned item missing from scenario same-kind catalogue')
            self.items.append(rows)
            # An index, not a replacement for the actual native scene XML.
            (ctx['folder'] / 'scene-index.json').write_text(json.dumps(dict(
                box_replicas=index, scope='static scenario catalogue for private evaluation only'), indent=2)+'\n')
            contexts.append({**ctx, 'visibility_gids': sorted({g for row in rows for g in row['gids']})})
        self.scratch = owner.hooks.wp.zeros((owner.n, 2), dtype=float)
        self.targets = [owner.hooks.wp.array([
            rows[k]['gids'][0] if k < len(rows) and rows[k]['item_id'] != owner.plans[i]['item_id'] else -1
            for i, rows in enumerate(self.items)], dtype=int)
            for k in range(max(map(len, self.items)))]
        before, public = owner.integration(), deepcopy(owner.current)
        eyes = BatchVisibility(owner.hooks, contexts)
        eyes.update({name: getattr(owner.hooks.wd, name).numpy()
                     for name in ('geom_xpos', 'geom_xmat', 'cam_xpos', 'cam_xmat')})
        visibility = []
        for i, rows in enumerate(self.items):
            values = []
            for row in rows:
                seen, total = eyes.region_visible(i, row['gids'])
                values.append(dict(item_id=row['item_id'], seen_probes=seen, total_probes=total,
                                   any_probe_visible=seen > 0,
                                   qualified_visible=total > 0 and seen >= math.ceil(total / 3)))
            visibility.append(dict(seed=owner.plans[i]['seed'], world=i, items=values,
                any_probe_visible_count=sum(x['any_probe_visible'] for x in values),
                qualified_visible_count=sum(x['qualified_visible'] for x in values),
                own_start_RGB_sha256=owner.current[i][0]['rgb'][-1]['sha256']))
        self.unchanged(before, public)
        owner.write('initial-same-kind-visibility.json', dict(rows=visibility,
            scope='evaluation-only geometric seven-probe visibility, existing qualified1/3 boundary; any-probe count also retained; not pixel segmentation'))
        self.sample([True] * owner.n)

    def unchanged(self, before, public):
        after = self.owner.integration()
        if (public != self.owner.current
                or any(not self.np.array_equal(value, after[key]) for key, value in before.items())):
            raise RuntimeError('private instance evaluation changed actor input or integration state')
        self.checks += 1

    def sample(self, active):
        from sim.grasp_act_solo_evaluation import bottom_z
        owner, np, h = self.owner, self.np, self.owner.hooks
        before, public = owner.integration(), deepcopy(owner.current)
        force_slots = []
        d = h.wd
        for targets in self.targets:
            self.scratch.zero_()
            h.wp.launch(h.eval_kernel, dim=d.naconmax, inputs=[d.nacon, d.contact.worldid,
                d.contact.geom, int(h.m.opt.cone), int(d.njmax), d.contact.frame,
                d.contact.friction, d.contact.dim, d.contact.efc_address,
                d.contact.adhesion, d.efc.force, targets, h.finger_ids, self.scratch])
            force_slots.append(self.scratch.numpy().copy())
        for i, rows in enumerate(self.items):
            if not active[i]:
                continue
            model, data = owner.contexts[i]['world'].model, owner.contexts[i]['world'].data
            now = owner.origin + owner.tick * .1
            for k, row in enumerate(rows):
                bid = row['body']; position = data.xpos[bid].copy()
                previous = self.last.get((i, row['item_id']))
                speed = 0. if previous is None else float(np.linalg.norm(position-previous[1])/(now-previous[0]))
                forces = (h.contact_forces[i].tolist() if row['item_id'] == owner.plans[i]['item_id']
                          else force_slots[k][i].tolist())
                value = dict(world=i, seed=owner.plans[i]['seed'], item_id=row['item_id'],
                    assigned=row['item_id'] == owner.plans[i]['item_id'], t=now,
                    elapsed_sim_s=int(owner.ages[i])*.1, speed=speed,
                    min_z=min(float(bottom_z('box', data.geom_xpos[g], data.geom_xmat[g].reshape(3, 3), model.geom_size[g])) for g in row['gids']),
                    tilt_deg=math.degrees(math.acos(float(np.clip(data.xmat[bid, 8], -1., 1.)))),
                    finger_forces=forces, weld_active=bool(data.eq_active.any()))
                self.log.write(json.dumps(value, allow_nan=False)+'\n')
                self.last[i, row['item_id']] = now, position
                self.samples += 1
        self.log.flush()
        self.unchanged(before, public)

    def close(self):
        if self.log.closed:
            return
        self.log.close()
        self.owner.write('same-kind-evaluation-audit.json', dict(
            samples=self.samples, input_and_integration_unchanged_checks=self.checks,
            privileged_actor_inputs=0, teacher_actions_executed=0,
            scope='private evaluation only; assigned forces copied unchanged; other items use exact qualified force kernel'))
