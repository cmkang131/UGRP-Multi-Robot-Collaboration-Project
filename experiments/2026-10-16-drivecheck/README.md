# drivecheck — mapbuild2 변위 붕괴의 짝 비교 진단

진단 전용, `codex/drivecheck`를 `origin/main` **0936e5609b500fa95d5db07a6441c328e5c4738e**에서 만들었다. 본 흐름·구동 모델·카메라·장면 기본값은 바꾸지 않는다. mapbuild2 [PR #556](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/556)의 README·`command-phase-scale.json`·`camera-summary.json`을 먼저 읽고 시작했다.

**CPU에서 이미 같은 변위 붕괴를 재현했다. 주된 원인은 초기 장면의 차체–화물 관통이다.** C3.12에서 0.1초 전진 후 정지 변위는 0.6091mm, C3.16에서는 0.2739mm다. 원래 장면의 r1 하부가 `cargo_box_00_geom`과 처음부터 15.3449mm 겹친다. 1초 settle 뒤에는 앞바퀴만 바닥을 지지하고 뒤바퀴는 바닥 접촉이 없다. 6° tilt가 주행 명령보다 먼저 생긴다. 사용자 분기에서 “명령 척도(v122) 문제”에 해당하는 **CPU에서도 재현되는 장면/척도 부적합**이며, v122 자체를 32배 보정해야 한다는 뜻이 아니다.

상자 하나만 옆으로 0.253321m 옮긴 기본 off 인과 진단에서는 C3.12 settle tilt가 6.2172°→0.0436°, 1초 전진 후 정지 변위가 0.5630→138.3674mm로 바뀌었다. 0.1초에서는 0.6091→16.6501mm다. 충돌·마찰·바퀴·로봇·카메라는 그대로이며 물체 하나의 초기 위치만 바꿨다. 이동량은 원래 차체/상자의 XY 외접 반경 합의 2배에서 계산했다. 이 개입은 원인 확인용이며 실제 장면 수정안이나 연구 성공으로 채택하지 않았다.

같은 상자 이동 대조의100ms에서 **native3.16 17.03288mm / MJWarp17.04845mm**, 차이는0.01557mm(0.0914%)다. Warp settle tilt도0.01978°로 회복됐다. 이 짧은 고정 조건에서는 초기 겹침을 제거하면 두 엔진의 주행 크기가 일치하며, “Warp만32배 느린 구동”이라는 해석은 지지되지 않는다. 임의 장면·하중·제어기의 엔진 동등성이나 새 v122 보정을 검증한 것은 아니다.

**진행 상태:** CPU 두 버전·인과 대조와 NoSlip OFF 토글은 완료했다. NoSlip ON의 MJWarp 전체 18펄스와 일부 짧은 토글은 수집 중이다. 최종 짝 비교·판정은 완료 원본 회수 뒤 이 기록에 반영한다. 진행 중인 결과는 완료로 세지 않는다.

## 입력·조건·평가 경계

- 장면은 mapbuild2와 같은 `zone_hardmaps1_h1_final_v3`, `walls_floor_contrast_v5_indigo110_s80` / `no_mip_v1`; r1 FOLDED, 물체·로봇·카메라 원형을 유지한다. 장면 생성 소스는 `5974a181a2cec9731339a6ce3aadc0464b8dddcf`다.
- 전진 `[+,+,+,+]`, 횡 `[-,+,+,-]`, 회전 `[-,+,-,+]`, 값 0.35. 각 축에 사용자 지정 0.25·0.5·1·2·4 SIM초, 그 앞/뒤 정지 각각 1초. 원래 mapbuild2의 100/60/100ms 펄스도 각각 추가해 **18개**다. mapbuild2의 “1–2 SIM초 구간”은 전진 1초 연속이 아니라 100ms 명령과 정지 꼬리다.
- 물리 timestep 0.00025초와 v7 command relay를 그대로 써서, 물리 0스텝으로 생성한 같은 테이프/초기 qpos를 두 엔진에 준다. GPU 업로드의 float32 변환은 별도 엔진 특성이다. 모든 제한은 고정 SIM tick이고 wall 기반 행동 선택·모델 호출은 없다.
- CPU 기준은 `ugrp-sim-gcp2` / `ugrp-sim-b-1014` / n4-highcpu-64 / MuJoCo3.12.0. 보조 native3.16과 MJWarp3.16/Warp1.15는 `ugrp-act-l4-gcp5` / `ugrp-sim-e-1016` / g2-standard-8·L4에서 돈다. 호스트/버전 결과를 합산하지 않는다.
- 같은 XML의 C3.12↔3.16 컴파일 결과에서 질량·관성·마찰·solref·dof damping·actuator gain/bias는 동일하다. `geom_quat/geom_size/mesh_vert`의 **컴파일 표현**은 다르므로 C3.12와 Warp의 차이를 곧바로 GPU 단독 결함으로 부르지 않는다. [선택 필드 대조](compiled-comparison.json).
- 정답 pose·관절·접촉·힘·미끄럼은 평가 출력뿐이다. 명령은 고정되어 어떤 측정도 피드백하지 않는다. 원본 상태/접촉은 10Hz와 모든 펄스 경계에 기록한다. 접촉력은 각 엔진의 실제 force API다. 미끄럼은 저장한 실제 접촉점과 qpos/qvel의 별도 기구학으로 계산한 바닥 접선 상대속도다.
- 통상 `mj_step`/`mjw.step` 의미대로 접촉/힘은 마지막 solver 계산, qpos/qvel은 그 step 적분 뒤 상태다(간격0.25ms). slip은 이 저장 상태에서 구한 평가값이며 raw 센서나 엄밀한 solver 잔차가 아니다. float32 저장 quaternion은 평가 산술에서 float64로 올려 작은 tilt의 `acos` 상쇄를 줄인다.
- 전체 10Hz 상태 기록과 별도로 `--record-own-rgb-ring`은 제어와 무관한 기록 전용 옵션이다. 별도 MjData에 자기 RGB640×480 두 카메라를 10Hz, 마지막 10 SIM초까지 보존하고 bytes를 적는다. native3.16 인과 대조에서 44장·1,055,973bytes를 확인했다. 초기 실행은 상태 기록 뒤 필요한 전체 자기 영상을 gcp2에서 재구성했으며, 이를 온라인 원시 RGB와 혼동하지 않는다.

## 수치가 물리적으로 가능한가

기존 공식 바퀴 지름 65mm(반경 0.0325m), v7 무부하150rpm·구동 입력0.35·kinetic fraction1/12를 쓰면 부하 없는 모델의 기준은

`ω = (150×2π/60) × (0.35−1/12)/(1−1/12) = 4.56959rad/s`, `rω = 0.148512m/s`다.

따라서 명령 중 100ms는 약14.85mm, 1초는148.5mm다. 이는 **견인력을 보장하는 예측이 아니라 기존 모터 모델의 무부하 기준**이다. 정지 꼬리·가속·하중·충돌은 별도다. 개입 대조의 1초 138.4mm와 같은 크기다. 반면 원래 장면에서 4초를 줘도 약0.567mm만 남았고, 뒤바퀴 각도는 각각18.278rad인데 앞바퀴는0.016/0.018rad였다. 부유한 뒤바퀴는 돌고 차체는 상자에 얹힌 상태다. 접지 바퀴의 slip이 작다는 이유로 주행이 정상이라고 판단하지 않는다.

v122의 정확히 등록된 100/60/100ms profile만 예측값을 쓴다. 등록되지 않은 긴 펄스는 `null`로 남기며 임의 선형 외삽/32배 보정을 하지 않는다. 전체 길이 비교에는 실제/무부하 기준을 별도 열로 쓰고, 원래 짧은 펄스에는 실제/v122를 함께 쓴다. 새 수용 오차나 성공 임계값은 만들지 않았다.

상자 이동 대조의4초 전진은3.4초부터 기존 r2의 양쪽 finger와 접촉했다(최소간격-0.2944mm). [전체 영상 검토](playback-review.md)에서도 상대 로봇이 커져 서로 닿고 멈추는 순서를 확인했다. 최종355.6mm를 자유 주행 속도나 척도 보정 근거로 쓰지 않는다. 0.1/1초의 원인 개입 대조와 이 추가 막힘을 구분한다.

## 원인 분포·토글·영상

[초기 원인 분포/funnel](contact-rejection-table.json): CPU18개 전부 초기 차체–상자 관통, 정상 비관통 시작0/18. 이 표를 먼저 저장하고, `causal-queue.json.rejection_table`에 원격 절대경로를 연결한 뒤 상자 한 개 이동을 시험했다. 실행 관문, 원래 장면 적합성, 인과 대조는 서로 다른 누적 funnel로 남긴다.

`legacy-plane-v1`×`dense-capacity-v1`×NoSlip10/0의 8조합은 원래 3개 짧은 펄스로 비교한다. 전체 길이 기준은 18세계, 토글은 3세계이므로 서로 다른 세계 수를 표시한다. legacy plane은 기존 로컬 진단 어댑터만 쓰며 공유 MJWarp 설치를 고치지 않는다. dense는 측정한 실제 contact/constraint 최대를 다음 2의 거듭제곱으로 올리는 **메모리 할당**이다. 원래 장면에서는 ON/OFF의 실제 용량이 같을 수 있고, 이를 물리 수정으로 해석하지 않는다.

상자 이동 뒤 첫 Warp 시도는 import 기반64 contacts/256 constraints가 모자라 `NEFC|NARROWPHASE`(mask 9 = 1|8) overflow로 즉시 HOST_ERROR였다. 원본은 보존했다. 같은 native3.16 인과 대조의 매 물리 step 최대78/345를 확인한 뒤128/512로 할당해 다시 잰다. 마찰·solref·actuator 설정을 추측으로 고치지 않았다.

[시간순 검토](playback-review.md): 실패2개와 인과 주행 대조1개를 전체 2Hz와 마지막10초의10Hz(모두 실행 전체)로 직접 읽었다. MP4는 개요+r1+r2, 3배속, 각각 ≤8MB다. Mac 화면 앱은 열지 않았다. 대조에서 정상적인 전진이 회복된 것은 확인했지만 임무·지도·운반 성공으로 세지 않는다.

## 재현·원본·운영

원본은 gcp2와 gcp5 `/home/ugrp/ugrp-sim/runs/drivecheck/`의 영속 디스크에 남긴다. Mac에는 짧은 요약·표·hash·검토 영상/띠만 가져온다. 초기 raw 예산은2GiB이며 모델 키·에이전트 자격 증명을 전송하지 않았다. `RUN_META.json`은 dev다.

```sh
# gcp2, 커밋한 소스에서 생성; pinned source의 원래 asset cwd를 사용
MUJOCO_GL=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python -m scripts.drivecheck prepare \
  --renderer-source /home/ugrp/ugrp-sim/src/drivecheck-renderer-5974a181 \
  --out /home/ugrp/ugrp-sim/runs/drivecheck/NEW-fixture
# 예: 새 출력 경로, 자기 lease와 existing absolute rejection_table 필수
python -m scripts.drivecheck run --enabled --engine cpu \
  --fixture /home/ugrp/ugrp-sim/runs/drivecheck/fixture-v3 \
  --queue /home/ugrp/ugrp-sim/src/drivecheck-v2/experiments/2026-10-16-drivecheck/plan.json \
  --out /home/ugrp/ugrp-sim/runs/drivecheck/NEW-cpu
# Warp: gcp5 .venv-warp, --engine warp; source archive의 원래 --source-sha 명시
# --only forward-0.1,left-0.06,turn-0.1 / --legacy-plane-v1 / --noslip-off-v1
# --dense-capacity-v1 --capacity-reference /절대경로/capacity-reference.json
# --clear-overlap-v1 은 인과 진단만, --record-own-rgb-ring 은 기록만 바꿈
```

각 실행 `result.json.reproduce`에 정확한 명령과 소스 SHA가 있다. fixture 생성/기록기는 실행 전에 커밋했다. gcp2 사본은 공용 `git-shared.git`을 직접 `git clone --reference`로 참조한다. gcp5의 기존 공용 저장소는 shallow라 reference clone이 거부됐다. 공용 이력은 건드리지 않고 필요한 추적 소스만 `git archive`로 전송해 원래 SHA와 파일 hash를 기록한다. 전체 이력 복사는 하지 않았다.

gcp5 시작 전 TERMINATED·다른 lease/Python/GPU 작업0을 확인했다. 8h 상한을 다시 넣지 않았다. 유휴20분 timer와 `us-central1/budget-stop` ACTIVE, 대상 프로젝트와 Pub/Sub 연결을 확인했으며 변경하지 않았다. CPU gcp2의 다른 `beamdiag` lease는 보존한다. 다중 GPU context의 경쟁을 줄이려고 자기 짧은 ON 실행만 SIGSTOP으로 보류하고 기준 실행 뒤 SIGCONT로 잇는다. 명령/SIM 예산·물리 설정은 그대로이며 이 wall 시간은 성능 벤치마크가 아니다. 작업 종료 후 gcp5 정지 확인을 남긴다.

비물리 단위검사3개(roller namespace·tilt yaw·상대 좌표), Python compile·whitespace, CI shard 등록을 확인했다. 새 threshold·학습·모델 호출·운반·본 흐름 기본값 변경은 없다. PR은 DRAFT로 남긴다.

## 참고 자료

- [공식 MJWarp batch/capacity 설명](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html#batch-sizes): nconmax는 세계당 기대 접촉, njmax는 세계당 constraint 상한이며 overflow를 확인해야 한다. 이번 bit9 할당 실패의 해석 근거다. 최신 문서를 설치된3.16과 같은 소스로 간주하지는 않는다.
- [공식 NoSlip issue #87](https://github.com/google-deepmind/mujoco_warp/issues/87): 구현 완료로 닫힌 기능 항목이다. “NoSlip 미지원”을 원인으로 추측하지 않았다. [공식 마찰/NoSlip 모델 설명](https://github.com/google-deepmind/mujoco/blob/main/doc/modeling.rst)은 slip 억제와 solver 수렴/비용을 구분한다.
- [공식 deterministic convex-contact issue #1635](https://github.com/google-deepmind/mujoco_warp/issues/1635): 특정 deterministic 모드에서 convex 접촉이 사라지는 별개 증상이다. 이번 실행의 deterministic=0이고 상자 지지 접촉이 실제 있으므로 이 이슈를 동일 원인으로 채택하지 않는다.
- [공식 CPU/Warp 비교 issue #3663](https://github.com/google-deepmind/mujoco/issues/3663): 다른 과제의 폐루프 차이 보고다. 이번 고정 테이프·초기 관통과 동일 재현이라는 증거는 없다.
- [기존 legacy Plane–Mesh 알고리즘 원전](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/engine/engine_collision_convex.c#L966): 기존 어댑터의3접촉/.3 간격 값 출처다. 새로운 튜닝값을 넣지 않았다.

공식 자료/이슈에서 이번 **차체–상자 초기 관통으로 뒤바퀴가 떠서 전진이 멈추는 동일 재현**은 확인하지 못했다. 외부 이슈를 원인 확정 근거로 대신 쓰지 않았다.
