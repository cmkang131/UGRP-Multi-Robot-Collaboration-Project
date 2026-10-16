# 단일 모델 차이 표

동일 관절 구성으로 free-root pose를 고정해도 아래 실제 차이가 남았다. 원본을 정규화하거나 제거하지 않는다. `world_model_parameters_v1`에서 지원되는 모델 배열만 세계별로 보존하며 `dof_length`는 PR534의 정확한 world-indexed sleep 읽기를 쓴다. SLEEP-off 값 무시 예외는 쓰지 않는다.

| 시드8318728 vs8318711 | 필드 | 값 | 기준 값 |
|---|---|---|---|
| warehouse_oak_plank_geom | mass | 0.1901 | 0.2125 |
| warehouse_oak_plank_geom | size | 0.028252 0.221864 0.019467 | 0.028917 0.190067 0.018945 |
| warehouse_oak_plank_grain_l | size | .003 0.222 .0015 | .003 0.190 .0015 |
| warehouse_oak_plank_grain_r | size | .003 0.222 .0015 | .003 0.190 .0015 |
| warehouse_steel_pipe_geom | mass | 0.2097 | 0.2158 |
| warehouse_steel_pipe_geom | size | 0.027836 0.222493 0.019887 | 0.025908 0.218047 0.022368 |
| warehouse_steel_pipe_visual | size | 0.0199 0.222 | 0.0224 0.218 |
| warehouse_wood_crate_geom | mass | 0.2326 | 0.2159 |
| warehouse_wood_crate_geom | size | 0.029599 0.170082 0.021841 | 0.029508 0.164041 0.020796 |

release S1/S3: S3에는 `cargo_can_1`, `cargo_cyan_2`, `cargo_green_1`의 free-root가 없다. 관절 구성 자체가 달라 물체 추가/삭제 없이 동일 모델로 합칠 수 없다. 원본 물체를 보존하고 S1/S3를 별도 구성으로 검증한다.

초기화(교사 성공 아님): 빔 짝4개, release S1 6개(A/B 각3), S3 2개(A/B 각1). CPU C312는 exact XML의 compiler asset export용이며 CPU 교사 성공으로 세지 않는다.
