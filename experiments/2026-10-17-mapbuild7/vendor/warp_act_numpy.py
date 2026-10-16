"""Command-only NumPy IK: frozen SDK triangles over all 51 allowed pitches.

No simulator imports or measured state. Numerical/acceptance constants are read
from the original calibrated SDK, including its PWM rounding and tie order.
"""
import numpy as np


def solve_grip_site_ik(target_xyz_m, *, preferred_pitch_deg=-66., calibrated_grasp_only=True):
    from harness import visual_arm as sdk
    from harness import visual_arm_v3 as v3
    if len(target_xyz_m) != 3:
        raise ValueError('target_xyz_m must contain x, y, z')
    x,y,z = (sdk._finite('target coordinate', v) for v in target_xyz_m)
    preferred = sdk._finite('preferred_pitch_deg', preferred_pitch_deg)
    x -= v3.MOUNT_X_M; z -= v3.SHOULDER_DELTA_Z_M
    radius = np.hypot(x,y)*100.
    lo,hi = sdk.CALIBRATED_GRASP_RADIUS_CM
    if calibrated_grasp_only and not lo-1e-10 <= radius <= hi+1e-10:
        raise ValueError('target radius is outside the calibrated arm-axis envelope')
    pan = round(sdk.BASE_CENTER + float(np.degrees(np.arctan2(y,x)))*sdk.PULSE_PER_DEGREE)
    if not sdk.CALIBRATED_PAN_MIN <= pan <= sdk.CALIBRATED_PAN_MAX:
        raise ValueError('target yaw is outside the calibrated servo-6 grasp sector')
    pitches = np.arange(-90,-39)
    alpha = np.radians(pitches)
    extra = sdk.GRIPPER_LINK_CM-v3.GRIPPER_LINK_CM
    horizontal = radius + (extra-sdk.GRIPPER_LINK_CM)*np.cos(alpha)
    vertical = z*100.-sdk.ROBOT_BASE_FLOOR_HEIGHT_CM-sdk.LINK_1_CM+(extra-sdk.GRIPPER_LINK_CM)*np.sin(alpha)
    diagonal = np.hypot(horizontal,vertical)
    valid = (diagonal>1e-9)&(diagonal>=abs(sdk.LINK_2_CM-sdk.LINK_3_CM))&(diagonal<=sdk.LINK_2_CM+sdk.LINK_3_CM)
    safe_diagonal = np.where(valid,diagonal,1.)
    elbow_cos = np.clip((sdk.LINK_2_CM**2+sdk.LINK_3_CM**2-diagonal**2)/(2.*sdk.LINK_2_CM*sdk.LINK_3_CM),-1.,1.)
    shoulder_cos = np.clip((diagonal**2+sdk.LINK_2_CM**2-sdk.LINK_3_CM**2)/(2.*sdk.LINK_2_CM*safe_diagonal),-1.,1.)
    theta4 = 180.-np.degrees(np.arccos(elbow_cos))
    theta5 = np.degrees(np.where(vertical<0.,-1.,1.)*np.arccos(np.clip(horizontal/safe_diagonal,-1.,1.))+np.arccos(shoulder_cos))
    theta3 = pitches-theta5+theta4
    pwm = np.stack([np.rint(theta3*sdk.PULSE_PER_DEGREE+1500)+sdk.SERVO_DEVIATION[3],
        np.rint(theta4*sdk.PULSE_PER_DEGREE+1500)+sdk.SERVO_DEVIATION[4],
        np.rint(1500+(90.-theta5)*sdk.PULSE_PER_DEGREE)+sdk.SERVO_DEVIATION[5]],axis=1).astype(int)
    valid &= np.all((pwm>=sdk.SAFE_PULSE_MIN)&(pwm<=sdk.SAFE_PULSE_MAX),axis=1)
    if not valid.any():
        raise ValueError('target has no safe v3 physical-pad IK solution')
    i = int(np.argmin(np.where(valid,np.abs(pitches-preferred),np.inf)))
    return {3:int(pwm[i,0]),4:int(pwm[i,1]),5:int(pwm[i,2]),6:pan}
