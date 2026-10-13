# E2E18: 코드 프로토콜 상태기계와 Gemma 대화 분리

Refs #461, #463, #466, #470. code_v1 소스 `269dacff`; draft #470. 브랜치 `claude/e2e18-llmmemory`, 재생 실행 소스 `6ec1ab8e`.

**2026-10-13 후속: 새 v346 기본은 `dialogue_decider=code_v1`.** 동일 저장 10사례×10회에서 코드 계약 선택 **100/100**, GO 필요 **30/30**, call-0021/0023/0025 각각 **10/10**이다. d1 최종 82/100·GO 12/30·call-0021 0/10은 비교 기록으로 유지한다. 기본 CLI는 과거 번들 재현을 위해 gemma_v0를 유지하며, 새 번들은 code_v1을 명시한다. d1/Jev를 자동 호출하거나 fallback하지 않는다.

## code_v1 후속 구현·판정

- 기존 `Dialogue.check_action`의 상태 전이 순서를 코드로 선택한다: 현재 유효 창에서 자기 GO 미등록 → GO, 자기 GO 등록 + 현재 peer_go_ref + 미등록 ACK → ACK, 그 외 대기. 경로 수신 승인·역할 claim도 현재 계약으로 한 번만 선택한다. 재요청의 거절 이력은 승인으로 간주하지 않으며, 구간 변경 뒤 옛 GO·메시지 ID를 참조하지 않는다. 최종 호스트의 영상/epoch 유효기간·상호 합의 검증은 유지한다.
- live에서는 자기 RGB의 기존 `held_signature` 면적/이전 영상 IoU와 **자기 발행** servo 명령만으로 grip 가설을 만든다(기존 `BodyGate.grip_state` 규칙 재사용). camera posture가 같을 때의 signature 급변은 slipping이고, 같은 영상 재요청은 경고를 지우지 않는다. 집게 close 명령만으로 holding을 만들지 않는다. 정렬 범주는 자기 영상 정렬기의 통과 이력이며 새 물리 성공 관측이 아니다. 측정 관절·접촉·평가 상태는 읽지 않는다.
- 현재 자기 slipping/not_held/misaligned 또는 열린 집게 명령이면 투표를 대기한다. 수신 10초 이내·생성 20초 이내·현재 구간의 명시적 stop/danger/slipping/please wait와 정형 blocked도 대기한다. 일반적인 “waiting for mutual agreement”는 대기 요청으로 오인하지 않는다. 수신 시각을 모르는 과거 메시지는 최신 경고/투표로 승격하지 않는다. 원문은 수정하지 않는다.
- **저장 10사례에는 위 grip/alignment 범주가 없으므로 100/100을 unknown으로 보존했다.** code_v1은 기존 호스트 계약과 같이 현재 창의 GO를 프로토콜 의사 표시로 허용하며, unknown을 holding으로 바꾸지 않는다. 따라서 100/100은 다음 계약 행동의 일치이지 영상으로 파지 성공을 증명한 결과가 아니다. d1의 별도 unknown 차단 정책과 조건이 다르며, 기존 d1 판정을 실제 파지 오판으로 해석할 수 없다. 실제 파지 안전/GOACK 창 통과는 감독자 live 실행에서 확인해야 한다.
- Gemma는 고정 행동을 받아 `{text: ...}`만 쓴다. 코드 결과와 참조는 수정할 수 없으며, 추가 action 필드는 거절한다. 코드와 d1은 동일 메시지 작성/응답 조립 경로를 공유한다. no_comm은 실제 메시지 입력/출력과 Gemma 호출이 없고, 정형 조건은 기존 고정 스키마를 쓰며, 자유/리더 조건만 Gemma 문장을 그대로 전송한다. code_v1 경로는 D1 생성자·Keychain 조회·결정 API를 호출하지 않는다.
- 최종 코드 재생 `outputs/llmmemory-code-replay-v3`: 결정 모델 **0회**, 결정 비용 **$0**, 로컬 규칙 선택 중앙 **0.146 ms**. 이것은 로컬 Python 변환 시간이며 Gemma/network/시뮬레이션 속도가 아니다. 이번 코드 재생은 Gemma를 호출하지 않았다. 앞선 d1 경로의 실제 Gemma 100/100 무모순 검증과 새 코드 경로의 모의 메시지 시험을 구분한다.
- 불일치 **0/100**. 새로운 독립 장면 100개가 아니라 이미 사용한 **10개 입력의 결정론적 10회 반복**이며 확증 자료가 아니다. 초기 code 재생 v1/v2도 100/100·GO30/30, 원본을 별도 보존한다. ACK 양성은 실제 호스트 검증기를 거친 단위 시험으로 확인하며 저장 코호트에는 없다.

재현: `python3 experiments/2026-10-13-e2e18-llmmemory/replay_code.py --output outputs/NEW_CODE_REPLAY`

새 번들 **e2e18-v346 / workflow 7.239.0** = v332 + `--dialogue-decider code_v1`. 번호는 main 및 열린 PR 원격 전체 최대 v345 확인 뒤 #461 코멘트 6141964852로 예약했고 감독자가 6142022016에서 확인했다. 모델 옵션을 켰던 v338의 ID/워크플로는 보존한다. 감독자가 실행할 때 기존 v332 관리 옵션에 `--dialogue-decider code_v1`을 적용하고, 같은 소스 Mac S4 릴레이에도 이 옵션을 지정해야 한다. receipt 소스 해시와 등록 loopback 주소 검증은 공통 적용한다. VM을 직접 조작하지 않았다. 몸 code_v1과 결합하려면 별도 새 ID/등록·부모 검증이 필요하며, 두 옵션만 임의로 덧붙여 v346으로 제출하면 안 된다.

아래 d1 구현/결과는 **기존 비교 기록**이다.

관련 3개 시험 파일 최종 **78 passed, 1 skipped (38.26 s)**. 건너뛴 항목은 외부 작업 금지 fixture의 mujoco import 차단이다. 네 통신 조건·Keychain/결정 호출 0·Gemma 행동 필드 주입 거절·현재 GO/ACK 실호스트 수락/중복 거절·소스 receipt·v346 등록을 검사했다. `code-validation.txt`와 `code-verification.json`에 범위를 기록했다.

검증 기록: `code-replay-summary.json`, `code-replay-evidence.json.zst`, `code-evidence-manifest.json`, `code-number-reservation.json`. 모든 개발 재생 v1/v2/v3(각 100회, 전부 일치)를 보존하며 최종 비교 분모는 v3 100회다. 원 요청/이미지 해시와 라벨 없는 실제 코드 입력, 선택 결과 전부를 압축·해제 SHA-256 검증했다.

## d1 비교 구현 (기존 기록)

- `dialogue_decider=gemma_v0`가 기존 기본값이며 `d1_v1`은 당시 추가한 비교 경로다. **d1 자기 RGB 범주 판정 → d1 프로토콜 행동 선택 → Gemma 문장 작성** 순서다. 장면당 d1 HTTP 2회이며, Gemma는 영상 해석/행동 선택을 하지 않는다.
- d1은 과제·역할·현재 프로토콜 단계, 자기 grip/alignment 범주, 자기 결정 최근 8개와 accepted/rejected/why, 자기 발행 명령, 실제 파트너 메시지 원문과 수신 시각/나이/이전 구간 표시, 현재 peer GO 참조를 받는다. 두 d1 단계 모두 동일한 자기 카메라를 받는다. unknown/not_held/slipping이면 코드가 GO/ACK 후보를 제거한다.
- 현재 계약으로 이미 승인된 claim, 중복 GO/ACK, 자기 GO/현재 peer 참조 없는 ACK, 오래된 영상/epoch 후보를 제거한다. d1은 남은 후보를 선택한다. 새 구간은 투표만 초기화하며 claim은 유지한다. GO는 자기 준비 투표이므로 파트너 GO나 양쪽 ACK를 선행 조건으로 요구하지 않는다. 최종 호스트 계약·유효기간 검증은 그대로다.
- Gemma는 고정 행동과 자기 상태를 받아 `{text: ...}`만 작성한다. 행동·구간·참조·허용 수신자·경로 계약은 캡처된 값으로 구성하고 Gemma가 추가 행동 필드를 내면 거절한다. 자유 메시지 본문은 수정하지 않고 다음 d1 맥락에 전달한다. no_comm에서도 d1을 호출하고 송수신 메시지는 빈칸이며, 정형 조건은 기존 enum 스키마를 유지한다. 자유/리더 조건의 언어·통신 토폴로지도 기존 계약을 따른다.
- d1 Choice는 최소 2개 라벨이 필요하다. 프로토콜 대기 `WAIT`와 시각/안전 불확실 대기 `WAIT_UNCERTAIN`은 모두 기존 `continue`로 실행된다. 후보 수를 맞추려고 불가능한 투표를 넣지 않는다.
- live 실행은 기존 `scripts/s4_proxy_relay.py --dialogue-decider d1_v1` 경로만 허용한다. d1 키는 Mac Keychain을 Python subprocess 안에서 읽고 전송 헤더 외에 기록하지 않는다. 릴레이 identity/소스 해시/멱등 응답 기록을 유지한다. 서버도 d1 소스 해시를 검사하고 receipt에 지정된 기존 등록 loopback 포트 18391/18393 중 하나만 사용한다. 실제 VM/터널/기존 릴레이 프로세스는 이번 변경에서 조작하지 않았다.

## 기억 보강과 원인

call-0021은 이미 claim이 승인됐지만 과거 seg0 GO/ACK와 반복 claim 거절이 새 seg1 요청에 함께 노출됐다. 초안의 모호한 거절 힌트·과도한 후보를 현재 상태와 명시적인 거절 사유로 고쳤다. `own_decision_log`의 accepted는 프로토콜 수락이며 물리 성공이 아니다. `peer_reports[].window`는 실제 수신 구간, `sent_window`는 발신 구간이고 본문은 그대로다. 과거 저장 자료에서 수신 시각이 없으면 null로 남기며 만들어 넣지 않는다.

`own_command_history=[]`는 대화 전용 `s4_llm_host.Trial._on_action`이 dispatch 기록 후 return하여 기존 `_remember_command`를 건너뛰고 실제 발행 루프도 이력을 채우지 않았기 때문이다. compute_budget/lean과 무관하다. `v1_commands`가 `backend.issue` 뒤 자기 발행 방향·속도·요청 시간·servo/pan 명령을 기록한다. 같은 명령만 합치며 좌우 반전은 보존한다. 측정 관절·접촉·실제 이동 성공은 넣지 않는다.

## 실행 번들

| ID | workflow | 구성 |
|---|---|---|
| e2e18-v330 | 7.223.0 | v324 + llm_memory v1 | **10/10** |
| e2e18-v331 | 7.224.0 | 같은 v324 + llm_memory v1 + vote_ref v1 | **10/10** |
| e2e18-v332 | 7.225.0 | v324 + llm_memory v1_commands | **10/10** |
| **e2e18-v338** | **7.231.0** | v332 + dialogue_decider d1_v1 |

v338은 원격 main·열린 PR의 최대 v337 확인 후 예약했다. 부모 브랜치의 `version-reservation-340.json`도 338/339를 다른 작업 예약으로 보존한다. v338의 몸 제어는 v332 그대로다. 몸 스킬 선택/안전 후보 필터는 #462 범위이며 여기의 프로토콜 재생을 몸 제어 검증으로 합산하지 않는다. #463은 감독자가 07:56 UTC에 병합했으므로 이 후속 변경은 별도 draft PR로 연결한다. 작업자는 PR 병합·VM3 제출을 하지 않는다.

## 사례별 비교

기존 label은 저장 dialogue의 다음 프로토콜 행동이다. **현재 RGB가 실제로 파지를 증명한다는 정답은 아니다.** 같은 원 요청·이미지를 사용했고 예전 old/vote_ref 대조군은 재호출하지 않았다. 숫자는 각 10회 중 일치 수이며 실패를 제외하지 않았다.

| 사례 | 기준 행동 | Gemma 옛 맥락 | Gemma 기억 | Gemma 기억+ref | d1 수정 전 | d1 최종 | 문장 일치 | code_v1 계약 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| e2e18-v304 / call-0014-r1 | continue | 5/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v320 / call-0014-r1 | continue | 4/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v321 / call-0020-r2 | continue | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v321 / call-0021-r1 | GO | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 10/10 | **10/10** |
| e2e18-v321 / call-0023-r1 | GO | 0/10 | 0/10 | 0/10 | 9/10 | 2/10 | 10/10 | **10/10** |
| e2e18-v321 / call-0024-r2 | continue | 0/10 | 8/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v321 / call-0025-r1 | GO | 0/10 | 0/10 | 9/10 | 0/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v321 / call-0026-r2 | continue | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v322 / call-0014-r1 | continue | 6/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |
| e2e18-v323 / call-0018-r1 | continue | 0/10 | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** |

| 전체 | | 15/100 | 68/100 | 79/100 | 79/100 | **82/100** | **100/100** | **100/100** |
| GO 사례만 | | 0/30 | 0/30 | 9/30 | 9/30 | **12/30** | 30/30 | **30/30** |

이전 Gemma-only vote_ref 40/100(GO 30/30), 초기 memory 50/100(GO 0/30), 초기 결합 60/100(GO 0/30)도 `saved-replay-summary.json`에 별도 보존했다. 이 결과는 모두 Gemma가 행동을 결정하던 구조의 기록이다.

## 지연·비용·전체 실패 기록

- 최종 100회: d1 영상 100/100 + d1 결정 100/100 + Gemma 문장 100/100 정상 응답. Gemma 모델 `google/gemma-4-31b-it`, provider DeepInfra, finish_reason=stop 각각 100/100이다. d1 두 단계 합산 지연 중앙값 **1.102 s**, Gemma **0.896 s**, 전체 **2.078 s**. Gemma 출력 토큰 중앙값 **22.5**. 옛 Gemma는 6.511 s/139 tokens, 기억+ref는 2.936 s/42 tokens였으나 동일 시각 부하 비교는 아니다.
- 최종 응답 usage.cost 합: d1 **$0.02567884**(200 HTTP), Gemma **$0.01124542**(100 HTTP), 합 **$0.03692426**. 청구 콘솔 대조는 하지 않았다. 기존 Gemma 재생 비용은 저장되지 않아 미확인이다.
- 첫 d1 100회는 79/100(GO 9/30)이었고 후속 Gemma 요청 100회가 잘못된 멱등 키 때문에 **릴레이 HTTP 400**으로 거절됐다. 이 단계 upstream Gemma 호출은 0이다. 실제 Journal 통과/캐시 시험과 SHA-256 키로 고쳤다. 이 실패도 `d1-replay-summary.json`과 원문에 전부 남겼다.
- 첫 d1은 독립 질문을 한 번에 줘 GO와 grip=unknown이 함께 나온 경우가 있었다(0023의 6/10). 영상 범주를 먼저 판단해 다음 결정 후보에 반영하는 두 단계로 고쳤다. 최종 GO 12회는 모두 해당 시점 d1 파지 범주 holding이었다.
- 별도 개발 pilot은 d1 5회(4 정상, 1 HTTP 422: 단일 후보), Gemma 1회 정상이다. **첫 실패 배치·pilot까지 이번 작업에서 응답으로 확인된 전체 비용은 $0.06257467**이다. pilot과 최종 100회를 성공률 분모로 섞지 않는다.

## d1 비교의 남은 문제

call-0021은 최종 10/10 모두 grip=unknown으로 판정되어 GO 후보가 제거됐다. 저장 자기 영상에서 빔이 화면 대부분을 차지하고 집게가 명확하지 않음을 직접 확인했다. call-0023은 holding 2/10·unknown 8/10, call-0025는 holding 10/10이었다. 따라서 남은 정체는 단순 JSON/참조 오류만이 아니라 **허용 영상으로 현재 파지를 판정할 수 있는지**에 걸려 있다. 여기서 실제로 잡고 있다는 평가 정답·접촉·명령 성공을 입력해 GO를 강제하지 않는다.

Gemma 문장 100개를 Codex가 전수 판독했다. 현재 WAIT 중 과거 승인 GO를 설명하는 문장은 현재 새 GO 선언과 구분했다. **행동/현재 프로토콜과 무모순 100/100**이며, 파지 표현의 물리적 진실성이나 독립 사람 평가가 아니다. ACK를 선택해야 하는 사례는 이 코호트에 없으므로 ACK 실호출 정확도는 미검증이다. 네 통신 조건은 단위 시험으로 연결을 확인했고 실제 provider 100회는 저장 peer_en 사례다. 라이브 응답 유효기간·GO/ACK 통과·물리 성공은 감독자 실행에서 별도 검증해야 한다.

## d1 비교의 검증·재현·보존

부모 `067ef151`의 기존 몸 제어/조합 변경과 연결부를 통합했다. 보호 대상 파일의 부모 대비 차이는 없으며(`e2e18_v32x.json`은 양쪽 모두 없음), 재생의 영상 요청·결정 요청·Gemma 요청·최종 응답 재구성이 각각 100/100 동일함을 확인했다. 관련 시험은 아래 3개 파일만 한 pytest로 실행했다: **69 passed, 1 skipped (31.41 s)**. 건너뛴 기존 native RGB 시험은 외부 작업 금지 fixture의 mujoco import 차단 때문이다.

```sh
python3 -m pytest -q -rs tests/test_e2e_dialogue_decider.py tests/test_e2e_llm_memory.py tests/test_e2e_s4_live.py
python3 experiments/2026-10-13-e2e18-llmmemory/replay_d1.py prepare outputs/NEW_REPLAY
python3 experiments/2026-10-13-e2e18-llmmemory/replay_d1.py run outputs/NEW_REPLAY --proxy-url http://127.0.0.1:PORT/v1/chat/completions
python3 experiments/2026-10-13-e2e18-llmmemory/replay_d1.py report outputs/NEW_REPLAY
```

재생은 승인된 유료 Mac OpenRouter 릴레이를 확인한 뒤 사용한다. 저장 장면 재생의 d1 호출만 Mac에서 Keychain을 읽어 직접 API를 사용하며 live 로봇은 Mac 릴레이만 사용한다. 기존 완료 배치를 다시 실행할 이유는 없다.

- `d1-replay-summary.json`: 두 배치·pilot·사례별 분모·비용·지연 및 채택 불가 판정.
- `d1-message-audit.json`: 문장 100개·선택 행동·판독 이유·텍스트 해시.
- `d1-replay-evidence.json.zst`, `d1-evidence-manifest.json`: 원문 요청·응답·실패, 이미지 SHA-256, 원본 566파일의 위치/크기/해시. 압축 해제 바이트·전체 해시 검증 완료. 원 이미지와 Mac 원자료는 보존했다.
- `d1-verification.json`, `d1-validation.txt`: 시험 범위·실행 소스/프롬프트 해시. 상속 기록 `saved-replay-summary.json`, `replay-text-evidence.json.zst`, `call-0021-fixture.json`도 유지한다.
- 원 실행은 VM3 `~/ugrp-sim/runs/{e2e18-v304-s61006-r64,e2e18-v320-s61006-r65,e2e18-v321-s61006-r65,e2e18-v322-s61006-r65,e2e18-v323-s61006-r65}/raw/`. 현재 원격 보관 상태는 재조회하지 않았다.

## 참고 자료

아래 원문/초록은 2026-10-13 직접 확인했다. 방법의 근거이며 논문의 성능을 본 연구 결과로 옮기지 않는다.

- [ReAct, Yao et al.](https://arxiv.org/abs/2210.03629): 행동과 관찰을 번갈아 반영하는 구조. 여기서는 숨은 추론 전문 대신 구조화된 자기 행동/호스트 피드백만 보존한다.
- [Reflexion, Shinn et al.](https://arxiv.org/abs/2303.11366): 피드백을 에피소드 기억에 남겨 후속 판단에 사용. 여기서는 자유 생성 반성 대신 검증 코드와 고정 힌트를 쓴다.
- [SayCan, Ahn et al.](https://arxiv.org/abs/2204.01691): 가능한 스킬과 언어 선택의 결합. 여기서는 현재 프로토콜 계약으로 후보를 제한하며 학습된 affordance 성능을 주장하지 않는다.
- [Inner Monologue, Huang et al.](https://arxiv.org/abs/2207.05608): 닫힌 루프 언어 피드백을 계획에 반영. 논문의 성공 검출기와 달리 여기서는 물리 성공·접촉 정답을 제어 입력에 주지 않는다.
- [Lamport, Time, Clocks, and the Ordering of Events in a Distributed System](https://lamport.azurewebsites.net/pubs/time-clocks.pdf): 발신·수신 사건과 인과 순서 구별의 표준 근거. LLM 다중 에이전트의 별도 성능 검증으로 인용하지 않는다.

- [RoCo](https://arxiv.org/abs/2307.04738): 로봇 간 대화와 실행 가능성 피드백으로 협업 계획을 수정한다. 여기서는 원문 대화와 호스트 프로토콜 거절만 사용하며 논문의 환경 피드백 전체를 허용 관측으로 간주하지 않는다.
- [CoELA](https://arxiv.org/abs/2307.02485): 분산 관측·유료 통신에서 지각/기억/실행을 모듈로 연결한다. d1/Gemma 분리의 성능을 입증한 논문은 아니다.
- [Liquid 공식 decision model 문서](https://docs.liquid.ai/lfm/models/decision-models): 고정 선택지의 결정과 자유 텍스트 생성을 구분한다. [공식 d1 vision 예제](https://www.liquid.ai/blog/d1-decision-model)는 `images` data URL 입력을 확인한다. 실호출에서 Choice는 최소 2개 라벨을 요구해, 둘 다 기존 continue인 프로토콜 대기/시각 불확실 대기로 표현한다. 불가능한 투표를 후보로 넣지 않는다.
- [Google Gemma 대화 문서](https://ai.google.dev/gemma/docs/gemma_chat): 매 호출에 관련 과거 맥락을 명시적으로 공급한다. [Google 공식 프롬프트 지침](https://ai.google.dev/gemini-api/docs/prompting-strategies): 역할·제약·출력 형식을 구체적으로 지정한다. 후자는 Gemini 지침이며 Gemma 성능 보장은 아니다.

코드 상태기계의 직접 근거는 [`harness/e2e_dialogue.py`](../../harness/e2e_dialogue.py)의 `check_action`/`allowed`와 [`harness/e2e_live_transport.py`](../../harness/e2e_live_transport.py)의 합의 창 진입이다. 자기 영상 가설은 [`harness/e2e_body_controller.py`](../../harness/e2e_body_controller.py)의 `grip_state`를 재사용한다. main 지침과 #467 갱신안을 읽었고 17:50 사용자 지시에 따라 코드 기본을 우선 적용했다.
