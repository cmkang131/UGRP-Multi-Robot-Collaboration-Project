# E2E18 Gemma 작업 계획기 v357 (DEV, draft)

요청: 로봇별 Gemma가 무엇을·어디로·어느 길/방향으로·혼자/같이 할지 고르고,
코드는 실행 가능한 후보와 비용을 제공하고 선택을 그대로 실행하거나 이유를 붙여 거부한다.
`e2e_options.planner=gemma_v1`; 키가 없으면 off. 기존 실행기와 번들의 기본 경로는 변경하지 않는다.

## 구현과 재사용

- `harness/task_planner.py`: 로봇별 8개 결과 기억, 시작/완료/실패/거부/실제 메시지/s2–s5/파지 사건, 한 JSON에 act·args·message·reason. 형식/안전 거부는 한 번 재질의, 모델 실패·30초 초과·비정상 finish는 명시적 규칙 대체. 모델 정답률에 대체 결과를 합산하지 않는다.
- `task_planner_runtime.py`: 후보 Cartesian product, 로봇별 모델/기억/미래 작업, 최대 세 동시 모델 호출과 메인 스레드 실행 커밋. 없음/정형/영어 peer/영어 leader 채널의 전달 원문만 수신. legacy dialogue/vote/peer 상태는 읽지 않는다.
- 기존 `multi_object_plan._fields`의 엄격한 형식 검사, `dispatch_plan_guidance`의 정적·자기 추정 기반 preview 원칙을 재사용했다. `dispatch_plan`의 공동 계획을 선택 뒤에 재배정하는 경로는 쓰지 않는다.
- `task_planner_zone.py`는 `zone_own_executor`의 deliver/goto/look_around/wait 및 pair_carry API에 연결한다. 지원하지 않는 화물·경로·접근 방향은 거부한다. native solo는 기존 cyan/west/지도상의 door 스킬이다. 지원 가능한 A1/A2 같은 하역 칸은 모델이 직접 고른다. 임의 route/approach를 실행한 것으로 주장하지 않는다.
- `zone_mixed_jobs`의 고정 r1/r2/r3 배정은 새 선택기로 재사용하지 않았다. `zone_own_team_host`의 자기 프레임/명령/상태 경계를 사용한다. `pair_llm_contract`, `pair_llm_dispatch`, `pair_llm_inputs`는 실제 파일명으로 읽었다(요청의 `pair_llm_contract/dispatch/inputs.py`라는 단일 경로는 없음).
- `e2e_dialogue`, `e2e_dialogue_decider`, `e2e_llm_memory`, `s4_compact_prompt`를 조사했다. 전자의 구조화 경로/투표를 새 입력에 복사하지 않고, 후자의 영어 조건 이름 변환과 짧은 자기 기억 방식을 재사용한다.
- `scripts/run_task_planner.py`는 표준 simulation_workflows에 등록한 native 장면 어댑터다. 실제 장면은 기존 zone own-camera 장면이며 e2e18 ownmap 빔 장면과 물리 동등성을 주장하지 않는다. Mac 물리/렌더는 코드에서 거부한다.

## 자료·검증

조정자 원본: `/private/tmp/claude-501/-Users-changmin/2eb0ff27-da4f-4484-8131-64ef091df6ae/scratchpad/tasklevel/`.
원본 384개 중 비애매 331개, 애매 53개. 동일 공개 후보 의미를 새 act API로 옮긴다.
거리·초 단위가 원본에 없으면 unknown으로 두며 합성 팀 비용을 실제 거리/시간으로 바꾸지 않는다.
`results_scored.json`의 라벨은 응답 후 채점에만 사용한다.

고정 강한 규칙의 공개 비용식/메시지 파서는 `task_planner_cost_rules.py`로 재사용했다.
생성기·숨은 상황·평가 입력은 복사하지 않았다. 새 형식 규칙 재집계:
없음 123/331, 정형 222/331, peer 영어 231/331, leader 영어 231/331.
leader 조건은 r1(지휘자)이 r2의 원래 영어 보고를 받은 단일 판단이다.
다회 중계나 3대 통신 효과를 측정한 것으로 해석하지 않는다.
별도 작성한 단독 운반 24개는 목적지×경로×접근 방향 8개 후보의 예상 시간 최소 선택이다.
원본과 분리한 합성 시험이며 물리 성공/확증 자료가 아니다.

실제 Gemma 평가는 `scripts/evaluate_task_planner.py --source <원본> --out <새폴더> --execute`.
기존 `study_gemma4_31b_v1` Mac 유료 중계만 사용, OpenRouter/`google/gemma-4-31b-it`/DeepInfra 신원을 검사한다.
코드는 키를 취급하지 않는다. 동시 4개, $2 상한(요청 전 보수적 예약), 실패·비정상 응답도 분모와 원장에 남긴다.
비용 미확인 호출은 예약액을 유지한다. raw·요청·응답은 로컬 outputs에, 해시·짧은 집계는 이 폴더에 보관한다.

## 실행 번들 예약

2026-10-13 main 및 열린 PR #471/#467/#461/#459/#440/#437/#385/#339 브랜치를 fetch하고
`harness/rgb_execution_bundle.py`의 RUNNABLE_ID 및 E2E 모듈·workflow 등록을 조사했다.
최댓값 v356(PR #471), 다음 v357 / workflow 7.250.0을 예약했다.
[#461 시작/예약 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/461#issuecomment-6142990147).
실제 실행은 조정자/감독자의 Azure 제출로만 확인하며 이 작업은 VM을 직접 조작하지 않는다.

## 참고 자료

2026-10-13 아래 저자 프로젝트 페이지 또는 논문 초록을 열어 방법을 확인했다. 전체 논문 재현/정독이나 성능 수치 재현은 주장하지 않는다.

- [SayCan](https://say-can.github.io/): 언어 유용성과 스킬 실행 가능성의 결합. 여기서는 가능 후보/preview만 코드가 제공하고 최종 선택은 Gemma가 하므로 원 논문의 확률 곱을 재현한 것은 아니다.
- [ProgPrompt](https://progprompt.github.io/), [Code as Policies](https://code-as-policies.github.io/): 명시적 스킬 API로 작업 계획을 접지한다. 임의 Python 실행 대신 엄격한 JSON act와 whitelist executor를 사용한다.
- [RoCo](https://arxiv.org/abs/2307.04738): 로봇별 대화·실행 가능성 피드백. 자기 입력과 전달된 조건 채널을 분리하는 원칙을 적용한다.
- [CoELA](https://arxiv.org/abs/2307.02485): 지각·기억·통신·계획 모듈을 나눈 협력 에이전트. 공동 정답 상태를 새 입력으로 복사하지 않는다.
- [SMART-LLM](https://arxiv.org/abs/2309.10062): 분해·팀 구성·배정을 스킬 실행과 분리. 본 구현은 매 사건마다 하나의 다음 act를 선택한다.
- [Inner Monologue](https://arxiv.org/abs/2207.05608): 실행 피드백으로 계획을 갱신. referee 성공 대신 자기 act의 확인/실패/거부만 쓴다.
- [Reflexion](https://arxiv.org/abs/2303.11366): 실패 기억을 후속 판단 맥락에 보존. 별도 반성 모델 호출 없이 짧은 실행 결과 기억을 사용한다.

남은 물리 검증·CI·실제 모델 수치는 summary.json 및 PR 본문에 별도 기록한다.

## 최종 소프트웨어·오프라인 결과 (2026-10-13)

구현 후보 `df0981d7271b5c4affc5ca3fa3eb1a49a729d7e9`: 관련 시험 **40/40** 통과.
세 시험 파일만 실행했다. 최종 입력에는 전체 정적 지도 geometry와 자기 추정 yaw도 포함하며 다른 로봇의 위치나 실시간 정답은 넣지 않는다. 실제 PairTeam/ZoneOwnExecutor 제출 경로의 fake-controller 시험,
무통신에서 peer 상태 미전달, 잘못된 공동 요청이 상대를 직접 중단하지 않음,
형식 거부와 실행 거부를 합친 최대 2회 호출, 원본 요청 기록 불변을 포함한다.
마지막 두 실행기 시험은 fake host 또는 중계 시작 실패이며 MuJoCo 모델을 생성하지 않는다.

Gemma 실제 평가 소스는 `7e3eef0427639b39365305dbdc654ba2bb1c0032`로 고정했다.
각 조건의 비애매 331개와 애매 53개를 나눴으며 실패·대체도 분모에 남겼다.

| 조건 | Gemma n/N | 애매한 자료 n/N | 최종 응답 오류/대체 | 강한 규칙 n/N |
|---|---:|---:|---:|---:|
| 무통신 | 131/331 | 46/53 | 34/384 (비애매 31, 애매 3) | 123/331 |
| 고정 신호 | 187/331 | 50/53 | 0/384 | 222/331 |
| 영어 peer | 207/331 | 51/53 | 0/384 | 231/331 |
| 영어 leader | 208/331 | 51/53 | 0/384 | 231/331 |

통신 조건에서 Gemma가 강한 규칙보다 좋다는 근거는 없다. 응답 오류의 대체 선택은
Gemma 정답에 합산하지 않았다. 별도 합성 단독 선택 **24/24**.
본 평가 1,593회와 추가 단독 24회를 합쳐 실제 요청 1,617회,
응답에 표시된 비용 합계 **$0.24476471**(별도 청구서 대조 아님).
초기 잘못된 중계 헤더 묶음과 4개 사례+단독24개의 probe도 `summary.json`에 따로 남겼다.
초기 묶음의 $1.998는 실패 요청의 보수적 예약액이며 실제 청구액으로 보고하지 않는다.

재질의 때 공유 맥락이 이전 요청 기록을 바꾸는 audit 버그를 발견해 복사로 수정했다.
오래된 raw를 바꾸지 않고, 각 호출 직전 거부 이력만 복원해 저장된 전송 본문 SHA-256과
**1,617/1,617** 일치시켰다. `verified_wire_requests.jsonl`에 보완 요청을 저장했다.
현재 계획기로 저장 응답 1,536개와 추가 단독 24개를 재생해 동일 판단을 확인했다.
이는 새 모델 평가가 아니라 저장 응답 회귀 검사다. 재현은 프로젝트 루트에서
`PYTHONPATH=. python experiments/2026-10-13-e2e18-planner/verify_saved_responses.py`.

## 실제 스킬 경계와 감독자 확인

- native 공동 스킬의 기존 공유 status 버스를 로봇별 수신함으로 바꿨다. 자기 상태는 자기만 발행하고, 상대 상태는 선택된 조건 채널에서 실제 배달된 뒤에만 안전 장벽에 반영한다. NL은 문장, structured는 닫힌 `PAIR_STATUS` 신호, no_comm은 전달 없음이다. 모델 문장은 코드 안전 신호를 위조할 수 없다.
- 기존 PairTeam의 공유 대기 요청 비교도 새 경로에서는 사용하지 않는다. 각 로봇의 고정 주문·목적지·자기 시도 번호로 작업 ID를 만들고 독립 제출한다. 서로 다른 요청은 채널에서 같은 작업의 합의를 만들지 못하며, 상대 요청을 직접 읽거나 상대를 바로 abort하지 않는다. 기존 번들 함수는 변경하지 않았다.
- `set_down_and_regrip`는 기존 wrist skill의 안전한 재집기 단계(`_start_reseat`)를 사용한다. 완료 뒤에는 멈춰 있고 Gemma가 정확한 원래 carry를 다시 고르면 재개한다. wait도 안정된 자기 파지 상태에서만 pause한다. 소프트웨어 검증이며 물리 재파지 성공은 미확인이다.
- native adapter는 임시 표식 기반 zone 장면, cyan/west/단일 door와 기존 r1/r2 공동 역할의 실제 지원 범위를 그대로 명시한다. 일반 act 후보의 임의 경로/접근 지원과 **E2E18 ownmap 빔 장면 전체 이관은 이 검증으로 완료되지 않았다**. 기존 몸 스킬을 호출했다고 실제 운반 성공으로 보지 않는다.
- `e2e18-v357` 표준 workflow를 #461 감독자에게 30 SIM초 제출 요청한다. 이 작업에서는 Mac 물리·렌더 및 Azure VM 조작을 하지 않았다. 결과는 아직 없고 draft를 병합하지 않는다.

## 보관

조정자 원본 4파일을 `outputs/task-planner-v357-source-20261013/`에 복사하고 전체 해시를 대조했다.
전체 원장·실패·보완 요청은 `raw_manifest.json`의 로컬 경로와 해시로 연결한다.
`compress_json_traces.py`는 8개 큰 파일을 찾았지만 샌드박스의 `ps` 거부로 실행 중 확인을
할 수 없어 안전하게 중단했다. 원본을 제거하지 않았으며 압축은 남은 작업이다.
코드·짧은 요약·해시는 GitHub에 올리고 raw의 로컬 보관을 원격 백업으로 표현하지 않는다.
