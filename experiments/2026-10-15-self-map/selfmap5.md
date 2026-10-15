# selfmap5 — innovation 기반 격리·명령 구간 재구성·다중 프레임 등록

2026-10-15, PR #506 / `claude/map-selfmap`, 기준 selfmap4 `d8a7530a9f3f6f11d77d0ea7d06838db1486d296`.
**오프라인 정책 검증, 실제 개선 미검증**. 새 동작은 모두 기본 off이며 이전 결과·질감 on/off 결과를 합산하지 않는다.
실행할 정확한 소스 SHA는 아래 새 큐의 `source_sha`로 고정한다. 이 기록 작성 중 GCP 실행·서버 접속은 하지 않았다.

## S1: `--revision-gate selfmap4_revision_gate_v2`

- `Options.revision_gate` 기본 `off`. 기존 `selfmap4_recovery_v1`을 명시해야 켜진다.
- 시각 자세의 SE(2) innovation을 **전체 공분산**으로 검사한다. yaw는 ±π로 감싸고 `sqrt(dᵀ(P+R)⁻¹d) <= 3`이면 재구성 격리를 켜지 않는다. `P`는 현재 발행 명령과 허용 plane-flow로 전파한 예측 공분산, `R`은 시각 맞춤 공분산이다. 기존 bootstrap이 이미 `P+R`을 보존하므로 P를 다시 더하지 않는다. 예측 분산이 0인 첫 시각 보정에도 관측 분산을 포함한다. 영공간 방향의 0이 아닌 innovation은 거부한다.
- 고정 문턱 `revision_xy_threshold_m=.1`, `revision_yaw_threshold_rad=5°`를 삽입 σ 상한과 분리했다. 기본 off의 기존 경로는 이 고정 문턱을 사용한다. `max_sigma_yaw_rad`는 삽입 불확실성 상한만 담당한다.
- 재구성이 필요하면 마지막 `visual_update`/`visual_relocalized` 또는 bootstrap 앵커 뒤 **삽입된 command_only 관측의 자세만** 보정한다. 그 전 자세는 유지한다. 보정량은 누적 자기 이동 거리 비례이며 제자리 회전도 차체 반경 .15 m의 회전 호 길이로 센다. 측정 관절·정답 위치를 읽지 않는다.
- 기존 전체 ORB 재맞춤은 하지 않는다. 보존한 body ray를 수정 자세로 원자적으로 다시 rasterize한다. 실패 시 기존 지도를 유지한다. 재구성한 command prior는 시각 검증으로 승격하지 않고 `prior_map_unverified`를 유지한다. 구간 밖 시각 기록, 이동 거리 0은 거부한다.
- **정적 지도 좌표계 보정**에 대해 이전 ORB만으로 과거 전 구간을 증명할 수 없는 기존 차단은 유지한다. 새 S2가 등록돼도 큰 정적 좌표계 보정이 자동으로 완료 지도 인증을 주는 것은 아니다.
- 재구성 쿨다운 **5 SIM초**, 최대 시도 2회는 유지한다. 복구 시한은 별도 **80 SIM초**: `(9회 1초 pan + 기존 body sweep 상한 30초 + 전환 1초) × 2회`. 시한/시도 소진은 기존 `selfmap4_relocalization_exhausted` / HOST_ERROR이며 지도 완성이 아니다.

## S2: `--multiframe-registration selfmap4_multiframe_registration_v1`

- `Options.multiframe_registration` 기본 `off`. 360° body sweep 시작 때 버퍼를 새로 만들고 끝/30초 만료 때 폐기한다. 최대 400개 관측만 유지한다. 각 선은 관측 당시 자기 SLAM 상대 자세로 묶고 **현재 PF의 동일한 map-from-own 앵커**에서 함께 평가한다. 서로 다른 프레임의 PF 절대 자세를 섞지 않는다.
- hue 12 조건과 유한 선분 끝점·방향 검사를 유지한다. 5 cm 고정 잔차 대신 PF 공분산을 endpoint Jacobian으로 전파한 3σ 잔차를 사용하며, 선 추출 잡음(.05/3 m, 5°/3)을 더한다. 독립 축 2개와 기존 클러스터 질량 .9·공분산 상한·**서로 다른 새 장면 3회 앵커 일관성**을 모두 요구한다. 캐시만 반복 조회해 확인 횟수를 늘리지 않는다. 성공적인 자세 재구성 때 예전 상대 자세 증거도 무효화한다.
- 기존 PF 코어와 vendored augmented 정책은 수정하지 않았다. S2에서만 별도 `RecoveryPolicy(alpha_slow=.001, alpha_fast=.1)`를 주입한다. 이전 코드에도 같은 slow/fast 평균이 있었으나 ESS가 높으면 회복 추첨까지 건너뛴다. 새 정책은 likelihood 감소로 주입 확률이 양수가 되면 높은 ESS에서도 재주입한다. 균일 입자는 정적 지도 자유 공간에서만 생성한다.
- 보고/잔차/등록/자기 자세 갱신에 `cov × 6² + diag(.02²,.02²,0.5°²)`의 보수적 envelope를 일관되게 사용한다. 이는 **보류 자료로 보정한 통계적 calibration이 아니다**. raw covariance와 PF resolved·주입 수치도 별도로 저장한다. 넓어진 σ 때문에 등록이 줄 수도 있다.
- PF 0.2–0.3 m 편향의 원인은 미확인이다. 카메라/선 관측 모델을 바꾸지 않았으며 S2의 등록 성공·정확도 향상은 장담하지 않는다.

## 93531 저장 trace 오프라인 재생

입력: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/selfmap-93531-d8a7530a/raw/`.
검토 RGB: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/selfmap-d8a7530a-ops/frames-selfmap-93531-d8a7530a/`.
전체 수치: `/Users/changmin/projects/ugrp/outputs/selfmap5-analysis/offline-v2.json`.
입력·결과·구현 파일 SHA-256과 검증 요약은 [selfmap5-summary.json](selfmap5-summary.json)에 보존한다.

- trace **432/432**, 시각 갱신 **51/432**의 기존 경로·명령·저장된 flow를 고정해 재계산했다. 제어 입력으로 eval_only 파일을 열지 않았다.
- 고정 문턱의 `rebuild_required` 신규 발생 시점은 **t=24.5 1회**, S1의 3σ 발생은 **0회**다. t=24.5의 보정은 xy .0419 m, yaw −6.383°이며 전체 상관 공분산의 Mahalanobis는 **1.937σ**다. 보고서의 yaw 1.46σ·xy .6σ는 각 성분 기준이고 이 값과 구분한다.
- t=24.5 재구성을 **강제로 요청한 수치 진단**에서 자세 보정 **91/91개**, 앞부분 **122개 보존**(전체 과거 삽입 213개)이다. 마지막 실제 시각 앵커는 **t=15.3, frame 141**, command_only는 **frame 142–232**다. 분석 보고서의 t=21.3 이후 약30개 추정과 다르며, trace의 source를 우선한다.
- 이 91개는 **자세 재계산 성공 수**다. 전체 body ray/RGB가 로컬에 없어 실제 93531의 213프레임 지도 재rasterize 성공이나 실제 commit으로 보고하지 않는다. 합성 body-ray 회귀 시험에서 원자적 삽입·보존·실패 rollback을 별도로 검증한다.
- S2는 저장된 RGB **6/432개**(frame 1/87/173/260/346/432)의 JPEG 해시를 확인하고 선을 다시 추출했다. 기록된 sweep 구간에서 독립 축 수는 최대 **1**, 2축 지지는 **0/6**이다. 이 중 sweep 안에 있는 RGB는 **2/6**뿐이며, 그 부분집합의 2축 지지도 **0/2**다. 전체 훑기 영상 누적·변경 PF 재실행·등록 성공은 **미검증**이다.
- 경로/영상을 생성하지 않은 고정 trace의 정책 반사실 계산이다. 이후 200프레임의 실제 `map_updated`, 프런티어 도착, 완주 개선을 주장하지 않는다. Mac 물리·렌더·학습, 원격 접속, 모델 호출은 모두 0이다.

재현:

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.analyze_selfmap5 \
  --raw /Users/changmin/projects/ugrp/outputs/gcp1-runs/selfmap-93531-d8a7530a/raw \
  --images /Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/selfmap-d8a7530a-ops/frames-selfmap-93531-d8a7530a \
  --output /Users/changmin/projects/ugrp/outputs/selfmap5-analysis/NEW.json
```

## 질감 연결과 새 GCP 큐

`--render-profile floor_light_textured_v1`이 선택되면 장면 첫 install, nearclip 감사, 상속된 reset의 `verify_model`까지 같은 프로필을 전달한다. 생략 시 기존 `floor_light_v1`이다. `wall_texture=off`, weld off를 유지한다. bundle/result의 별도 장면 이름과 프로필 감사가 적용값을 남긴다.

**PR #511 / `claude/scene-floor-texture` / `6a73c3aab305f250d0ecd9591922b160b9c709ab`는 확인 시 OPEN**이다. 그 PR의 profile/assets/nearclip API는 이 브랜치에 복사하거나 병합하지 않았다. 해당 의존이 없으면 질감 프로필을 plant 생성 전에 거부한다. 질감 실행 전 #511을 실제 실행 소스에 통합하고 **새 source SHA로 큐를 다시 만들고 승인**해야 한다. 이 큐의 현재 SHA로 질감 실행을 시작할 수 없다. 현재 PR에 타 브랜치 AGENTS 변경이나 자산을 몰래 포함하지 않는다.

새 파일: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-selfmap5-s1-s2.json`.
기존 `20261015-selfmap-d8a7530a.json`은 형식만 읽었고 수정하지 않았다.

- smooth S1+S2: first30 seed93550, 180초 seed93551/93552.
- 질감 on S1+S2: 비교용 first30 seed93550, 180초 seed93551/93552. 질감에도 first30 관문을 별도로 두어 총 **6개 계획**이다. 같은 시드의 장면별 짝 비교이며 결과를 합산하지 않는다.
- `approved/enabled/ready/stage_ready`, 각 단계 ready, execute, 자동 승격·실행 권한은 **모두 false**. 실행은 제출하지 않았다. 동시 1개, 매 실행 원본 검토 뒤 다음 단계, GCP 비용·8시간·유휴20분 가드·저장 용량·속도·시드 충돌은 조정자가 실행 전 확인한다.
- 첫30 비교: ORB features/matches/inliers·visual 비율·map_updated, P+R innovation, 재구성 대상·성공 수, sweep 시간, 독립 축·PF raw/보정 σ·재주입, 등록 3회 확인, 프런티어 선택/도착, wall/SIM과 입력 감사를 남긴다. 실제 결함 확인 시 같은 결함 실행을 멈추고 고친 소스로 다시 시작한다.

## 시험과 남은 문제

관련 파일 `tests/test_selfmap5.py`, `test_selfmap4.py`, `test_self_map_integration.py`, `test_self_map_executor.py`만 pytest 동시 1개로 검증한다. 최신 결과와 로그 해시는 요약 JSON에 있다. 새 시험은 CI 목록에도 등록했다. 부작용 검사는 native plant import 없이 AST로 질감 선택 전달을 확인한다.

실제 body-ray 전체 재생, 전체 sweep의 독립 축, PF 편향 원인·S2 재주입의 효과, #511 통합 뒤 실제 질감 바인딩/영상과 GCP first30·180초 실행은 남아 있다. 실제 지도 완료/주행 준비 완료 판정은 하지 않는다. 사용자가 남긴 미추적 `selfmap4_slam_error.json`은 수정하거나 커밋하지 않는다.

## 참고 자료와 확인 범위

- 직접 출발점: Claude 분석 [`report.md` 4절](/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/relocalization-carry5-selfmap4/report.md), 같은 폴더 `scripts/selfmap4_rebuild_refit.py`, `selfmap4_slam_error.py`, `selfmap4_table.py`와 `logs/selfmap4_rebuild_refit.txt`, `selfmap4_slam_error.txt`를 읽었다. 로컬 분석이며 웹 출처가 아니다. 보고서의 일부 수치/시점 추정은 위 trace 재계산으로 구분했다.
- 보고서가 인용한 Thrun, Fox, Burgard, Dellaert, [Robust Monte Carlo Localization for Mobile Robots (2001)](https://publications.ri.cmu.edu/robust-monte-carlo-localization-for-mobile-robots): 2026-10-15 CMU 공식 서지와 초록을 열람했다. mixture/dual sampler 일반 근거이며 이 구현의 slow/fast 식을 논문에서 직접 확인한 것은 아니다.
- slow/fast 업데이트와 `max(0,1-w_fast/w_slow)` 무작위 재주입은 [Nav2 AMCL의 공식 pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c)에서 2026-10-15 직접 확인했다. 이 후보는 기존 선택적 재표집에서 recovery 신호를 건너뛰던 부분만 별도 토글에서 바꾼다. Nav2 문서 페이지는 접근 실패(404/열람 불가)로 **문서 권장 alpha 값은 웹 확인 미완료**이며, .001/.1은 기존 vendored 상수와 일치하는 값이다.
- Coltin & Veloso, [Multi-Observation Sensor Resetting Localization with Ambiguous Landmarks, AAAI 2011](https://ojs.aaai.org/index.php/AAAI/article/view/7983): 공식 초록·서지에서 다중 프레임 관측 병합의 동기를 확인했다. 논문의 sensor-reset 후보 생성 알고리즘을 그대로 구현한 것은 아니며 본 후보의 성공 근거가 아니다.
