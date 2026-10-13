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
