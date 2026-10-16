# Batch G 지적 수정 — PR #325, 2026-10-01

**DRAFT 유지 / 병합하지 않음 / 오프라인 코드 검증만.** 검토 `01edc483`의 대상은
`be97d9dd53638a1efbda7627b420bd9b1cbd9880`이었다. 이번 검증의 실행 소스는
`review_fixes_verification.json`의 파일별 SHA-256으로 고정했다. 커밋 SHA는 이
기록을 포함한 PR head에서 확인한다. 검증 뒤 커밋하며 실행 중 소스를 바꾸지 않았다.

## 지적과 조치

| 항목 | 수정 및 확인 |
|---|---|
| G-325-1 / P1: 현재 v6e 봉인 소스 5개 변경 | `owncam_delivery_shared`, `zone_own_deliver`, `zone_own_executor`, `zone_own_status`, `zone_own_team_host`를 origin/main 바이트로 복원. 기존 prereg JSON·해시·승인·성공 기록 불변. v6e 85개와 scene 12개 pin을 검사한다. |
| 새 색 기능의 연결 | `ZoneColorBoxExecutor`, `ColorDeliverController`, `ColorSharedPoseDelivery`를 별도 모듈에서 명시적으로 선택한다. 기존 봉인 코드의 의존성 목록에 새 색 모듈은 없다. 기본 host의 동적 skill 선택만으로 red/green을 활성화하지 않는다. |
| 실제 연결과 상태 | 새 executor → 실제 controller 생성 → 동일 자기 pose/gate/guard → kind별 검색·coarse order·skill 전달을 검사한다. coarse slot 밖 후보, 다른 kind의 clip/holding/placement와 종료 뒤 kind 소실을 검사한다. |
| fixture 시간 순서의 한계 | ‘구현 전 고정’ 표현을 정정했다. 최초 구현과 fixture는 같은 `ae9726a3` 커밋으로 시간 순서를 독립 입증하지 못한다. 합성 라벨·PNG/JPEG·해시는 보존했다. |
| workflow/main 합성 | 요청대로 먼저 main을 병합하고, 진행 중 병합된 #323도 main `394f9cda`로 합성했다. `.github/workflows`는 origin/main과 동일하며 직접 수정하지 않았다. |
| #328 오프라인 잠금 | `offline_checks.py`에서 공용 잠금 획득·재시도·대기를 제거했다. 기존 다른 작업의 잠금을 읽거나 해제하지 않는다. |
| 변이 검사에서 발견한 테스트 빈틈 | placement kind 차단 제거 시 기존 fake의 `lookback_gates` 누락이 잘못된 승인을 가렸다. 성공/실패 경로를 모두 갖춘 fixture와 결과 assertion으로 보완했다. 이 최초 변이는 검출 성공으로 세지 않는다. |

## 재현과 검사

수정 전 두 필수 pin 검사와 xfail을 제거한 검토 원문 반례를 함께 실행해
**52 passed, 10 failed**를 재현했다. 등록 회귀 5개와 같은 원인을 파일별로 검사하는
검토 반례 5개이며 서로 다른 제품 결함 10개가 아니다. 소스 고정 회귀는 34개 통과했다.
실행 중 main #323을 추가 병합했으나 다섯 봉인 소스·등록 파일·검토 대상 테스트는
그 병합에서 변경되지 않았다. 수정 전 결과를 최종 소스 검증으로 쓰지 않는다.

최종 결과·명령·raw 위치·해시는 `review_fixes_verification.json`을 따른다.

- 관련 회귀 **1,101 passed + 291 subtests passed, 7 deselected**, 실패·오류 0.
- 이후 제어 소스는 그대로 두고 placement 검사 fixture만 보완했다. 최종 색·봉인 검사 **161 passed**이며 위 158개와 중복되므로 합산하지 않는다. 새 양성 placement 3개를 포함한다.
- xfail 제거 원문 반례 **6 passed**. v6e 85개·scene 12개 pin, 봉인 5파일 및 workflow의 origin/main 동일성을 확인했다.
- 최종 변이 **10/10 assertion 검출**, collection/setup error 0, 원본 소스 변경 0.
- CI fixture 3개, v63 정적 manifest/source 검사, 기존 registry 불변성, 전체 shard coverage·색/봉인 검사 각 1회 포함, `git diff --check` 통과.

검토 반례는 xfail을 제거한 원문으로 다시 실행하며, 현재 트리의 같은 5개 조건을
`tests/test_zone_own_executor_color_seals.py`에도 정규 회귀로 포함했다. 후자는 과거
PR Git object가 없는 CI에서도 같은 등록 JSON 해시와 소스 해시를 검사한다.

`mutation_checks.py <새 출력 경로>`는 검토의 6개 변이에 슬롯 필터·실제 controller
검색 경로·job 종료 뒤 kind·잘못된 holding 거절 변이 4개를 더한다. 테스트 subprocess의
메모리에만 변이를 적용한다. return code 1, assertion failure 1개 이상, collection/setup
error 0, 원본 source 불변일 때만 검출로 인정한다. 해시 검사 실패로 색 논리의 변이
검출을 대신하지 않는다. 원본 테스트가 통과한 뒤 변이를 실행한다.

새 dependency record는 새 executor와 선택 색 skill을 시작점으로 한 전체 Python
의존 소스다. 별도 host/runner·provider·모델·구성 선택은 추가 고정 대상이며, 기존
실행 번들의 소스 목록이나 해시를 갱신하지 않는다.

## 범위와 인계

로컬 물리/SIM/렌더/실제 모델 호출 **0회**. MuJoCo/Torch import 및 네트워크 연결을
막는 guard를 유지했다. 관련 기존 테스트 중 world/물리 3개 및 MuJoCo import
geometry/projection 4개는 이름으로 제외하고 제외 목록을 기록했다. 자동 검사 통과로
red/green 실제 배송·최종 환경·4조건 실행 성공을 주장하지 않는다.

`PHYSICS_CHECKS.md`에 별도 executor 선택을 반영했다. 과거 proposal은 원본 그대로
보존하고 새 source/config/bundle/workflow로 다시 고정해야 한다. 기존 v3 consumer gate,
최종 카메라/FK/IK/provider, distractor 실제 가시성, 독립 재검토와 물리 인수는 남는다.
물리 제안의 cap은 staging 포함 4×900=3,600 SIM초다. 새 코호트가 없어 TensorBoard
변환/표시는 수행하지 않았다. 실제 결과 회수 때 별도 snapshot·scalar/video 검증을 한다.
raw는 primary `outputs/cap-t03-redgreen/`의 로컬 보관이며 원격 백업이 아니다. Drive 작업 없음.
