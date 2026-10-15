# crate16 — FIX_FIRST 수정, 기본 OFF

기준 `d3571214`(crate15, PR #500). `--crate-profile crate16_v1`에서만 새 동작을 켠다. 이전 프로필·큐는 유지한다. **저장 입력 검증만 완료했으며 물리 성공·VM 속도·관문·학습은 미검증/미승인이다.** 기준 SHA의 CI는 **CI 미실행**; 후보 CI 상태는 push 뒤 PR에서 별도 확인한다.

수정: 손잡이가 가려져도 `seen_t`로부터 5.2초 이내의 상자 자세는 직사각형 3개로 유지한다. 기억이 끝난 search/relook은 crate14처럼 벽만 검사하고 원판 대체를 쓰지 않는다. 여유 안에서 시작하면 장애물별 여유를 줄이지 않는 후퇴·회전을 허용한다. 잡은 화물은 기존 `held_object_hidden_v1` 입력 제거를 유지하고, 틱 사이에 기하 캐시를 버린다. 77990 r2 틱 45·70은 [route-fixtures.json](route-fixtures.json)에 추가했다(회전 유지, 측면 경로 각각 7/7).

A*는 패드/목표당 heap 확장 96개, 같은 입력 틱의 모든 목표·상대 제거 진단을 합쳐 384개로 제한한다. 같은 기하의 segment·clearance·path 결과를 캐시한다. 15mm 패드로 먼저 찾고 실패할 때만 5mm로 재시도하며 발행 펄스는 5mm와 탈출 규칙으로 다시 검사한다. 막힌 대기는 상대 때문에 시계가 멈춰도 12 SIM초 뒤 검사된 후퇴 1초와 다른 시점 재관측을 시도하고, 이동·유효 경로 회복이 없으면 총 24초에 인계한다. 틱 원장에 `teacher_prepare_s`, `teacher_step_s`, 합계 `teacher_compute_s`와 누적 시간을 쓴다. 새 시험을 PR CI 목록에도 추가했다.

검증: 관련 시험 **104 통과**, 새 동작 OFF **1,424/1,424** 일치. 같은 저장 후보 **196/196** 경로를 찾았고 모두 15mm 패드였다. 2mm/0.5° 간격에서 독립 polygon 거리로 잰 경로별 최소 직사각형 간격(mm)은 **최소 15.550 / 중앙값 18.906 / p95 28.718 / 최대 28.728**이다. 이는 측정 위치 오차나 팔 전체 sweep의 보장이 아니다. 도달 불가 빈 목표는 **192확장·0.0288초**로 종료했다.

| 저장 실행 | 로봇 틱 | 틱 계산 최대(s) | 계산 합계(s) |
|---|---:|---:|---:|
| 77990 | 290 | 0.23042 | 9.98023 |
| 79314 | 282 | 0.05299 | 0.44189 |
| 79317 | 232 | 0.08810 | 0.74073 |
| 79450 | 346 | 0.00771 | 0.38590 |
| 79451 | 274 | 0.02801 | 0.74415 |
| 전체 | 1424 | **0.23042** | **12.29290** |

시간은 prepare+step, 재생 도구의 exact IK/lift 캐시를 사용한 Mac 수치 측정이다. 원래 발행 명령 이력과 저장 관측을 고정한 비교여서 새 행동 뒤 물리를 재현하지 않는다. 새 명령이 달라진 틱은 실행별 142/137/53/43/62개이며, 원래 실패 이력을 주입하므로 인계·정렬 실패가 남는다([요약](summary.json)의 모든 실행 포함). 저장 구간은 11.5–17.2 SIM초라 실제 VM의 첫 30 SIM초 점검은 남아 있다. 입력 경계 감사는 각 실행 `held_world_reads=0`, `invisible_measurements=0`이며 측정 어댑터의 정확도 인증은 아니다.

새 큐: 기존 재현 77990·79314·79317·79450·79451 + 신규 **79900–79907·79910–79911**. 로컬 10,633 JSON·저장 재고·실행 이름에서 신규 범위 충돌 0; 79700/79800번대는 solo 큐가 사용 중이라 채택하지 않았다. 정적 시작 제안 21개 중 9개 거부, 완성 12개 중 벽 근처 2개 제외(원본 보존). 정적 kinematics/LOS만 사용했고 physics/forward/render는 차단했다. live 재고는 운영자가 재확인해야 한다. push된 clean SHA에서 [queue.py](queue.py)가 `20261015-crate16-diag-<sha8>.json`을 새로 쓰고 이전 큐 해시를 확인한다. 승인·실행·관문·학습 플래그는 모두 false다.

재현(프로젝트 루트, pytest는 단일 프로세스로 먼저 실행):

```sh
bash experiments/2026-10-15-crate16/check.sh /private/tmp/crate16-recheck
# 큐 생성: 최종 clean·push SHA에서만, 기존 큐는 수정하지 않는다.
python3 experiments/2026-10-15-crate16/queue.py --sha "$(git rev-parse HEAD)"
```

원본/세부 기록은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate16-d3571214-final/`의 `verification.json`, `ticks.jsonl`, `route-retests.json`, `pytest.xml`. 원본 위치·전체 SHA-256은 `verification.json`, 최종 소스·시험·자료 해시는 `summary.json`에 있다. raw는 로컬 보관이며 원격 백업을 뜻하지 않는다. 새 물리 실행·렌더·원격 호스트 접속·모델 호출은 0이다.

## 참고 자료

- [crate15 기록·원장 재생](../2026-10-15-crate15/README.md), [이전 재생기](../2026-10-15-crate15/replay.py): 원래 발행 이력 고정 및 수치 캐시의 근거.
- [학생 기억 시간](../../harness/grasp_act_contract.py), [가시 입력 생산자](../../harness/grasp_act_visible_world.py), [crate14 제약](../../sim/grasp_act_visible_route.py): 5.2초, `seen_t`, no-closer 탈출 경계.
- Sonnet 독립 검토의 `side.py`, `stuck.py`, `paths.py`, `worst.py`를 읽었다. 원본은 사용자 지정 `/private/tmp/claude-501/-Users-changmin-projects-ugrp/71c0cb65-eb0b-48a4-a56c-4c39977a7c14/scratchpad/rv/`에 보존했으며 수정하지 않았다. 독립 거리 재검사 원리를 [verify.py](verify.py)에 포함했다.
