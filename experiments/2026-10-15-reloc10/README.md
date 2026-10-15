# reloc10 — 3라운드 직접 검증, not-ready

회전 관문과 selfmap 정착 진동은 개선됐지만 **정적 등록은 0/456이며 운반 목적지 배치도 미완료**다. 사용자 상한인 **GCP 3/3라운드에서 종료**했고 4라운드는 내지 않았다. 11/11개 실행의 원본 result·원장·VM SHA256SUMS와 회수한 텍스트 파일을 검증했다. 정상 기록 종료는 5개이며, 감독중단·HOST_ERROR 6개도 제외하지 않았다. 이는 실행/회수 집계이고 연구 성공률이 아니다.

기준 carry `05e3e61f`(PR505), selfmap `a18b1f84`(PR506). 실행은 전부 gcp1 / `ugrp-act-train-1014` / n4-highcpu-64였다. 새 실행·이전 큐·smooth·texture·다른 소스의 성능을 합산하지 않는다. 모델 호출·학습·학생 독립 실행은 없다.

## 실제 결과

| 라운드 | 실행 | 실행 소스 | 상태 / EXIT | result·원장 재계산 |
|---|---|---|---|---|
| 1 | carry93261 | `0fb980e6` | interrupted / 130 | 감독중단(TOP 검토촬영 발견) |
| 1 | rotation | `0fb980e6` | complete / 0 | 4/4; 1.02098, 0.94950, 1.04208, 0.94614 |
| 1 | selfmap smooth | `442f94eb` | HOST_ERROR / 1 | 등록0/189, 정착0, 관측0, 최근20초 반전0/44 |
| 2 | carry93261 | `e55d7a8d` | complete / 0 | 60초 상한; 들기성공, 낙하0, 목적지배치실패 |
| 2 | rotation | `e55d7a8d` | complete / 0 | 4/4; 1.02098, 0.94950, 1.04208, 0.94614 |
| 2 | selfmap smooth | `44f7f7e1` | HOST_ERROR / 1 | 등록0/456, 정착6, 관측6, 최근20초 반전3/51 |
| 2 | selfmap texture | `44f7f7e1` | HOST_ERROR / 1 | {'type': 'ValueError', 'message': "unknown render profile 'floor_light_textured_v1'; choose from ['floor_light_v1', 'noshadow_bright_v1', 'noshadow_v1', 'shadows_v1']"} |
| 3 | carry93261 | `96712d69` | complete / 0 | 60초 상한; 들기성공, 낙하0, 목적지배치실패 |
| 3 | rotation | `96712d69` | complete / 0 | 4/4; 1.02098, 0.94950, 1.04208, 0.94614 |
| 3 | selfmap smooth | `f7c052f0` | HOST_ERROR / 1 | 등록0/456, 정착6, 관측6, 최근20초 반전3/51 |
| 3 | selfmap texture | `f7c052f0` | HOST_ERROR / 1 | {'type': 'TypeError', 'message': "audit() got an unexpected keyword argument 'base_profile'"} |

원본 위치·SHA-256·모든 실패·입력 감사·첫30초·운영 정지는 [summary.json](summary.json), 제출한 정확한 argv는 [gcp-commands.json](gcp-commands.json)에 있다. 회전비는 좌90/우90/좌180/우180 순서다. 명령에서 다시 적분한 추정 회전은 보고값과 정확히 일치했다. 첫 구간의 사전 평가 yaw가 원장에 없어 평가용 authored spawn을 쓴 재계산과 보고값은 약0.000005 차이가 난다. 나머지는 이전 구간의 마지막 평가 yaw를 썼다.

각 영상이 있는 9개 실행에서 자기 RGB 6장씩, 총54장을 직접 확인했다([review/](review/)). 원본 프레임의 경로·시각·해시는 각 montage 옆 JSON에 있다. 질감 두 실행은 제어/영상 루프 진입 전 0프레임 실패여서 6장 검토가 불가능했다. 원본 RGB 전체는 GCP 영속 디스크에 남고, Mac에는 텍스트 전체와 선택 RGB만 회수했다. 완전한 RGB 백업 완료로 보고하지 않는다.

## 회전: 경계·방향·각도 분리

- reloc9 원장411행의 90L1.01953 / 180R1.14499는 보고값과 일치했다. 정지 꼬리는 좌0.007407rad(0.424°), 우0.001132rad(0.065°)다. 내부 구간에서도 좌1.062–1.068 / 우1.121–1.218이라 경계만의 문제는 아니다.
- 기존42구간에서 마지막 발행 펄스까지 포함하면 비율 변화 중앙 −0.235%, 절대 변화 p90 0.583% / 최대1.443%다. 14.5% 초과의 주원인으로 보기 어렵다([경계 재생](rotation-boundary-replay.json)).
- 기존 보정27구간의 좌/우 최소제곱 계수0.64078/0.55299가 별도15검증에서는0.53777/0.62978로 뒤집혔다. 방향·회전 크기·장소/하중이 혼입돼 있고, 저장 원장만으로 가속·포화·마찰을 각각 식별할 수 없다. 한쪽만의 고정 편향으로 모든 구간을 설명하지 않는다.
- 새 모델은 UMBmark식 체계적 계수 식별 원칙을 따른 **좌/우 별도 계수**다. reloc9 진단90L/180R 두 구간만 보정 자료로 사용해 **좌0.586523002994 / 우0.658696095987**로 고정했다. 기존0.575285159654에 각 원장 비율을 곱한 값이다. 새4방향 원장은 검증 전용이며 재맞춤하지 않았다. 사각 주행 UMBmark 전체를 수행했다는 뜻은 아니다.
- 새4방향은 모두0.9–1.1. 90→180에서 비율 차이는 좌+2.11%p / 우−0.34%p다. 이 장면만으로 각도 의존 항을 추가하지 않았다. 같은 seed/장면을 반복한 진단이며 통계적으로 독립인 새 seed 검증은 아니다.
- 새 계수로 기존15 holdout은10/15(기존8/15), **여전히5/15 범위 밖**이다. 모든 장소·하중·짧은 펄스의 정확도를 보증하지 않는다. XY/혼합 회전은 바꾸지 않았고 불확실성 예산은 최소0.40, 기존 잔차0.4921을 유지했다.

## 정착과 정적 등록

`sim/settle_pulse.py`는 release20 **[e897b0c2c96ad99cb0a3f5eb3cc255d2686bba09](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/e897b0c2c96ad99cb0a3f5eb3cc255d2686bba09/sim/settle_pulse.py)**에서 바이트 그대로 복사했다. SHA-256 `a7167d2bae2b10dc93c02f84e0c5563b48241f6d996825e8b88eadd1bff7fc09`. 어댑터는 잔차 비례 요청을 기존 안전·보정 펄스 격자에 양자화한다. 이 격자에서 최소 효과는 약0.10354rad, 허용은0.6배인 **0.06213rad(3.56°)**다. 기존2°를 유지했다고 주장하지 않는다. 실제 발행된 명령만 반전을 누적하고 안전상 막힌 hold는 세지 않는다. 연속반전3회 제한도 공통 모듈 그대로다.

마지막 selfmap은 6회 정착·6개 시점 관측을 끝냈고 **동일 목표 안 반전은0**이었다. 최근20SIM초의 전체 회전51회 중 반전3회는 목표 교체까지 포함한 원래 집계법이다(기존100회/99회). 정착 실패 주기2 진동은 이 재현에서 제거됐다.

등록은 별개로 실패했다. 원래93571의 0/978에서 자연 특징 추적은928회 insufficient_matches, 정적 특징은 주로2–4개였다. 센서 미갱신935, PF미해결732, xy공분산 기각940, yaw공분산 기각948, 독립축 없음620(중복 집계). **원래 실행은 벽 가드off**이므로 가드가 원인은 아니다([원본 진단](original-diagnosis.json)).

마지막456행에서도 센서 미갱신391, PF미해결115, xy공분산418, yaw공분산426, 기하125로 등록0이다. ambiguity는456회 모두 상류 관문 때문에 미평가였으며 실제 다중해 기각으로 세지 않는다. 특징·일치·인라이어·기각 분포는 [registration-diagnostics.json](registration-diagnostics.json)에 있다. 평가 전용 궤적 대조에서 두 번째 라운드의 PF resolved341건은10cm/5° 안0건, 위치 오차 중앙1.030m / yaw2.510°였다. 신뢰도 관문을 낮춰 통과시키지 않았다([PF 모드 진단](pf-mode-diagnosis.json)).

등록 토글에서는 최근30초 버퍼를 유지하고, SLAM 보정 전후 좌표를 과거 버퍼와 섞지 않도록 **하나의 자기명령 오도메트리 좌표계**로 시점을 고정했다. 개선은 등록 성공으로 이어지지 않았다. 45.5SIM초에 기존 재관측 예산이 소진돼 HOST_ERROR로 끝났다.

## 질감 후보와 벽 가드

PR511 병합 `db0a6858f6387e9048d4a37e78bc8eefd2ead484`의 natural_scene_texture 모듈과152개 자산을 그대로 복사했다. 별도 장면이며 기본off다. 두 번째 라운드는 하위 render_profile 이름 미지원으로, 이를 어댑터에서 base floor_light_v1로 고친 세 번째 라운드는 **nearclip audit의 base_profile 인자 미지원**으로 실패했다. 후자는 모델 빌드 이후, 제어/영상 루프 이전이다. PR511 nearclip API 의존성을 빠뜨렸으며 **질감 영상·컴파일 픽셀 검증·특징 개선은 미검증**이다. 3라운드 상한 뒤 추가 실행이나 검증 없는 실행 코드 수정은 하지 않았다. 질감 후보는 차단 상태이며 selfmap 큐는smooth만 준비한다.

벽 가드는 변경하지 않았다. 기존 자기 영상67장 진단에서 실제 벽점3,237→2,849(**−388, −12.0%**), 체커 근접621→606(−15, −2.4%)였다. 유효 벽 손실을 줄였다고 보고하지 않는다. 이 수치는 320×240 검토 JPEG를 확대한 과거 진단이고 새 native640×480 정탐률이 아니다.

첫 라운드에서 새 정착 이벤트 reason 키 충돌을 발견해 selfmap을18.8SIM초에 즉시 중단하고 수정·회귀 시험했다. carry에서는 상속된 평가용 TOP 촬영을 발견해54.2SIM초에 즉시 중단했다(제어 입력 사용은 없음). 이후 계획의 own-only 토글을 켜 TOP 촬영 자체를 없앴고, 두 후속 carry의 TOP 촬영은0이다. 이 중단들을 성공 분모에서 지우지 않았다.

## 토글·검증·운영

새 토글 기본값은 모두false: carry `reloc10_rotation_calibration_v1` / `reloc10_own_review_only_v1`, selfmap `reloc10_settle_v1` / `reloc10_registration_v1`. carry의 reloc9/reloc10 회전 계수는 상호배타다. off 경로는 관련 단위시험에서 기존 입력/출력을 유지하며, 이번 GCP에서 별도 off 코호트를 돌린 것은 아니다. 정답은 오프라인 보정·평가에만 사용했고 실제 입력 감사 invisible_measurements/held_world_reads는0이다. 제어기는 자기 RGB·발행 명령·허용된 고정 지도만 받았다.

관련 시험은 **carry10 / selfmap13 통과**. MuJoCo import를 막은 프로세스에서도 통과했고 Mac 물리/렌더를 실행하지 않았다. 실제 backend 생성 대신 mock을 썼으며, 벽 가드 시험에서는 별개 CAD 그림자 센서를 격리했다. 새 시험을 CI 목록에 등록했다. 전체 CI는 로컬에서 돌리지 않았다.

세 번째 실행 소스는 carry `96712d69f4bac4e5a8b52c958706abfcef717cb0`, selfmap `f7c052f07638196b0858483f79370ce402dda3a6`. 이후 게시는 기록·CI 시험 등록·시험 격리만 더하며 실제 실행 모듈은 바이트 동등하다([runtime-equivalence.json](runtime-equivalence.json)).

첫30초 wall/SIM은 마지막 carry **3.855(경고)**, selfmap **7.183(6.0 초과)**다. 이후 새 제출은 없고 완료 원본만 회수했다. 속도·등록·배치 모두 자동 승격 근거가 아니다. 각 제출 전 전체 동시 수를 확인했고 자기 실행은 최대4개였다. budget-stop ACTIVE / 당일 정지 발동0, 당일 stdout21건의 최신 순비용 보고0KRW였다. 크레딧 잔액 자체를 확인했다는 뜻은 아니다. 기존8h STOP/idle20m을 유지했고 키를 VM에 두지 않았다.

최종 자기 실행0 / 자기 임대0. 전체 활성 실행은 마지막 조회0이지만 **기존 임대547개 때문에 gcpctl stop이75로 보류**, VM은RUNNING이었다. 다른 작업 임대를 제거하거나 정지 관문을 우회하지 않았다. 유휴 종료 장치는active다. VM 정지 완료로 보고하지 않는다.

## 대기열과 재현 명령

게시 HEAD에 고정해 지정된 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/`에 만든다. 정확한 SHA·큐 해시는 해당 JSON 및 로컬 delivery.json에 기록한다.

- `20261015-solo-carry-<sha8>.json`: 회전4방향1개 → 재현3(93261/93262/93266)+신규8(93310–93317), 후보2개 동일 seed/배치. 총23개.
- `20261015-selfmap8-<sha8>.json`: 93571 먼저 + 신규4(93580–93583), smooth 총5개.
- 둘 다 max_parallel16. approved/enabled/ready/stage_ready/execute/submitted는 모두false, 자동 승격false, 이전 큐 합산false. 이번 확인은 이 대기열을 제출한 것이 아니다. 등록·속도·질감 결함이 남아 ready=false다.
- 신규 seed는 로컬 큐와 원격 비압축 메타데이터2,190개에서 충돌0을 확인했지만 제출 직전 전체 이력을 재검사하도록 플래그를false로 유지한다.

다음은 향후 명시적으로 재현할 때 쓰는 명령이며 **이번 작업의 추가 실행으로 수행하지 않았다**. 기본 호출은 준비 정보만 출력한다. `--execute`는 깨끗한 소스·budget-stop·전체 동시40 상한을 확인한 뒤 기존gcp1에서만 remote_run.py를 호출한다.

```sh
cd /Users/changmin/projects/ugrp-wt/map-carry-zone
bash experiments/2026-10-15-reloc10/reproduce-rotation.sh --execute
```

실제 세 라운드의 전체 인자는 [gcp-commands.json](gcp-commands.json)에, 검증 원본은 `outputs/reloc10-gcp/round1`–`round3`에 있다. carry 재현은 해당 JSON의 `scripts/remote_run.py --host gcp1 --class dev --pr 505` 항목, selfmap은 `--pr 506` 항목이다. 과거 실행 SHA를 재현하려면 소스도 그 SHA에 맞춰야 한다. 이미 쓴 실행 이름/원본을 덮어쓰지 않는다.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no:cacheprovider tests/test_reloc10_carry.py tests/test_reloc9_carry.py
# 위 명령 종료 후 map-selfmap에서만 다음 시험을 직렬 실행한다.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no:cacheprovider tests/test_reloc10_selfmap.py tests/test_reloc9_selfmap.py tests/test_reloc8_selfmap.py
```

## 참고 자료

- [Borenstein & Feng1996, IEEE TRA12(6),869–880](https://ieeexplore.ieee.org/abstract/document/544770/), [원문 PDF](https://web.cecs.pdx.edu/~mperkows/CLASS_479/S2006/Paper-correction-odometry-error.pdf): UMBmark의 양방향 체계적 오도메트리 계수 식별 원칙. 차동구동 식을 메카넘에 그대로 적용하거나 사각 주행 전체를 수행하지 않았다. IEEE 초록/서지와 논문 사본을 확인했다.
- [Thrun·Burgard·Fox, Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/), [오도메트리 모형 장](https://robots.stanford.edu/probabilistic-robotics/corrections1/pg122-139.pdf): 명령 이동 모형·관측 갱신·불확실성 구분. 출판사 소개/검색된 장 내용을 확인했으며 장 PDF 직접 열기는 timeout이었다.
- [Papadopoulos et al., quantized feedback limit-cycle analysis](https://arxiv.org/abs/1701.07482), [MathWorks quantization](https://www.mathworks.com/help/fixedpoint/quantization.html): 양자화 주기진동을 명시적으로 다루는 표준 원칙. 0.6 quantum/3회는 공통 모듈의 공학적 설정이며 일반 안정성 정리를 주장하지 않는다.
