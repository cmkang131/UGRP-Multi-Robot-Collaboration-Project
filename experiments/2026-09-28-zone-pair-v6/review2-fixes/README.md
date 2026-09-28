# PR #246 v6 검토 2 수정

기준 HEAD `19b3a7b242ccecf63ac5087ba122b1cb559d0991`, 브랜치 `codex/zone-pair-beam-relative`.
사용자가 지정한 `codex-246-review2.md`의 P1 3건/P2 1건을 다룬 로컬 미커밋 수정이다.
물리 step·실제 모델 호출·실험 잠금·프로젝트 Git 커밋은 실행하지 않는다.

## 수정과 실제 경로 검사

| 검토 항목 | 원인과 조치 | 검증 종료점 |
|---|---|---|
| P1 접근/회전 HIGH abort | PF HIGH를 전역 envelope의 abort 조건으로 사용했다. 이제 실제 endpoint의 before_control이 전역 안전 여유를 검사한 뒤 HIGH/여유 부족 예고를 접근 드라이버의 hold→look 요청으로 전달한다. 새 informative receipt와 전역 검증까지 기다리고 복귀한다. | 명령 응답 모델에서 실제 driver+guard+endpoint가 전진 목표와 회전 목표에 도착, `wait_approach`. 기존 위험 이동 반례는 계속 거부. |
| P1 가림 경계=끝 오인 | 단일 부분뷰의 near-end 갱신을 제거했다. FOV 내부에 있다는 이유로 끝을 확정하지 않는다. 불완전한 영상은 기존 축 위치를 유지하고 명령/시간 bound만 증가시킨다. | `.33→.306 m` 뒤 `x<.38 m` 가림은 위치/anchor를 갱신하지 않고 bound를 줄이지 않으며 not-ready. |
| P1 다른 성분 혼입 | 표식 fit과 shape fallback에 모두 해당 성분만 남긴 영상을 전달한다. 분리된 성분을 합쳐 catalogue 길이를 만들지 않는다. | LOOK_P20의 `.37–.80 / .84–.97 m` 두 조각에서 실제 `judge_route_blockage`: 기존과 수정 후 모두 `yes`, 후보 1개, flat 1개, 목표 제외 0개. |
| P2 재획득 첫 후보 abort | 기존 anchor의 도달 범위와 검증 중 후보를 모두 감싸는 별도 정지 관측 envelope를 사용한다. 이 값은 주행 fix가 아니며 base 명령은 계속 금지한다. align 복귀에 전역 anchor 검증을 추가하고, gate dwell/재획득만 남으면 같은 자세에서 관측을 이어간다. | 같은 XY, yaw `0→.2`에서 실제 stop→relook→return→align. 중복 receipt는 횟수에 포함하지 않는 기존 3회/0.3초/1초 간격 검사는 유지. |

부분뷰를 계속 거부하면서 정상 접근이 교착되지 않도록, **정지 상태의 서로 다른 카메라 자세**에서
관측한 같은 beam의 형상을 합치는 경로를 추가했다. 단일 부분뷰를 끝 측정으로 취급하지 않는다.
기존 full-shape 길이/폭/paired-edge 조건을 함께 충족하고, 3 mm 공간 격자로 픽셀 밀도 편향을 제거한
전체 형상이 5 cm/3° 준비 조건을 만족할 때만 갱신한다. 보이지 않은 catalogue 길이와 시간 drift는
bias에 추가한다. 새 base 명령·segment 변경·loaded 진입은 이 조합을 끊고, 보존은 4초로 한정한다.
원래 full-shape identity의 30초 수명을 연장하지 않는다. 원본 뷰 SHA는 track과 보고서의 `view_sha256`에 남긴다.

실제 align은 base 이동 후 기존 search/p45/inspect 각각을 한 번씩만 시도한다. 필요한 먼쪽 뷰로도
돌아갈 수 있지만 3자세가 소진되면 명시적으로 실패하며 무한 왕복하지 않는다. 정상 `.33 m` 시작은
합성 자기 JPEG와 명령 응답으로 정렬을 마치고 `pregrasp_descend`까지 진행한다. pregrasp 이후의
파지·lift·운반 성공은 이 시나리오의 주장에 포함하지 않는다.

## v6 전체 동류 감사 목록

범위는 `zone_pair_{global,relative,guards,align,grasp,executor,obstruction,v6_policy}`,
`owncam_{recovery_v6,observability_v6,pose_source}`, 실제 접근 드라이버/STATUS/obstruction 호출자,
prereg/등록 계약과 관련 테스트다. 실행 입력은 자기 RGB·발행 명령·자기 pose report·정적 지도/주문뿐이다.

| 부류/점검 지점 | 발견/조치 |
|---|---|
| 보수화→교착: 접근 HIGH | stop/relook으로 연결. 낮은 nominal PF σ로 전역 envelope를 덮어쓰지 않는다. |
| 보수화→교착: 전체 pan 반복 | A 조건에서 요청한 새 informative fix와 전역 검증이 끝났으면 남은 pan을 종료한다. 기존 settle/arrival gate는 그대로 통과해야 한다. |
| 보수화→교착: hold-only arm tick | `arm_step`이 hold만 반환한 tick도 blocked pan으로 취소하던 분기 수정. 실제 arm/look 명령을 거부한 경우에만 큐 취소. |
| 도달 불가: 후보 1회 뒤 abort | old anchor+candidate 정지 envelope, global-anchor-verified 복귀 gate, 같은 pan에서 연속 관측. 위치/회전/시간 예산은 원래 검증 조건 유지. |
| 예산 우회: 작은 σ의 미검증 후보 | reobserve 누적 대기는 HIGH뿐 아니라 anchor 미검증도 포함. 후보가 compact해도 대기 예산을 멈추지 않는다. 관측이 없으면 기존 timeout으로 종료한다. |
| 안전 cache 우회 | A 조건에서는 uninitialized report를 과거 stationary pose로 대체하지 않는다. recovery envelope에도 posterior_envelope 유효성·범위를 동일 적용한다. |
| 가림/FOV 경계 오인 | 단일 부분뷰의 축/anchor/bound 갱신 제거. 색 패치·중복·만료·다른 segment·loaded·카메라 불일치 실패 조건 유지. |
| 전체뷰 가림 범위 추가 점검 | search에서 실제 grip .33 m에 대해 .30/.32/.33/.34/.35/.36/.38 m 아래를 가린 해석 투영 검사. .32 절단의 2.159 cm 오차는 4.237 cm bound 안이고 .33 이상 절단은 unknown. 표본 조건의 결과이며 임의 가림에 대한 보증은 아니다(`full_shape_occlusion_probe.json`). |
| 부분뷰 보수화→정렬 교착 | 움직임 없는 complementary full-shape 조합과 유한한 3자세 스캔. 실제 endpoint에서 정렬 종료까지 검사. 이동 명령 또는 오래된 뷰를 섞는 반례를 추가했다. |
| identity 수명 우회 | multiview report에 원래 identity 시각을 전달하고 ready에서도 검사한다. 30초 경계 직후 같은 JPEG를 다시 읽어도 최신 fusion 시각으로 수명을 연장하지 못한다. |
| 다른 성분 혼입: 장애물 제외 | 검사 중인 성분만 band/shape fit. flat으로 분류되는 다른 성분도 더는 fit 재료가 되지 않는다. 기존 복수 목표 후보 복원 검사 유지. |
| 다른 성분 혼입: 상대 형상 초기화 | floor residual로 분리된 foreground 성분 둘을 전체 빔으로 fit하지 않는다. 동일 반례는 상대 track 초기화도 거부. 회색 배경 위 연속 검정 띠는 같은 silhouette로 유지하지만 검정 배경과 구분되지 않는 gap은 unknown이다. |
| 도달 불가: 마지막 접근 pan | 후보 검증 대기는 마지막 pan의 발행 PWM에 도달한 뒤에만 적용한다. 마지막 pan으로 가는 보간을 대기 분기로 막지 않으며 base 명령은 계속 금지한다. |
| provider/recovery | routine begin_observation의 posterior/RNG 유지, lost 요청 상한·혼합 proposal, current 정보/retained receipt 구분, ±π·무명령 큰 yaw·불일치/공백 회귀 유지. 검출 acceptance나 낮은 σ만으로 새 fix를 만들지 않는다. |
| observability/ranking | 점수는 정적 지도와 posterior에 의한 제안만 제공. 모든 실행 sweep은 전역 envelope로 다시 검사하며 점수로 성공/fix를 만들지 않는다. |
| 닫힘/loaded/STATUS | 전역 후보 검증을 완료해도 상대 ready·preclose clearance·동일 close GO가 별도 필요. loaded unilateral recovery는 계속 금지하고 peer abort를 유지한다. |

5 cm/3° 상대 readiness, PF HIGH/LOW, 35 mm 기하 여유, 전역 envelope 지원 범위,
재획득 compact/시간 조건, 재관측 누적 예산과 작업 timeout을 완화하지 않았다. 측정이 없어 안전 여유를
증명할 수 없거나 envelope 모델 지원 범위를 벗어나면 기존 fail-closed 제한은 남는다.
형상/단안 평면/명령 응답 bound는 개발 가설이며 실제 센서 오차 coverage 보장이 아니다.

## 테스트와 출처

`tests/test_zone_pair_v6_review2.py`는 실제 PairExecution.step/arm_step, GuardedPairApproach,
PairCommandGuard, align/grasp adapter, 공유 recovery provider의 상태 전이를 사용한다.
가짜는 물리 plant/센서 응답뿐이다. 명령에서 전진/회전을 적분하고 자기 센서 report와 고정 wrist ray로
투영한 JPEG를 돌려준다. guard·align 판정이나 controller 메서드를 성공값으로 monkeypatch하지 않는다.
장애물은 실제 component 추출/height/flat/target 판정을 끝까지 통과시킨다.

검토 1 테스트의 부분뷰 갱신 기대는 새 multiview 근거로 바꿨다. 기존 검정 바닥+검정 띠 fixture는
가림과 구별할 수 없으므로 unknown을 검사하고, 구별 가능한 회색 바닥 fixture에서 표식 유무에 따른
grip 동일성을 계속 검사한다. 과거 실행/검토 원본 기록은 수정하지 않았다.

`run_tests.py`는 기존 관련 glob 전체와 추가 의존성 `test_pair_owncam_approach.py`,
`test_m2_pair_door_v3.py`, `test_pose_provider*.py`를 수집한다. `OMP_NUM_THREADS=1`,
`--basetemp=./.pytest_tmp`를 강제하고 finally에서 임시 폴더를 제거한다. MuJoCo step/실제 vision worker/
네트워크 sentinel과 Python 자식 step tripwire를 사용한다. 테스트용 임시 Git 저장소 fixture 외에는
Git 커밋을 만들지 않는다. 최종 집계는 아래 결과 절과 `validation.json`, `pytest.xml`, `pytest.log`를 따른다.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
V6_STEP_AUDIT=/private/tmp/v6-review2-step-audit.log \
PYTHONPATH=/private/tmp/v6-review2-no-physics:. \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
experiments/2026-09-28-zone-pair-v6/review2-fixes/run_tests.py
```

재실행 전 `/private/tmp/v6-review2-no-physics/sitecustomize.py`에 기존
`../source-regression/step_tripwire.py`를 복사하고 결과 경로를 새로 정해 기존 기록을 보존한다.
시작 시 fetch는 공유 `.git/FETCH_HEAD` 쓰기 제한으로 실패했고 GitHub 조회도 연결 실패했다.
원격 HEAD/CI는 검증하지 않았다. main 갱신·push·PR 댓글·병합은 수행하지 않았다.
UGRP 예외에 따라 Drive는 사용하지 않는다. 이번 결과는 코드 회귀이며 새 물리/학습/평가 실험이 없어
TensorBoard 변환·대시보드 재실행 대상에 포함하지 않는다.

## 개발 중 검사 기록

첫 확대 회귀는 **2697 passed / 8 failed / 2 skipped, 382 subtests passed**였고 `first-pass/`에 보존했다.
8개는 아직 발행되지 않은 hold를 동반한 arm/look/drive/mecanum 배치가 즉시 abort해야 한다는
기존 검토 6 계약이었다. motion_until 이전의 거부를 복원하고, 정상 HIGH 전환에서는 endpoint가 먼저
hold를 발행하도록 분리했다. 이후 해당 검토 6와 새 시나리오, 추가 드라이버/provider 경계 104개가
통과했다. 최종 전체 실행 전에 identity 수명, 마지막 pan 도달성과 source hash도 다시 고정한다.

## 최종 결과

**80개 파일, 2787 passed / 0 failed / 2 skipped, 382 subtests passed** (pytest 336.15초).
Skip은 물리 step이 필요한 기존 host 테스트 2개이며 이름/사유는 `validation.json`에 기록했다.
새 검토 2 테스트 12개에는 실제 endpoint 접근·회전 도착, align→pregrasp, yaw 재획득 복귀와
실제 own status 호출자의 두 조각 장애물 판정이 포함된다.

`verify.py`로 현재 등록 소스 65개/scene 계약, 인접 조건당 행동 플래그 하나, 동일 seed·설정·예산,
6개 DRAFT 실행 거부, 기존 등록/제어기/기하/provider/정책 등 frozen 파일 18개 불변을 확인했다.
전역 margin/certificate, 3회 재획득 검사, align relook 만료 함수는 기준 HEAD와 AST가 같다.
prereg SHA-256은 `a12ebaa29d628955f29a968aa68e1b3723996e4f6cb502543ce4bfe4199f2ca5`다.

물리 step·실제 vision worker·네트워크 sentinel은 모두 0이고 Python 자식 step tripwire 호출도 0이다.
`.pytest_tmp` 삭제를 확인했다. HEAD는 `19b3a7b242ccecf63ac5087ba122b1cb559d0991` 그대로이며
프로젝트 커밋·push·병합을 하지 않았다. [최종 검증 JSON](validation.json), [전체 로그](pytest.log),
[JUnit](pytest.xml), [실행 설정](test_execution.json)이 근거다. 원격 CI·실제 provider 정확도·물리 파지/운반
성공은 검증 범위 밖이고, v6 등록은 계속 DRAFT/prepare-only다.

## 추가 CI 검토: v5 scene receipt의 호스트 의존성

Ubuntu CI의 dev09/dev10 실패는 현재 소스 계약만 합성한 fixture에서 과거 macOS scene-instance
해시도 승인될 것이라 가정한 테스트였다. 카탈로그의 삼각함수 float 1 ULP 차이가 전체 scene 해시를
바꾸는 반례로 동일한 2건 실패를 재현했다. prepare 복사와 scene guard 검증을 분리하고,
등록 커밋의 카탈로그 blob/현재 호스트/1 ULP 변형 각각을 검사한다. 기대 해시·과거 등록·실행 guard를
변경하지 않았고 v6 등록 해시와 한 플래그 공정성도 유지했다.

추가 수정 후 **80개 파일 2793 passed / 0 failed / 2 skipped, 382 subtests passed**다.
누락된 tracked 파일 1,555개를 HEAD 바이트로 임시 복원한 **6,743개 전체 파일 존재 조건**에서도
집중 회귀 **104 passed / 0 failed**를 확인했다. 여기에는 수정 전 HEAD의 원래 문제 테스트
두 개도 포함되어 sparse 누락 가설을 배제한다. 복원 사본은 모두 해시 확인 후 제거했다.
물리 step·실제 모델·네트워크 호출 0, `.pytest_tmp` 삭제, 프로젝트 커밋 없음.
Ubuntu 자체 실행·원격 CI 재실행은 미검증이다.
[상세 원인·수정·검증 기록](ci-scene-fix/README.md), [최종 검증](ci-scene-fix/validation.json).
