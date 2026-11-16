# 공동 운반 차분 진단 — 2026-09-27

**진단 결과:** 실패는 하나의 “너무 엄격한 σ” 문제가 아니다. 우선순위는 **서로 다른 pose를 쓰는 통합과 관측 공백 → 파지 전 빔 부착 가정 → 근접 부분 관측 계약 → 출발/입장 계약**이다. 안전 검사 자체를 없애는 근거는 없다. 최신 grasp v5는 dev07의 거부 조건을 실제 저장 입력에서 해소하고 dev08의 재관측 시점을 앞당긴다. 공동 파지·운반 완주는 미검증이다.

M2 성공 **49회 / 로봇 trace 98개**, 공통 실행기 실패 **dev03–08 6회**를 분석했다. M2의 **정확한 전체 반사실 중단시각은 `insufficient_evidence`**다. 연속 자기 PoseReport/yaw covariance와 변경된 look 경로의 RGB가 원본에 없다. 이 한계를 숨기지 않고 **저장 입력의 직접 판정**과 **RGB·발행 명령만 사용한 별도 PF 재구성(S)**을 나눴다. S의 98개 gate 거부를 실제 실패율로 읽으면 안 된다.

- 기계 판독: [results.json](results.json), [실행별 표](m2-runs.md).
- 직접 판정: [dev-main](dev-main.json), [grasp v4](dev-grasp-v4.json), [최신 grasp v5](dev-grasp-v5.json), [M2 영상 계약](m2-input-contracts.json).
- 조건부 PF 재구성: [m2-shadow-main.json](m2-shadow-main.json).
- 실행기 수정·물리 step·렌더·학습 모델/LLM 호출·커밋 **모두 0**. 원본은 읽기만 했다. GT는 마지막 사후 대조에만 사용했다. weld OFF, Google Drive 사용 없음.

## 기준과 코디네이터 결정

[이슈 #221 최신 결정 5856549507](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5856549507)을 GitHub 연결 도구로 직접 확인했다. 차분 재생으로 전환하고, 기준을 일괄 완화하지 않으며, 검토 후 v5 dev09/10을 병행한다는 결정이다. [원문 영수증](coordinator.json)을 보존했다. 이전 저장소 URL은 이동되었고, 쉘의 GitHub 네트워크도 차단되어 정식 변경 주소를 통해 읽었다.

| 역할 | 고정 SHA / 의미 |
|---|---|
| 작업 checkout·main 판정 코드 | `97f91cb040bf382973ce84b24b1ca8399e64a6fb`, `zone_pair_executor_v4_dev` |
| dev05/06 원본 | `4a17e7d47616056db85f35933327c6b63581853d` |
| grasp v4 / dev07/08 | 실행 `8effc2cee5c3534d553adb75a0d82b49097e5286`, 진단 포함 판정 `3790372dfdd8e9de894bad7414657461bc8ba91d`; executor **v5** |
| 최신 grasp v5 | `3839555dc0de0880f74a40c831044e2b5be2d2d7`; executor **v6**, STATUS v5. 작업 중 다른 세션이 갱신한 ref를 추가 확인 |
| 작업 중 최신 main | `ba0eb4f547996af880de65003442882c5326c71d`; 이 진단의 pair/guard/PF/M2 관련 코드가 기준 main과 동일함을 diff 확인 |

**grasp v4/v5와 executor v5/v6는 번호 체계가 다르다.** 위 SHA를 기준으로 읽는다. M2 stage1은 `3fdf011…`, stage2b 및 Kiro 완료분은 `ed15489…`, stage2c는 `ca44f66…`이다. 나머지 dev 성공은 각 결과의 source SHA로 분리했다. ON/OFF·test/dev·버전을 합쳐 성공률을 새로 계산하지 않는다. stage1 8/8과 stage2b 4/5는 기존 코호트 판정이며 이번 49회는 저장된 성공 실행 전체의 목록이다.

원본 루트는 `/Users/changmin/projects/ugrp/outputs/zone-m2-pair-20260926/`, `zone-m2-pair-kiro-20260926/`, `zone-pair-dev-v2-*`, `zone-pair-dev-v3-*`, `zone-pair-dev-v4-*`다. 완료된 `zone-pair-dev-v5-*` 결과는 점검 시 없었다. dev09/10을 완료로 세거나 기다리는 자동 작업을 만들지 않았다.

## 구조 차분표

코드 위치는 main 기준이며 최신 파일은 [grasp v5 소스](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/tree/3839555dc0de0880f74a40c831044e2b5be2d2d7/harness)를 가리킨다. 수치는 실행 코드에서 확인했다.

| 항목 | M2 러너 | 공통 main | grasp v4 → 최신 v5 |
|---|---|---|---|
| 전체 순서 | approach → approach 장벽 → align → hover/하강/close → RGB grip → lift 장벽·lift → carry 장벽·carry → lower·open. 문 중간에는 내려놓기·open·backoff·재정렬·재관측·재파지 | 먼저 look API·입장 검사·start 랑데부. 내부 M2DoorStudent **v3**를 GuardedPairApproach와 감싼다 | v4: align → shared PF relook → standoff anchor → 열린 채 하강 → close READY/GO → close. v5: **align 진입/도중 relook** 추가 |
| M2 원본 버전 | stage1은 PairApproach v1, stage2b는 approach v2/door v2, Kiro stage2c는 door v3. 단일 불변 baseline이 아님 | approach v2/door v3 고정 | 동일 M2 기본 모듈, 어댑터 mixin으로 확장 |
| 입장 | 별도 PairTeam 입장 gate 없음. 초기 불확실성은 접근 중 look로 해결 | mode m1·idle·미정지·빈 손·올바른 주문·완전 PWM, gate OK, report age ≤0.3 s, obs ≤0.3 s 및 valid_frame ≤0.25 s. 양쪽 제출은 5 s 이내 | 유지. dev03/04는 60 s 1회 제출, 거부 뒤 재시도 없음 |
| 정적 계획 | 열린 바닥과 문 작업 각각 존재. 문 마지막 beam x=3.20, y=.05 | pickup x∈[.7,1.2], y=.05±.15, yaw±10°, 문 (2.2,.05)/폭 .5만 지원. `make_plan`은 경로의 2 cm 표본마다 ±.625×±.20 m 팀 envelope 검사 | 유지. B구역까지 추가 leg·최대 .85 m 분할, 최대 8 segments. M2의 문 밖 3.2 m 도착과 동일 종점이 아님 |
| unloaded gate | 접근 look trigger: σxy>.05 m, σyaw>3°, 태그 공백>3 s. 즉시 동일 의미의 hard gate는 없음 | HIGH .08 m/.10 rad, LOW .05 m/.06 rad; entry dwell .6 s / exit .4 s | 유지 |
| loaded gate | align/파지/대기/운반에는 공통 전역 pose hard gate 없음 | approach/reapproach/wait_approach 밖은 **파지 전 align도 loaded gate**. HIGH .07 m/3°, LOW .06 m/2.5°. HIGH 초과는 즉시 중단; .6 s는 알림 dwell | 수치 유지. gate profile과 명령 기반 localizer load_state는 별개 |
| 접근 중단/복구 | approach 200 s, wait_approach 150 s. 도착 3 cm·yaw .06 rad + arrival look. unfixed look 3회, σxy>.15 m의 lost, v2 재초기화 최대 2회 | 동일 접근 정책 + guard/progress. 누적 재관측 대기 10 s, look backoff 최대1회(.08/.15 m 후보), 진행 복구 최대2회 | 유지. 잡힌 뒤 일방적인 backoff/look는 허용하지 않음 |
| 진행 부족 | M2 자체 단계 timeout·시각 hold 판정 | 신뢰 태그 age≤.3 s와 LOW에서 진행 기준을 설정. 명령 누적 .40 m, 실제 자기 추정 변화 .10 m 기준; 로딩 후 확인 필요면 `POSE_UNCERTAIN_PROGRESS`, stall이면 `PAIR_blocked` | 유지. 성공 로그만으로 이 보호를 없앨 근거 없음 |
| 위치 추정 연결 | open-floor는 pre-station 후 command feed 종료. 문은 grasp까지 feed하며, align 영상은 beam용; 일반 align에서 PF 태그 update를 계속하지 않음. 첫 grasp의 VO는 arrival pose+자기 beam 변위에서 별도 계산 | 모든 own frame·명령이 shared PF에 들어감. M2 VO는 grasp_estimate에만 저장되어 **guard/PF와 불일치** | v4부터 VO-only 우회 제거, 동일 shared PF 새 태그 fix 필수 |
| align | search→p45→inspect; 전환 거리 .34/.255 m. 두 번 연속 오차 x≤.012 m, y≤.008 m, yaw≤.035 rad이면 파지. align 제한60 s, posture switching 4회면 backoff | M2 정렬 정책 동일하나 매 제어/팔 단계 guard로 중단 가능 | v5는 진입 시 및 tag gap≥6 s / σxy≥.055 m / σyaw≥2.5°에 먼저 정지·재관측. 단계60 s 시계는 리셋하지 않음 |
| pregrasp fix | door v2/v3 첫 VO가 있으면 sweep 생략. sweep하면 σxy≤.06 m만 요구, 최대2회 | VO 우회가 유지됨 | v4/v5: σxy≤.05 m·yaw≤3°·fresh report·gate OK·**look 시작 이후 새 태그**. 최대2회 |
| 관측/제어 주기 | approach RGB .2 s, beam/hold look .4 s(실제 tick 때문에 .4~.5 s), controller .1 s, arm .05 s. 팔 시퀀스 중 RGB 공백 존재 | 공통 capture + 제어 직전 fresh frame 요구로 pair 활성 시 약 .1 s. frame age .25 s, report age .3 s | 유지. 더 자주 촬영해도 빔 쪽 시야에서 태그는 사라질 수 있음 |
| look 자세 | LOOK_P20={3:1072,4:2400,5:1482}, 기본 pan 1500/1230/970/1770/2030/1500(±48°). 문 v2 pan은 700/2300 포함 8개(±72°). 기존 카메라/FOV 유지 | 동일 자세; 전신 sweep 검사로 안전 pan 제한 | v5는 동일8개 pan의 중복 제거7개 후보를 정적 태그 투영면적+기존 guard로 정렬, 최대3방향. 실제 태그 수용 없이 성공 취급 금지 |
| 재관측 예산 | 기존 look 횟수·lost·단계 timeout | guarded sweep 누적10 s | v5 align relook: 작업8회, 회당8 s, 합계40 s, 회당3방향. 정지·팔 이동·복귀·대기 포함 |
| 명령 속도 | 접근 forward [-.05,.12], lateral±.08 m/s, turn±.10 rad/s, .15 s 명령. align fwd[-.05,.08], lateral±.06, turn±.10, .2/.3 s 펄스(최소 floor .035) | 동일 M2 명령 생성. guard가 통과한 명령만 발행 | 새 relook 외 정렬/운반 속도 변경 없음 |
| 운반/안정화 | 목표 .06 m/s, gain fwd=2.2/1.4·lateral=1.65/1.4, carry scale .772/.697. 문 축 보정6 s+정지.5 s, 보정 clamp .15 m/.20 rad | 원본 스케줄 재사용. grasp estimate 없으면 원본의 보정 생략 대신 중단. 새 B행 leg는 동일 보정/속도로 분할 | 동일. v5로 align이 개선돼도 loaded gate·장기 blind carry의 양립은 별도 검증 필요 |
| 팔 궤적 | 공통 ArmSequence smoothstep, .05 s 발행. hover1 s+기본 settle .1 s, 하강7×.12 s/settle0, close .5+.4 s, lift1.2+.3 s, lower1.2+.4 s | 동일 sequence. PWM당 full transition 검사, 막힌 재관측은 queue 시각을 지연시켜 burst 방지 | v4는 descent와 close를 분리하고 READY/GO 후 close. relook 팔 .8+.6 s, pan .4+.6 s |
| 형상·margin | A* 정적 beam keepout+격자오차 .06 m, peer 주문서 station/prestation±.17 m. 근접 각 PWM에 full-beam sweep 없음 | margin=.020+.015+2min(σxy,.15)+2min(σyaw,.20)×lever. 전체600×40×32 mm 빔을 **grasp state부터 손목 부착** 가정 | v4/v5는 자기 RGB grasp receipt 이후만 부착. 미파지 빔은 own RGB의 stationary geometry로 별도 검사 |
| preclose 물체 관측 | 근접 grip_view는 주로 close 후; dark≥.40, top 또는 bottom beam≥.04. lift co-motion 확인은 별개 | M2 검사+valid_frame. 검은/무변화 영상 fail-closed | full standoff anchor, segment 일치, age≤30 s, σ≤.05 m/3°, camera PWM 동일, fresh frame, partial 점수≥.95, full beam 여유≥0. v4 BAND_CLIPPED만 → v5 END_CLIPPED/end_visible=false도 부분 패치로 허용. 위치/age/σ reset 금지 |
| 동기화 | PairCarrySync own frame 장벽, TTL1 s. lift20 s(재정렬 후60 s), carry15 s, lower20 s, open15 s. 상태 채널 ON/OFF는 별도 실험 | STATUS enum만 교환, heartbeat .05 s/timeout .15 s, readiness TTL .6 s, GO .1 s 격자, 누락 GO/partner abort 시 정지 | v4/v5 close 장벽20 s 추가. 양쪽 open 상태 READY 후 함께 close; 좌표·σ·영상 공유 없음 |
| 장면/spawn/contact | TaggedCargoZoneScene, tags_v2, 벽높이 .10 m, 문폭 .50 m. 기본 spawn x=-.85+seed offset·yaw offset; 문은 depot assignment. r3 유휴 | dev03/04는 old dock. dev05–08은 tags_v2_dock_v3, x=-.65, yaw0, seed별 y row, 정적 spawn keepout 연결 | v5 장면 유지. 모두 cargo_noslip_v1/noslip10/0.00025 s/implicitfast/weld OFF. 이번 원인에 contact 프로필 변경 근거 없음 |

주요 소스: [M2](../../scripts/run_m2_pair.py), [원본 manipulation](../../scripts/study_owncam_pair_beam.py), [approach](../../harness/pair_owncam_approach.py), [공통 어댑터](../../harness/zone_pair_executor.py), [gate·margin](../../harness/zone_own_guards.py), [pair guard](../../harness/zone_pair_guards.py), [입장](../../harness/zone_pair_admission.py), [공통 pose](../../harness/owncam_pose_source.py).

## 오프라인 재생 방법과 한계

1. **직접 재생:** dev `robots.json` 자기 report/PWM, `inputs/<rid>`의 실제 JPEG, own events·명령으로 `readiness_snapshot`, `UncertaintyGate`, `PairCommandGuard.before_control/check`, `PairSweepGuard`, `RestingBeamTrack`, 최신 `relook_reason/ranked_look_pans`를 호출했다. 보고 σ는 소수5자리이므로 PF 내부 full precision 재현이라고 하지 않는다. 입장 시점과 같은 시간의 **입장 후** 새 capture는 제외했고, 미래 프레임을 끌어오지 않았다.
2. **M2 그대로 재사용 가능한 입력 검사:** `make_plan`과 실제 `valid_frame`·`_same_camera_commands`를 호출했다. 원본이 새 카메라 자세의 영상을 저장하지 않은 시점에는 이전/미래 영상을 대용하지 않았다. 성공49회, 닫힘 시작206건 모두 last RGB age **1.99025–3.13945 s**, camera PWM 불일치였다. 따라서 문자 그대로의 로그 재사용은 v4/v5 preclose 필요조건을 통과하지 못한다. **실제 공통 러너가 새 촬영하면 달라지므로 206건의 물리 실패를 뜻하지 않는다.**
3. **M2 별도 PF 재구성(S):** 원본 자기 JPEG·시간·발행 명령·원래 seed와 해시로 고정한 map/calibration만 `OwnCamPoseSource`에 넣었다. 43,699개 사용 JPEG의 SHA를 확인했다. 연속 PF feed·저장 프레임/명령 시계이며 원래 M2의 feed 중단·PF reset·세부 predict 호출격자를 복원한 것은 아니다. 원본 align 추정 로그가 들어 있는 `localizer-eval.jsonl`은 제어 입력으로 읽지 않았다. 각 로봇 최초 gate 거부와 최초 현재 형상 음수 여유를 독립적으로 기록하며, 둘 다 확보하면 해당 prefix 분석을 끝낸다.
4. **원본 이후 경로는 식별 불가:** 거부 후 원래 trace를 계속 읽은 값은 별도 조건부 진단이다. 바뀐 look→새 RGB→다른 PF→다른 명령을 재현하지 않는다. C는 현재 형상 필요조건이며 pending PWM/10 s 복구/실제 abort 전체를 뜻하지 않는다. M2 입장 API가 없으므로 임의60 s로 입장 실패를 만들어 세지 않았다. `first_admissible_shadow_frame`은 자기 입력 필요조건만 평가하며 양쪽 동시 입장 판정이 아니다.

### M2 성공 실행의 판정

전체49회는 [m2-runs.md](m2-runs.md)에 로봇별 시점·단계로 제시했다. static plan은28회 통과,21회 `PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE`다. 여기에는 stage1 test16회 전부가 포함된다. 이는 성공 동작의 안전 실패가 아니라 공통 API의 **지원 작업 범위 차이**다.

S에서는 98/98 로봇 trace에 yaw 3° 초과로 manipulation gate 거부가 있었다(carry63, wait_carry19, wait_lift10, lift6). geometry 필요조건 음수는96/98개(approach93, carry3)였다. **동일한 최초 전과정 abort가 98개였다는 뜻이 아니다.**

| 예시 | r1 S gate | r2 S gate | 해석 |
|---|---|---|---|
| stage1 s711-on | 82.471 s carry, σyaw .05349 | 79.865 s lift, σyaw .05435 | 실제 열린 바닥 성공을 새 loaded gate는 조건부로 거부; static admission은 이미 범위 밖 |
| stage2b s821-on | 141.518 s carry, σyaw .05248 | 136.606 s wait_lift, σyaw .05266 | 둘 다 3°=.05235988 rad 초과; M2 해당 phase에는 이 중단 검사가 없음 |
| Kiro stage2b s826-on | 150.641 s carry | 147.634 s lift | 완료분도 동일 계열. 별도 seed이며 성공률에 중복 합산하지 않음 |
| Kiro stage2c s831-on | 136.105 s wait_carry | 138.912 s carry | door v3에도 추가 loaded gate와 no-tag 명령 예측의 양립 문제 가능 |

### 공통 dev 실패를 M2 기준으로 보면

| 실행 | 직접 재현된 공통 최초 원인 | 같은 입력의 M2 판정 | 최신 grasp v5 재판정 |
|---|---|---|---|
| dev03 | 60 s r1 SELF_UNCERTAIN. σxy .05033, gate 초기 LOW 미충족. r2는 수락 후65 s timeout | 이 입장 gate가 없어 동일 이유로 거부하지 않음. 앞선 look의 guard 실패도 M2에는 없음. M2 approach 성공 여부는 미정 | 입장 조건 동일; 해결됐다고 하지 않음 |
| dev04 | 60 s r2 SELF_UNCERTAIN, σxy .95959. r1 수락 후65 s timeout | M2는 불확실 접근에서 look/lost 경로로 갈 수 있음. unsafe pose를 수락해도 성공이라는 뜻 아님 | 입장 조건 동일 |
| dev05 | r1 190.429 s grasp: PAIR_COLLISION_GUARD. 원본 발행 팔 명령65개와 복원 prefix 완전 일치, 다음 servo3=687에서 거부 | M2 ArmSequence는 같은 다음 batch를 발행한다. 당시 아직 hover 중이므로 grip_view=false를 조기 실패로 적용하면 안 됨 | 부착 가정을 제거한 v4/v5 guard에 같은 batch를 넣으면 통과. 전체 v5 phase 재실행 아님 |
| dev06 | r2 193.7 s wait_lift: σxy .05753, σyaw .05238 >3°. HIGH 알림 dwell 이전의 즉시 gate | 같은 JPEG `grip_view_m2=true`; M2에는 이 pose stop이 없어 장벽 대기를 계속하는 경로. 상대 준비·lift 후 성공은 미정 | 옛 trace의 σ 조건 자체는 그대로 거부. align 중 재관측은 r2 169.2 s에 요청하게 됨 |
| dev07 | r1 202.8 s wait_close: fresh anchor/σ는 적합, END_CLIPPED를 v4 track이 거부. grip_view=true | M2에는 preclose track 계약 없음. 같은 영상의 grip 검사 자체는 통과하지만 아직 열린 손이므로 실제 파지 증거로 쓰지 않음 | **preclose=true**, partial support1.0, beam clearance **+.680877 m**. r2의 미래202.9 s RGB를 가져와 양쪽 READY를 선언하지 않음 |
| dev08 | r2 175.6 s align: σxy .07004>.07, yaw1.512°·load_state=unloaded | 같은 full-band beam 입력에 M2 align_command는 fwd .035/left .035/turn0, duration .2 s. 새로운 전역 gate가 멈춘 것 | 옛 trace에서는 **166.3 s/tag gap6 s**에 hold/relook 요청(9.3 s 선행), 안전 정적 pan후보7개. 새 관측 성공은 미정 |

최신 v5는 align 진입(dev05 153.1, dev06 154.6, dev07 154.8, dev08 152.2 s)에 이미 새 look를 시작하므로, 위 “도중 trigger” 시점은 **그 진입 look가 없었던 옛 trace에 대한 독립 판정**이다. 실제 v5 도중 trigger 시각을 예측한 값이 아니다.

## 영향 순 분류와 한 번에 적용할 권고

“안전상 필요”는 기능의 필요성을 뜻한다. 과거 성공이 운이 좋았다고 통계적으로 입증한 것은 아니다. 임계값의 과도함/최적성은 실패 로그와 성공 선택 표본만으로 결정할 수 없다.

| 순위 | 차이·분류 | 근거와 권고 |
|---|---|---|
| P1-1 | **통합 버그/계약 불일치:** M2 VO·beam 제어와 guard shared PF 분리, align 중 관측 공백에 대한 복구가 늦음 | dev05/06/08의 같은 자기 보고가 원인을 재현. 사후 XY 오류 r1/r2는 .759/.887, .703/.949, .683/.760 m. 작은 σ만으로 정확도 보증 불가. v5의 align 전/중 shared PF relook를 일괄 포함 |
| P1-2 | **과잉/버그:** 미파지 빔을 손목에 붙인 full-beam 형상 | dev05 동일65개 명령 이후 main 거부/v4·v5 통과. 부착은 RGB grasp receipt 이후로 제한하되 미파지 빔의 own-RGB stationary clearance는 유지 |
| P1-3 | **과잉/관측 계약 누락:** END_CLIPPED를 무조건 거부 | dev07 동일 JPEG·anchor·전파σ에서 v4 false→v5 true. 최신 v5의 partial 패치 경로를 포함. 임의 end fit/PCA로 anchor 위치·나이·σ를 새로 확정하면 안 됨 |
| P1-4 | **안전상 필요 + 수치 근거 미완:** pose HIGH·sweep margin·fresh-frame interlock | dev06/08은 실제 부등식 초과. 성공49회도 shadow loaded gate와 충돌하므로 연속 PF·phase·noise 계약을 검증해야 함. 7 cm/3°/35 mm 일괄 완화나 dwell을 유예로 쓰는 수정은 권고하지 않음 |
| P1-5 | **구성 버그 + 안전상 필요한 입장 검사:** dock와 보수적 envelope 불일치, 고정60 s 단발 admission | old dock x=-.85에서 차체 뒤끝-벽 여유25 mm <기본35 mm. σ=0이어도 부족. x=-.65의 정적 map/scene 계약을 함께 유지. 새 admission은 시각 경과보다 자기 준비 상태를 사용하고 시도/전체시간은 유한하게 제한하는 설계를 권고. dev03만 시각을 늦추는 처방은 dev04를 해결하지 않음 |
| P2-1 | **안전상 필요:** 양쪽 fresh READY/GO, silent/abort/cancel, 잡힌 뒤 일방 recovery 금지 | M2 성공군은 정상 통신·계획된 동작에 선택된 표본. 이 guard를 제거해도 된다는 반례가 아님. 두 손이 잡은 상태의 미래 sweep은 GT 순간 여유만으로 안전 승인 불가 |
| P2-2 | **지원 범위 차이:** 열린 바닥 admission, 추가 B목적지, 관측률·버전 | stage1 차단은 버그로 완화할 항목이 아님. 다음 비교는 같은 scene·spawn·종점·버전·contact·입력률로 맞춘 한 쌍의 계약 필요 |

**권고 묶음:** 최신 grasp v5의 **공통 pose 능동 재관측 + 단계에 맞는 부착 형상 + full-anchor 기반 근접 partial 검사 + 양쪽 close READY/GO + 이미 고친 dock**를 하나의 세트로 유지한다. 이번에 새 실행기 구현은 하지 않았다. 해당 세트의 구현은 이미 별도 PR #240에 있으므로 중복 구현하지 않는다.

다음 후보에는 **loaded 단계 관측/불확실성 예산**도 명시해야 한다. v5는 주로 파지 전을 바꾸므로, 태그 없는 wait_lift/carry의 σ 증가는 남는다. 닫힘·높이 명령으로 loaded를 선택하는 PF와 정지에도 누적되는 process noise, 낮춘 팔의 운동 모델, 각 carry segment·장벽 대기시간을 함께 검토한다. 보정 자료 없이 noise를 줄이거나 σ를 reset하지 않는다. 잡은 뒤에는 일방 pan 대신 양쪽 상태 장벽과 기존 내려놓기/재관측 checkpoint 정책 안에서 해결해야 한다.

예상 효과는 dev05의 잘못된 부착 검사 제거, dev07의 유효한 부분 관측 수용, dev08의 오래된 PF에 대한 조기 대응이다. **위험:** relook이 align60 s·close20 s 예산을 소모함, 정적 태그 가시성 순위가 실제 가림/잘못된 pose 때문에 틀릴 수 있음, near-field partial의 다른 물체 오탐, loaded blind 구간의 후속 abort. 성공률 향상 폭은 이 재생으로 산출할 수 없다.

## 사후 평가 대조와 기록 보존

판정 계산이 끝난 뒤에만 `eval_only/trace.jsonl`과 SHA를 대조했다. dev07 중단 직전 XY 오차는 r1/r2 **9.25/9.11 mm**, dev05/06/08은 위 표처럼 약0.68–0.95 m다. dev06 r2의 손가락 힘은 약5.48/5.49 N, r1은0/0 N이며 다른 세 실행의 중단시 양쪽은0이다. **전역 pose가 개선돼도 부분 관측 계약에서 별도로 막힐 수 있고, 한 손의 파지가 공동 운반 성공은 아님**을 보여준다. 이 값은 제어·gate 선택·보정값으로 돌려보내지 않았다.

사용한 dev 로그7종/회차와 선택 JPEG, M2 결과·입력목록·이벤트·명령 해시를 확인했다. M2 shadow에서 사용한43,699개 JPEG와 direct close 검사 영상도 원본 SHA 일치. 영상 전부·모든 raw artifact를 이번에 다시 해시하거나 overview 전체를 새 승인한 것은 아니다. 결과 JSON은 로컬 원본 경로·해시·판정 시각·프레임 ID를 담는다. 로컬 보존을 원격 백업이라 하지 않는다.

## 재현·검증·TensorBoard

기존 Mac 환경을 재사용한다. 새 환경·서버·실험 프로세스는 시작하지 않는다. Python import 단계에서 `mujoco`, `torch`, `tensorflow`를 차단하며 모델 로드도 하지 않는다. OpenCV 태그 기하/PF/정적 FK 계산만 수행한다.

```sh
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_DIR=experiments/2026-09-27-zone-pair-parity
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
"$PAIR_PY" "$PAIR_DIR/replay.py" --mode dev --output "$PAIR_DIR/dev-main.json"
"$PAIR_PY" "$PAIR_DIR/replay.py" --mode dev --ref 3790372dfdd8e9de894bad7414657461bc8ba91d --output "$PAIR_DIR/dev-grasp-v4.json"
"$PAIR_PY" "$PAIR_DIR/replay.py" --mode dev --ref 3839555dc0de0880f74a40c831044e2b5be2d2d7 --output "$PAIR_DIR/dev-grasp-v5.json"
"$PAIR_PY" "$PAIR_DIR/replay.py" --mode m2 --shadow --output "$PAIR_DIR/m2-shadow-main.json"
"$PAIR_PY" "$PAIR_DIR/trace_contracts.py" --output "$PAIR_DIR/m2-input-contracts.json"
"$PAIR_PY" "$PAIR_DIR/verify_latest.py"
"$PAIR_PY" "$PAIR_DIR/tensorboard_snapshot.py"
"$PAIR_PY" "$PAIR_DIR/summarize.py"
```

분석 스크립트 출력은 자기 실험 폴더 또는 임시 디렉터리에만 저장한다. 재실행 시 기존 분석 JSON은 새 결과로 대체하므로 보존이 필요하면 새 출력명을 쓴다. 실제 frozen runner 파일은 git show/import overlay로만 읽는다.

- 기존 main 관련 회귀 **37 passed** (`test_zone_pair_admission`, `review6`, `review7`).
- 최신 v5 판정·저장 영상·동기화 관련 회귀 **28 passed / 9 deselected**. 처음 전체파일 실행에서는 v5 CLI 사전등록 테스트9개가 main CLI의 `PREREG_V5` 부재로 실패했다. 실행기 checkout을 바꾸지 않는 이번 overlay 범위에서 CLI 사전등록9개를 명시적으로 제외했다. **전체 v5 CI 통과 주장이 아니다.** 테스트 helper도 해당 branch blob으로 읽었고 fixture root만 기존 원본 위치에 연결했다.
- 분석 검증 **6 passed**. 합계 **71개 관련 검사**이며 물리/모델 검증과 구분한다. 모든 pytest는 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`, bytecode/cache OFF로 실행하고 임시 폴더를 지웠다.
- Native TensorBoard **새 임시 snapshot 5개 run 변환 및 EventAccumulator scalar/HParams 실제 로딩 확인**. 위치·해시는 [tensorboard.json](tensorboard.json). offline 수치만 표시하며 새 물리 성공/영상으로 만들지 않았다.
- **공유 게시·GUI 검증은 미완료.** primary `outputs/tensorboard`는 쓰기 허용 범위 밖이고 Chrome/IAB가 사용할 수 없었다. 기존 viewer·pin·HParams 열·snapshot은 변경하지 않았다. [기존 TensorBoard](http://127.0.0.1:6006)에 이번 결과가 표시된다는 주장은 하지 않는다. 임시 snapshot을 허용된 세션에서 공유 root에 게시하고 비교 run/핀/열을 확인하는 작업이 남는다.
- `git fetch`는 공유 FETCH_HEAD 쓰기 제한으로 실패했다. 대신 정식 저장소의 최신 이슈·열린 PR을 연결 도구로 조회했다. 커밋·push·PR 게시/댓글·병합·primary 갱신 없음. `harness/`, `scripts/`, `tests/`와 기존 실험 파일은 수정하지 않았다.
