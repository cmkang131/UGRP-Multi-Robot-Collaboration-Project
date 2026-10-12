"""Default-off evaluation lifecycle fixes; never supplies control feedback."""
import math

OPTIONS=('off','supported_phase','floor_latch')


def supported_final(row,final_segment,option='off'):
    if option not in OPTIONS:raise ValueError('UNKNOWN_FINAL_RELEASE_GUARD')
    if option=='off' or not final_segment:return False
    if set(row['states'])!={'r1','r2'} or any(s!='released' for s in row['states'].values()):return False
    if not all(math.isfinite(row[k]) for k in ('floor_normal_n','cargo_z_m','vertical_speed_m_s','cargo_tilt_deg')):return False
    return (row['floor_normal_n']>=.1 and 0.<=row['cargo_z_m']<=.025
        and abs(row['vertical_speed_m_s'])<=.02 and 0.<=row['cargo_tilt_deg']<10.)
