# v91 새 무하중 자료에 고정 기준 B 연결 — PR #356 리뷰 수정

기존 기준 B와 r4 후보를 바꾸지 않고, v91 수집 자료의 신원과 수집 전 약속의
선후관계를 검사하는 [별도 검증기](../../scripts/validate_consumer_criterion_b_v91.py)를 추가했다.
실제 v91 자료는 이 작업에서 채점하지 않았다. 합성 자료(synthetic raw)만 사용했다.
후보는 계속 `CANDIDATE_UNVALIDATED`이며 학생 제어기나 보정 로더를 수정하지 않았다.

## 허용하는 자료

| 항목 | 고정값 |
|---|---|
| 번들(bundle) | `zone-final-pair-v91` |
| 실행 경로(workflow) | `zone-final-pair-heldout-v91`, `3.3.0` |
| 수집 소스 | `04043e274af7351f3d35cb6be77d948cac1b8c6a` |
| 조건 | `calibration-unloaded`, seed `911` |
| 지도 | `zone_wide_corridor_final_v3`, `zone_wide_door_geometry_v3` |
| 자료 용도 | `HELD_OUT_VALIDATION`, `training_eligible=false`, `teacher_only=true` |
| 물리·관측 설정 | `masterpi_v3`, `floor_light_v1`, `cargo_noslip_v1`, weld OFF, 초음파 OFF |

각 지도 수집의 plan·bundle·사례 result·전체 result를 대조한다. 완료, 전체 분모 1,
소스 불변, 일정, 발행 명령, 명령 유효시간(lease), pose 간격·행렬은 기존 검증기로 검사한다.
plan이 가리키는 전체 bundle 내용과 `inputs/schedule.json`도
[고정 수집 계약](acquisition_contract.json)의 지문과 일치해야 한다.
bundle 지문을 만들 때 `source_sha256` 항목을 corridor 254개, door geometry 253개 각각
지정 수집 SHA의 실제 Git 파일 바이트와 모두 비교했다. 전체 bundle 비교에는 지도 해시, source 파일별 해시,
측정 일정, 설정, 버전이 포함된다. v88/v90의 ID·용도·소스 문자열만 바꿔도 통과하지 않는다.
case의 `artifacts.sha256.json`은 실제 읽은 bundle/result/schedule/명령/pose와 비교한다.
영상이나 아직 읽지 않은 다른 artifact까지 검증했다고 주장하지 않는다.

훈련 지도 `zone_wide_two_doors_final_v3`, 미등록 지도, 이전에 본 pose 바이트는 거부한다.
자료를 이 후보의 재적합이나 튜닝에 사용하면 새 검증 자료(held-out)가 아니다.
등록과 raw 표시는 출처 감사에 쓰이며, 악의적으로 모든 기록을 다시 만든 경우까지
암호학적으로 증명하는 서명은 아니다.

## 수집 전 약속과 시간 비교

[GitHub 댓글 5958329647](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5958329647)을
`gh api`로 읽고 [commitment.json](commitment.json)에 id, URL, `created_at`, `updated_at`,
본문 원문·SHA-256, 본문에 열거된 네 파일의 해시와 수집 소스를 보존했다.
GitHub 서버의 생성 시각은 **2026-10-02T18:04:39Z**다. 당시 조회에서 수정 시각도 같았다.
댓글 본문에 적힌 로컬 작성 시각을 서버 생성 시각으로 대신 쓰지 않는다.

| 파일 | 댓글에 적힌 SHA-256 |
|---|---|
| `consumer_criterion_B.json` | `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f` |
| `calibration_candidate_r4.json` | `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071` |
| 기존 `validate_consumer_criterion_b.py` | `8d2a693a6e3bbca79a8214fd388bff79a0609400f07de831ad9be3cf22e85a88` |
| `configs/zone_final_pair_v91.json` | `a07d412ced2e5e301c327a07f61ca5ab6bc4cfe1f2c8b7b7f33740e4b3a29307` |

검증기는 스냅샷과 수집 계약 자체의 고정 해시를 확인하고, 위 네 해시를 실제 파일 바이트와
대조한다. 기존 채점기가 불러오는 두 수치 계산 모듈의 바이트도 고정한다.
채점 후에는 약속·계약·원시 입력을 다시 읽어 도중 변경/삭제가 없었는지 확인한다.
보고서의 `input_files`가 이 연결을 보존한다.

**04043e27의 수집기는 plan/result에 직접적인 `started_utc`를 쓰지 않는다.**
대신 실행 직전과 사례 시작 때 `host_start`에 이미 획득한 잠금의 Unix 시각을 남긴다.
검증기는 다음 세 파일에서 아래 항목을 모두 읽고, UTC로 바꾼 뒤 가장 이른 것을 선택한다.

- `<collection>/plan.json`
- `<collection>/result.json`
- `<collection>/<map>/result.json`

읽는 필드는 `host_start.physics_holder.acquired_unix`와
`host_start.concurrent_holders[*].acquired_unix`다. Unix 초는 UTC로 변환한다.
직접적인 `started_utc` 또는 `start_utc`가 최상위나 `host_start`에 함께 기록돼 있으면
이들도 비교에 포함한다. 이 문자열은 UTC 시간대가 명시돼 있어야 한다.
어느 파일의 필수 host/잠금 시각이 빠지거나 잘못되면 거부한다.
끝 시각, 예상 잠금 종료 시각, 파일 생성/수정 날짜(mtime), Git 커밋 날짜는 사용하지 않는다.

잠금 획득 시각은 **정확한 수집 시작 시각이 아니라, 수집 시작 전 하한(lower bound)**이다.
댓글 생성 시각이 이들 중 가장 이른 시각보다 **엄격하게 작아야** 판정을 허용한다.
같은 시각도 거부한다. 오래 유지한 잠금 때문에 실제로 늦게 시작한 수집이 부적격으로
남을 수 있다. 보고서는 선택한 파일·필드·원래 값·변환 UTC·근거 종류를 모두 표시한다.

이 비교는 **GitHub 서버 시계와 실행 컴퓨터가 기록한 UTC 시계에 의존한다.**
실행 컴퓨터 시계의 동기화나 raw 시각의 위변조 불가능성을 증명하지 않는다.
댓글은 수집 전 raw 해시를 예언하지 않으며, 이번 보고서가 실제 읽은 raw 해시를 연결한다.

기본 모드는 커밋된 스냅샷으로 재현한다(`snapshot_only`).
`--refetch-commitment`를 주면 `gh api`로 같은 댓글을 다시 읽어 id·URL·생성/수정 시각·본문을
정확히 비교한다. 이 옵션을 요청했는데 통신/인증이 실패하거나 내용이 달라졌다면
스냅샷 모드로 자동 전환하지 않고 `INELIGIBLE`로 남긴다.
필수 신원·해시·시간·완료·입력 재검사 중 하나라도 확인할 수 없거나 실패하면
전체 및 모든 축의 `pass`는 `null`이고 종료 코드는 2다.

## 수치 판정은 고정 B 그대로

새 검증기는 기존 `score`, `evaluate_axis`, `metrics`, 축 지원 검사와 결과 결합을 재사용한다.
읽기 단계에서 복사한 설정의 수집 ID만 v91로 연결하고, 채점에는 원래 B를 그대로 넘긴다.
선후관계가 확인된 경우 기존 결과의 ‘수집 순서 미확인’ 거부 사유만 해제한다.

- 예측 시간 0.2/0.5/1/2/3/3.2초, 전진·측면·yaw 성분을 지도·축·계단·PRBS별로 검사한다.
- 모든 그룹에서 `p95(|error|/sigma) <= 2`, 2σ 포함률 `>= 90%`가 필요하다.
- 1σ 포함률과 NEES는 참고 수치이며 문턱을 추가하지 않는다.
- 부호 양쪽의 계단/PRBS 또는 충분한 시간 창이 없는 축은 `null`이다.
- **r4의 회전 후보는 null이므로 회전 판정도 계속 null**이다. 두 병진축이 통과해도
  전체 통과는 null(종료 2)이다. 검증된 축 중 실패가 있으면 전체 실패(종료 1)를 유지한다.

합성 사례를 기존/신규 경로에 각각 넣어 모든 그룹·성분 수치가 정확히 같음을 검사한다.
판정은 과정 잡음 예산(process budget)에 대한 오프라인 검사다. PF의 실제 위치 추정,
loaded/fine 보정, 카메라 가용성, 학생 운반 또는 실물 성공을 뜻하지 않는다.
criterion A는 계속 `FAILED_NOT_RESCORED`다.

## 완료 뒤 실행할 명령

아래는 인계용 명령이며 이번 작업에서는 실행하지 않았다. 출력 파일은 존재하지 않는 이름으로
지정한다. 이 검증기는 raw를 수정하지 않고 결과 파일도 덮어쓰지 않는다.

```sh
python3 -m scripts.validate_consumer_criterion_b_v91 \
  --raw /Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-04043e27-20261003/zone_wide_corridor_final_v3 \
  --raw /Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-04043e27-20261003/zone_wide_door_geometry_v3 \
  --refetch-commitment \
  --output /absolute/path/outside-raw/criterion_B_v91_NEW.json
```

각 raw 인자는 plan/result가 있는 지도별 수집 폴더나 그 바로 아래 case 폴더다.
case만 골라도 상위 완료 기록을 함께 검사한다. 두 지도를 함께 넘기는 것을 권장하며,
한 지도만 넘기면 보고서의 `maps_not_supplied`에 빠진 지도를 적는다. 그 보고서는
입력한 지도에만 해당하고 두 지도 코호트 전체 결과를 뜻하지 않는다. 같은 지도 중복 입력은 거부한다.
NumPy·SciPy가 필요하다. 이 Mac의 기존 `python3`에서 관련 검사를 실행했고,
시뮬레이션 가상환경에는 SciPy가 없어 환경 변경 없이 사용 환경을 바꿨다.

## 보존과 검증 범위

작업 기준은 `origin/main=0bf41800272ec4c4bfa035cfc5609af8850e3e48`, 브랜치는
`codex/critb-v91`이다. [preservation.json](preservation.json)의 23개 파일 SHA-256을 테스트한다.
기준 B·r4 후보·기존 검증기, v88/v90/v91 설정·등록·workflow와 관련 실행 소스는 바이트 동일하다.
새 번들 ID나 workflow 번호를 예약하지 않았다. PHYSICS_HANDOFF의 기존 56,860바이트를
그대로 두고 새 절만 덧붙였다. `.github/workflows`는 수정하지 않았다.

관련 자동 검사와 환경·초기 실패는 [검증 기록](verification.json)에 남긴다.
기존 관련 검사 포함 `222 passed in 164.18s`, 중첩 raw 형식 오류 대응을 추가한 뒤
신규 검증기 최종 검사 `75 passed in 12.90s`를 확인했다. 두 실행은 겹치는 테스트를 포함한다.
GitHub 댓글도 실제로 다시 조회해 저장된 스냅샷과 일치함을 확인했다.
물리·렌더·모델 호출·실제 held-out 채점은 수행하지 않았다. 공용 `outputs/`와 실행 중인
프로세스·잠금·서버를 변경하지 않았고 Drive도 사용하지 않았다. 새로운 실험 결과가 없는
합성 회귀검사이므로 TensorBoard 변환/서버/화면을 만들지 않았다. 위 수치와 draft 상태는 초기 구현 당시의
기록이다. 이후 독립 검토의 P1/P2 수정과 로컬 재검증은 [리뷰 대응 기록](fixes/README.md)에 남긴다.
실제 held-out 채점과 TensorBoard 평가 결과 등록은 이번 수정에서도 수행하지 않았다.

## 참고 자료

- [고정 기준 B와 r4의 의미](../2026-10-01-final-env-v87-calibration-fit/README.md)
- [기준 B 원문](../2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json)
- [동결 검증기](../../scripts/validate_consumer_criterion_b.py), [신규 합성 검사](../../tests/test_consumer_criterion_b_v91.py)
- [수집 전 약속 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5958329647), [그 스냅샷](commitment.json)
- [v91 수집 변경·제한](../2026-10-03-calib-fast-guard/README.md), [v90 배경](../2026-10-01-calib-heldout-maps/README.md)
- [수집 인계](../../PHYSICS_HANDOFF.md), [TensorBoard 절차](../../docs/tensorboard.md)

Refs #219 #344
