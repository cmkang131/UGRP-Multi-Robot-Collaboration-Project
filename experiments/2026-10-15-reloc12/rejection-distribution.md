# 수정 전 거부 사유 분포

GCP 원본 7회, 중복 사유 포함.

|사유|프레임 수|
|---|---:|
|ambiguity_pending_upstream|3940|
|yaw_covariance|3755|
|xy_covariance|3706|
|no_sensor_update|3313|
|geometry|1133|
|pf_unresolved|744|
|cluster_mass|128|
|geometric_ambiguity|1|

첫 거부: {'no_sensor_update': 3313, 'pf_unresolved': 88, 'yaw_covariance': 22, 'xy_covariance': 514, 'geometry': 3, 'geometric_ambiguity': 1}

공분산 신뢰도 경로를 먼저 수정한다. 미갱신 프레임은 새 확인 근거가 아니다.
