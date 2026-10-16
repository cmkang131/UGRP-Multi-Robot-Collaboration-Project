# reloc20 16시도 종료 관문표

|실행|종료|마지막 단계|잔여 직선/경로 m|
|---|---|---|---|
|reloc20-r1-carry-baseline-93266-aede24d6|cap_end: sim_cap|destination_acquire|0.609/0.048|
|reloc20-r1-carry-candidate-93266-aede24d6|cap_end: sim_cap|align|2.610/0.000|
|reloc20-r1-carry-baseline-93315-aede24d6|cap_end: phase_timeout|destination_acquire|1.330/0.052|
|reloc20-r1-carry-candidate-93315-aede24d6|HOST_ERROR: fixed-floor declaration scenario hash mismatch|precontrol|해당 없음|
|reloc20-r1-selfmap-short_regression-93584-aede24d6|controller_failure: selfmap4_relocalization_exhausted|stopped|해당 없음|
|reloc20-r1-selfmap-short_regression-93583-aede24d6|controller_failure: selfmap4_relocalization_exhausted|stopped|해당 없음|
|reloc20-r2-carry-candidate-93266-1b310860|cap_end: phase_timeout|carry_to_zone|3.187/4.642|
|reloc20-r2-carry-candidate-93315-1b310860|cap_end: sim_cap|carry_reobserve|2.547/0.000|
|reloc20-r2-selfmap-short_regression-93584-1b310860|controller_failure: selfmap4_relocalization_exhausted|stopped|해당 없음|
|reloc20-r2-selfmap-short_regression-93583-1b310860|controller_failure: selfmap4_relocalization_exhausted|stopped|해당 없음|
|reloc20-r3-carry-candidate-93266-cb8b37c2|cap_end: phase_timeout|carry_to_zone|3.191/4.778|
|reloc20-r3-carry-density-93266-cb8b37c2|cap_end: phase_timeout|carry_to_zone|3.756/7.342|
|reloc20-r3-carry-candidate-93315-cb8b37c2|cap_end: phase_timeout|carry_to_zone|1.095/3.483|
|reloc20-r3-carry-density-93315-cb8b37c2|cap_end: phase_timeout|carry_to_zone|1.354/3.098|
|reloc20-r3-selfmap-short_regression-93584-cb8b37c2|controller_failure: selfmap4_relocalization_exhausted|stopped|해당 없음|
|reloc20-r3-selfmap-short_regression-93583-cb8b37c2|controller_failure: selfmap4_relocalization_exhausted|stopped|해당 없음|

{"attempts": 16, "controller_started": 15, "carry_attempts": 10, "carry_control_started": 9, "carry_travel_started": 9, "destination_entered": 2, "place": 0}

잔여 거리는 자기 추정 좌표계이며 실제 정답 도착 거리와 다르다. HOST_ERROR 원상태는 보존하고 위치추정 소진을 별도 분류했다.
