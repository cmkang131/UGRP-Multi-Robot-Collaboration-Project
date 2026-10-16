# Line extraction reference

Source: https://github.com/kam3k/laser_line_extraction
Commit: 34de3e9d7560c04bec29e97f07339407c0bca6a6
BSD-3-Clause license preserved in LICENSE. Original reference sources are unchanged.

Python adaptation: harness/self_wall_segments.py. Endpoint split, range/outlier
filter, length/count filter, weighted perpendicular fit, chi-squared merge are
retained. C++ recursive iterator endpoint omissions are not reproduced: Python
slices retain every measured point and share a corner between adjacent lines.
Cartesian camera point covariance replaces fixed laser polar covariance. SciPy
least_squares minimizes the same squared normalized perpendicular residual;
its Jacobian supplies local linearized parameter covariance rather than the C++
closed-form derivative. Temporal association adds observed-extent gap<=0.4m.
Unknown inter-frame correlation uses covariance intersection with fixed omega=.5.
Own first-scan Manhattan axes replace unconstrained global directions. No GT/map.
