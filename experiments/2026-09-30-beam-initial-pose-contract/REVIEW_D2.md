# PR #315 D2 보완 — 독립 형상과 누락 변이

검토 기준은 `823ca2ced2fb65e771ce2be9c08a2864e08db804`와
[독립 리뷰 D](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/322),
[#315 지적 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/315#issuecomment-5911364934)이다.
수정 전에 `origin/main`을 병합했고 충돌은 없었다. 기존 실행기·등록·소스 pin은 수정하지 않는다.

## 지적 → 수정

D2는 현재 차체·팔 구현의 누락이 아니라, 누락을 탐지하지 못하는 테스트 결함이다.
기존 테스트는 planner가 돌려준 부품 수로 검사 횟수를 정하고 같은 출력으로 기대 형상과
장애물 위치를 만들었다. 빈 목록이면 실제 carrier 검사가 한 번도 실행되지 않았다.

- v3 규약의 정류장 반경 `.4732`, 사전 정류장 반경 `.7232`, 차체
  `[-.100, .1682] × [-.105, .105]`, 팔 `[0, .2332] × [-.035, .035]`를
  테스트에 독립적으로 고정한다. production 상수·TeamFootprintV3·반환 형상으로 기대값을 만들지 않는다.
- 양 역할 모두 정류장·사전 정류장의 차체/팔 **4개 다각형**, 각 꼭짓점 4개,
  부품 순서·좌표·heading·접근 양끝·SEARCH를 검사한다.
- 세 공개 coarse 자세에서 독립 형상을 직접 이동시켜 전체 XY 오차 모서리,
  yaw 양끝/내부, 접근 비율 0/.17/.5/.91/1을 검사한다. yaw 내부 극값 테스트도 유지한다.
- 리뷰의 2mm 정류장 벽 `(1.118816959, .055312013)`과 반대 역할의 대칭 벽을 고정한다.
  독립 규약의 실제 차체 꼭짓점과 겹침을 확인한다.
- 접근 90% 지점의 차체 벽과 팔 때문에 확장되는 정류장 AABB의 벽을 양 역할,
  obstacles/terrain 모두에 넣는다. SEARCH·빔·반대 carrier는 전체 오차 범위를 감싼
  독립적인 보수적 사각형에서도 닿지 않아야 한다. 팔 사례는 AABB의 보수적 거절이며
  실제 3D 접촉을 주장하지 않는다.

## 재현 방법

`review_d2_verify.py`는 공용 테스트 잠금 아래 기존 Python 환경으로 실행한다.
원본 테스트를 리뷰 SHA의 Git blob에서 임시 폴더로 읽고 정상/누락 변이를 비교한다.
변이는 각 별도 Python 프로세스에서 planner의 TeamFootprintV3 참조만 교체하며
디스크의 production 소스·봉인·등록 bytes는 바꾸지 않는다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-beam-initial-pose-contract/review_d2_verify.py \
  /Users/changmin/projects/ugrp/outputs/beam-initial-pose-contract/review-d2-NEW-ID
```

로컬 물리·렌더·모델·네트워크 호출은 차단한다. 이 로컬 제한은 GitHub CI에는
적용하지 않는다. 정상 CI 전체를 실행하고 취소하거나 skip 지시를 넣지 않는다.
정적 회귀 결과이며 새 물리/훈련/평가 trial과 TensorBoard 성공률을 생성하지 않는다.

## 실행 결과

최신 검증 소스의 SHA-256은 [summary.json](review_d2/summary.json)에 있고,
정확한 명령·개별 실패 사례는 [results.json](review_d2/results.json)에 있다.
전체 파일/원본 해시는 [verification.json](review_d2/verification.json)에 연결했다.

- 수정 전 정상/전체 carrier 제거/팔 제거: 각각 **56 passed**. 기존 검사의 허점을 재현했다.
- 수정 후 정상: **164 passed** (새 geometry 64, 기존 passage 44, 등록 source 22,
  study pinning 33, 기존 목적지 B 경로 1). 소스 pin 실패 0건.
- 수정한 geometry 사례 **18/18**이 적어도 하나의 제거 변이에서 실패한다. 변이 프로세스는
  모두 pytest exit 1이며 collection/import error 0건이다. 정상 suite와 같은 64개를 수집했다.

| 제거한 형상 | 양쪽 역할 | end_neg만 | end_pos만 |
|---|---:|---:|---:|
| 차체+팔 | 18 failed / 64 | 12 failed / 64 | 12 failed / 64 |
| 팔 | 10 failed / 64 | 8 failed / 64 | 8 failed / 64 |
| 차체 | 3 failed / 64 | 3 failed / 64 | 3 failed / 64 |

이 표의 failed는 의도적으로 지운 형상을 탐지한 결과다. 원본 전체 형상에서는 164개 모두 통과한다.
전체 carrier 제거 18건과 팔 제거 10건의 실패 원문은 각각
[carrier 로그](review_d2/after-carriers-both.txt), [arm 로그](review_d2/after-arms-both.txt)로 확인한다.

작업 시작 시 최신 main `b10907c5f2c84f2712030f48fb38061fd4f51281`를 먼저 병합했다.
병합 충돌은 없었고 merge commit은 `d2ac7437905dc4b9d2c8be6725e951e218d22e3a`다.
기존 planner/runtime·지도·설정은 검토 SHA와 바이트가 같으며 보호 파일 **44/44**도 원본 해시와 같다.
기존 등록 소스 테스트를 약화하거나 해시/등록을 다시 봉인하지 않았다. 공용 잠금 반환 기록도 보존했다.

첫 검증은 새 테스트의 SEARCH 꼭짓점 시작 순서 때문에 3 failed/161 passed였다.
기하 자체가 아니라 기대값 배열의 순서 문제였으며 테스트만 고친 뒤 위 전체 결과를 얻었다.
[첫 실패 로그](review_d2/initial-fixture-order.txt)를 보존한다.

원본 로그와 JUnit은 `/Users/changmin/projects/ugrp/outputs/beam-initial-pose-contract/review-d2-20260930-b` 및 첫 시도 `/Users/changmin/projects/ugrp/outputs/beam-initial-pose-contract/review-d2-20260930-a`에 로컬 보존한다.
Git의 작은 로그 사본은 줄 끝 공백만 정리했고 원본/사본 해시를 구분했다. 이 기록은 raw 전체의 원격 백업이 아니다.
정상 GitHub CI는 push 후 별도 상태로 보고하며, CI와 본 정적 검사는 물리·E2E 인수가 아니다.
