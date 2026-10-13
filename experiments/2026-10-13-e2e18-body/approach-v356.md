# v356: 접근 개선 + 감독의 관측 목표 소실 복구

Refs #461, PR #471. **v356 / 7.249.0 = v354 + `--approach-efficiency regulated_v1`**, 일반 기본off. 비교 기준은 v354이고, v350/v351 단독 제출 요청은 철회했다. 감독의 `504c5d0f`를 통합했으며 기존 `boundary_lifecycle=abort_v1`을 그대로 사용한다. 새 탐색 복구를 중복 구현하지 않는다.

## 변경 이유와 실행 구성

감독자는 r74/r75에서 `view_active=True, target=None` 상태의 공통 예외를 원본으로 확인하고 동일 결함 실행을 교체했다(#461 2026-10-13 09:47/09:50 UTC 코멘트). 이 결과는 감독자의 증거이며 이 작업자의 물리 검증 분모에 합산하지 않는다. v351을 새로 실행해 같은 결함을 재현할 필요가 없으므로 이미 수정된 v354에 접근 개선을 결합했다.

- v350 인수 기준: `--boundary-lifecycle abort_v1 --approach-efficiency regulated_v1` → v356.
- 감독의 v354 인수 기준: `--approach-efficiency regulated_v1`만 추가.
- 몸/프로토콜code_v1, Gemma 문장, 기존 카메라·정답 입력 금지·안전 필터를 유지한다.
- v351 최초 코드343bce42와 workflow 바이트·자기 입력/재생·39시험 기록을 보존한다. v351은 물리 실행0인 비교 기록이며 새 제출 대상이 아니다.

## 접근 변화와 근거

[원본 진단·구현·참고 문헌](approach-v351.md)을 그대로 적용한다. 마지막 관측 방향/시도 섹터를 기억하고, 팬 작은 오차 조정을 줄이며, 기존 보정 펄스를 안전한 먼 직선에서만 더 자주 발행한다. 새 v356에서 물리 효과를 확인한 것은 아니다.

저장 재생은 같은 r69 자기 입력 **537/537 주행·114/114 팬 =651개**이며 이전 재생과 행별 일치한다. 새로운 독립651개를 더한 결과가 아니다. 빠른 주기 대상215/537·팬 생략59/114, 동일 명령 수 가정의 로봇별 조건부 감소 여지는 주행20.2/22.8초·팬25.6/21.6초·완료 탐색 창34.4/36.4초다. 항목은 합산하지 않고 전체435초의 실제 단축으로 보고하지 않는다.

최종 검증과 소스 SHA는 `approach-v356-summary.json`, 감독 제출 인수는 `approach-v356-submission-request.json`에 기록한다. 요청은 execute=false이며 직접 VM 제출/진행 프로세스 변경은 없다. 첫30SIM 원본 및 정렬 진입 이후 실제 발행률·재획득·공동 파지/E2E 시간은 감독 비교를 기다린다.

## 참고 자료

- [Nav2 RPP 규제](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_regulated_pure_pursuit_controller/include/nav2_regulated_pure_pursuit_controller/regulation_functions.hpp), [RPP 논문](https://arxiv.org/abs/2305.20026), [1Hz 재계획·순서 복구](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml).
- [맥락 기반 능동 재탐색](https://arxiv.org/abs/1912.06754): 과거 관측 활용의 근거이며 DBN/POMDP를 복제한 것은 아니다.
- 감독의 `harness/e2e_boundary_lifecycle.py`, `experiments/2026-10-12-e2e18/boundary-lifecycle-candidates.json` 및 #461 공통 결함 코멘트.
