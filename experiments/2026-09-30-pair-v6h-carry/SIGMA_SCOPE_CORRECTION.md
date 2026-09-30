# 인수 실패 뒤 시그마 범위 수정 — 미봉인 (2026-09-30)

조정자 결정은 **시험한 probe 범위를 그대로 등록**하는 것이다. b-v6h1에만 `door_relax_sigma_scope="probe_all_sweeps"`를 켠다. 다른 18개 정책은 `loaded_base_motion`, 배수 2/2와 기존 계산 순서를 유지한다. probe 모듈은 수정하지 않았다.

근거는 `claude/v6h1-acceptance-run`의 `68219d91c1c635b746f7e12b9bf31b2c8b4b031b`, `ACCEPTANCE_REPLAY.md`와 `acceptance_replay.json`이다. 이 작업에서는 두 파일과 연결된 S03 raw를 읽었고 제어기의 물리 인수 재생은 하지 않았다. 기존 등록 head `3afc61b00f2c127ac3fbe2be5e7bb57da989b15a`는 lag-on 10건 중 4건만 같고 6건은 leg 1 pregrasp 시야 확인에서 갈라졌다. lag-off(tX0 X01)도 같게 실패했다. 원인 확인은 margin만 전체 1/1로 덮어쓴 7건에서 명령 SHA·leg 결과 일치를 회복했다. 이 숫자는 다른 작업의 물리 증거이며 이번 수정의 재생 성공이 아니다.

tS/tR/tX의 29/29 탐색 기록은 probe 범위에서 얻었다. 더 좁힌 범위는 다른 제어기이며 그 기록을 성능 근거로 넘길 수 없다. 사용자에게 이미 승인된 문 가드 완화·접촉 허용을 이 범위로 등록한다. 하드 한계(penetration >5 mm, tilt >15°)는 평가 분류기가 우선 확인하며 제어 입력에는 넣지 않는다. 최종 분류기·평가 정의 병합/pin은 REVIEW_RESPONSE의 지적 2에 남아 있다.

| 검사 경로 | probe k1g | 수정 b-v6h1 | 다른 정책 |
|---|---|---|---|
| 짐 없는 팔: pregrasp/align 시야 후보, look/pan, 하강·열기·재파지 | 모든 `margin` 호출 1/1 | 1/1 | 2/2 |
| 짐 든 팔: lift/lower/복귀, 전이·진단 | 모든 `margin` 호출 1/1 | 1/1 | 2/2 |
| 짐 없는 접근·후진·차체 이동: chassis/arm/translation/plan | 모든 `margin` 호출 1/1 | 1/1; 접근 driver의 작업별 가드 복사본 | 2/2; 기존 own 가드 사용 |
| 짐 든 차체 이동: chassis/팔/전체 빔 | 모든 `margin` 호출 1/1 | 1/1 | 2/2 |
| preclose의 정지 빔: 자기 위치 추정 여유 | `margin` 호출 1/1 | 정책 가드를 사용해 1/1 | 2/2 |
| preclose의 별도 빔 영상 불확실성 | `K_SIGMA * (beam std_xy + beam std_yaw * lever)`는 2 | 2 유지 | 2 |
| GlobalPairSweepGuard의 override, 정합/앵커 검사 | 직접 쓰는 K_SIGMA는 2; probe 패치 대상 아님 | 2 유지; b-v6h1은 beam_relative=False | 기존 값 |

`zone_pair_door_relax.install()`은 프로세스의 `SweepGuard.margin`을 바꾸므로 짐 유무·단계·문 leg 조건이 없다. 표는 이를 등록 정책 인스턴스에 옮긴 것이다. 고정 35 mm, sigma cap(xy .15 m / yaw .20 rad), geometry, 전이 샘플, 차체 명령 이동 pad, veto, gate/p2f 범위와 운반 시간은 그대로다. advisory/contact-reaction은 추가하지 않았다. 자체 own executor의 가드를 수정하지 않아 이후 단독 작업에는 적용되지 않는다.

오프라인 회귀 입력 `tests/fixtures/zone_pair_v6h/pregrasp_s03.json`은 S03 seed 911의 r2, SIM 28.2초 자기 추정·발행 서보·정적 빔 형상과 원본 파일 해시를 보존한다. 기록은 robots.json이 반올림한 값이며 평가 정답은 없다. 실제 `ranked_look_pans()`에 양의 고정 observability 점수를 주어 충돌 후보 필터만 검사한다. 2/2는 후보 0개, 1/1은 7개(1500/1230/1770/970/2030/700/2300)이며 probe 수식과 점수까지 같아야 한다. 이 검사는 PF·영상·명령 전체 재생을 대신하지 않는다.

검증 산출물은 `analysis/sigma_scope/`에 새로 보존한다. 첫 확장 pytest에는 `test_zone_own_executor.py::test_team_host_feeds_each_executor_only_its_own_camera`의 물리 통합 검사가 잘못 포함돼 렌더 초기화에서 `CGLError`로 실패했다(1371 passed / 1 failed). 이 시도도 JUnit에 보존한다. 제어기 코드와 통과한 검사는 변경하지 않고, 해당 파일은 기존 `tests.pose_provider_no_physics` 플러그인으로 재검사해 물리 검사를 제외한다. 이 실패를 제어기 회귀나 물리 통과로 세지 않는다. 기존 off/schedule/stop-tick 골든 값과 과거 봉인 파일은 변경하지 않는다. `source_changes_UNSEALED.json`과 builder의 소스·정책·범위 출력을 갱신하되 `prereg_v6h.json` 생성과 CURRENT_REVISION 전환은 하지 않는다. 새 실험/학습/평가 결과가 없는 코드 수정이므로 TensorBoard 재변환·서버 작업은 없다.

**조정자는 새 head SHA에서 물리 인수 재생을 다시 실행해야 한다.** 기존 10 lag-on + lag-off 원인 확인의 고정 입력을 사용해 commands 바이트/전체 SHA, leg 검사와 연쇄 전체 접촉/하드 한계 판정을 확인한다. 확증·봉인·병합은 이번 작업에 포함하지 않는다.

이번 수정의 검사: `test_zone_pair_v6h.py` **140 passed**, `test_zone_pair_registered_source.py` **24 passed**. 검색으로 고른 관련 44개 파일은 **1371 passed / 물리 통합 1 failed(CGLError)**였고, 유일한 실패 파일을 기존 no_physics 플러그인으로 재검사한 결과 **14 passed / 물리 1 skipped**다. 제어기 소스는 두 검사 사이에 바뀌지 않았다. 중복을 뺀 오프라인 통과는 **1535개**이며 실패 시도와 제외 확인을 모두 보존했다. 빌더 두 모드는 **미봉인 72건 / 268개 pin**을 확인했다.
