# 빔 상대 좌표계와 전역 여유 예산의 공동 운반 설계

2026-09-28 KST · 설계 후보 · **구현/물리 dev NOT_READY**.

**권고: 국소 조작은 빔 상대 관측으로 제어하고, 세계 좌표의 벽 안전은 독립된 보수적 도달 영역으로 계속 검사하는 두 계층을 설계한다.** 먼저 [dev09·10의 시각 결함](dev09_10_diagnosis.md)을 별도로 해결해야 한다. “태그가 안 보여서 두 번 실패했다”는 전제는 이번 자기 입력 재검출에서 반증됐다. 과거 낮은 팔 align에서의 PF 과신과 loaded 무관측은 여전히 남는다.

이 문서는 [loaded_stage_design.md](loaded_stage_design.md)의 후속 통합안이다. 원래 기록·계수·과거 판정을 덮어쓰지 않는다. 이전 B(checkpoint)+C(오차 예산)는 유지하고, A(빔 관측)를 **상대 조작 상태**로 확장한다. 이전 문서가 권고에서 제외했던 scalar gate 대체는 이번에 **별도 profile의 검토 대상**으로만 올린다. [기계 판독 설계](beam_frame_design.json)의 `runnable=false`, 미정 calibration/bundle/실행 SHA를 유지한다.

## 1. “좌표계만 변경”의 정확한 의미

`W`: 정적 지도, `R_i`: 자기 base, `B`: 현재 구간의 빔. 상대 조작 상태는 `T_Ri_B`, 바닥 빔의 초기 world anchor는 `T_W_B(t0)=T_W_Ri(t0) T_Ri_B(t0)`다. 관측 원점은 로봇별 자기 RGB와 자기 명령이다. task sheet의 coarse pickup 좌표를 실제 빔 위치로 대입하지 않는다.

평면 상태를 좌표 회전만 하면 `P'_xy=R P_xy Rᵀ`이고 `trace(P'_xy)=trace(P_xy)`다. 그래서 PF의 σxy를 그대로 회전했다고 줄어들지는 않는다. **σglobal → σrelative로 바꾸는 것은 다른 상태 변수와 새로운 관측 모델을 사용하는 결정 정책 변경**이다. 숫자 5 cm/3°를 유지해도 이전과 허용 행동 집합이 달라진다. 단순 표기 변경이나 안전 동등성이 이미 증명된 변경으로 부르지 않는다.

| 항목 | 보존할 값/행동 | 변경/추가할 의미 |
|---|---|---|
| M2 align 잔차 | 전후 .012 m, 좌우 .008 m, 각도 .035 rad, 연속 2회 | 자기 빔 band/axis 잔차에 계속 적용 |
| preclose fix | .05 m / 3° | calibrated **상대** 불확실도에 적용하는 새 gate. 영상 fit scatter를 바로 σ로 부르지 않음 |
| loaded 상대 품질 | HIGH .07 m / 3°, LOW .06 m / 2.5°, dwell 기존값 | 상대 상태의 품질 계약으로 제안. world safety는 아래 별도 certificate 필수 |
| geometry 여유 | .035 m = .020 base + .015 body residual, k=2 | base·팔·빔 전체/stop/lower sweep. bias·상대 오차·표본 gap을 추가, 기존 cap으로 σ 자르기 금지 |
| lift/carry 영상 검사 | co-motion IoU .45, fullframe hold IoU .70 등 frozen M2 profile | 상대 metric pose의 대체가 아니라 필요한 추가 receipt |
| 프로토콜 | control .1 s / arm .05 s, heartbeat .05 s, timeout .15 s, readiness TTL .6 s, 8 segment | 기존 STATUS enum/epoch/GO 사용. 이미지/좌표/공분산 메시지 금지 |
| 이동/문/목적지 | 기존 global gate·경로·성공 판정 | 빔 relative gate로 이동을 우회 승인하지 않음 |
| 물리 평가 | 접촉·들기·문 통과·B 배치/방출·weld OFF 등 prereg v5b | 평가 전용, control 성공 통보에 주입 금지 |

기존 global σ 7 cm/3°가 조작 전체를 막던 조건을 방향별 certificate로 대체하는 부분은 **새 안전 기준의 적용 구조**다. 일괄 σ 완화와는 다르지만, 별도 검토·calibration·새 cohort 없이 “기존 안전 기준과 동등”이라고 주장할 수 없다.

## 2. 관측 상태와 입력 경계

각 endpoint가 `BeamRelativeReport`와 `GlobalEnvelopeReport`를 따로 가진다.

- 상대 보고: 구간/anchor ID, 자기 frame_id·SHA·capture 시각, 명령 PWM epoch, 빔 role/identity hypothesis, 관측 가능한 축, 상대 pose/set, covariance와 별도 bias 상한, 마지막 유효 관측 시각, `resting/attached_hypothesis/unknown` 모드. partial view는 보이는 축만 갱신한다. 비어 있는 축은 0이 아닌 unknown이다.
- 전역 보고: 마지막 유효 absolute fix와 출처, 정적 map/calibration hash, world 위치·yaw의 불확실 집합, 이후 시간/이동/회전/정지 지연/팔 동작의 누적 bound. 상대 beam update와 STATUS heartbeat로 absolute fix age나 global gauge를 reset하지 않는다.
- 허용: 자기 wrist RGB, 고정 카메라 보정·정적 map·고정 task/물체 형상, 자기 발행 명령과 자기 로컬 상태. 두 로봇 간에는 정해진 STATUS와 기존 evidence metadata만.
- 금지: GT 물체/로봇 좌표, 측정 관절, 접촉·하중 truth, 성공 평가, TOP/상대 영상, peer PF/VO/공분산, host가 생성한 상대 자세/준비 판단. 자기 사진에 찍힌 상대 로봇은 관측될 수 있으나 그 로봇의 내부 상태가 아니다.
- 같은 JPEG/anchor의 반복 처리를 독립 측정으로 곱하지 않는다. 명령 발행은 실제 이동·정지·파지 증명이 아니다. time/PWM/anchor 불일치, 검은 영상, 가림, identity ambiguity는 fail closed다.

### 바닥 빔과 loaded 빔의 관측 모델은 다르다

현 `owncam_pair_beam_v2.observe_beam`은 **바닥에 놓인 빔의 상면 z=.032 m**와 band를 사용한다. 이를 들린 빔에 그대로 적용하면 깊이·scale을 잘못 환산한다. 새 설계도 같은 카메라/FOV/외관을 유지한다. loaded에서는 기존 co-motion/hold signature로 파지 유지의 필요조건을 검사하고, metric 상대 자세가 필요하면 알려진 빔 형상·식별 가능한 여러 모서리의 own-RGB fit과 명령 FK 오차 bound를 별도로 검증해야 한다. 평면/원근/tilt 모호성이 풀리지 않으면 가능한 3D 자세들의 합집합으로 sweep을 계산한다. 해가 너무 넓으면 READY하지 않는다.

끝점이나 band가 없는 긴 직선만 보이면 축 방향 위치와 양끝 identity가 모호하다. END_CLIPPED/BAND_CLIPPED는 v5의 segment-local standoff track과 fresh 부분 증거를 함께 사용한다. `RestingBeamTrack`의 15 mm/1° floor, 시간·명령 drift와 30 s age 제한도 calibration 보증은 아니다. loaded로 넘어갈 때 resting anchor를 ground model로 계속 update하지 않는다.

## 3. M2 성공 방식과의 관계

`scripts/run_m2_pair.py:480–494`의 `_vo_pose()`는 초기 도착 추정 `(x0,y0,ψ0)`와 첫/마지막 자기 빔 `(g0,h0),(gt,ht)`로:

```
bW = p0 + R(ψ0) g0
ψt = wrap(ψ0 + h0 − ht)
pt = bW − R(ψt) gt
```

를 계산한다. 첫 파지의 `grasp_estimate`에 넣고(`:540–552`), door schedule의 y/yaw 보정에 쓴다(`:592–608`). 낮은 팔 align의 명령 motion model이 약 4배 과대 예측했던 문제를 피하는 구조다. **초기 도착 추정의 world 오차는 그대로 남는다.** 바닥 빔이 실제로 움직이면 위 정지 landmark 가정도 깨진다. 첫 관측 전에 이미 움직였거나 beam/role association이 모호하면 anchor를 만들지 않는다.

49회 성공선정 원본은 21회 open_floor, 28회 door다. 유효 `vo_pose`가 기록된 것은 **46/98 로봇 trace**다. 모든 49회가 같은 VO/grasp_estimate 기법으로 성공했다고 일반화하지 않는다. door v1·재파지 등에는 tag sweep/PF fallback이 있으며 open_floor의 상대 align도 별도다. 원본 M2에는 새 global/relative uncertainty certificate가 없고 world geometry 안전을 보증하지 않는다.

새 후보는 이 **관측된 빔 변위에 의한 상대 갱신**을 계승하되, 도착 공분산/공통 오차의 상관을 보존한다. base와 beam을 동시에 같은 SE(2)만큼 이동시킨 가설은 beam-only 관측으로 구별할 수 없다. global PF에 빔을 고정 landmark로 반복 주입해서 world σ를 줄이지 않는다. 두 로봇의 receipt를 독립 world 측정으로 결합하지 않는다.

## 4. 벽 여유에서 σ 상한 역산

`d_j`: 자기 base/팔/전체 빔의 예상 swept envelope 표면부터 정적 벽까지의 명목 여유. point/radius를 이미 반영한 값이다. 벽 법선 `n`, body point lever `r_j`, `J_j=[I, R'(ψ)r_j]`에 대해 모든 시간/가능 자세에:

```
d_j > .035 + sampling_pad + B_j + stop_pad + relative_pad
            + k sqrt(nᵀ J_j P_global J_jᵀ n)
```

를 요구한다. covariance의 XY–yaw 상관을 유지한다. 비정규/다봉 PF면 평균+σ 대신 가능한 모드의 합집합을 검사한다. 미보정 model bias `B_j`는 σ와 별도다. 통계 coverage가 입증되지 않은 k=2를 “95% 안전”이라 부르지 않는다. 이것은 map/형상/calibration/동적 장애물 가정이 유효할 때의 조건부 certificate이며 물리 안전 보증이 아니다.

full covariance가 없는 저장 자료에서는 더 보수적인 기존 등방 margin 형태로 역산한다:

```
σxy,max = [d − .035 − B − relative_pad − stop_pad − sampling_pad − 2 L σyaw] / 2
```

방향별 버전은 `σxy` 대신 `σn=sqrt(nᵀPxy n)`를 쓰고 yaw/상관을 따로 안전하게 상계한다. 모르는 bias를 0으로 확정하지 않는다. 우변 ≤0이면 거부다. 실제 움직임 동안 yaw, lever, 여유가 바뀌므로 시작점 한 번의 역산으로 전체를 승인하지 않는다.

예시: **d=.50 m, L=.90 m, σyaw=3°**라면 다른 오차를 0으로 가정했을 때 σxy 상한은 **.18538 m**다. B 등 추가 예산이 .10 m면 **.13538 m**, .30 m면 **.03538 m**, .80 m면 음수다. 이는 현재 지원 cap .15 m를 해제해도 된다는 허가가 아니다. calibration 지원영역 밖은 거부하고, 상한 계산이 크다고 실제 σ/편향이 작다는 근거가 생기지는 않는다.

### 이 지도에서의 수치와 +50 cm 전제

dev09 정적 sheet의 nominal beam x=1.0, prestation x=.275/1.725, grasp station x=.575/1.425를 사용했다. 정적 벽·문설주, 차체 모서리/팔 spheres와 full-beam envelope를 검사했다. 높이로 통과를 면제하지 않는 보수적 평면 계산이다. 명령 팔 LOOK_P20/search/p45/inspect를 포함하지만, **연속 lift/lower 물리 sweep 전체를 인증한 계산은 아니다**. attached LOOK 자세는 허용 동작이 아닌 envelope stress case다. 실시간 beam 위치로 sheet를 사용하지 않았으며 다른 seed/위치에는 여유를 다시 계산해야 한다.

| 명목 구간 | 가장 좁은 여유 d | 대표 제한 요소 | yaw σ3°, 추가 bias0일 때 σxy 상한 |
|---|---:|---|---:|
| r1 prestation | 1.150 m | 서쪽 벽/차체 | .54834 m |
| r2 prestation | **.31953 m** | divider/차체 모서리 | **.13311 m** |
| r1 grasp station, 검사한 자세 중 최악 | .87011 m | divider/full beam | .37815 m |
| r2 grasp station | **.61000 m** | divider/차체 | **.27834 m** |

r2 grasp에서 50 cm 이상이라는 nominal 근거는 확인되지만 **align 진입의 r2 prestation에는 적용되지 않는다**. grasp 여유 .61 m도 `.035 + 2σxy(.07) + yaw`를 빼면 약 .41668 m다. “50 cm”가 raw 여유인지 기존 margin 차감 뒤 여유인지 구분해야 한다. static plan route 통과나 예상 station은 로봇이 실제 그곳에 있다는 증거가 아니다.

기존 loaded 기록의 낮은 팔 구간 사후 오차 .68–.95 m는 이번 정적 여유보다 크다. 이 오차 전체를 분포가 검증되지 않은 σ에 묻거나 상대 좌표계 전환으로 없앴다고 하면 false-safe가 된다. 새 설계는 **align 진입 당시 검증된 absolute anchor를 고정하고** 이후 resting beam 상대 변위/명령에 따른 bound를 전파해야 한다. 그 entry bound 자체가 확인되지 않으면 계산 결과는 `INSUFFICIENT_EVIDENCE`다.

## 5. 단계·동기화와 loaded 설계 통합

| 단계 | local 판단 | global 검사 | STATUS 전이 |
|---|---|---|---|
| 접근/이동 | 기존 own PF+정적 경로 | 기존 global gate와 벽 여유 | `approach_ready/go_s` |
| align | resting beam band/axis의 새 anchor, 기존 잔차 기준 | 짧은 base/arm 명령+stop의 전체 tube; 넓은 pickup도 실제 현재 위치 기준 | `aligning`, 실패 `abort`; base pulse도 world 검사 유지 |
| wait_close/close | fresh 동일 PWM 영상, 상대 .05 m/3°, target identity/부분뷰 track, 두 번째 준비 확인 | 아직 들지 않은 빔은 관측된 resting 영역, 차체/팔 sweep 별도 | `close_ready_s → close_go_s` |
| wait_lift/lift | close receipt, fresh grip/co-motion; loaded metric/형상 hypothesis | 대기+lift+최소 안전 lower까지 예산, base 이동 금지 | `lift_ready_s → lift_go_s` |
| wait_carry/carry | 상대 slip/held 관측 지속 | **world 이동 예산 필수**, 다음 checkpoint+stop+lower 전체. relative만으로 carry 허가 금지 | `carry_ready_s → carry_go_s` |
| wait_lower/lower | local 유지와 support 후보; 낮아진 순간 ground 모델로 강제 switch 금지 | 검증된 support 구역/전체 lower sweep·settle 예산 | `lower_ready_s → lower_go_s` |
| wait_open/open | fresh 자기 support·안정/분리 증거; 불명확하면 unknown | release 이후 재관측 가능한 정적 영역 | `open_ready_s → open_go_s` |
| checkpoint/재파지 | 양쪽 분리 확인 후 순차 look, 새 relative anchor | 태그 refix로 새 absolute bound, 다음 구간 사전검사 | segment+1의 기존 approach/close/lift barrier 재사용 |

채널 fields는 기존 `robot_id,task_id,seq,state,sent_at_s,observed_at_s,frame_id,ready_until_s` 안이다. 좌표·이미지·sigma·자유문장을 추가하지 않는다. anchor/certificate 숫자는 각 endpoint 로그에만 둔다. host는 양측 유효 enum과 공통 GO 시각을 전달하고 준비 여부를 대신 계산하지 않는다. 두 독립 submission의 plan hash/역할/목적지가 맞아야 한다. 고정 수의 readiness enum/정해진 barrier 외에 시각·반복 횟수로 좌표를 인코딩하지 않는다.

READY의 내용은 **자기** relative와 global certificate가 모두 유효하다는 assertion이다. peer의 READY를 자기 세계 위치 관측으로 취급하지 않는다. fresh frame TTL .6 s와 certificate 만료 중 이른 시각을 적용한다. heartbeat는 증거 수명을 늘리지 못한다. phase/task/segment/seq가 다른 이전 READY/GO는 거부한다. 양쪽 GO의 실행 시각, silent/stale/abort 때 양측 예약 base/arm 폐기, 한쪽만 닫기/들기 금지를 기존 검사에 추가한다.

기존 loaded B+C의 **safe set-down → open → 순차 look → regrasp**를 유지한다. 새 enum은 첫 범위에서 만들지 않는다. 추가 checkpoint가 필요하면 기존 최대 8 segment 내에서 static plan에 사전 고정하고 불가능하면 계획을 거부한다. loaded인 한쪽 손목만 태그를 보려고 pan하지 않는다. hold 명령은 실제 정지 증명이 아니므로 stop lag와 영상 안정성/계획 tube가 필요하다. 예산 초과 뒤 “내리면 안전”이라고 가정하지 않고 **진입 전에** lower까지 예약한다. 비상 hold/abort와 안전하게 내려놓기 완료를 구분한다.

## 6. 가능한 오프라인 판정

새 상대 calibration, global bias bound, dual certificate가 아직 없으므로 새 제어기를 구현한 것처럼 pass/fail을 만들어내지 않았다. 최초 새 관측/명령 분기에서 exact replay를 끝내고 이후는 unknown이다.

| 원본 | 이번에 확인한 것 | 새 후보에서의 판정 범위 |
|---|---|---|
| M2 성공 49회 / 98 trace | 기존 98/98 global loaded gate 거부는 과거 조건부 PF 재생. 유효 VO 46 trace. 첫/마지막 align 자기 JPEG 각 98장을 새로 검사해 기존 standoff 형태 fit은 96/98, 93/98 | full 후보 **49회 모두 INSUFFICIENT_EVIDENCE**. shape-fit pass가 calibration/파지/운반 pass가 아님 |
| M2 close 206회 | 기존 입력계약 0/206 fresh+matching preclose 영상. 목록과 result/commands/inputs/events hash 재확인 | 추가 close-ready 뷰는 원본에 없으므로 후보 전체 통과로 승계 불가 |
| dev03 | dock/look 실패, r1 SELF_UNCERTAIN admission, r2 timeout | 상대 조작에 도달 안 함. admission/기존 dock 문제는 그대로 거부 |
| dev04 | r2 SELF_UNCERTAIN, r1 timeout | 동일. abort intervention은 여전히 not_reached |
| dev05 | 190.429 s r1 PAIR_COLLISION_GUARD. 기존 v5 판정 재생은 미파지 빔 부착 오류를 해소 | resting/attached 분리 유지. 상대 좌표계의 새 world bound가 없으므로 추가 통과는 미확인 |
| dev06 | 193.7 s r2 wait_lift yaw3.001°; partner abort | hold와 lift READY를 분리할 수 있으나 calibrated relative·global budget 없이 lift 허가 불가 |
| dev07 | 202.8 s END_CLIPPED/PREGRASP_NOT_READY; v5 partial predicate는 통과 | 상대 anchor+fresh 부분뷰 방식과 부합. 새 close/loaded 증거 없어 전체 unknown |
| dev08 | 175.6 s align σxy .07004 m; v5는 166.3 s에 먼저 relook 요청 | 빔 anchor 방식도 새 policy 분기. 세계 편향 상한을 검증하지 않으면 base motion 불허 |
| dev09 | r1 179.5 s NO_FIX; 시각 항만 수정하면 첫 look177.3 s에서 조건부 재개 | full candidate unknown. 이후 새 align 뷰 없음 |
| dev10 | r1 156.7 s NO_FIX; r1 첫 look는 실제 σ 초과, 두 번째155.6 s에서 조건부 재개 | r2는154.5 s부터 분기. 이후 원본을 새 동기화 경로로 붙이지 않음 |

M2 49회는 성공선정·이미 진단에 사용한 자료이고 dev03–10도 개발 자료다. 새 blind holdout이라 부르거나 서로 다른 cohort의 성공률 분모로 합치지 않는다. 기존 43,699 JPEG 전체 재생을 이번에 다시 수행한 것도 아니다. 이번 영상 검사는 dev154+blockage2+M2 align196=352회 읽기, **중복을 뺀 351 JPEG**다(dev10 blockage 프레임은 relook 구간에도 포함). 결과/목록/로그 등의 hash 검증은 별도다.

## 7. 권고 구현 범위와 검사

이번에는 아래 production 파일을 수정하지 않았다. 우선순위는 시각 결함 → 상대 보고와 안전 계산의 오프라인 구현/검토 → 별도 승인된 dev다. #240 병합 및 재검토 전 물리 실행을 준비 완료로 표시하지 않는다.

| 순서 / 예정 파일 | 변경 범위 | 핵심 테스트 |
|---|---|---|
| P1 `zone_pair_align.py`, `owncam_pose_source.py`, `zone_own_contract.py` | accepted-tag 시각 계약 통일, 실패 conjunct 진단 | dev09/10 실제 float clock, 양/음 반올림, 시작 전 태그·진짜 미래·stale 거부. σ 임계값 불변 |
| `zone_pair_beam_track.py`, 신규 `zone_pair_relative.py`, 필요시 beam detector adapter | resting/loaded 모드 구분, observable axes/bias/cov/anchor/PWM provenance | 전체/END_CLIPPED/BAND_CLIPPED/black/부분 가림/유사 물체/beam 이동/중복 JPEG, loaded에 ground-plane 재사용 금지 |
| 신규 `zone_pair_budget.py`, `zone_pair_geometry.py`, `zone_pair_guards.py` | 방향별 full covariance 또는 보수적 support-set, sigma cap 역산, bias/stop/lower 전체 tube | inside-wall 음수, 문설주 corner, full-beam 중앙, pan·curve·sample gap, XY-yaw 상관, 다봉, NaN, sigma cap 미적용, 증가 오차에 안전 여유 단조 감소 |
| `zone_pair_executor.py`, `zone_pair_grasp.py`, `zone_pair_status.py` | relative readiness+world certificate, 기존 enum barrier/고정 checkpoint | stale/duplicate/cross-segment/늦은 GO/peer silence, abort 후 양측 큐 0, support unknown 거부, 한쪽 loaded-pan 금지 |
| `zone_own_status.py`, `zone_own_perception.py` adapter | 해당 target 성분의 expected occupancy association | 이번 bbox 2개, 다른 장애물 동시 존재, target 오연결·가림 unknown; 모든 blockage off 금지 |
| 기존 `test_zone_pair_*`, `test_owncam_localizer.py`, `test_m1_owncam.py`, 신규 `test_zone_pair_relative.py`, `test_zone_pair_budget.py` | 위 회귀와 입력 경계 | 공통 SE(2) gauge 변화로 relative-only world 확신 증가 없음; GT/peer 접근 sentinel, dt10/25/50/100 ms 같은 명령 시간 적분 |
| 기존 `run_zone_pair_dev.py` / sim_cli workflow·bundle·prereg | 별도 기본 OFF profile, 실제 적용 계약과 로그 저장 | 소스/calibration/map hash 불일치 fail closed, baseline 불변; ID/seed는 main·열린 PR 재확인 후 예약 |

calibration은 낮은 팔/loaded/stop/partial 단계별 bias와 방향별 coverage를 episode·seed 단위로 분리해 확인한다. 오차 11–16σ의 알려진 과신을 충분히 포괄하지 못하면 global certificate를 발행하지 않는다. 새로운 이미지나 물리 입력이 필요한 데이터 수집은 별도 실행 과제다. 계수·허용 구간 길이를 M2 49회가 전부 통과하도록 조정하지 않는다. 기준 초안은 기존 loaded 문서의 coverage/단위/정지 예산·고정 8-run 비교안을 계승하되, **새 상대 모델이 확정될 때 별도 prereg로 다시 검토**한다. 이번에 물리 seed·bundle을 예약하거나 실행하지 않았다.

## 8. 검증·전달

[분석 JSON](dev09_10_diagnosis.json)에 프레임·선택 pan·검출·시각 재생·정적 상한·49회 목록·입력 hash를 저장했다. [검증 기록](beam_frame_validation.json)은 실제 pytest 결과와 원본 hash 재확인 범위를 담는다. [TensorBoard 영수증](beam_frame_tensorboard.json)의 새 3-run snapshot은 scalar/HParams를 파일에서 재로딩했으나 shared root 게시·GUI 검증은 제한으로 미완료다. [기존 대시보드](http://127.0.0.1:6006)의 현재 표시를 이번 결과라고 주장하지 않는다.

**설계 평가 완료. 채택 권고는 오프라인 구현·검토 단계에 한정한다.** 실제 파지/운반 성공, 보정된 uncertainty, 새 viewpoint, support/release 관측, 양측 동기화 완주 증거가 남아 있다.
