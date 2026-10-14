# search12 — 순차 접근 퇴행 분리와 관측된 막힘에 한정한 수정

2026-10-15, PR #484. 부모 `845a189072d0e82f4638b72a02f6f1bb33e8acc6`,
동작 기준 `86367b4b78a14c772f6194f6b36d524a0f934afe`.
새 물리·MuJoCo 렌더·원격 호스트 접속·모델 호출은 0회다. 저장 JPEG를 열고 조합한 것은 새 렌더가 아니다.
최종 실행 SHA는 `outputs/e2e18-admin/vm3-queue/20261015-grasp-search-<SHA8>.json`에 고정한다.

## 결론과 검증 범위

**정상 시작을 바꾼 것은 기존 상시 순차 접근이다.** GT 누설 제거만 켜면 정상6개의
4,664명령 전부 기준과 같고, 기존 순차 접근만 켜면3,396개가 달라진다.
두 토글을 함께 켠 명령은 순차 접근만 켠 명령과 같았다. 새 조건부 순차 접근+GT 제거도
4,664/4,664 명령·phase·done이 같고 정상6개에서 발동0회다.
이는 저장 입력 재생이며 **새 GCP 정상6/6 물리 성공을 뜻하지 않는다.**

원본 `outputs/gcp1-runs/grasp-search-diagnostic-gcp-845a1890/`의13개를 직접 재생했다.
저장 명령14,088/14,088의 시각·바퀴·PWM·phase·done을 확인하고 duration은 플랫폼 연산차≤1e-12초만 허용했다.
계획·결과·두 교사 원장·평가 원장의 manifest/압축 해제 SHA를 검사했다.
완료13/13, 물리0/13(정상0/6·어려운0/1·옛 관문실패0/6), HOST_ERROR/중단0,
approach handoff13/13이다. 실패도 모두 [요약](search12-summary.json)에 포함했다.

## no_path와 긴 대기의 원인

`diagnose_grasp_act_priority.py`는 실제 저장 관측·실제 발행 이력을 재생한 뒤,
실패한 계획에서 장애물 종류별로 하나씩 빼 보는 **평가 전용 기하 반례**를 만든다.
제어 입력은 `visible_measurements`와 자기 발행 명령뿐이다. 장애물을 빼는 진단은 실행 정책에 들어가지 않는다.

- **ep0 r1:** 최초 no_path +19.4초. 상대 몸체를 빼도 실패하고, 반대 끝 예약 원만 빼면 경로가 생긴다.
  이 순간 관측 constraint에 상대 몸체 자체가 없다. 빔 좌표계 시작(0.500931,0.393206),
  목표(-0.473,0). 예약 원은 반대 끝의 가상 중심과 반경0.25m이고 차체 여유0.13m가 더해진다.
  시작 여유14.197mm인데 A* 격자 시작점으로 연결하는 선분이 이 원에 들어가 `checked_path`가 거절한다.
  대기 중인 상대 몸체나 실제 대기점이 직접 원인이라는 관찰은 지지되지 않는다.
- **ep6 r1:** 최초 no_path +12.1초. 상대 몸체 제거는 효과가 없고, 추가한 통로 사각형 제거 시 경로가 생긴다.
  시작 빔좌표(0.308625,-0.921585), 목표(-0.473,0). 통로 사각형에 대한 시작 여유는 -91.375mm다.
  A*가 시작 여유 탈출 규칙으로 만든 경로를 매 선분의 새 시작점에서 다시 검사하면서 여러 선분이 거절된다.
  청록 시작이 설계한 반대쪽 통로에 이미 들어간 경우를 search11의 이상적 단면 검사가 놓쳤다.
- **ep1/4/5/8/11/12:** 첫 no_path도 예약 통로를 빼면 해소된다. ep4/5/9에서는 실제 발행 직전
  펄스가 가상 사각형에 걸리고, ep10/12에서는 반대 끝 예약 원에 걸린다. ep9의 최초 no_path는
  예약을 모두 빼도 남으므로 모든 계획 실패를 하나로 단정하지 않는다.
- **ep7(옛 관문3):** 첫 목표는 관측 화물의 여유를5.05mm 침범한다. 예약을 빼도 막힌다.
  기존 화물 실패가 남아 있으며 이번 순차 토글이 이를 해결했다고 보고하지 않는다.
- **ep2/3:** no_path가 아니라 **round1 READY 교착**이다. 청록은 ready, 파랑은 이미 주차 후 hold다.
  파랑의 대기점을 매번 새로 관측한 빔 좌표로 다시 계산하여 거리25.323/25.437mm가 됐다.
  허용치25mm를 넘으니 파랑 READY는 false인데 round1에서는 재주차도 안 한다. +118.1초 상한으로 끝났다.
  양끝에 같은 배정을 받은 문제가 아니며, 대기점의 위치가 변하면서 두 번째 GO/ACK가 열리지 않은 문제다.

**실패 핸드오프와 학습 표본 선정은 다른 판정이다.** ep0/6의 실패는 기존 `ApproachProgress`가
자기 발행 명령으로 적분한 위치의 순이동≤1cm를3초 보아 replan, 다시3초 보아 handoff한 것이다.
처음3초가 즉시 handoff라는 운영 관찰은 정정한다. ep0은+22.4초 replan→+25.4초 handoff,
ep6은+15.1→+18.1초다. 이 실패 판정에는 GT 거리도 local sample 거리도 쓰지 않는다.
`visible_handoff_v1`은 학습 표본을 현재 보이는 끝/최대5.2초 기억+자기 발행 위치의 거리≤0.8m와
기존 가시 시점 handoff latch로 고른다. 최종 관측 거리 ep0 r1=0.862556m, ep6 r1=1.088150m로
local sample은 제외된다. GT 제거는 에피소드 물리 성공 분모를 줄이지 않는다.

[직접 본 영상 목록](search12-frame-review.json):13개 모두 처음·중간·끝을 포함한6시각,
overview+r1+r2 총234개 JPEG의 원본 해시를 확인하고 직접 열었다.
최대 간격24초이며 긴 실행도60 SIM초마다1장 이상이다.
ep0/6은 파랑 대기 후 청록이 접근 도중 멈추고, ep2/3은 청록이 맡은 끝에 정렬해 기다리는 동안
파랑이 주차한 자리에 남는다. 다른 실행에서도 로봇 관계·끝 배정부터 확인했다.
전체 진단448KB와 원본 보존 위치/해시는 요약 JSON에 있다. 새 원격 백업을 수행한 것은 아니다.

## 단일 토글 재생

[정상 재생](search12-replay.json), [관문 실패 재생](search12-failures-replay.json).
기준 소스와 원본 명령 대조를 통과한 같은 입력에서 비교했다.

| 정상 idx | 명령 수 | 기존 순차만 첫 차이(SIM초) | 기존 순차만 변경 수 | GT 제거만 변경 | 수정+GT 변경 |
|---|---:|---:|---:|---:|---:|
|0|550|0.7|527|0|0|
|1|706|0.7|605|0|0|
|2|1,034|8.6|402|0|0|
|3|612|1.0|536|0|0|
|4|880|1.0|665|0|0|
|5|882|1.0|661|0|0|

GT 제거는 학습 라벨53개를 바꾼다(첫 차이 idx3 +28.6초, idx4 +25.4초, idx5 +42.2초;
idx0–2 차이 없음). 명령은 바꾸지 않는다. 입력 감사 invisible_measurements=0, held_world_reads=0.
순차 갈래의 첫 다른 명령 이후 출력은 이전 주행의 입력을 계속 넣은 shadow이며 새 시점/성공 증거가 아니다.
기존 관문 실패3/7/8/14/17/32도 따로 재생했다. 수정 조건은14/32에서만 발동했고,
3/7/8/17에서는 발동하지 않았다. 이 범위 제한을 숨기지 않으며 실패6개 해결을 주장하지 않는다.

## 수정: 기본 OFF observed_blocked_priority_v2

- 평소에는 `priority=None`, 기존 경로·진행 감시·60초 위상 시한·pick 장벽을 그대로 쓴다.
  현재 자기 RGB에 상대가≤0.65m로 보이고, 목표/경로가 상대 때문에 막혔으며,
  자기 발행 위치가3초간1cm 넘게 이동하지 않은 접근 단계에서만 BLOCKED boolean을 보낸다.
  READY 대기·search·보이지 않는 상대 기억·그냥 가까운 상대는 발동 조건이 아니다.
- 코드 프로토콜은 BLOCKED 한 비트만 받아 순차 접근을 켠다. 상대 좌표·경로를 전달하지 않는다.
  이후 기존 READY→GO→ACK를 매 순차 단계에서 새로 연다. 이미 집기를 시작한 장벽은 바꾸지 않는다.
- 새 모드는 search11의 가상 통로 사각형/반대 끝 예약 원을 사용하지 않는다.
  **실제 벽·화물·상대 몸체의 기존 여유는 유지**하고 경로와 발행 펄스를 검사한다.
  파랑 대기점은 자기 관측으로 안전한 후보를 고른 뒤 자기 명령 좌표계에 고정한다.
  관측한 상대→청록 목표 직선 통로에서0.38m 이상 떨어진 후보만 쓰며, 상대를 현재 못 보거나
  안전한 대기점이 없으면 제한 시간 뒤 실패로 돌린다. 이 직선 검사는 실제 상대 경로 보장이 아니다.
- 기존 `prioritized_approach_v1`은 원본 재현용으로 보존하되 새 대기열에는 넣지 않는다.
  visible_only 학습 기록은 `visible_handoff_v1` 없이 시작하려 하면 물리 생성 전에 거절한다.
  GT 제거 토글은 진단 비교를 위해 기본 OFF를 유지하지만 실제 기록에는 필수다.

관련3파일 **45 passed**, `git diff --check` 통과. 실제 no_path 두 원본 단면·새 모드에서 물리 제약 유지,
조건부 요청/미발동·boolean 장벽·주차점 좌표 고정·시한·GT 없는 표본 선정/기록 거부를 검사했다.

재현(모두 오프라인):

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.diagnose_grasp_act_priority --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-gcp-845a1890 --out /private/tmp/search12-diagnosis.json
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_ablation --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-gcp-86367b4b --out /private/tmp/search12-replay.json
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_priority.py tests/test_grasp_act_batch.py tests/test_grasp_act_progress.py
```

## 다음 GCP 진단과 승인 경계

두 갈래는 같은13개 시작을 쓴다: 정상6+기존 관문 실패6에 기존 어려운idx6을 포함해 동일13개를 유지한다.
`teacher-search11-diagnostic-plan.json`을 바이트 그대로 재사용하며 새 표본 배제는0이다.
A=86367b4b 프로필+GT 제거만, B=A+조건부 순차 접근. recovery는 둘 다OFF다.
실행 cap은 A/B 모두 기준과 같은60 SIM초로 고정한다(활성 순차화의 내부118초 상한보다 먼저 끝난다).
순차 접근에 더 긴 예산이 필요하더라도 이번 비교의 시간 상한을 묵시적으로 늘리지 않는다.
A는 정상6/6 물리 보존이 핵심이고, 기존 실패6·어려운1은 원인 비교용이다.
B도 정상6/6 보존을 먼저 확인하며 어려운1·기존 실패6의 실제 파지는 별도로 집계한다.
A의 기존 실패가 개선되지 않은 것을 정상 보존 실패와 혼동하지 않는다. 핸드오프는 항상 물리 실패다.

진단A→회수·검토→진단B 순서로 운영자가 제출한다. 새 SHA·프로필별 속도16과 관문40은
**모두 조정자 새 승인 필요**, ready=false이며 `gate_promotion_authorized_if_all_conditions_pass=false`다.
선택 갈래가 정해지기 전 후속 실행 명령을 만들지 않는다. 이전845a1890 대기열은
원본 사본/해시 보존 후 superseded/ready=false, 모든 실행 ready=false로 바꿨다.
GCP 비용·8시간/유휴20분·저장/동시 수 admission과 repeated_cause_v1 정지는 유지한다.

남은 것: A/B의 정상6/6 실제 보존, 조건부 발동 뒤 새 영상·대기점 안전·파지 결과,
남은 화물/벽/시야/격자 경로 실패, 후보별 실제 속도와 새 관문40. 새 실행은 전부 NOT_STARTED다.
