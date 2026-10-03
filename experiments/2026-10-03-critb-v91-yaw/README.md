# v91 기준 B의 별도 yaw 부록 연결 — 합성 검증만 완료

`codex/critb-v91-yaw`에서 #356의 `d4694309d13da8fd562d62ce809a22eeb5bdc065`를
기준으로 [후속 연결 설계](../2026-10-03-critb-rotation/SCORING_HOOK.md)를 구현했다.
**이 PR은 #356이 먼저 main에 병합되는 데 의존한다.** #360의 동결 부록·r5를 그대로 읽는다.
시작 시 `origin/main=db37ee4a`를 확인하고 `git merge origin/main`은 already up to date였다.

이번 구현자는 실제 `/Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-*`의
파일을 **열람·해시·채점하지 않았다.** plan/bundle/result의 허용된 신원 필드도 읽을 필요가
없었으며, 테스트는 임시 폴더에 직접 만든 합성 raw만 사용했다. 물리·렌더·모델 호출은 0회다.
실제 held-out 채점은 이 PR의 독립 검토 뒤 코디네이터가 한 번 수행한다.

## 분리된 시간 근거

| 결과 | 공개 약속 | 확인하는 선후관계 |
|---|---|---|
| 기존 B/r4 forward·left | 댓글 5958329647, 2026-10-02T18:04:39Z | 기존 수집 시작/잠금 획득 하한보다 앞선 `PRE_COLLECTION` |
| 별도 r5 yaw | 댓글 5966135675, 2026-10-03T05:56:19Z | `PRE_SCORING_AND_READING_NOT_PRE_COLLECTION` |

**실제 v91 수집은 yaw 공개 고정보다 먼저였다.** yaw를 수집 전 동결로 소급하지 않는다.
새 결과의 `rotation_addendum.ordering_evidence.kind`, `pre_collection_claim=false`,
`v91_collection_precedes_commitment=true`에 이 차이를 명시한다. 기존 B의
`ordering_evidence`와 수집 전 시간 검사는 그대로 보존한다.

[공개 yaw 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966135675)의
id·URL·GitHub 서버 생성/수정 시각·본문 원문·본문 SHA-256·두 공개 해시를
[commitment.json](commitment.json)에 저장했다. 생성/수정 시각은 같고, 스냅샷 SHA-256은
`cad257ab12c41b786e36a1688ef522ee512551460ec91dc8e1b44a162fe450ca`다.

- 부록: `6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08`
- r5: `978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97`

검증기는 raw를 읽기 전에 스냅샷과 실제 두 파일의 바이트 해시를 검사한다.
`created_at < raw_read_started_at <= scoring_started_at`를 엄격하게 요구한다.
여기서 읽기 시각은 **이번 호출의 첫 raw 읽기 시각**이다. 공개 댓글의 미열람 선언과
이 구현 기록을 연결하지만, 다른 참여자의 과거 미열람이나 실행 컴퓨터 시계의 동기화를
암호학적으로 증명하지 않는다. 이 선언을 수집 전 증거와 혼동하지 않는다.

기본값은 고정 스냅샷 재현이다. `--refetch-commitment`는 선택한 두 댓글을 모두 다시 조회한다.
조회 실패·내용 변경 시 해당 경로는 자동 fallback 없이 `INELIGIBLE`, `pass=null`이다.
이번 작업에서 두 댓글 모두 실시간 재조회하여 스냅샷과 같음을 확인했다.

## 결과와 판정

`--rotation-addendum`를 명시하면 기존 B 보고서 옆에 `rotation_addendum`와
`with_rotation_addendum`를 추가한다. 기존 최상위 `axis_pass`·`pass`·사례·수치와 r4 회전
null을 덮어쓰지 않는다. yaw 전용 약속/후보 오류는 yaw만 무효화한다. yaw 계산 도중
raw 또는 B 증거가 바뀌면 두 보고서 모두 무효화한다.

r5의 `candidate_axes.rotate.consumer_fields`만 별도 프로필로 사용한다. 기존 r4
forward/left 동일성, 미검증 상태, null인 `axis_validation`/`params.motion`, turn 단독 gain,
양의 스칼라 tau, M1 잡음 하한, dt=0.05, rest noise ON, scale OFF/0을 검사한다.
고정 r5 훈련 manifest를 읽어 pose 해시를 기존에 본 목록에 합치며 훈련 원본을 다시 열지 않는다.

수치는 동결된 `evaluate_axis(case, 2, profile, B)`를 그대로 호출한다. 계단/PRBS·coast의
모든 0.05초 시작점, 0.2/0.5/1/2/3/3.2초 예측 시간, forward m·left m·yaw rad의
각 그룹에서 p95 정규화 절대오차 ≤2와 2σ 포함률 ≥90%를 모두 요구한다.
두 지도 중 하나가 없거나 지원/후보가 없으면 null이며, 관측한 그룹에서 실패가 있으면 false다.
정규화 p95 조건은 90% 포함률을 달성했다고 완화되지 않는다.

별도 결과는 두 파일 해시, 공개 기록, 채점 소스 SHA-256, 실제 읽은 입력의 해시,
지도별 수치·미제공 지도·null 사유를 보존한다. 읽은 raw·증거·채점 소스는 계산 후 다시 해시한다.
옵션 사용 시 CLI 종료 코드는 별도 결합 요약 기준 0=true, 1=false, 2=null이다.
후보 승격·학생 제어기·로더·혼합 명령·loaded/fine·물리 성공 검증은 포함하지 않는다.

## 검증

```text
관련 합성·회귀검사: 289 passed in 37.30s
CI 분할·실행 경로 검사: 102 passed in 8.36s
```

합성 yaw의 정상/지도별 실패/지도 누락, 임계값 직전·직후, 세 오차 성분,
±계단/±PRBS/시간 지원 누락, 공개 기록·후보·부록·manifest 변조, 재조회 실패,
훈련 pose 재사용, 명령 lease/시계, 계산 중 입력 변경을 검사했다. 같은 합성 자료의
forward/left 및 기존 B 보고서는 옵션 사용 전후 JSON 직렬화 바이트가 같다.
yaw 수치도 동결 evaluator의 직접 호출과 직렬화 바이트가 같다.

[관련 로그](related-tests.txt)·[JUnit](related-tests.xml), [CI 로그](ci-tests.txt)·[JUnit](ci-tests.xml),
[환경·검증 기록](verification.json), [64개 파일 보존](preservation.json)을 남긴다.
첫 profile 점검에서 동일한 지도 목록의 순서 차이를 발견해 집합 비교로 바로잡았다.
이후 첫 yaw suite 60개와 위 최종 확장 suite가 통과했다. 테스트 중 실제 held-out 경로 접근은
금지하며 네트워크·물리·렌더 모듈도 차단한다.

새 실험/held-out 평가 결과가 없는 합성 회귀검사이므로 TensorBoard 변환·뷰어를 만들지 않았다.
실제 채점 후 평가 결과 등록은 코디네이터에게 남는다. Drive·공용 실행 잠금·서버는 사용하지 않았다.
`.github/workflows`, 실행 번들·workflow 번호와 frozen 파일은 바꾸지 않았다.

## 코디네이터 인계 — 검토 뒤 한 번만 실행

아래 명령은 이번 작업에서 실행하지 않았다. 존재하지 않는 새 출력 파일을 지정한다.

```sh
python3 -m scripts.validate_consumer_criterion_b_v91 \
  --raw /Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-04043e27-20261003/zone_wide_corridor_final_v3 \
  --raw /Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-04043e27-20261003/zone_wide_door_geometry_v3 \
  --rotation-addendum --refetch-commitment \
  --output /absolute/path/outside-raw/criterion_B_v91_with_yaw_NEW.json
```

Refs #219 #344
