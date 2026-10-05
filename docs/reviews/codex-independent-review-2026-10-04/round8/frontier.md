> **후속 정정:** 아래는 05:55 UTC 스냅샷입니다. 이후 #371 `a009112f`에서 own_status와 prompt slot 문제가 해소된 것을 [전달 직전 수정 검증](frontier-followup.md)에서 확인했습니다. 아래 §5의 own_status 미해결 판정은 `1883c56`에 한정합니다.

# 8차 — 현재 개발 경계와 #363 변경분 독립 검토

기준 시각 **2026-10-04 05:55:22 UTC / 14:55:22 KST**. 공식 GitHub API에서 종료 직전 다시 확인한 head는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #363 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`, #371 `1883c56a749dc89597d57f570d4a2243cbb9595d`이다. 확인 이후 변경에는 이 판정을 자동 적용하지 않는다.

**가장 중요한 갱신은 막힌 위치가 바뀌었다는 점이다.** 이전 원고의 바닥 자세 `BEAM_UNCERTAIN`는 현재 구현에 추가된 호버 확인과 제한된 개루프 하강으로 우회되었고, 공개 DEV 보고는 두 로봇의 HIGH 도달을 기록한다. 다음은 HIGH 운반 기준 영상의 경계 맞춤 실패다. 처음부터 시작하는 접근의 guard 문제는 여전히 별개다. 또 최신 시작 상태 완화 수정은 과거 r2의 첫 접근 명령 자체를 이제 거부하므로, 과거 9.0초 실패를 현 head에서 재현한 결과로 부르면 안 된다.

이 메모의 새 기여는 변경분 검토, 수정의 독립 재현, 아직 남은 경계의 최신 소스 재확인, 다음 진단의 우선순위다. 이전 발견을 신규 결함 수에 합산하지 않는다. 구현 수정·실제 로봇·물리·렌더·LLM·학습 실행 및 raw/비공개 held-out outcome 열람은 없었다. 공개 작성자 보고와 이번 합성 재현을 구분한다.

## 1. 비교 범위

PR #375의 동결 원고가 다룬 #363 `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6` 이후를 읽었다. 코드 변경은 8파일, 966추가/6삭제다. 주요 변경과 판단은 다음과 같다.

| 변경 | 현재 의미 | 검토 결과 |
|---|---|---|
| `ace8b257`: `zone_pair_highpose_blind_close.py` | 호버에서 기존 preclose + 가로 정렬 검사를 서로 다른 연속 2프레임으로 통과한 후 고정 7단계 하강 | 자기 RGB·측정 카메라 보정·자기 발행 명령을 사용한다. 저자의 HIGH 도달은 단계 성공이며 배달 성공이 아니다 |
| `0865a788`: `guardlog`, `start_relief` | 기존 guard 거부를 상세 기록하고 이미 여유 안쪽인 시작 상태의 제한적 탈출 허용 | 기록·판정 분리는 코드에서 확인. 그룹 바닥값은 점별 비악화보다 약하다는 기존 한계 유지 |
| `d41465a2`: `enters` | 시작 시 상자 밖이던 점/구가 새로 들어가는 것을 표본마다 거부 | 실제 현재 함수와 공개 테스트 스칼라로 수정 효과를 독립 재현 |
| `d5ca2ec3`: `align_to_carry`, `PARKED` | 같은 정렬 진입 뒤 carry/release까지 계속 관찰; 입장 불가능했던 HIGH 정적 준비 두 개는 보류 | 무리하게 준비 정답을 더하는 대신 도달한 상태부터 계속하는 진단 경로. E2E 일반화 주장은 불가 |
| `0d7c5eb3` | blind 중단 경로 시험과 문구 보강 | 거리 제한은 실제 이동계가 아니라 고정 자세표의 설정 검사라는 한계를 명시 |
| `scripts/run_pair_highpose.py` | terminal state 조건·v98 실패 분류 | 원래 고정 실패표를 바꾸지 않고 v98 보고층에서 확장. 분류 이름은 원인 입증이 아니다 |

`configs/ci_test_durations.json`과 CI 목록 변경도 확인했다. source snapshot 1,723개는 필요한 import 의존성을 확보하기 위한 코드/구성 사본 수이며, 1,723파일을 모두 심층 정독했다는 뜻이 아니다. 기존 checkout의 HEAD/작업 파일은 바꾸지 않았으며 read-only fetch로 검토 ref만 확보했다.

## 2. 수정 확인: 최신 r2 접근은 과거 8.7초 명령부터 달라진다

정확한 소스: [start_relief@0d7c5eb3](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/zone_pair_highpose_start_relief.py), [공개 회귀 입력](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/tests/test_highpose_guard_veto_log.py), [수정 회귀 검사](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/tests/test_highpose_start_relief.py).

`StartReliefGeometry.motion_clear`는 동결 guard가 거부한 뒤에만 완화를 계산한다. 최신 `enters(start_pair, pair)`는 `start.signed >= 0`이고 현재 표본의 `signed < 0`이면 거부한다. 이 검사는 그룹 최악 clearance 바닥값과 별개다. 이전 검토 5차가 발견한, clamp가 상자 안 깊이를 구별하지 못하는 허용 사례를 직접 막는다.

이번 `frontier-start-relief-repro.py` (Mac 전달본 증거)는 원문 AST의 geometry 함수/클래스 body를 수정 없이 실행했다. 다른 런타임의 CV/물리 import를 피하기 위해 필요한 정의만 적재했으며, 사용한 좌표·PWM·명령은 이미 공개된 테스트의 스칼라다. 영상·raw replay를 수행하지 않았다.

| 같은 공개 guard 입력 | 원래 guard | 최신 완화 | `enters`만 끈 돌연변이 대조 |
|---|---:|---:|---:|
| r1 8.7초 첫 명령 | 거부 | 허용 | 이번 표의 대조 대상 아님 |
| r2 8.7초 첫 명령 | 거부 | **거부** | 허용 |

r2는 `chassis/0/wall_west`, sample 2에서 `start_outside_pair_enters`: 시작 signed **+9.642188 mm**, 표본 signed **−9.395921 mm**다. 더 엄격한 `scope='pair'` 대조도 거부했다. 실행 후 residual·loaded flag 복원과 내부 예외 없음도 확인했다. `frontier-start-relief-result.json` (Mac 전달본 증거).

따라서 [0865 공개 실행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5976434592)의 “8.7초 진입 성공 → 9.0초 `inside_pair_deeper`”는 역사적 결과다. 현재 head에서 같은 8.7초 guard 입력을 주면 그때 이미 거부된다. 현재 E2E가 반드시 정확히 8.7초에 실패한다는 뜻은 아니다. 앞선 상태·관측·입력이 같을 때의 국소 판정만 검증했다.

이 수정이 위치 추정 과신을 고친 것은 아니다. 공개 보고의 44–48 mm 위치 오차와 2.6 mm 내외 표준편차, NEES 값은 저자의 사후 평가로만 인용한다. 이번 검토가 GT를 제어에 넣거나 그 raw를 확인한 것은 아니다. 다음 구별은 “코드 수정 후 guard의 결정이 달라졌는가”와 “자기 관측 추정의 평균/분산이 왜 불일치하는가”다. 이미 전자는 재현됐으므로 guard 문턱을 다시 낮추기 전에 후자의 관측·갱신 경로를 분리하는 편이 정보량이 크다.

## 3. 새 blind 단계가 실제로 보장하는 범위

[blind_close@0d7c5eb3](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/zone_pair_highpose_blind_close.py)의 흐름을 읽었다.

1. 고정 호버 자세를 발행하고 기존 안정화 시간을 기다린다.
2. 기존 `preclose_check`가 자기 pose 신선도·불확실성·frame·같은 카메라 명령·빔 가설·정적 벽 여유를 확인한다. `station_lateral_m`의 가로 중심 허용치는 3 mm다.
3. 서로 다른 연속 2프레임이 통과해야 하강을 큐에 넣는다. 실패 프레임은 streak를 0으로 만든다. 같은 frame id를 두 번 세지 않는다.
4. 고정 7단계 하강 뒤 정확한 잡기 PWM 자세에서만 blind fallback을 허용한다. 시간은 확인 프레임 시각부터 최대 22.14초, 원래 anchor 나이는 30초 이내, 추적 sigma 제한도 유지한다.
5. 차체 이동·pan 변화·팔 명령 포락선 이탈·완전 재열기·알 수 없는 명령·segment 변경은 기억을 무효화하거나 거부한다. hold는 물체가 실제로 고정되었다는 증거가 아니다.

**남은 물리 가정은 이미 공개된 한계다.** 자기가 멈춰 있어도 동료가 물체를 움직일 수 있으며 그 동안 자기 카메라에서 빔이 안 보인다. 22.14초는 실행 시간표에서 얻은 상한이지 물체 정지의 실험적 보증이 아니다. 공개 [ace8b257 단계 보고](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5971862111)에서 r1이 닫기까지 11.4초를 기다렸다는 값은 이 가정이 필요한 실제 구간을 보여준다. 알려진 한계를 신규 버그로 세거나, 로그 전용 grip monitor를 지금 당장 필수 제어 센서로 바꾸라고 요구하지 않는다.

포락선은 각 관절의 최솟값/최댓값 검사다. 그래서 소스 설명의 “고정 경로”는 controller가 고정 큐를 발행한다는 조건과 함께 해석해야 하며, 이 검사만으로 모든 관절의 동시 궤적이 고정 경로와 같음을 증명하지는 않는다. 현재 정상 발행 경로가 그 가정을 어기는 반례는 이번 범위에서 입증하지 못했으므로 결함으로 승격하지 않았다. 거리 항 `drop_m/xy_m`도 실제 이동 추정값이 아니라 호버와 잡기 고정 자세의 차이다. 이 점은 최신 문서/시험에서 이미 바로잡혔다.

## 4. 현재 운반 blocker와 다음 진단

[2026-10-04 04:34:44 UTC 공개 보고](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5976609395)는 `d5ca2ec3`의 `align_to_carry`에서 닫기 64.7초, lift 65.9초, HIGH 84.8초 후 99.9초에 `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT`이라고 기록한다. 배달하지 못했고 운반 이동도 시작하지 않았다. 이는 작성자 관찰이며 이번에 raw 604프레임을 다시 읽은 결과가 아니다.

현재 [HighController._wait_carry](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/zone_pair_highpose_runtime.py)는 `provider.beam_edge.available(now)`가 참이 될 때까지 기다리고 제한 시간을 넘으면 위 사유로 실패한다. 소스 경로가 공개 보고와 맞는다. 작성자는 `own_beam_edge.edge_line`의 전역 OLS 초깃값이 오른쪽 끝 소수 이상치 때문에 기울어지고, 잔차 4 px로 잘라낸 뒤 지지 열이 부족해지는 것을 진단했다. 이것은 이미 알려진 원인이므로 새 발견으로 포장하지 않는다. 이번 8차 기하 검토가 독립 합성과 더 넓은 입력 경계를 별도 문서에 제공한다.

우선순위는 다음처럼 나눌 수 있다.

| 진단 | 구별할 질문 | 최소 출력/음성 대조 | 해석 경계 |
|---|---|---|---|
| HIGH edge 후보 생성 | 실제 빔 경계가 충분해도 OLS 초기화가 버리는가 | 원본 열 좌표·유효 열 수·초기/최종 잔차·강건 합의 열; 이상치 없는 대조 | 알고리즘 수용성 확인이며 물리 운반 성공 아님 |
| ROI 경계 | 검출된 아래 경계가 물체 경계인가, crop 바닥인가 | 원본 mask의 ROI 경계 접촉 여부·crop 밖 연장 여부·유효 column span | 가짜 수평선이 기준을 오염시키면 OLS를 RANSAC으로 바꾸는 것만으로 해결되지 않음; 8차 기하 메모 참조 |
| HIGH slope→yaw | 낮은 자세에서 얻은 감도가 HIGH에서도 같은가 | 고정 HIGH 카메라 모델의 투영 Jacobian/부호·단위·작은 yaw 변동 합성 | edge_line 수용성과 yaw 보정의 정확성은 다른 계약 |
| PF 과신 | 잘못된 평균을 지지한 측정인가, 중복/상관 증거를 독립으로 센 것인가 | frame id·사용 열·accepted update·innovation·resampling 순서·평가 전용 일관성 지표 | held-out 자료를 보정에 재사용하지 않고 DEV와 분리 |
| blind 대기 | 허용된 기억의 나이와 동료 행동이 어떤 구간에서 겹치는가 | 확인 frame→하강→barrier→닫기 시각, 자기 명령, 허용된 enum 메시지 시각 | 성공했다고 보지 않은 구간의 모든 미래 조건을 보증하지 않음 |

표의 항목은 새 실제 실험을 실행했다는 보고가 아니라 다음 선택을 돕는 판별 기준이다. 실제 수정 전 표준 방법/논문 근거는 이번 별도 연구 메모와 연결하고, 공유 동결 모듈의 수정은 버전과 이전 증거 보존 계약을 먼저 지켜야 한다.

## 5. 기존 두 소프트웨어 경계는 최신 소스에서도 남는다

### 같은 tick의 상대 중단 후 이미 모은 명령

최신 #363의 `Runtime.step`은 로봇 순서대로 `issued`에 명령을 쌓고 마지막 `team.poll` 후 그대로 반환한다. HIGH runtime이 이 메서드를 상속한다. 뒤 로봇의 실패로 앞 로봇까지 terminal이 되어도 이미 모은 배치가 제거되지 않는다.

`frontier-peer-abort-dispatch-repro.py` (Mac 전달본 증거)은 최신 snapshot의 Runtime/OwnExecutor/PairExecution/PairTeam 원문 AST와 실제 command-only port를 사용했다. 제어기·관측·geometry·robot 출력 sink는 명시적인 fake다. 양쪽 terminal이 된 뒤 r1에 `[0.1,0.1,0.1,0.1]` 모터 setpoint가 dispatch되고, 다음 0.05초 tick의 hold에서 0으로 바뀌었다. `frontier-peer-abort-result.json` (Mac 전달본 증거). 물리 이동 거리·충돌·0.15초 전체 lease 지속을 주장하지 않는다. **기존 finding의 현재성 확인이며 신규 건수가 아니다.** 해결 확인 기준도 현재 tick의 peer revocation 뒤 stale 배치가 dispatch되지 않는지다.

### own_status의 두 시간축

#371 head는 7차와 같다. Git blob에서 dispatch/runtime/status 파일을 새로 확보해 동일 fake endpoint schedule을 다시 실행했다. 7차 connector 사본에 파일 끝 LF가 하나 더 있어 바이트 해시는 달랐지만 AST는 모두 같았다. 이번에는 Git blob 정확본으로 재현했고 공유 helper 3파일은 기존 local base와 바이트가 같음을 확인했다. `frontier-own-status-source-check.json` (Mac 전달본 증거).

동일 상대 history에서 permit 10.0초, look 종료 전달 10.5초일 때 origin=0은 `look_around_ended`, origin=1.3은 **`claim_released`**다. gate의 absolute timestamp와 종료 event의 reset-relative timestamp를 직접 비교하기 때문이다. gate 값을 같은 상대 시간축으로 맞춘 대조는 모두 `look_around_ended`다. `frontier-own-status-repro.py` (Mac 전달본 증거), `frontier-own-status-result.json` (Mac 전달본 증거).

이는 실제 모델 응답/실제 look 길이를 실행한 증거가 아니다. 현재 API가 허용하는 fake schedule에서 상태 의미가 origin에 따라 뒤집히는 소프트웨어 반례다. no_comm/peer_nl 양쪽에 적용되며 rule arm에는 이 입력이 없다. 실제 행동 영향의 크기·빈도는 측정하지 않았다. **기존 P2 후보가 지속하며 신규 finding으로 세지 않는다.**

## 6. 현재 이슈 지도: 더 할 일의 순서

- **#219/M2 + #363:** 접근 PF/guard 경로와 HIGH edge 경로가 분리되어 있다. `raise_high_align`의 단계 진전만으로 처음부터의 접근 문제가 해결되었다고 볼 수 없다. 두 경로의 첫 실패와 해당 소스를 별도로 고정하는 것이 다음 결과를 읽는 기준이다.
- **#216:** 불확실성 과신은 guard 완화와 다른 문제다. 입력량, 모델 적합, 갱신/가중치 상관을 분리하고 일관성 평가를 제어 입력으로 혼입하지 않는다.
- **#371 → #224:** #363 기반 코드가 아직 rebase 대기이고 v100 실제 실행 기록은 없다는 PR 설명을 유지한다. status 시간축과 live 비용 경계가 정리되어야 통신 arm 차이를 해석하기 쉬워진다. 8차 runtime 담당의 별도 검토를 참조한다.
- **#365/#372 → #219:** “채점 전”은 더 이상 최신 공개 상태가 아니다. [#219 공개 결과 5971577508](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5971577508)와 #372 `f676889f39df2de0679cc4e82e067565dcc5a775`의 결과 기록이 있다. 이 메모는 raw를 열지 않았다. 작성자는 steps의 몸체 좌표 운동이 과거 자료와 거의 같고 세계 좌표 제외 관문이 이를 분리하지 못한다는 한계, 두 지도가 독립 반복이 아니라는 한계를 이미 밝혔다. 이를 새 누설 발견으로 세지 않는다. PF 전체·짐 적재·학생 성공의 검증으로 확장하지 않는다.
- **#217/#366:** 관측 기억/능동 관측 연구는 현재 blind 대기와 정보 획득 문제에 연결할 수 있다. 지도 없는 경로는 원래 E2E 이후 과제이므로 지금 blocker를 피하려고 연구 입력 계약을 바꾸는 지름길로 쓰지 않는다.
- **#3/#226:** 공개 해시가 원격 원본 복구를 보장하지 않는 문제는 별개로 남는다. 현 review deliverable은 GitHub+Mac에 보존되어 있어도 실험 raw까지 원격 복구 가능하다는 뜻은 아니다.

## 7. 실행·검증 범위

이번 직접 실행은 위 세 종류의 오프라인 소프트웨어 재현이다. 전체 pytest, CI, 물리 인수, 실제 LLM, 모델 학습, 영상 렌더, 실물은 수행하지 않았다. source snapshot은 import 의존성용이며 binary DEV fixture도 읽지 않았다. 공개 타인의 실험 수치를 자체 성과로 합산하지 않았다.

현재성 원본은 `current-frontier.json` (Mac 전달본 증거), 종료 직전 metadata는 `frontier-final-heads.json` (Mac 전달본 증거)에 있다. 이 메모는 독립 검토이며 PR 병합 승인이나 제어기의 물리 안전 보증이 아니다.
