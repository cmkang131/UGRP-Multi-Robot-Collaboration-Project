# PR #342 독립 검토

**판정: MERGE AFTER FIXES — 코드 수정 지적은 없으나 CI 복구 전에는 병합 불가.**

- 대상: `04eb11c6a001f2a7d2ab916765d59b3661c06efe`, `codex/final-env-floor-light`.
- 비교 기준: 조회 당시 `origin/main` = `78ce79162d907d88d38ef3afcfc0c62e4a72aaba`.
- 검토자: Codex. `codex/review-342`에서 기록·독립 검사만 작성했다.
- 물리 step·모델 컴파일·렌더링·실제 provider·학습 실행은 0회다. 호스트 잠금을 사용하지 않았다.
- P0/P1/P2 구현 반례 **0건**. 따라서 실제 결함용 strict xfail은 **0개**다. 의도적으로 만든 렌더 검사 우회 변이는 통과 검사와 분리했다.

## 한 묶음의 검토 결과

| 항목 | 독립 확인 결과 |
|---|---|
| v84 보존 | 기존 번들 **9개**를 main과 후보에서 각각 생성해 digest 일치를 확인했다. 관련 소스·등록·보정·보호 파일 **162개**는 Git의 main blob과 후보 파일·기존 해시가 모두 같다. workflow `zone-final-environment-check` **2.17.0** 유지. PR의 merge-base diff에서 과거 실험 기록 수정·삭제와 `.github/workflows` 변경은 없다. |
| v87 차이 | 새 ID **zone-final-environment-v87**, workflow **2.20.0**과 출처 정보 외에는 렌더 조건만 다르다. 세 지도 전체 XML 트리를 비교했으며 지도마다 바뀐 속성 **23개**는 `floor_light_v1`의 조명·바닥 정의와 정확히 같다. 로봇 XML hash, 카메라 배치/FOV, 물체·접촉·옵션·weld 정의는 같다. 기존 `sim.render_profile.install/profile_record/verify_model`을 그대로 사용한다. |
| 적용 검사 | 그림자 잔존, 반사 잔존, 잘못된 cutoff, 어두운 바닥, 바닥 누락 **5종**을 주입하면 새 backend → 실제 `verify_model` → `run_case`를 거쳐 모두 **HOST_ERROR**, `protocol_complete=false`, reset 이전 world 정리가 된다. |
| 변이 검사 | `verify_model` 호출을 `audit_model` 기록으로만 바꾼 메모리 내 변이는 잘못된 그림자를 `COLLECTED_UNQUALIFIED`로 통과시킨다. 동일한 HOST_ERROR 단언이 실패함을 확인해 **우회 변이 검출**. 후보 파일 자체는 수정하지 않았다. |
| 예산·명령 | 기존 `run_case`, `advance_to`, `cap_world_steps`를 가짜 시계로 실행했다. 각 reset을 최대 **5초**로 둬도 P01은 정확히 **30초 × 3**, 합계 **105초**; unloaded는 정확히 **120초 × 3**, 합계 **375초**다. 종료 후 한 step을 더 요청하면 **SIM_CAP_EXCEEDED**이고 시계는 증가하지 않는다. 고정 명령 시각·내용은 측정 JSON과 같고 eval 반환값으로 바뀌지 않는다. |
| 입력 경계 | 실제 저장 메서드에 식별 가능한 가짜 GT를 넣어 카메라 정답·접촉이 `eval_only/`에만 기록되는 것을 확인했다. RGB 대신 고정 배열을 사용했다. provider 모듈을 차단해도 수집 메서드가 동작하며 외부 입력 로그에 GT가 없다. P03는 파일 없음→**MEASURED_V3_CALIBRATION_REQUIRED**, null 계약 또는 v2 파일 제공→**FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED**로 물리 import·출력 생성 전에 거부된다. |
| 측정 상태 | 새 정적 계약은 기존 계약에서 render_profile만 바뀌고 카메라 sag/pan, unloaded/loaded/fine, measurements는 null이다. 이번 경로는 raw 수집만 하며 null/v2를 MEASURED_SIM 산출물로 바꾸는 fitting/writer가 없다. P03 인자에 제공해도 산출물은 생성되지 않는다. |
| 번호 | 열린 PR **14개 전체**의 head를 확인했다. #339 `9912bb15`는 **v86/2.19.0**, #342만 **v87/2.20.0**을 등록한다. 다른 열린 PR과 번호 충돌 없음. |

정확한 주요 경로: `sim/final_environment_floor_light.py:28`의 프로필 적용,
`:33`의 실제 모델 검사, `:40`의 정리; `scripts/run_final_environment_checks.py:82`의
고정 시간 진행과 `:95`의 HOST_ERROR 처리; `sim/zone_final_v3_scene.py:45`의
step 전 상한 검사; `scripts/run_final_environment_floor_light.py:40`의 P03 차단.

순수 XML 비교는 빈 `mujoco` 모듈로 네이티브 API를 사용할 수 없게 한 상태에서
기존 XML 생성·변환 함수를 실행했다. 실제 컴파일 모델 배열·영상·물리 완주는 검증하지 않았다.

### 적용값 대조

- 지도 파일·정적 지도 hash: 세 지도 모두 v84와 같음.
- 로봇: `masterpi_v3`, 각 지도 r1/r2/r3 XML hash 일치.
- 카메라: 기존 mount/FOV·`robot_cam` 640×480, 계약의 segmentation 480×360 유지.
- 접촉: `cargo_noslip_v1`, `noslip_iterations=10`; weld OFF, ultrasonic OFF.
- timestep: **0.00025초**; eval **0.05초**, RGB P01 **5초** / unloaded **0.2초**.
- 명령: `configs/final_environment_measurement_v1.json` 원본 byte 보존, 세 지도에서 전 이벤트 일치. P01 추가 명령 없음.
- 렌더만 변경: ground rgb1 `.20 .22 .24`→`.36 .35 .34`, rgb2 `.27 .29 .31`→`.62 .61 .59`; groundmat reflectance `.035`→`0`; 네 광원 castshadow=false, cutoff=180, ambient/diffuse/specular 기존 값×0.3. 새 구현이나 다른 물리 값 변경 없음.

## 테스트와 남은 조건

기존 Mac `.venv-sim-worker-mac`에서 실행했다. 결과를 중복 합산하지 않는다.

| 묶음 | 결과 |
|---|---|
| 새 경로·v84·batch K 회귀 | **62개 통과**: 최초 60 통과/2 실패, archive의 Git 이력 연결 후 실패한 2개 재실행 통과 |
| manager·소스 pinning·P01/P03·CI shard·순수 XML 회귀 | **248개 통과, 환경 제약 1개**: 최초 232 통과/17 실패, Git 이력에 의존한 16개 실패는 연결 후 모두 통과(해당 파일 전체 22 통과, 6개 중복) |
| 추가 독립 검토 `tests/test_review_342.py` | **14개 통과**, 위 렌더 우회 변이 검출 포함 |

남은 로컬 검사 1개는 기존
`tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_parent_exit_cleans_background_child`다.
`ps` 호출이 sandbox에서 `PermissionError: [Errno 1] Operation not permitted`로 거절됐다.
테스트를 변경하거나 xfail로 감추지 않았다. 제품 결함 반례로 세지 않는다.

archive에는 원래 Git 이력이 없으므로 과거 `git show`/`merge-base`를 쓰는 검사들이
처음 실패했다. 추출 폴더에만 독립 `.git`/index를 만들고 원본 object DB를 alternates로
읽도록 연결한 뒤 재검증했다. 원본 저장소의 브랜치·index·소스는 변경하지 않았다.
독립 검사 초기 1건은 main의 후속 커밋을 PR 삭제로 오인한 검토 테스트의 two-dot diff였다.
이를 merge-base diff로 고치고 14개 전체를 다시 실행했다. 이 실패도 PR 결함이 아니다.

**필수 남은 조건:** [CI 실행 36766082408](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36766082408)의
`offline-regression-shard (4/8)`이 **CANCELLED**, 집계 `offline-regressions`가 **FAILURE**다.
해당 검사와 집계를 정상 완료시키고 최종 head가 검토 SHA와 같은지 확인해야 한다.
조회 당시 PR은 draft·MERGEABLE·REVIEW_REQUIRED이며, 이 검토에서 병합하거나 CI를 재실행하지 않았다.

코드 수준에서는 요청된 수집 경로 범위에 대한 수정 요구가 없다. 실제 밝은 P01/unloaded
자료 수집·영상/FOV 확인, loaded/fine 보정, fitting, v3 provider/chain 연결·인수는 별도 작업이다.
이 검토를 v87 물리 성공·MEASURED_SIM·P03 실행 승인으로 해석하지 않는다.

## 재현·보관

```sh
git fetch origin
review342_scratch=$(mktemp -d /private/tmp/ugrp-review-342.XXXXXX)
git archive origin/codex/final-env-floor-light | tar -x -C "$review342_scratch"
REVIEW_342_ROOT="$review342_scratch" \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  -m pytest -q tests/test_review_342.py
```

위 명령 전 원격 head가 `04eb11c6`인지 확인한다. 추가 독립 검사 자체는 archive에
Git 메타데이터가 없어도 동작한다. 기존 역사 소스 회귀는 앞서 설명한 Git 객체 접근이 필요하다.
사용한 `/private/tmp/ugrp-review-342.GBkmG2` 추출 폴더는 검증 종료 후 삭제하고 부재를 확인했다.

원본 로그·전체 XML 차이·열린 PR head·main blob 비교·CI 조회는
`/Users/changmin/projects/ugrp/outputs/review-342-04eb11c6/`에 로컬 보관했다.
파일별 SHA-256은 이 문서와 함께 커밋한 `REVIEW_342_EVIDENCE.json`에 있다.
raw 로그가 원격 백업됐다는 뜻은 아니다. 새 물리·학습·평가 코호트가 없어 TensorBoard
변환/화면은 추가하지 않았다. Drive 미사용, 기존 raw·스냅샷 보존.
