# v97 두 로봇 짝 운반 LLM 판단 층 — 가능성 시험 (배관 단계, 연구 결과 아님)

번들 `zone-pair-llm-v97`, 워크플로 3.9.0, 상태 `DRAFT_UNSEALED`, `research_result=false`. 이슈 #219 참조.
2026-10-03 사용자 결정("일단 지금 상황에서, llm을 쓰고 되는지를 보자 그 다음에 고도화를 해나가자")의
첫 단계다. **이 문서의 어떤 숫자도 운반 성공·모델 성능·조건 간 효율에 대한 결과가 아니다.** 모델 호출은
한 번도 하지 않았다(가짜 모델만 사용). 첫 실제 호출 시험은 조정자(coordinator)가 따로 승인한다.

## 무엇을 만들었나

스크립트 기술(v88 짝 운반: 집기·들기·문 통과·내려놓기, 고정 열거형 짝 상태 통신)은 **그대로** 두고,
그 위에 LLM이 "무엇을 할지"를 정하게 했다. 한 실행기에 세 조건이 있다.

| `--condition` | 이름 | 내용 |
| --- | --- | --- |
| `rule` | C-rule | 모델 없음. 두 로봇이 한가해지면 곧바로 같은 청구(claim)를 낸다(기존 `Runtime`, 수정 없음) |
| `no_comm` | C-llm-nocomm | 각 로봇의 모델이 자기 RGB·정적 지도·주문서·자기 명령 이력만 보고 판단. 메시지 없음 |
| `peer_ko` | C-llm-nl | 위와 같고 r1↔r2 한국어 자유 대화 채널이 추가됨 |

세 조건 모두 고정 열거형 짝 상태(스크립트 기술 내부)는 켜져 있고, 지도·주문·300 SIM초 한도·평가기가 같다.

- **자리(seam)**: `Runtime.step`이 한가한 로봇마다 `team.start`를 부른다. LLM 조건에서는 그 앞에
  `ClaimGate`를 둔다(`harness/pair_llm_runtime.py`). 모델의 `claim`이 *허가(permit)*를 풀어야만 실제
  `Team.start`가 호출된다. 허가 없으면 `CLAIM_NOT_RELEASED`로 거절하고 아무 일도 없다.
  허가가 있으면 **모델이 낸 청구의 인자**(주문·구역·상대)로 원래 `Team.start`를 부른다. 그래서
  잘못된 구역(`WRONG_PAIR_DESTINATION`)·역할·제출 불일치(`PAIR_SUBMISSION_MISMATCH`)도 스크립트 경로와
  같은 곳에서 같은 이유로 거절되고 측정된다.
- **허가 규칙**: `SELF_*`(아직 자세 불확실 등) 거절이면 허가를 유지하고 다음 틱에 다시 시도한다(스크립트
  조건도 매 틱 재시도). 수락·되돌릴 수 없는 거절이면 소진한다. 허가 대기 중 `abort`/`hold`가 받아들여지면
  허가를 취소한다. 짝 작업 도중 중복 청구는 `BUSY:pair_carry:<job>`로 거절한다.
- **재사용**: 존-스터디의 `DecisionScheduler`/`EventScheduler`, SIM 비용 모델 `zone_sim_cost.v1`(잠정),
  `SendLedger`(요청·응답 원문 보존), `GeminiProxyCompleter`, 메시지 전송·`language_report`(한글 비율
  0.9 미만은 전달하되 표시). 스터디 계약이 세 로봇(`ROBOTS`, `team_size=3`)에 고정되어 있어 봉인된 코드를
  고치지 않고 **두 로봇용 프롬프트·입력·시도(trial)를 따로** 두었다(`harness/pair_llm_*.py`).
  "세 로봇 r1, r2, r3" 문구는 두 로봇 문구로 바꾸고 `r3`/`세 로봇`이 남지 않음을 시험으로 고정했다.
- **입력 경계**: 자기 `robot_cam` RGB 1장 + 정적 지도 그림 1장(요청당 정확히 2장), 정적 지도 투영, 주문서,
  자기 발행 명령 이력·자기 판단, 조건이 전달한 메시지뿐이다. 정답 좌표·측정 관절·접촉·성공 신호·공용 top
  카메라·상대 상태 내부는 없다. 평가기(`harness/pair_llm_eval.py`)는 로봇 쪽 어떤 모듈도 가져오지 않는다.
- **번들 기록**: 모델 ID·온도·프롬프트 템플릿 해시·"시드 없음" 문구(프록시 요청에 seed 필드가 없다)·비용
  모델 버전/다이제스트·조건 라벨·v88 기술 번들 해시·소스 해시를 `bundle.json`에 남긴다.
- **시간**: 모든 조건 같은 300 SIM초(`--cap-s`, 스모크는 60). LLM 조건은 토큰 기반 결정적 SIM 비용을
  낸다. 응답 wall 시간은 기록만 하고 SIM에 넣지 않는다.

## 감사 3건 닫음 (시험으로 고정)

- (a) `holding()`/`box.held`는 자기 RGB 추정이다: `visual_box_skill.py`/`zone_own_status.py`는 시뮬레이터를
  직접 가져오지 않고, `held=True`는 양쪽 자기 카메라 부착 점검 통과 뒤에만, `False`는 시각 확인된 해제
  뒤에만 설정된다(`tests/test_pair_llm_inputs.py`).
- (b) `map_bundle('zone_wide_door_geometry_v3')` 공개 투영에는 landmark·tag·pose 키가 없다.
- (c) 전송선 수준 보관: 보존된 모든 요청 본문에서 이미지가 정확히 2장(`CURRENT OWN WRIST RGB` jpeg,
  `STATIC MAP FIGURE` png)이고 해시가 자기 프레임·지도 그림과 일치한다(`tests/test_pair_llm_case.py`).

## 1단계: 배관 시험 (가짜 모델, 물리 없음)

`tests/test_pair_llm_{inputs,runtime,case,eval}.py` 58개. 핵심:

- 메시지가 r1↔r2로만 흐르고 전달은 보낸 호출의 SIM 비용 뒤에 일어난다. 영어 메시지는 전달하되 표시한다.
  `no_comm`에서 `messages`가 있으면 검증 단계에서 거절한다.
- 청구가 `team.start`를 게이트한다: 허가 없이는 시작되지 않고, 가용 자세(시험용 주입)에서는 청구 뒤 스크립트
  짝 기술이 실제로 시작된다. 청구 안 하는 모델은 시작을 막는다(같은 조건 `rule`은 첫 한가한 틱에 시작).
- 원장이 모든 요청·응답을 바이트 그대로 보존하고 보관 요청이 디스크에서 다시 해시된다.
- `rule` 조건의 발행 명령은 `scripts/run_final_pair_v3.run_case`와 같은 런타임·같은 120 SIM초에서
  **바이트 단위로 같다**(2401 캡처, 동일 `actions`).
- 성공은 별도 평가기에서만 나온다. 같은 가짜 빔 궤적에서 세 조건이 같은 판정을 받는다.
- ENOSPC는 `HOST_ERROR`(`failure.class=ENOSPC`)로 분류하고 부분 기록을 남긴다.

## 2단계: 짧은 SIM 스모크 (렌더링 물리, 가짜 모델, 실제 모델 호출 없음)

소스 `b201f777`(커밋·깨끗한 트리), SIM 슬롯 `sim-claude-pair-llm-v97`(owner claude, 비타이밍), `nice +10`,
조건마다 60 SIM초, 시드 911, 지도 `zone_wide_door_geometry_v3`. 원본은 기본 체크아웃
`outputs/pair-llm-v97-smoke/<조건>-60s/`(로컬 보관이며 원격 백업이 아님).

| 조건 | 결과 상태 | 명령(r1+r2) | 모델 호출 | 모델 SIM 비용 | 입력/출력 토큰 | 메시지 | 한국어 | 청구 허가 | wall(s) | 평가기 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule | COLLECTED_UNQUALIFIED | 191+191 | 0 | 0 | 0/0 | 0 | - | - | 93.8 | NOT_IN_ZONE |
| no_comm | COLLECTED_UNQUALIFIED | 191+191 | 12 | 30.8 s | 35970/528 | 0 | - | 2 | 84.2 | NOT_IN_ZONE |
| peer_ko | COLLECTED_UNQUALIFIED | 191+191 | 14(12 완료·2 중단) | 36.2 s | 45008/826 | 4 | 4/4 (1.0) | 2 | 107.9 | NOT_IN_ZONE |

**읽는 법(중요)**: 스모크는 **합성(가짜) 보정과 모든 프레임을 거절하는 시각 작업자**로 돌렸다
(`harness/pair_llm_plumbing.py`, 번들에 `synthetic_plumbing_only`로 표시). v3 측정 보정이 아직 없어
(`measured_calibration`이 PARTIAL을 거절) 제어기가 자기 위치를 모른다. 그 결과 두 로봇은 `look_around`
(7.8 SIM초에 종료)만 하고, `Team.start`는 매 틱 `SELF_UNCERTAIN`(조건당 로봇마다 1069회)로 거절되어 짝
작업이 시작되지 않는다. `rule`도 같은 이유로 시작하지 못한다. 따라서 스모크가 보여주는 것은
**배관**(프레임→호출→응답→청구→게이트→스크립트 기술→물리→평가기, 원장·이미지 2장·비용·한국어 판정 기록,
`rule`/LLM 조건의 같은 한도·같은 평가기)이지 운반이 아니다. 청구가 받아들여져 짝 기술이 시작되는 경로는
1단계 시험(가용 자세 주입)에서만 확인했다.

원본 해시(각 조건 `artifacts.sha256.json`의 sha256): rule `708effbc20cd…`, no_comm `3b3a01aaeb21…`,
peer_ko `306ca258f6fa…`. 번들 해시: rule `9de77e7fb751…`, no_comm `b7cbb28bebc4…`, peer_ko `561cadc29880…`.
10 SIM초 rule 사전 점검(`probe-rule-10s`) 해시 `937f9663d3f9…`. 렌더링 물리 실행은 이 Mac에서 약 0.6배속
(부하 평균 13~40).

## 알려진 한계·위험 (결과 해석 전에 읽을 것)

1. **블라인드 제어기**: 측정 보정·실제 시각 작업자 없이는 어떤 조건도 운반하지 못한다. 진짜 시험은 #363(v96)
   쪽 OpenCV 위치 추정과 측정 보정이 준비된 뒤다.
2. **작업 한도 120 vs 300 s**: 실행기 `job_sim_limit_s=120`이라 짝 작업은 120 SIM초에 `LOCAL_TIMEOUT`으로
   끝날 수 있다. 300초 한도의 의미는 재시도·재청구에 있다.
3. **평가기는 잠정**(`PROVISIONAL_GEOMETRIC_JUDGE_NOT_THE_363_JUDGE`): 빔 궤적만으로 구역 안·들림·내려놓음을
   본다. v88 경로는 `physical_success: None`을 유지한다. #363 판정기가 확정되면 교체한다.
4. **호출 예산 소모**: `pose_uncertain` 이벤트가 `failure` 촉발이 되어 호출 한도(로봇당 12)를 빨리 쓸 수
   있다(가짜 모델 30초 시험에서 확인). 스터디 스케줄러 규칙이라 고치지 않았고, 실제 모델 시험 전에 정할 일이다.
5. **비용 모델 잠정**(`zone_sim_cost.v1` provisional), **시드 없음**(프록시 요청에 seed 필드 없음 → 실제 모델
   실행은 비트 단위 재현 불가, 요청·응답 원문과 해시가 재생 기록), 프록시 할당량 미확인.
6. 허가 규칙(위)은 이 층의 설계 결정이다. 다른 규칙(예: 대기 중 허가 만료)은 비교하지 않았다.
7. 공용 파일 충돌 가능: `scripts/run_ci_tests.py`(패턴 1줄), `tests/test_simulation_workflow_manager.py`
   (카탈로그 개수 +1, 샘플 1줄). 번들 번호 v97은 v94 소각·v95=#365·v96=#363 이후 번호다.

## 재현

```
python3 -m scripts.run_pair_llm --condition peer_ko --expected-source-sha <커밋 SHA> --output <기본 체크아웃 outputs/ 절대 경로> \
    --cap-s 60 --synthetic-plumbing-calibration --sim-slot <슬롯> --lock-owner claude --execute
python3 -m pytest tests/test_pair_llm_inputs.py tests/test_pair_llm_runtime.py tests/test_pair_llm_case.py tests/test_pair_llm_eval.py
```

`--live`는 이 변경에서 거절한다.

## 참고 자료

- 같은 저장소: `harness/zone_study_integration.py`(`IntegratedTrial`), `zone_study_offline.py`(`OfflineTrial`),
  `zone_event_scheduler.py`, `zone_study_decisions.py`, `zone_send_ledger.py`, `zone_study_llm_transport.py`,
  `zone_study_prompts_ko.py`(KO_LANGUAGE), `zone_study_protocol.py`(`language_report`),
  `zone_final_pair_runtime.py`/`zone_final_pair_skill.py`(v88), `scripts/run_final_pair_v3.py`(`run_case`).
- 설계 기록: 이 세션의 `llm_pair_design.md`(옵션 A: 얇은 두 로봇 층, 기존 스케줄러·비용·원장 재사용).
- #363(v96) 실험 README `experiments/2026-10-03-pair-carry-highpose/README.md`: "`run_camera_pair_transport.py`는
  이전 LLM 두 로봇 경로이며 … 새 LLM 제어기로 대체하지 않는다" — 이 PR은 v88 어댑터를 대체하지 않고 그 위에
  결정 층만 얹으므로 일치한다.
- 외부 방법론을 새로 도입하지 않았다(기존 스터디 스케줄러·ledger 재사용). 같은 문제로 두 번 막힌 일은 없었다.
