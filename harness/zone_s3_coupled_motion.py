"""S3 paired-beam exception: preserve the registered continuous carry plant.

Own issued grasp/release history selects prediction. The existing two-party
GO protocol authorizes motion; no truth, shared pose or dock prior is added.
"""
import copy

HEADING_EXCEPTIONS = {
    'coupled_beam_carry': dict(robots=['r1', 'r2'], required_robots=2,
        controller_state='carry', partner_enum='carry',
        motion='unchanged registered pair schedule, including lateral',
        entry='existing two-party GO and own commanded grasp',
        exit='own commanded release', gt_inputs=False),
}


def authorized(endpoint, now):
    if endpoint.own.robot_id not in HEADING_EXCEPTIONS['coupled_beam_carry']['robots']:
        return False
    if endpoint.controller.state != 'carry' or not endpoint.own.pose.localizer.pose.provider.loc._pf.load.loaded:
        return False
    peers = endpoint.status.channel.partner_view(endpoint.own.robot_id, now)
    return bool(peers) and all(p['alive'] and p['state'] == 'carry' for p in peers.values())


def attach_prediction(runtime, pair_params):
    """Keep one posterior; route its predictor below the same AMCL odom integrator.

    The private closure belongs to this PF instance. update_obs and predict_to
    share it, so both retain the unchanged global-filter odometry accounting.
    Only the loaded command plant is restored; cameras/likelihood stay S2 v3.
    """
    if runtime.robot_id not in ('r1', 'r2'):
        raise ValueError('coupled prediction requires a registered pair role')
    pf = runtime.pose.provider.loc._pf
    predictor = pf.predict_to
    if predictor.__qualname__ != 'install_global_update.<locals>.predict_to':
        raise ValueError('expected instance-local global prediction wrapper')
    cells = dict(zip(predictor.__code__.co_freevars, predictor.__closure__))
    if cells['pf'].cell_contents is not pf:
        raise ValueError('foreign prediction closure')
    pulse_predict = cells['predict'].cell_contents
    pulse_command = pf.command
    old_loaded = copy.deepcopy(pf.params['motion_loaded'])
    pair_loaded = copy.deepcopy(pair_params['motion_loaded'])
    mode = False
    audit = dict(exception='coupled_beam_carry', pose_reset=False, gt_inputs=False,
        motion_loaded=pair_loaded, source='same static pair params used by door_schedule', transitions=[])

    def predict(t):
        if mode:
            return type(pf).predict_to(pf, t)
        return pulse_predict(t)

    def command(row):
        nonlocal mode
        # The previous mode predicts up to the issued command's own timestamp.
        if mode:
            type(pf).command(pf, row)
        else:
            pulse_command(row)
        loaded = bool(pf.load.loaded)
        if loaded != mode:
            mode = loaded
            pf.params['motion_loaded'] = copy.deepcopy(pair_loaded if mode else old_loaded)
            if mode:
                pf._load_transition(True)  # only latent plant variables, never pose/weights
            audit['transitions'].append(dict(t=float(row['t']),
                mode='coupled_continuous' if mode else 'heading_pulse', source='own command history'))

    cells['predict'].cell_contents = predict
    pf.command = command
    # S2 loaded pulse-flow buffering assumes profile_key(one axis). The pair
    # model is continuous and already includes lag; keep own RGB wall updates.
    if hasattr(runtime, 'flow'):
        supported = runtime.flow.supported
        runtime.flow.supported = lambda servo: not pf.load.loaded and supported(servo)
    runtime.s3_coupled_motion = audit
    return runtime
