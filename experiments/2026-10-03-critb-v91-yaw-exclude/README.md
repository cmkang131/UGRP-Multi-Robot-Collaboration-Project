# v91 yaw: 이미 본 pose를 사례별로 제외

기준 소스는 `89ea80d536b3d2406848ba6e85ead4150ac06bd6`(#356·#362 포함),
작업 브랜치는 `codex/critb-v91-yaw-exclude`다. yaw 부록의 제외 처리와 범위 표시만 수정한다.

## 결정론적 중복 발견

2026-10-03 코디네이터가 한 번 채점한
`/Users/changmin/projects/ugrp/outputs/criterion-b-v91-score-20261003/criterion_B_v91_with_yaw.json`은
종료 코드 2였다. 코디네이터 보고에 따르면 forward/left는 PASS였지만 yaw는
`rotation training/prior pose, map or sample interval ineligible`로 전체가 중단됐다.
이 구현자는 그 결과 파일을 열거나 실제 v91 자료를 다시 채점하지 않았다.

코디네이터는 v91 `zone_wide_door_geometry_v3`의 `eval_only/{r1,r2}/pose.jsonl`이
v88 무하중 훈련 지도 `zone_wide_two_doors_final_v3`의 각 로봇 자료와 바이트까지
같음을 발견했다. r1 SHA-256은
`7eea9447212e3de1ffea9a61876e3234c2d348bc38de7962cca0cc169b86b216`이며,
동결 r5의 `previously_seen_pose_sha256`에 들어 있다. corridor 자료는 다르다.
같은 시작 자세에서 지도별 벽과 접촉하지 않아 결정론적 시뮬레이션이 같은 궤적을
만들었다는 원인 설명은 코디네이터의 관찰이다.

이번 작업에서는 허용된 파일 경로·바이트 수·SHA-256만 따로 대조하여 door의 두 파일이
각 훈련 파일과 같고 corridor의 두 파일은 다름을 확인했다([해시 기록](pose_identity.json)).
pose 행을 파싱하거나 접촉·수치 오차를 조사하지 않았다.

**로봇이 지도 고유의 형상과 상호작용하지 않았다면, ‘다른 지도’라는 이름만으로
새 held-out 근거가 되지 않는다.** held-out 수집은 훈련과 시작 자세·궤적이 달라야 한다.
v92를 포함한 앞으로의 held-out 설계는 **수집 전에 훈련 pose 바이트와의 중복을 반드시
점검해야 한다.** 기존 자료의 해시와 예정 시작 자세·명령 궤적에서 중복 가능성을 확인한다.
실제 수집 파일의 해시는 수집 뒤 채점 전에 다시 대조하고, 겹친 자료를 새 근거로 세지 않는다.

## 제외와 판정 범위

[동결 B 설명](../2026-10-01-final-env-v87-calibration-fit/README.md)은
“이미 본 pose 바이트·훈련 지도는 held-out에서 제외”한다고 정했다.
동결 `validate_consumer_criterion_b.py::score`는 `prior` 여부를 사례별로 판단하고
그 사례의 검증 판정을 null로 남긴다. 이 사례별 제외를 yaw 경로에도 적용했다.

- 이미 본 pose 사례는 `reason=PREVIOUSLY_SEEN_POSE_BYTES`, `pass=null`,
  `metrics=null`로 남기며 pose 해시를 표시한다. 제외 사례는 수치 계산에 넣지 않는다.
- 나머지 사례는 같은 동결 `evaluate_axis`와 임계값으로 채점한다.
  훈련 여부·허용 지도·dt=0.05·지도 중복 검사는 여전히 전체 부적격 오류다.
- `maps_observed`는 제공된 지도, `maps_scored`는 실제 수치를 계산한 지도다.
  누락·제외·지원 부족으로 계산하지 못한 지도는 `maps_not_scored`에 남긴다.
  `maps_not_supplied`는 제공되지 않은 지도만 나타낸다.
- 한 지도만 남으면 yaw 범위는 `PARTIAL_MAPS`다. 남은 사례가 통과해도 두 지도 전체
  `pass`는 null이며, 남은 사례가 실패하면 false다. 전부 제외된 경우도 null이다.
  CLI 결합 요약의 `rotation_scope`와 지도 목록에도 같은 제한을 표시한다.

forward/left·기존 B 보고서·동결 파일·임계값·훈련 후보는 보존한다.
실제 v91 재채점은 독립 검토 뒤 코디네이터가 한 번 수행한다.
이 수정은 새 확증 수집이나 후보 승격이 아니다.

## 검증

```text
yaw 합성 검사: 87 passed in 23.96s
관련 회귀검사(yaw 포함): 305 passed in 39.61s
원본 보존: 66 files byte-identical; 15 functions byte-identical
```

합성 자료로 중복 pose 제외, 남은 지도 통과/실패, 전부 제외, 지도 누락,
학습·지도·dt 오류의 강제 거부, CLI 범위·종료 코드, forward/left 보고서의
JSON 직렬화 바이트 동일성을 확인했다. 남은 yaw 수치도 동결 evaluator의 직접 호출과 같다.
기존 `validate` 함수는 yaw 결합 요약의 범위 필드 추가 외에 바이트가 같다.
동결 B·r4·r5·부록·약속·기존 기록을 포함한 66개 파일의 해시가 보존됐다.

[관련 검사 로그](related-tests.txt)·[JUnit](related-tests.xml),
[환경·검증 기록](verification.json), [보존 해시](preservation.json)를 남긴다.
GitHub CI와 독립 검토·실제 재채점은 로컬 합성 검사와 별도다.

물리·렌더·모델 호출은 0회다. 새 실제 평가 결과가 없는 합성 회귀검사이므로
TensorBoard 변환·뷰어를 만들지 않는다. 실제 재채점과 결과 등록은 코디네이터에게 남긴다.
Drive·공용 실행 잠금·서버는 사용하지 않는다.

Refs #219 #344
