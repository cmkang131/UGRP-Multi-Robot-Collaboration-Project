# E2E18 속도 수정 v290/v291 (DEV, 기본 off 토글)

기준: origin/codex/e2e18 526c20a2. 분석 근거: 후반 속도 보고서(scratchpad sdk-speedlate-report.md, r52 @ azure3).

## 바뀐 것
| 토글 | 값 | 기본 | 내용 |
|---|---|---|---|
| `stage_physics` | `release_dt1_v1` | off (`pregrasp_dt1_v1` 기존 동작 유지) | 자기 집게 열림 **발행 명령**(servo 1, pulse≥1900)으로 로봇별 닫힘 래치를 해제(두 로봇 모두 열려야 해제). relook_camera/relook 단계는 dt 1 ms. 주행 mapping 2 ms, align 1 ms, 그 외 접촉 단계 0.25 ms는 그대로. 읽는 것은 발행 명령과 단계뿐이며 접촉·관절·자세는 읽지 않는다. dt는 물리 엔진 설정이라 제어기로 새 정보가 흐르지 않는다. |
| `controller_timing` | `phase_v1` | off | `Robot._receive`·`goal.receive`·`observe_beam`·`observe`(벽 분할)·`settled_receive`·`ownmap_record`·`health`·`transport.step`·`host.step_to`·`backend.capture`를 phase별·함수별(calls, wall_s)로 `raw/controller-timing.json`에 1초 주기로 기록(`backend.measure('controller.<이름>')`도 병행). 중첩 구간이라 합이 아니다. 결과·물리 불변. |
| 번들 | `e2e18-v290` = v273 구성 + 두 토글, `e2e18-v291` = v277(`relook_search=view5_restore_v1`) 구성 + 두 토글 | – | 두 토글은 함께만 허용(`SPEED_PHASE_REQUIRES_BOTH_TOGGLES`). 번들 ID 사용 범위는 v290–v291. |

## 속도 감시가 r52에서 경고하지 않은 이유(확인됨)
- 감시 프로세스는 **살아 있었다**(azure3 pid 42039, `scripts.azure_speed_gate watch`, 코드는 HEAD와 동일). v269-r50에는 경고 파일이 있다.
- 원인은 측정 창이다. `e2e-progress.json`의 `sim_s`는 정수 SIM초 단위이고, 30초 창의 Δsim은 5/6/7로 흔들려 wall/SIM이 6.0/5.0/4.29로 튄다. 한도 4.5(=3.0×1.5) 바로 위(4.7~5.6)에서 4.29인 창이 하나만 나와도 `slow_since`가 초기화되어 10분 연속이 성립하지 않는다.
- 재생 증거: r52 log.txt(966행, `r52-wall-sim-phase.tsv`)를 2초 폴링으로 재생하면 창 시작 위상 15~27초(5/10가지)에서 옛 규칙은 끝까지 미발화, 나머지는 wall 3573~3909초에 발화. 새 규칙(`RollingSpeedWarning`, 직전 600초 전체 평균)은 10가지 위상 모두 SIM 910 이전에 발화(시험으로 고정). 실제 r52가 어느 위상이었는지는 직접 복원하지 못했다(위 설명은 재생 가능성과 일치하는 것이지 그 순간의 직접 측정은 아님).
- 추가: `PhaseSpeedWarning`이 e2e-progress의 `phase`로 단계별 누적 wall/SIM을 계산해(≥20 SIM초, ≥120 wall초) 한도(기본 게이트×1.5, `--phase-limits '{"relook":3.5}'`로 단계별 변경)를 넘으면 `SPEED_PHASE_WARNING.json`에 사건·단계 구간 이력을 남긴다. 경고 전용이며 실행을 멈추지 않는다. 30 SIM초 사전 게이트(`PROBE_SIM_S`)는 그대로다. 이 변경은 번들 토글이 아니라 감시 인프라다(실행 결과에 영향 없음).

## 표준 방법 확인(짧게, 인용 URL은 이번 세션에서 열어 보지 않음 = 미확인)
- 속도 감시: 이동 평균/슬라이딩 윈도 비율로 노이즈에 둔감한 임계 경보는 모니터링의 표준 관행이다(Prometheus `rate()`/`avg_over_time` 방식과 같은 개념; 문서 URL 미확인).
- 물리 스텝: MuJoCo `mjOption.timestep`은 접촉 안정성과 속도의 직접 교환이다(문서 URL 미확인). 스텝 크기를 단계별로 바꾸는 방식은 이 저장소의 기존 `pregrasp_dt1_v1`을 확장한 것이다.

## 남은 위험(미검증)
- dt 1 ms 복귀 뒤 바닥 빔 미끄러짐·침투: 직접 검증 없음. 조정자 실행에서 relook 구간의 `setdown.jsonl`·`contacts.jsonl`을 r52(0.25 ms)와 비교해야 한다. 실패 시 .0005를 선택지로 한다.
- `controller_timing`은 계측만이라 wall 단축 없음. 가장 큰 함수 확인 뒤 후속 최적화가 필요하다.
- lower_open(열림 직후)은 접촉 민감 단계라 기존 0.25 ms를 유지한다(relook부터 1 ms). 즉 기대 절감은 relook 구간 물리분(보고서 추정 약 1.5 wall/SIM)이며 실측 아님.
- `tests/test_simulation_workflow_manager.py::test_every_catalog_workflow_has_a_read_only_explicit_plan`은 이 브랜치 기준(526c20a2)에서 이미 `e2e18-arm-clearance-probe` 표본 누락으로 실패한다(내 변경과 무관). 따라서 v290/v291의 카탈로그 계획은 그 시험으로 검증되지 않았다.
