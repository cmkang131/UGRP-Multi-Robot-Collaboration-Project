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
        import cv2
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
                                 visible_gids=[g for g in range(model.ngeom)
                                               if model.geom_bodyid[g] == bid and model.geom_group[g] in (0, 1, 2, 3)],
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
        h = owner.hooks
        segmentation = h.mjw.create_render_context(h.m, nworld=owner.n, cam_res=(640, 480),
            render_rgb=False, render_depth=False, render_seg=True, use_textures=True,
            use_shadows=True, enabled_geom_groups=[0, 1, 2, 3], cam_active=['r1__robot_cam'])
        h.mjw.refit_bvh(h.wm, h.wd, segmentation)
        h.mjw.render(h.wm, h.wd, segmentation)
        ids = segmentation.seg_data.numpy().reshape(owner.n, 480, 640, 2)
        visibility = []
        for i, rows in enumerate(self.items):
            values = []
            for row in rows:
                seen, total = eyes.region_visible(i, row['gids'])
                raw_mask = (np.isin(ids[i, ..., 0], row['visible_gids'])
                            & (ids[i, ..., 1] == int(h.mjw.ObjType.GEOM))).astype(np.float32)
                mask = cv2.remap(raw_mask, h.mx, h.my, cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT) > 0
                yy, xx = np.nonzero(mask)
                values.append(dict(item_id=row['item_id'], seen_probes=seen, total_probes=total,
                                   visible_pixels=int(mask.sum()),
                                   visible_bbox_xyxy=[int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())] if len(xx) else None,
                                   any_probe_visible=seen > 0,
                                   qualified_visible=total > 0 and seen >= math.ceil(total / 3)))
            visibility.append(dict(seed=owner.plans[i]['seed'], world=i, items=values,
                pixel_visible_count=sum(x['visible_pixels'] > 0 for x in values),
                any_probe_visible_count=sum(x['any_probe_visible'] for x in values),
                qualified_visible_count=sum(x['qualified_visible'] for x in values),
                own_start_RGB_sha256=owner.current[i][0]['rgb'][-1]['sha256']))
        self.unchanged(before, public)
        owner.write('initial-same-kind-visibility.json', dict(rows=visibility,
            scope='native MJWarp start-frame instance segmentation, same camera/groups/fisheye bilinear footprint, at least1 visible pixel; seven-probe diagnostics retained; scenario catalogue boxes only; evaluation only'))
        self.sample([True] * owner.n)

    def unchanged(self, before, public):
        after = self.owner.integration()
        differences = {key: dict(shape_before=list(value.shape), shape_after=list(after[key].shape),
            numeric_equal=bool(self.np.array_equal(value, after[key])),
            bytes_equal=value.dtype == after[key].dtype and value.shape == after[key].shape and value.tobytes() == after[key].tobytes())
            for key, value in before.items()}
        # Bitwise identity is stronger than numeric equality (+0/-0), and does
        # not falsely flag an unchanged NaN payload in unused workspace state.
        if public != self.owner.current or any(not value['bytes_equal'] for value in differences.values()):
            self.owner.write('instance-evaluation-state-diff.json', dict(
                actor_inputs_equal=public == self.owner.current, fields=differences))
            self.np.savez_compressed(self.owner.out/'instance-evaluation-state-before.npz', **before)
            self.np.savez_compressed(self.owner.out/'instance-evaluation-state-after.npz', **after)
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
