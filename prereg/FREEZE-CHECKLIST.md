# 동결 체크리스트
순서가 중요하다: 코드와 문서를 먼저 끝내고, 마지막에 해시를 한 번 기록한다. 기록 뒤에는 아래 파일을 고치지 않는다. D1~D11 은 PREREG 9절에서 닫혔다. D11 은 기준선 게이트가 건 실행층 수정 6cbd3db 다. 이 목록은 그것을 코드와 해시에 반영하는 절차이며, 진행 상황은 적지 않는다(현황·숫자는 프로젝트 이슈 트래커에 적는다).

**A. 기록 전에 닫을 것**
- [ ] **변경 중지 선(PREREG 9절 D10)을 지킨다**: 프롬프트 문구, 메시지 규칙, 허용·λ, 행동 선택지, 덮임 판정 규칙, 장면 파일, FixedPlan, 3대 패치 02·03 은 확인 묶음 결과가 어떻든 고치지 않는다. 고쳐도 되는 것은 분석 전용 꼬리표·표, PREREG 글, 스케줄러 고장, 버전 문자열뿐이다. 예외는 D11(B0·B1·B4, 6cbd3db) 하나다. 계획기 버전은 `brain-v3-msg4-20261116` 이다(team/brain/__init__.py 의 `PLANNER_VERSION`).
- [ ] 연결 코드의 HEAD 가 6cbd3db 계열인지 확인한다(`git log`, `git status --short`). PREREG 가 인용하는 줄 번호(run_team_carry.py, launch_team_run_v3.sh, approach_core.py, carry_nav_v1.py, run_grasp_act_student.py)를 그 HEAD 에서 다시 열어 확인한다. 이후 커밋이 생기면 다시 확인한다.
- [ ] confirm3(코드 1452d43; 확인 묶음 18 + 조건 스위치 4) 결과를 읽는다. 볼 것: 18칸이 고장 없이 끝남 / 멈춤·형식 오류가 18 중 2 이하(D1: 3 이상이면 temperature 되돌림) / 조건 4회가 끝까지 돎 / T0 프롬프트가 옛 것과 같음 / T2 에서 기회·라우팅이 도는지 / 상한에 닿은 로봇 수 / 내려놓기 판정. `llm-calls.jsonl` 한 건에서 temperature 0.7·max_tokens 2048·reasoning 값이 PREREG 8절과 같은지 연다.
- [ ] 기준선 BASE2 40회를 읽는다(코드 6cbd3db 한 판; PREREG 7절 기준선 규칙·D11): 물리 실패(S=0) 8 이상이면 본 A 를 시작하지 않고 멈춘다. 장면은 빼지 않는다. 첫 BASE-*(코드 혼합)는 버렸으니 섞지 않는다(PREREG 6절 "기준선 게이트" 행). BASE2 에서 B0 가 설명한 실패(시작 방향에서 많이 틀어진 상자의 첫 집기 empty)가 줄었는지, 새 실패가 생겼는지 시간순 표로 본다.
- [ ] `prereg/freeze_hashes.py` 의 `ANALYSIS_FILES` 에 `analysis/analyze_main.py` 가 들어 있는지 읽는다. 알려진 빈틈: `PROMPT_SEGMENTS` 에 `MESSAGE_RULE`·`CHANCE_NOTE`·`TeamBrain.chance` 가 없다(파일 전체 해시는 덮는다).
- [ ] 분석 스크립트(`analysis/analyze_main.py`)를 실제 계획기 기록 + VM team.json 형식의 시험 자료로 끝까지 돌린다(도구 시험, 결과 아님). 시험은 `analysis/` 에서 `python3 -B -m unittest test_analyze_main test_compare test_make_figures`. confirm3 기록이 나오면 한 번 더 돌린다(T0·T2 칸으로 SP 구간 판정·손익분기 λ\* 가 실제 자료에서 채워지는지, 실패 칸 3모드, 하이픈 장면 ID).
- [ ] 장면 목록은 PREREG 5절(핵심 348, 선택 242 중 3대 42 제외)과 매니페스트 줄 수가 맞는지 직접 센다. `batch/check_manifests.py` 는 `batch/make_manifest.py` 의 `FROZEN_SHA`·`FROZEN_VMRUN`·`SEED` 와 줄을 대조하므로(저장소 값은 이전 동결 값 `dbb692c`, `run_team_v32.sh`), 동결 HEAD(6cbd3db)와 VM 실행 스크립트에 맞게 두 상수를 먼저 고친다. 모든 줄에 같은 sha·`--cap-s 900`·같은 VM 실행 스크립트가 있는지 센다.
- [ ] 벽시계 상한은 실행기 `WALL_CAP=4.5h`(batch/launch_team_run_v3.sh)와 코드 14400 s(run_grasp_act_student.py)가 강제한다(PREREG 7절 (b)). 매니페스트 모든 줄에 `--cap-s 900` 이 있는지 센다.
- [ ] 통합 작업 트리가 clean 인지 확인한다(`git status` 에서 변경 없음, 커밋됨). 스크립트가 경고를 출력한다.
- [ ] 작업 VM 쪽(VM 실행 스크립트, VM 코드 폴더, ACT 체크포인트) sha256 을 VM 에서 직접 구해 따로 적어 둔다. 이 도구는 못 본다.
- [ ] 스케줄러 점검: 포트 블록이 0개면 조용히 기다리지 않고 종료 2(batch/dispatch.py), 실행기 TERM 시 `.launch-pgid` 로 원격 프로세스 그룹까지 종료(batch/launch_team_run_v3.sh). 시험은 `batch/` 에서 `python3 -B -m unittest test_batch`.
- [ ] PREREG.md 최종본과 이 체크리스트를 확정한다. 이후 문서를 고치면 해시가 달라진다. 낡은 줄이 0 인지(날짜·커밋·버전·벽시계·3대 문구) 한 번 훑는다.

**B. 기록**
- [ ] 저장소 루트에서 `python3 -B prereg/freeze_hashes.py` → `prereg/FREEZE-HASHES.json` 생성, 종료 코드 0, 출력의 HEAD 가 예상한 커밋인지 읽는다(다르면 멈춘다). 파일 수도 읽는다.
- [ ] 바로 `python3 -B prereg/freeze_hashes.py --check` → `SAME`, 종료 코드 0 인지 확인한다.
- [ ] `FREEZE-HASHES.json` 을 다른 위치에 한 부 더 복사하고(작업 VM 포함) 복사본의 sha256 이 같은지 본다.

**C. 기록 남기기**
- [ ] 프로젝트 이슈 트래커에 동결 시각(KST), git HEAD, `prompt_templates_sha256`, 파일 수, 열어 둔 항목(PREREG 9절)을 댓글로 남기고 다시 읽어 확인한다.
- [ ] 저장소에는 완성된 PREREG.md 만 올린다(현황·숫자는 이슈 트래커로). 해시와 HEAD 는 PREREG 안에 쓰지 않는다(문서 해시가 바뀜).
- [ ] 실행 매니페스트(`batch/make_manifest.py --preset all --baseline-first` 의 `core.csv`, `optional.csv`)가 PREREG 5절 표와 합계가 맞는지 센다. 3대 42줄은 optional 매니페스트에 남아 있어도 돌리지 않는다. 동결 때 코드 HEAD 열이 해시 기록의 HEAD 와 같은지만 한 번 더 본다.

**D. 실행 중**
- [ ] 각 묶음을 시작하기 전에 `--check` 를 돌려 종료 코드 0 을 확인한다. 1 이면 시작하지 않고 달라진 파일을 본다.
- [ ] 새 묶음은 1건 먼저 돌려 본 뒤 넓힌다(첫 묶음은 기준선 BASE2 40회로 VM 처리량과 스케줄러 실제 경로를 확인). 재실행 이름은 `-rr1`, 기준은 PREREG 7절.
- [ ] 선택 묶음은 PREREG 5절의 "빼는 순서"를 따른다. 핵심 348회는 빼지 않는다.
- [ ] 지출 가드 잔액(상한 2 USD)을 묶음마다 확인한다. 키 값은 출력하지 않는다.
