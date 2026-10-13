# E2E18 LLM 기억 보강 — 기본 OFF, DEV draft

Refs #461. 기준 `495b606fe99e6ced0fa1659a9db89324f51e4c4e`, 작업 브랜치 `claude/e2e18-llmmemory`.
Claude의 미커밋 초안·완료된 재생을 Codex가 이어받았다. 기존 실행·원자료를 재실행하거나 덮어쓰지 않았다.

## 원인과 수정

- v321/s61006/r65의 call-0021(555.8 SIM초)은 `own_claim=true`, 새 구간 1, `own_go_sent=false`인데 과거 구간 0의 자연어 GO/ACK가 남아 있었다. memory 초안은 승인된 claim도 기록했지만, 후보에 claim을 계속 제공하고 거절 힌트도 “승인 후 claim”이라고 써서 claim을 다시 고르게 했다. 최종 후보는 현재 dialogue 상태로 이미 완료한 claim·중복 GO/ACK·불가능한 ACK 후보를 제거하고 거절 설명을 구체화한다. 영상 근거가 불충분하면 continue를 선택할 수 있다.
- 자기 결정 최근 8개(sim_s, kind, choice, seg, epoch, accepted/rejected, why)를 다음 요청에 넣는다. 성공의 뜻은 **프로토콜 수락**이다. 원래 호스트 검증과 응답 지연·유효기간 검사는 유지한다. 짧은 vote_ref 거절도 캡처된 구간을 기록한다. 상속된 재생 v0/v1의 `t`/`did` 필드는 원형대로 보존했다.
- `peer_reports[].window`는 실제 수신 시점 구간, `sent_window`는 발신 요청의 구간이다. `received_at_sim_s`와 `previous_segment`를 덧붙인다. 늦게 도착한 이전 구간 메시지는 현재 수신 구간이어도 이전 내용임을 표시한다. 수신 증거가 없는 과거 재생에서는 null로 남긴다. 자연어 본문·통신 경로·상대방 정보는 바꾸지 않는다.
- `own_command_history=[]` 원인은 `harness/s4_llm_host.py`의 대화 전용 `_on_action`이 dispatch 기록 뒤 return하여 기존 `_remember_command`를 건너뛰고, 실제 발행 루프도 이력을 채우지 않았기 때문이다. `compute_budget=lean_v1`은 영상/입자 작업량 옵션으로 이 원인과 무관하다. 별도 `v1_commands`에서 `backend.issue` 이후 자기 발행 방향·속도·요청 지속시간·servo/pan 명령 인자를 기록한다. 동일 인자 반복만 합치며 좌우 반전은 유지한다. 발행 명령을 실제 이동·관절 측정·성공으로 해석하지 않는다.
- 조정자 `cmp/run_complex.py`의 FIXED 우선순위 절을 재사용했다. 실험용 15도/10cm 동작 크기와 고정 카메라 방향 가정은 복사하지 않았다. 이 Gemma 인터페이스는 continue/claim/approve_route/route_vote만 제공한다. 몸 움직임의 충돌·좌우 반복·탐색 방향 후보 필터와 실행 연결은 병행 중인 jevmotion 작업이며, 여기서 구현·검증했다고 합산하지 않는다. [범위 공유](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/461#issuecomment-6140569253).
- 네 통신 조건에 동일 토글을 적용한다. off는 기존 요청을 유지하고 명령·거절·수신 이력을 수집하지 않는다. 자기 RGB·자기 명령·자기 지도·실제 수신 메시지·호스트가 이미 아는 자기 검증 결과만 사용한다.

## 예약 번들

| ID | workflow | 구성 |
|---|---|---|
| e2e18-v330 | 7.223.0 | v324 + `--llm-memory v1`, vote_ref off |
| e2e18-v331 | 7.224.0 | v324 + `--llm-memory v1 --vote-ref v1` |
| e2e18-v332 | 7.225.0 | v324 + `--llm-memory v1_commands`, vote_ref off |

v330과 v331의 모션 설정은 같다. 초안의 v331=v327 조합에는 approach_floor와 clip_hysteresis까지 섞여 있어 제거했다. v333–v334는 미사용 예약이다. 기존 v324–v327 코드/등록 파일은 수정하지 않았다.

## 상속된 실제 모델 재생

10개 실제 실패 시점 × 변형별 10회. old와 vote_ref 요청은 v0·v1 간 각각 **10/10 SHA-256 동일**하여 기존 대조군을 그대로 사용했다. v0 400회, v1 200회, 앞선 1회 pilot 40회를 구분해 보존했다. 이 작업의 추가 모델 호출은 0이다.

| 맥락 | 다음 프로토콜 행동 일치 | GO 필요 사례 | 출력 토큰 중앙값 | 지연 중앙값 |
|---|---:|---:|---:|---:|
| old (v0) | 15/100 | 0/30 | 139 | 6.511 s |
| vote_ref (v0) | 40/100 | 30/30 | 66 | 3.471 s |
| memory 초기 (v0) | 50/100 | 0/30 | 53 | 3.989 s |
| memory+vote_ref 초기 (v0) | 60/100 | 0/30 | 47 | 2.931 s |
| memory 수정 (v1) | 68/100 | 0/30 | 44 | 3.089 s |
| memory+vote_ref 수정 (v1) | 79/100 | 9/30 | 42 | 2.936 s |

판정은 저장 요청의 dialogue 상태에서 가능한 다음 GO/ACK/continue와 출력의 일치 여부다. 실제 RGB 그립 정답, 전체 메시지 계약, 정상 finish_reason, 라이브 응답 시점의 게이트 수락, 물리 성공까지 검사한 수치가 아니다. 모든 600개 비교 행은 HTTP 200으로 기록되어 있으나 상속 도구가 finish_reason/원 usage/cost를 저장하지 않았다. call-0021은 v1 memory와 결합형 모두 claim 10/10, 정답 0/10이다. 이를 고친 **최종 Codex 후보의 새 모델 일치율은 아직 미측정**이다. 서로 다른 프롬프트 버전의 수치를 합산하지 않는다.

상속 도구는 `openrouter_v1`, `google/gemma-4-31b-it`, DeepInfra 유료 경로였다. 무료 AI Studio 재생으로 표시할 수 없고 정확한 비용도 남아 있지 않다. 최종 재생 도구는 기존 Mac 릴레이만 사용하고 유료/미확인 provider는 별도 명시적 허가 없이는 POST 전에 거부한다. 현재 확인된 릴레이도 유료 경로여서 추가 호출하지 않았다.

## 검증과 남은 실행

```sh
python3 -m pytest -q -rs tests/test_e2e_llm_memory.py tests/test_e2e_vote_ref.py tests/test_e2e_s4_live.py
```

62 passed, 1 skipped (29.96 s). 건너뛴 것은 기존 `test_native_rgb_mapping_and_model_snapshot_no_scene_input`: 외부 작업 금지 fixture의 `sys.modules['mujoco']=None` 때문에 import 불가였다. 실제 물리/렌더 실행은 없다. 실제 call-0021 텍스트 fixture에서 일반·vote_ref 두 형태 모두 claim과 ACK가 후보에서 제거되는 것을 확인했다. 네 통신 조건, 자기 이력 격리, 지연 수신, 실제 명령 인자·좌우 반전, 세 번들 등록 검사를 포함한다.

최종 후보용 입력 20개는 `outputs/llmmemory-candidate-v3/`에 준비했다. 아직 POST하지 않았다. 재생을 실행할 수 있는 적합한 Mac 릴레이가 제공되면 다음과 같이 **새 후보만** 검증한다(대조군 재실행 없음).

```sh
python3 experiments/2026-10-13-e2e18-llmmemory/replay_memory.py run outputs/llmmemory-candidate-v3 \
  --reps 10 --threads 4 --variants memory,memory_vote_ref \
  --proxy-url http://127.0.0.1:PORT/v1/chat/completions
```

VM3 읽기 점검은 `vm3-admission.json`에 있다. 실행 폴더 0개, 디스크 78,156,304,384 bytes 여유지만 uptime 27,785.88 s로, 기존 실행기의 최소 cap 900 s + 종료 여유 1,200 s를 더하면 8시간(28,800 s)을 넘는다. 따라서 새 실행 0개, 속도 게이트/GO·ACK 통과/완주 모두 미검증이다. VM 재시작·정지·할당 해제는 감독자 소유이며 이 작업에서 수행하지 않았다.

감독자가 실행 수명·릴레이를 갱신하고 최종 재생 효과를 확인한 뒤 seed 61006의 v330·v331 두 개만, 총 12개 미만/자기 몫 최대 2개로 제출한다. 기존 `scripts.azure_speed_gate start`(30 SIM초, 한도 3.0), `remote_run_finish.py`, 기존 fetch-lite/보관 절차를 사용한다. 이 draft는 병합하지 않는다.

## 기록과 재현

- `saved-replay-summary.json`: 버전·사례별 n/N, 지연/토큰, 원본 경로와 SHA-256. `summarize_saved.py`는 네트워크 없이 재집계한다.
- `replay-text-evidence.json.zst`: 상속 요청 80개 텍스트+이미지 SHA-256, 모델 응답 640개(pilot 40 포함). 원 요청의 이미지 data URL만 이미지 바이트 해시로 치환했다. 압축 해제 바이트 일치·전체 SHA-256은 `evidence-manifest.json`에서 확인했다. 기존 Mac 원본은 보존했다.
- `call-0021-fixture.json`: 실제 원 요청 텍스트/이미지 해시/기존 결정 로그. 시험에 쓰며 새 의미 라벨이나 가짜 물리 성공을 추가하지 않았다.
- 원 실행: VM3 `~/ugrp-sim/runs/{e2e18-v304-s61006-r64,e2e18-v320-s61006-r65,e2e18-v321-s61006-r65,e2e18-v322-s61006-r65,e2e18-v323-s61006-r65}/raw/`. 이번 작업은 상속 저장본만 재집계했고 원 실행 전체의 원격 보관 상태를 재확인하지 않았다.

## 참고 자료

아래 원문/초록은 2026-10-13 직접 확인했다. 방법의 근거이며 논문의 성능을 본 연구 결과로 옮기지 않는다.

- [ReAct, Yao et al.](https://arxiv.org/abs/2210.03629): 행동과 관찰을 번갈아 반영하는 구조. 여기서는 숨은 추론 전문 대신 구조화된 자기 행동/호스트 피드백만 보존한다.
- [Reflexion, Shinn et al.](https://arxiv.org/abs/2303.11366): 피드백을 에피소드 기억에 남겨 후속 판단에 사용. 여기서는 자유 생성 반성 대신 검증 코드와 고정 힌트를 쓴다.
- [SayCan, Ahn et al.](https://arxiv.org/abs/2204.01691): 가능한 스킬과 언어 선택의 결합. 여기서는 현재 프로토콜 계약으로 후보를 제한하며 학습된 affordance 성능을 주장하지 않는다.
- [Inner Monologue, Huang et al.](https://arxiv.org/abs/2207.05608): 닫힌 루프 언어 피드백을 계획에 반영. 논문의 성공 검출기와 달리 여기서는 물리 성공·접촉 정답을 제어 입력에 주지 않는다.
- [Lamport, Time, Clocks, and the Ordering of Events in a Distributed System](https://lamport.azurewebsites.net/pubs/time-clocks.pdf): 발신·수신 사건과 인과 순서 구별의 표준 근거. LLM 다중 에이전트의 별도 성능 검증으로 인용하지 않는다.
