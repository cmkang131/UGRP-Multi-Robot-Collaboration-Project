"""DEV-only solo yaw calibration; v102 loaded translation stays unchanged.

Batch least squares on run3's saved command integrals / rigid cargo bearing;
run4 retrospective maximum angular residual 0.066 degrees. Both are s911
exploration, not independent validation. No live evaluation input is read.
See experiments/2026-10-05-solo-cyan-v106/yaw-fit.json and README.
"""
import copy

LEFT_TO_YAW = -0.11967128338166085
TURN_TO_YAW = 0.703348846717357
ID = 'solo-cyan-yaw-coupling-s911-exploratory-v1'


def record():
    return {'id': ID, 'raw_command_yaw_row': [0., LEFT_TO_YAW, TURN_TO_YAW],
            'source': 'ee40923c s911 three loaded legs; rigid cargo bearing proxy',
            'retrospective_check': 'd1860059 s911; not independent',
            'qualified': False, 'translation': 'v102 unchanged',
            'yaw_lag': 'v102 retained, not refitted'}


def install(pf):
    """Map the raw yaw operand locally; never alter issued commands or shared PF files."""
    if hasattr(pf, 'solo_yaw_model'):
        raise ValueError('solo yaw already installed')
    loaded = pf.params['motion_loaded']
    loaded['gain'][2] = [0., 0., TURN_TO_YAW]
    for key in ('c0', 'u0', 'u1'):
        loaded['deadband'][key][2] = 0.
    predict = pf.predict_to

    def predict_to(t):
        issued = pf.cmd
        if pf.load.loaded:
            pf.cmd = issued.copy()
            # Yaw responds to raw lateral input, before translation's affine
            # dead zone. The inherited predictor still handles expiry and lag.
            pf.cmd[2] += LEFT_TO_YAW / TURN_TO_YAW * issued[1]
        try:
            return predict(t)
        finally:
            pf.cmd = issued

    pf.predict_to = predict_to
    pf.solo_yaw_model = copy.deepcopy(record())
