# e2ewarp: LLM E2E → MJWarp 배치

기준 `origin/main=c8dc1e6545124ed69a996618bd11df684d233969`, 새 worktree
`/Users/changmin/projects/ugrp-wt/e2ewarp`, 브랜치 `codex/e2ewarp`.
사용자 10/16 “모두 MJWarp로 바꿔서 하게”, 10/17 “최신으로 업데이트”를 적용한다.
최종 정지 조건은 **한 실행에서 LLM 판단 + 자기 지도 + 처음부터 마지막 실제 운반 성공**이다.
첫 30 SIM초 배관 점검은 이 조건을 충족하지 않는다. CPU·다른 호스트·noslip10 결과와 합산하지 않는다.

## 구조와 경계

세계 하나가 독립 E2E 에피소드 하나다. 같은 장면 모델의 세계들을 `nworld` 축으로
묶고 세계마다 r1/r2/r3의 상태·RGB 이력·명령 이력·지도·LLM 문맥·메시지함을 따로 둔다.
공유하는 것은 고정 모델·GPU physics graph·GPU ACT 가중치뿐이다. 다른 장면/모델은 별도 묶음이다.
물리는 MJWarp의 `put_model/put_data → CUDA graph → step`, 자기 카메라는 MJWarp render다.
C MjData는 초기 설정·kinematic mirror·평가에만 쓴다. CPU `mj_step`, CPU 렌더,
CPU와 같게 만들기 위한 legacy plane/compiled actuator/geometry patch는 새 경로에 넣지 않는다.
공용 명령 tape 계산과 기존 backend의 명령·RGB 메서드는 vendor 바이트로 재사용한다.
초기 자세도 C settling 없이 명시된 setup으로 설정하고 이후 안정화는 GPU에서만 한다.

로봇 제어 객체에는 world/model/data/evaluator를 전달하지 않는다. 허용 입력은 자기 JPEG,
자기 발행 명령·시각, 고정 주문·정적 지도·카메라 보정, 해당 통신 채널의 메시지다.
집게 명령은 관절 측정이 아니다. held 화물 정답·접촉·실제 위치·성공 판정은
별도 evaluator 출력에만 기록한다. top은 제어·지도·LLM에 전달하지 않는다.

각 로봇의 판단은 Gemma 4 31B `google/gemma-4-31b-it`, CoreWeave fp4,
fallback false다. 기존 `scripts/openrouter_upstream.py`와 response journal을 Mac에서
재사용하고 SSH reverse tunnel의 loopback으로 VM과 잇는다. VM에는 키·계정·인증정보를
복사하지 않는다. 새 relay adapter는 e2ewarp call ID/이미지 1장 계약만 추가한다.
요청은 system → static(주문·정적 지도·규칙·형식) → dynamic(시각·자기 상태·후보·메시지)
→ 자기 RGB 1장 순서다. 원본 요청/응답 텍스트와 제거한 이미지 SHA를 기록한다.
cached_tokens/프롬프트·출력·total tokens·429·실제 upstream attempts를 원장으로 남긴다.
비정상 finish_reason의 응답은 비용을 보존하고 행동·메시지를 실행하지 않는다.
연결 실패 3회 연속 또는 30 SIM초 지속 시 HOST_ERROR로 전체 해당 실행을 멈춘다.
개별 실패는 hold로 안전하게 처리하고 다음 호출에 실패 이유를 전달한다.

LLM은 무엇·목적지·경로·끝·짝·대기·재집기를 고른다. 지도 코드는 자기 추정 위치로
경로·주행·운반을 실행한다. 근거리 접근·정렬·집기·놓기는 ACT 학생의 0.8초 청크다.
ACT는 자기 RGB 이력·자기 명령 이력·이산 skill/kind/role/destination만 받고 CUDA에서
추론한다. 교사 fallback은 학생 경로에 넣지 않는다. 학생 artifact가 없으면 nearfield
진입을 차단한다. 완료 출력과 자기 RGB 확인이 함께 있어야 추정 완료를 반환한다.

내려놓기 다음에는 `release_reloc_selfmap_v1` adapter가 실제 자기 RGB를 보며 둘러보고
위치를 다시 잡는다. 단순 팬 명령 발행을 위치 재획득으로 세지 않는다. 모듈이 준비되지
않았으면 재집기·운반 재개를 막는다. 명령 FK·LK·RBPF/정적 지도 정합은 mapbuild 소유
모듈을 byte vendor한다. loaded FK와 전역 정합이 미완성이므로 현재 own-gauge LK는
진단 전용이며 정적 지도 좌표를 안다고 가정하지 않는다.

## CPU 경로 재사용/교체

| 기존 구성 | 새 경로 | 범위 |
|---|---|---|
| run_e2e_ownmap_live/reviewed/s3_route/azure_batch | 그대로 보존 | CPU 재생·비교 전용, wall cap·Azure CPU admission 승계 안 함 |
| zone study 조건·주문·정적 지도·장면 빌더 | 재사용 | setup_only 위치는 제어에 전달 안 함 |
| v7 명령 relay/PWM interpolation·warp_act_core | byte vendor | 배치 world×robot 명령 tape; 자기 명령만 사용 |
| CPU mj_step·렌더·settling | 교체 | MJWarp step/renderer만; noslip0 runtime 검증 |
| 기존 RGB/명령 LK | mapbuild FK qualification과 연결 | RGB unknown은 정지 증거가 아님; command prediction 별도 표시 |
| 구 Hough 바닥선 release localizer | 승계 금지 | warp8e 자기 지도 release adapter 대기 |
| 손으로 짠 근거리 파지 | 승계 금지 | act16w GPU 학생; artifact 없으면 dependency wait |
| OpenRouter upstream·journal·Keychain | Mac 재사용 | VM은 localhost relay만 접근 |
| evaluator/성공 조건 | 별도 capability | 실제 운반 검증 전에는 E2E_success=false |
| result/명령/이미지 원장 | 새 통합 manifest | source/vendor/map/XML/model/contact hash·모든 종료 보존 |

## 통신 네 조건

기존 MAIN_CONDITIONS `no_comm`, `peer_ko`, `leader_ko`, `structured`를 쓴다.
no_comm은 inbox 자체가 없다. peer_ko는 수신자별 자유 한국어, leader_ko는 seed로
고정한 순환 leader의 star 연결만 허용한다. structured는 고정 schema만 전달한다.
같은 LLM 응답에서 선택과 메시지를 함께 받는다. 후보/실행 상태는 다른 로봇에게
직접 공유하지 않는다. 최소 GO/ACK 실행 동기화도 과제 판단의 옆길로 쓰지 않는다.
처음 1–2세계 점검은 전체 4조건 비교/통신 효과 검증이 아니다.

## 의존과 현재 상태

| 의존 | 소유자 | 확인한 상태 / 연결 조건 | ops-alert |
|---|---|---|---|
| 최종 native ACT 학생 checkpoint | act16w4 / claude/act16w | native 기록40 완료·A/B 학습 중; 최종 선택/재평가 미확인. inventory/hash/adapter/학습 출처 필요 | 준비된 commit/API/hash 요청 |
| LK/RBPF 판정 | mapbuild6 / codex/mapbuild1 | 실제 운반 경로 녹화 3라운드 종료, 운반 진입0. 채택 판정 대기 | 현 상태 확인 |
| 운반 자세 명령 FK | mapbuild6 | grip<=1600 거부 유지; 보정/자격을 임의 완화하지 않음 | warp8e·조정자 scope 요청 확인 |
| 정적 지도 전역 정합 | mapbuild6 | own-gauge→static map API 미완성 | 위 scope 요청 확인 |
| release 위치 재획득 | warp8e / codex/warp6 | release_reloc_selfmap_v1 오프라인 준비; 옛 Hough 승계 금지 | 준비된 commit/API/hash 요청 |
| native noslip0 | nsoff PR #568 / warpfit2 PR #562 | native owner SHA a5c8d370... byte vendor | 기존 완료 보고 확인 |
| current_stack/check_current_stack | stackaudit | JSON 로컬 초안 확인, remote ref/점검기 준비 대기 | commit/ref 요청 |

외부 부품은 `manifest + observe(own) + candidates() + execute(selection)` 계약으로
연결한다. 완료·성공·실측 여부를 어댑터가 지어내지 않는다. runtime/own inputs를
보존하고 각 dependency가 ready여도 처음→끝 새 물리 검증 없이는 ready 판정하지 않는다.

## 실행·검증 계획

기본 off `e2e_warp_batch_v1`; 새 후보에서 명시적으로 켠다. 현재 스택의 적용값은
`configs/current_stack.json`을 읽고 queue의 `stack_values`와 승인된 smoke 이탈을
`check_current_stack`로 검사한다. 자기 선언과 런타임 검사 결과를 분리한다.
대기열에는 존재하는 절대경로 rejection_table과 source/재현 명령을 넣는다.
거부 행은 category/reason/blocked_object/minimum_gap_m/gap_status를 항상 기록한다.
미관측·미측정 상태를 null+상태로 적고 빈 이유는 금지한다.

Mac은 compile/순수 단위 시험만. gcp6(`ugrp-sim-f-1016`,
`kcm5781kcm5781@gmail.com`)에서만 실제 step/render를 수행한다. 다른 VM은 사용하지
않는다. 작업 직전 budget-stop/idle20/상한없음·임대·기존 PID/GPU·저장 예산을 확인한다.
LLM batch 직전 endpoint_watch와 OpenRouter 잔액을 확인한다. 실행 소스는 먼저
커밋·고정하고 remote source는 공용 git-shared에 직접 reference한다.

최대 3라운드. 첫30 SIM초에 LLM 선택 분포·정지 구간·오류·모델 호출·토큰/SIM초·캐시
비율·429·응답시간·이미지 전달을 원본으로 재계수한다. 이 30초는 사용자 지정 진단
SIM 예산이며 wall 상한이 아니다. cap_end로 표시한다. 계산 상한은 노드/검사 수,
속도는 wall/(SIM×world)와 배치 지연을 함께 기록한다. 알려진 결함을 확인하면 즉시
자기 실행을 중지하고 거부 분포·필요한 프레임 검토 뒤 한 묶음으로 고친다.
10Hz 자기 카메라의 마지막10 SIM초 ring은 기록 전용이며 제어/학습 입력과 별개다.
원본 분석은 gcp6 CPU, Mac에는 요약·몽타주·실패 프레임만 회수한다. GUI 금지.
작업 종료 시 자기 프로세스·임대가 없고 다른 작업도 없음을 확인한 뒤 gcp6를 정지한다.

## 참고 자료 (2026-10-17 열람)

- [MJWarp 공식 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/): nworld 배치,
  PyTorch 연결, CUDA graph, workspace overflow 및 작은 capacity 권고. 런타임은
  gcp6의 설치 commit을 별도 기록하며 최신 문서 API를 무조건 가정하지 않는다.
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection):
  공급자·quantization 고정 및 fallback false.
- [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching):
  앞부분 일치와 cached token 사용량. 실제 CoreWeave cache hit은 원장에서 확인한다.
- 저장소 docs/decision_model_control.md, docs/act_execution_decisions.md와 stackaudit
  flows.md. 문서의 과거 DeepInfra/CPU 추론/8시간 구절보다 최신 AGENTS·사용자 지시가 우선한다.
