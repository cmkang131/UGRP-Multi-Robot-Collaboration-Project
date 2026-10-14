# 2026-10-14 상자 탐색·들기 확인 두 결함 수정 (PR #500)

사용자: "결함 두 개를 한 묶음으로 고친다", "입력은 자기 RGB와 자기 명령 이력만 쓴다(상자 세계 좌표·접촉·측정 관절은 금지, held_world_reads=0)", "undetermined가 남으면 놓기를 허가하지 않는 규칙은 유지한다". 기준 소스 `77151eec997ce9ab4cbdfd64d6952737d2f0f44d`, GCP `gcp1 n4-highcpu-64` 진단 0/4. 원본은 기본 체크아웃 `outputs/gcp1-runs/crate-{diag-77920,diag-77921,diag-77922,repro-77902}-77151eec/raw`, 요약은 `outputs/e2e18-admin/gcp-reports/crate-diag-77151eec.json`이다. 기존 실패와 새 후보를 합산하지 않는다.

## 먼저 조사한 표준 방법 (2026-10-14 원문 열람)

- Kalashnikov et al. 2018, **QT-Opt: Scalable Deep Reinforcement Learning for Vision-Based Robotic Manipulation**, [원문 PDF](https://arxiv.org/pdf/1806.10293), §5 Reward function 및 Appendix D의 성공 판정(인쇄 쪽 19, Fig.12). 팔을 영상에서 치운 장면과 잡힌 물체를 내려놓은 뒤 장면을 비교해 픽셀 차이가 임계값보다 크면 성공 라벨을 준다. 이것은 놓기 이후 얻는 학습용 보상이며, 놓기 전 자기 손목 카메라로 해제를 허가하는 판정에 그대로 쓸 수 없다. 원문의 관측에는 집게 상태/높이도 있어 이 프로젝트 입력과 같지 않다.
- Levine et al. 2016, **Learning Hand-Eye Coordination for Robotic Grasping with Deep Learning and Large-Scale Data Collection**, [원문 PDF](https://arxiv.org/pdf/1603.02199), §5 및 Appendix B Determining Grasp Success(인쇄 쪽 12). 실제 집게 닫힘 위치와 내려놓기 전후 장면 차분을 함께 쓰며, 얇은 물체는 집게 위치 판정에서 누락될 수 있다. 측정 집게 위치는 여기서 금지된 입력이므로 가져오지 않는다.

두 논문 모두 "물체가 손목 카메라와 같이 움직이면 들림" 규칙이나 아래 수치 임계값을 검증한 근거는 아니다. 이 구현은 발행 행동 전후 영상 비교라는 원칙을 해당 카메라의 관측 가능성에 맞춘 후보다. 논문 성공률을 이 교사 성능으로 인용하지 않는다.

## 영상 확인과 수정

`/private/tmp/ops/frames/crate-diag-7792{0,1,2}-montage.jpg`, `crate-repro-77902-montage.jpg`를 각각 6개 시점(전체 개요+r1+r2)으로 확인했다. 77920/77902는 0–25 SIM초, 77921은 0–54 SIM초, 77922는 0–32 SIM초의 균등 표본이다. 77921/77922 후반에는 두 로봇 화면이 서로 다른 색 손잡이와 분홍 몸체로 차 있고, 바닥이 보이지 않는다. 77920 r2/77902 r1은 바닥·벽을 훑는다. 접촉/10초 들림 등은 별도 평가 원장의 수치이며 영상만으로 측정한 수치가 아니다.

- `23a2a1137e3907073001ce079dd3294419fb5b1b`를 원격 확인 뒤 병합했다. `search_body_scan_v2`의 근거리 pitch·발행 PWM 도달 뒤 대기·pitch별 연속 회전을 상자 CLI/새 대기열에 연결했다. 상자 원장도 `search_timeout_handoff`와 취소된 짝 `peer_search_handoff`를 별도로 센다. 실제 탐색 회복은 GCP 진단에서 확인해야 한다.
- `crate_rgb_lift_v2`는 **각 로봇 자기** 들기 허가 때, 자기 팔 명령 완료 때, 완료 3초 뒤의 RGB를 저장하고 해시/시각을 남긴다. 자기 이력에 닫힌 집게 PWM ≤1600, 바퀴 정지, 팬 유지, 1.2초 이상 창과 팔 PWM 변화 ≥20이 있어야 한다. 명령은 실제 실행/측정 관절을 뜻하지 않는다.
- 맡은 청록/파랑 손잡이와 분홍 몸체를 각각 분리한다. 초기 최소 영상 면적 1%, 면적비 0.70–1.40, 중심 변화 ≤영상 폭/높이의 0.06, 폭/높이 변화 ≤0.10을 완료/유지 프레임 모두 요구한다. 배경 픽셀은 쓰지 않는다. 손잡이나 몸체가 사라지거나 40% 미만으로 줄면 `not_confirmed`, 다른 불일치는 `undetermined`다. 모두 미보정 임계값이다.
- 두 로봇 모두 `confirmed`이고 명령 완료 뒤 3초가 지나야 해제한다. `undetermined_n/N/rate`를 실행마다 별도 기록한다. 전체 정답은 평가 출력에만 있고 기존 hidden 측정 어댑터 차단은 유지한다.
- 문서에 팬 왕복이 집게를 밀어 이탈시킨 관측이 있어 추가 팬/기울이기 동작은 하지 않는다. 불명확한 시야는 해제를 막는다.

## 오프라인 검증

기존 Python 3.12 환경으로 아래 **3개 파일만** 실행: **94 passed, 1 skipped, 1 deselected**, 2.51초. skip은 선택 `sim.active_lookaround` 부재, deselect는 native MuJoCo world 생성 시험이다. 물리·렌더·모델·SSH·원격 제출은 0회.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_grasp_act_crate_teacher.py tests/test_grasp_act_search.py tests/test_crate_rgb_lift_v2.py \
  -k 'not crate_scene_resolves_lug_geoms_and_probes' --junitxml=outputs/crate-v2-tests.xml
```

합성 영상으로 배경 없는 두 손잡이 색, 소실/놓침, 몸체만 남음, 이동하는 덩어리, 명령 변화 없음/시간 부족/열린 집게/팬·바퀴 이동, 유지 중 놓침, 별도 자기 허가/완료/3초와 두 로봇 해제 조건을 확인했다. 탐색 v2의 병합된 오프라인 회귀와 CLI 전달도 통과했다.

실제 추출 RGB 8장의 SHA-256이 원본 `manifest.json`의 `eval-own` 항목과 같음을 확인했다. 77921 각 로봇 `000440→000540`은 들기 전에서 후기 유지로, 77922 `000260→000320`은 **둘 다 들기 뒤**인 표본이다. 네 영상 쌍 모두 손잡이/몸체의 형태 비교는 통과했지만, 별도 세 번째 프레임 또는 정확한 들기 전 프레임이 없어 전체 재생은 0회다. 세 번째 프레임을 중복/합성하여 실제 판정으로 보고하지 않았다. 후보 함수는 모두 `undetermined: settled hold frame missing`으로 끝냈다. 상세 특징·원장 해시·각 이미지 원본 경로·시험 해시는 [JSON](rgb-lift-v2-offline-summary.json)에 보존한다.

## 운영 인계와 미확인

새 SHA 대기열은 `outputs/e2e18-admin/vm3-queue/20261014-crate-<sha8>.json`이다. 진단 77920–77922와 v4 재현 77902를 먼저 최대 동시 4로 실행하고, 네 개 모두 들기·해제 성공/서로 다른 손잡이/두 RGB confirmed/`invisible_measurements=held_world_reads=0`, 영상 및 같은 머신·SHA의 속도 관문을 통과해야 v5 77100–77139 관문을 시작한다. 38/40 이상이 필요하며 HOST_ERROR/실패를 분모에서 빼지 않는다. 학습 기록·weld·lookaround는 off다. 운영 작업자가 제출하며 Codex는 제출/감시하지 않았다.

실제 팔이 명령대로 움직이지 않으면서 근접 영상이 그대로인 상황은 RGB+발행 명령만으로 구분이 어려워 오탐 가능성이 남는다. 이 후보를 물리 높이 확인으로 해석하지 않는다. 새 GCP 진단에서 RGB 판정/평가 정답의 오탐·미탐·unknown을 따로 대조해야 한다. 런타임 감사 0, 탐색 회복, 들기/놓기 성공률, 실행 속도, 전체 CI는 확인 안 됨. ACT 학습/학생 독립 성공은 이번 작업 범위 밖이다.
