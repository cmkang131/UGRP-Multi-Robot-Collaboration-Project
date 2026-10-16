# mapbuild4 — 횡60ms 되밀림 재현, 3라운드 중단 / NOT_READY

**전진 뒤의 짧은 횡 펄스는 약3mm 움직였다가 되밀린다. CPU와 MJWarp 모두 재현했으며,
warpfit 새 프로필에서도 남았다. 사용자 지정 3라운드 정지 규칙에 따라 지도 확장은 실행하지 않았다.**
400ms는 약44mm 이동하지만, 근거리60ms의7mm 예측을 그대로 대체하는 수정으로 수용하지 않는다.
[PR #556 DRAFT](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/556), 같은 `codex/mapbuild1` 브랜치다.

**ownership-ack:** 필수 `agent-ownership.md`와 `COORDINATOR_NOTE.md` 확인. gcp5 단독,
CPU 비교·분석도 gcp5. gcp2 시작0. 지도·새 진단 코드만 수정했고 공용 backend·장면 변경0이다.
warpfit의 `warp_native_contact_v1`은 소유자 소스 `0b5ef498eb152d630c3895edf5ce6097b1008afe`를
[byte 그대로 보존](vendor/warp_native_contact.py)해 명시 옵션에서만 읽었다. 소유 모듈 수정0이다.

## 측정과 원인 범위

mapbuild3 원본을 gcp5에서 다시 계산해 전진17.04048mm, FOLDED 횡0.09020mm,
HIGH 횡2.43458mm, 회전5.15871°를 확인했다([원본 해시·계산](original-verification.json)).
새 진단은 같은 비관통 시작·자세·질감·카메라·35출력·weld OFF를 사용했다.
[수정 전 분포](prechange-distribution.json), [전체 funnel](rejection_table.json),
[8실행 요약](analysis-final/summary.json), [112조건 수치](analysis-final/)를 보존했다.
각 조건은 고정 시작1회이며 독립112시드/임무 성공 관문이 아니다. 모든 정상 유한 실행은 `cap_end`다.

| 라운드 | backend별 조건 | 확인한 범위 |
|---|---:|---|
| R1 NoSlip10 | 각20 | 좌/우60·100·200·400ms×FOLDED/HIGH 16개 + 전진/회전100ms4개, 각2SIM초 |
| R2 NoSlip10 | 각8 | 먼저 전진100ms, 뒤에 좌/우60·400ms×2자세, 각3SIM초 |
| R3 warpfit v1 | 각28 | 새 프로필로 cold20 + 전진 뒤8을 모두 재측정, 각각2/3SIM초 |

모든 C 비교는 gcp5의 MuJoCo3.16 CPU이며 MJWarp·기존 결과와 합산하지 않는다.
R1/R2 scene XML SHA는 `6c4c907cd59c34e6bb717c7c991152d963f67ee2f6f25fdd134afd955c63890f`,
R3는 `dc71d38961bb95dcd6841124889eecc98ec78bddd0d41f6b3bf4a89b6cb3f74d`다.

| FOLDED 좌/우, 횡 성분(mm) | MJWarp NoSlip10 | CPU NoSlip10 | MJWarp warpfit v1 |
|---|---:|---:|---:|
| 깨끗한 시작60ms | +7.036 / −7.201 | +7.696 / −7.538 | +6.701 / −7.130 |
| 깨끗한 시작100ms | +11.201 / −13.203 | +11.274 / −13.233 | 전체 표 참고 |
| 깨끗한 시작200ms | +25.867 / −25.787 | +25.857 / −25.791 | 전체 표 참고 |
| 깨끗한 시작400ms | +47.485 / −48.267 | +47.696 / −48.228 | +46.807 / −47.738 |
| **전진 뒤60ms** | **−0.0349 / +0.1376** | **−0.0082 / +0.0595** | **−0.0023 / +0.0139** |
| 전진 뒤400ms | +44.306 / −44.141 | +44.330 / −44.153 | +44.161 / −44.177 |

표는 횡 성분이며 전체 XY 순변위와 다르다. 새 프로필 전진 뒤 FOLDED60ms XY 순변위는
좌0.1358mm/우0.0525mm다. 전진 드리프트·yaw·HIGH도 전체 표에 포함했다.
FOLDED cold 좌100ms의 MJWarp 전진 드리프트6.083mm 대 CPU0.694mm도 남겼다.

원인을 구분한 근거는 다음과 같다.

- **입력 relay 미발동이 아니다:** 모든35출력은 기존 시작 문턱32.5를 넘고,
  휠당0.03138128Nm가 적용됐다. 전진 뒤60ms에도 휠이 약0.05–0.08rad 회전한다.
  단순히 정지 마찰을 전혀 못 넘었다고 해석하지 않는다.
- **이력·롤러 접촉 상태와 정지 꼬리:** 전진 뒤 휠 위상은 약0.52rad 바뀐다.
  NoSlip10 FOLDED60ms는 CPU/MJWarp 모두 중간 XY peak 약3.0–3.2mm,
  펄스 종료 시 횡 약1.8mm까지 움직였다가 최종에 거의 돌아온다. 400ms는44mm가 남는다.
  휠/롤러 지지 형상과 접촉의 과도 응답으로 해석할 근거이며, 특정 마찰계수나
  단일 접촉 인자의 단독 인과를 식별한 것은 아니다. 펄스 시작 r1 비바닥 접촉0이다.
- **자세/하중 분포:** 전진 뒤 FOLDED와 HIGH의 차체 기준 COM x는 약9.01/15.33mm,
  z는49.10/47.08mm다. HIGH는 NoSlip10 전진 뒤60ms에 횡 약2.4–2.7mm가 남는다.
  자세는 차이에 관여하지만 cold60ms는 양 자세 모두 약7mm로, 자세 하나로 전부 설명되지 않는다.
- **접촉 설정:** warpfit v1(NoSlip0·elliptic·implicitfast·impratio5)에서도 짧은 펄스 결함이 남는다.
  v1은 설치 MJWarp의float32 tolerance floor 약1e-6, 기준은 명시1e-8을 사용했다.
  owner 구현의 변환 규칙을 그대로 썼으며 새 프로필을 독립 재측정했다.
- **예측기 문제:** v122는 과거 CPU S2 주행20Hz 궤적의 평균 응답으로, 현재 휠/롤러 위상을
  조건으로 받지 않는다. 같은60ms의 cold≈7mm/warm≈0mm를 단일 이득으로 설명할 수 없다.
  HIGH fine 직접 학습0개도 문제다. 따라서76.7배 보정은 넣지 않았다.

상세 trace·접촉 분류는 [압축 분석](phase-analysis.json.zst)과
[복원 검증](phase-analysis.json.compression.json)에 있다. 이 파일의 COM은 yaw 기준 변환이며,
접촉 수는 **세계 전체** wheel/floor 수다. 실제 r1 접촉 힘이나 정확한 하중 분배의 측정은 아니다.

## v122 출처와 준비한 수정의 한계

`harness/data/s2_motion_v7_pulse_cal_v122.json`은 과거 s1042/43/45를 fit,
s1044 등을 사후 holdout으로 썼다. 무하중 좌60ms17개/우21개 학습, loaded/HIGH fine 학습0개는
무하중 fine에 coarse65/650ms 비율을 곱한 미확증 전이다. 100/200/400ms lateral35는 없다.
원본 경로·SHA는 모델 파일에 남아 있으나 해당 과거 pulses.jsonl은 현재 Mac에서 찾지 못했다.
과거 backend의 정확한 MuJoCo 버전과 휠 접촉 위상 분포는 이번에 독립 복원하지 못했다.
20Hz 자료의10ms 보간은100Hz 실측이 아니다.

새 기본off `mapbuild4_pulse_prediction_v1`은 명시적으로 제공한 MJWarp 전진/회전 응답만 받으며
미측정 횡60ms 요청을 거부한다. `mapbuild4_frontier_v1`은 기존 LK·관측floor grid·frontier/A*와
heading-first 방식을 잇는 **준비 코드**다. unknown frame은 지도에서 빼고, unknown 때는 실제
RGB lookaround를 요청하며, 3명령 연속 시각 미회복은 중단하도록 했다.
[기준 prior](motion-calibration.json)와 [새 프로필 prior](native-motion-calibration.json)는
각 고정 시작1회의 탐색용 자료이며, 시각·주행·지도 물리 인수는 **0회**다.
기존 production 경로·상수 변경0, 새 bundle ID/workflow 추가0, 표준 관리 통합도 미완료다.
이 준비 코드를 횡이동 해결이나 지도 범위 확대의 결과로 보고하지 않는다.

## 기록·검증·종료

[시간순 영상 검토](playback-review.md): 실패2개(FOLDED/HIGH60ms)와 비교400ms의
개요+r1+r2, 전체2Hz·전체10Hz(실행3초라 terminal10초보다 짧음)를 직접 읽었다.
2Hz는 작은 이동 뒤 복귀를 숨기므로100Hz 상태 trace와 함께 해석했다.
Mac에는 요약·검토 영상·몽타주만 회수했다. raw state는 gcp5 영속 디스크에 있다.
[원본589파일 해시 불일치0](analysis-final/integrity.json),
[회수 영상49파일 해시 불일치0](playback-retrieval.json),
[모든 시도](attempts.json), [재현 명령](analysis-final/reproduce.json)을 보존했다.
물리 HOST_ERROR0이며 최초 소스 압축 전송 미완료/오프라인 의존성 오류는 별도 기록했다.
원본·과거 결과를 삭제하거나 합산하지 않았다.

비물리16 passed, compile·diff 검사 통과([검증](validation.json)). GitHub는 DRAFT head에서
checks 없음으로 응답했고 전체 CI·독립 검토·승인·병합은 확인하지 않았다.
지도 확장 coverage·잘못된 free·문/목적지·화물 복원은 새 측정0/미검증이다.
관문4는 warp10 NOT_READY 때문에 **WITHHELD 유지**다. [다음 큐](next-queue.json)는 ready=false다.

자체 실행 프로세스0·GPU작업0·타 lease0 및 자체 lease 제거를 확인했다
([종료 점검](operations/close-admission.json)). gcp5를 직접 정지해
**2026-10-16 22:42:57.057 KST (13:42:57.057 UTC), TERMINATED**로 확인했다
([GCP 응답](operations/gcp5-after-stop.json)). maxRunDuration/자체wall상한 추가0,
idle20/budget-stop 유지, gcp2 시작0·타 VM 조작0·모델/키 전송/Drive/Mac GUI0이다.
실제 청구 비용은 별도 미측정이다.

## 참고 자료 (2026-10-16 열람)

- [Menagerie Robot Soccer Kit MJCF](https://github.com/google-deepmind/mujoco_menagerie/blob/main/robot_soccer_kit/robot_soccer_kit.xml):
  free base·구동 휠 velocity actuator와 수동 휠 부품을 쓰는3륜 omni 예제. 메카넘 수치 복사 근거가 아니다.
- [MuJoCo contact mixing](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters):
  geom 우선순위와 friction/condim/solref/solimp의 결합, 명시 contact pair의 이방 마찰 경계를 확인했다.
- [MJWarp 공식 구현/배치 안내](https://github.com/google-deepmind/mujoco_warp/blob/main/README.md),
  [MJX 공식 문서](https://mujoco.readthedocs.io/en/stable/mjx.html): 배치 모델·상태·renderer를 재사용했다.
  검토 범위에서 메카넘 전용 보정 예제는 찾지 못했다.
- [Matsinos 2012 §§2.4–3](https://arxiv.org/html/1211.2323v1): 휠별 롤러 방향·정상력·저항을 분리한다.
  다른 로봇의 마찰계수는 이식하지 않았다.
- [TIAGo 2025 §III-A/B](https://arxiv.org/html/2510.10273v1): 수동 롤러 형상·접촉과 측정 명령 응답을
  구분한다. six-sphere 형상은 이번에 적용하지 않았다.
- [현재 FUJI roller 원본](https://github.com/DaiGuard/fuji_mecanum/tree/646431a5e107448e0e2bdeeba4575db9aa3665ff),
  [공개 MuJoCo 메카넘 생성기](https://github.com/JunHeonYoon/mujoco_mecanum/blob/master/wheel_code_gen.py).
  현재 v7은 `masterpi_dynamics_v2`의 reduced body wrench를 덮어쓰고 수동 hinge roller 접촉과
  네 wheel motor torque로 구동한다. scaled15→9롤러 형상의 원형 지지 적합성은 따로 미확증이다.

[웹 원본 열람/해시 영수증](research-receipt.json). 실제 하드웨어 사양·마찰·무게 분배는 아직 미보정이다.
