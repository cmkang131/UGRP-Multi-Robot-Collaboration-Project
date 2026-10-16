# Dev 평가기 재리뷰 P1 수정 — 2026-09-27

기준: PR #235, `codex/zone-pair-executor`, HEAD
`a2c1db7ef0a1b70d9e24fc737b388f26fd88d886`.
리뷰: `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-pair-dev-review2.md`.
이번 기록은 미커밋 로컬 수정과 비물리 회귀 검사이며 연구·물리 실행 결과가 아니다.

## 원인과 수정

기존 평가는 양쪽 lower GO·segment/상태·종점 거리만으로 다음 carry GO까지 면제했다.
그 결과 B에서 수평 낙하 후 재접촉하거나 체크포인트에서 재들기 후 재낙하해도
최종 배치가 정상이고 영상 승인 값이 있으면 `DEV_PASS`가 됐다.

- 명령 조건은 면제 후보만 정한다. 첫 들림 이후, 현재 바닥 지지가 확인되지 않은 표본은
  양쪽 로봇의 두 손가락이 모두 기존 1 N 기준을 충족해야 한다. 높이가 아직 높더라도
  파지를 잃은 표본을 `drop_samples`에 남겨 뒤의 착지·재접촉으로 실패가 사라지지 않는다.
- 바닥 지지는 8개 꼭짓점을 모두 검사한다. 윗면은 빔 두께만큼 높으므로, 각 꼭짓점의
  바닥에 놓였을 때 높이(아랫면 0, 윗면 빔 두께) 대비 기존 -5 mm~+1 cm 범위를 쓴다.
  두께는 observer가 기록한 순서의 로컬 수직 모서리 길이로 구한다. 기울어진 빔의
  현재 수직 전체 길이를 두께로 쓰지 않는다.
- 인접 trace 사이 각 꼭짓점의 절대 수직 속도도 기존 0.02 m/s 이하여야 한다.
  이전 표본이 없거나 간격이 0 이하/기존 최대 간격 초과이면 지지를 확인하지 않는다.
  이는 약 50 ms trace로 계산한 관측 구간 평균이며 연속 물리 검증을 대신하지 않는다.
- 해당 후보 구간에서 바닥 지지 후 공동 파지·모든 꼭짓점 4 cm 이상을 0.2 SIM초 유지하면
  재들림으로 확정하고 그 구간의 면제를 닫는다. carry GO를 기다리지 않으며, 이후
  낮아지거나 다시 바닥에 정지해도 면제를 다시 열지 않는다. 새 구간의 lower GO는 별도로 평가한다.
- 평가 근거에 구간별 `floor_supported_at_s`, `relifted_at_s`를 추가했다.
  제어기·물리 observer·입력·실행 경로에는 변경이 없다.

## 사전등록 변경 범위

`prereg_DRAFT.json`의 **criteria 전체와 모든 수치는 HEAD와 동일**하다. 실행 전 DRAFT의
`stage_rules.drop`, `planned_setdown.scope` 설명을 위 로직에 맞게 고치고
`planned_setdown.floor_support`, `planned_setdown.relift` 정의를 추가했다.
기존 release/floor/grasp/lift/sample-gap 수치를 재사용하며 새 임곗값은 없다.
정의 명시가 필요한 이유는 종전의 명령 구간만으로 실제 지지·재들림을 대신하던 해석을
제거하기 위해서다. 원본 바이트 해시 검사는 유지되므로 새 실행은 수정된 DRAFT를 새로
복사·해시 고정해야 한다. 과거 실행 사전등록·manifest를 수정하거나 재결합하지 않았다.

## 검증

평가기 수정 전에 두 리뷰 반례를 먼저 추가했다. B의 파지 상실은 r1/r2/양쪽의 3가지,
재들기 뒤 재낙하는 파지 상실/파지를 유지한 높이 상실 2가지로 검사했다.
수정 전 **5 failed / 정상 대조군 1 passed / 86 deselected**였고, 실패 5건 모두
기존 평가기의 잘못된 `physical_success=true`를 확인했다.

수정 후 추가 경계 검사까지 포함하여 **96 passed, 2.22 s**:

- 리뷰 반례 5가지 모두 `no_drop=false`, 최종 성공 거절.
- carry GO 전 재들림 시각 확인 및 다시 바닥에 정지해도 면제 재개 없음.
- 한쪽 끝만 바닥에 닿은 빔, 바닥 근처지만 빠르게 하강 중인 빔, 손가락 하나만 파지 상실 거절.
- 정상 대조군 2개 및 기존 x=2.40 하역·재파지·문 통과·B 최종 방출 유지.
- 기존 관측 누락·사전등록 해시 검사, 저장 파일 재평가, fake-world 정상/abort 통합 회귀 유지.

첫 수정 후 검사에서는 재낙하 fixture가 문 통과도 실패하여, 그 뒤 배치 성공까지 요구하던
부가 assertion 2건이 실패했다(90 passed / 2 failed). 문 slab 안 재낙하를 거절하는 것은
의도된 동작이므로 정상 대조군에서만 배치 성공을 요구하도록 테스트를 바로잡았다.

최종 명령:

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_dev.py --basetemp=./.pytest_tmp
```

잠금 없이 비물리 검사만 실행했다. MuJoCo world 생성·stepping·렌더링, 모델 호출은 없다.
`git diff --check` 통과, 기준 수치 불변 확인, `.pytest_tmp` 삭제·부재 확인을 수행했다.

## 남은 범위

- 물리 실행·실제 영상·실험 TensorBoard는 미실행이다. 합성 trace와 fake-world 소프트웨어
  회귀만 수행했으므로 실험 snapshot/viewer는 만들지 않았다.
- `git fetch origin`은 공용 `.git` 쓰기 제한, `gh pr list/view`는 네트워크 제한으로 실패했다.
  원격 PR/CI·최신 중복 작업은 미확인이다. 지정된 로컬 HEAD만 기준으로 사용했다.
- 커밋·push·PR 쓰기·병합·기본 checkout 갱신은 하지 않았다. UGRP 예외에 따라 Drive를
  사용하지 않고 이 로컬 프로젝트에 기록했다. 물리 실행 전 소스 검토·커밋·고정은 후속 작업이다.
