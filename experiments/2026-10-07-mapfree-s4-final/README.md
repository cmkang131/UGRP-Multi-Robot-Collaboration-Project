# explore7 — s4 격자 벽 거부, 마지막 개발 반복

## 수정·계산 전 사전 등록 (2026-10-07)

시작 `69054a84`, PR #409 `claude/mapfree-explore`. v4 개발 유효 참 B4/6·거짓0·s4 두 seed의
125s 회복 소진을 보존한다. 이번이 이 트랙의 마지막 개발 반복이며 새 결과 뒤 재튜닝하지 않는다.
MuJoCo/물리/렌더/모델 호출0. s4/G×4701/4702 oracle 동일 궤적은 독립 증거로 합산하지 않는다.

1. 저장 v4 own grid/명령/경로에서 첫 거부와 최종 정지 지점을 복원한다. B 목표 셀·경로 중심 셀·
   Nav2 외곽 footprint의 lethal 셀을 분리한다. 실제 벽과 셀 polygon 교집합/중심 거리, `.05m`
   정적 raster 여유 및0.1m 격자의 차이를 수치·그림으로 기록한다. 실제 벽은 평가 그림·진단에만.
2. pinned explore_lite ABORTED/timeout→blacklist→다음 frontier/소진 종료와 RoundRobin 종료를
   줄 단위 대조한다. 이미 같으면 반복/무한 재시도나 정적 B를 frontier로 바꾸지 않는다.
3. 차이가 있으면 원본의 누락 동작만 default-off `public_ros_v5`에 적용한다. 해상도 원인이면
   Nav2의 라이브러리 기본0.1m와 bringup 예시0.05m를 구분하고, **원 bringup0.05m 한 값만** 사용한다.
   static raster의 cell-half padding은 해상도의 절반으로 일관되게 정한다. 몸체/문/물체 형상·padding·
   soft inflation·회복·카메라·잡음·B 확인·예산·기준은 유지한다. 여러 해상도 탐색/결과 뒤 튜닝 없음.
   기존 v1–v4 bytes와 default off를 보존한다. runtime에는 평가 기하/물체 GT를 넣지 않는다.
4. 후보가 생기면 관련 시험 통과→소스 커밋·push→기존 개발10을 **한 번**만 실행한다.
   개발 관문은 원 `run_persistent.development_pass` 그대로: 시작 겹침4 HOST_SETUP_ERROR,
   유효6건 참 B6·거짓0·무한 정지/회복 소진 없음, 원 접촉/replan 집계 유지.
   s4만 성공해도 나머지 기준을 임의로 빼지 않는다.
5. 개발 전체 관문을 통과할 때만 소스·설정을 봉인하고 기존 미개봉 I/J×5701/5702 32쌍의
   oracle static을1회 실행한다(참 B≥30/32·거짓0 및 기존5기준 불변). 원 cohort hash/생성 규칙 불변.
   개발 또는 새32 관문 실패 시 중단·원인 기록. 추가 개발/재시도·frontier/noisy 임의 개봉 없음.

raw `/Users/changmin/projects/ugrp/outputs/mapfree-s4-final-v1/`, 기존 자료 보존·ENOSPC=HOST_ERROR.
CPU 속도 비교가 아니므로 timing lock 없음. 기존 venv/plot deps 재사용, 설치0. 사용자 미추적4파일 보존.
시험 통과를 확인한 뒤 commit/push·Codex trailer, PR #409 DRAFT·병합/강제 push/reset/다른 worktree 수정0.
TensorBoard 변환/Drive는 앞선 사용자 결정대로 생략한다.

## v4 진단 및 마지막 후보 동결 전 결정

[정지 셀 원장](results/diagnosis.json), [원본 줄 대조](REFERENCES.md).
첫 거부110s에서 B는 raw/cost0이고 경로 중심89개 모두 lethal/inscribed/unknown0이다.
frontier는 null이며 이번 실패는 static_map 모드다. +0.70s의 요청 footprint 외곽이
lethal `(57,60)`, `(58,60)`에 걸린다. 셀 중심의 실제 벽 여유는 각각15.802/5.737mm이며
각 cell polygon 일부가 wall_divider_1/wall_corridor_1과 실제로 겹친다. **벽 경계의 보수적
격자화**이지 목표 셀의 벽/벽 너머 frontier/완전히 허구인 장애물이 아니다. footprint의 실제 벽
교집합 면적은 현재·거부 자세 모두0이며, 이전 연속 여유 하한0.02836m를 유지한다.
원장의 `actual_geometry_overlap_fraction`은 인접 벽별 면적의 합(벽 중첩 중복 가능)이며 union 비율이 아니다.

![s4: 자유 B/경로, 거부 경계 셀2개, 회복 후 정지](figures/s4-blocked-cells.png)

원본 explore_lite와 frontier ABORTED→다음 목표 동작이 이미 같고, static B에는 다른 frontier가 없다.
따라서 RoundRobin 종료를 바꾸지 않는다. **`navigation=public_ros_v5`, 기본 off**는 원 Nav2
bringup의0.05m 한 해상도만 적용한다. 고정 지도 raster 여유는 기존 cell-half 원리대로0.025m;
shape·footprint padding0.02·inflation0.50/10·회복·센서·B·v7·예산·기준은 불변이다.
기존 v1–v4 경로 bytes 보존. 단위시험24개 통과 후 커밋·push하고 개발10을 한 번 실행한다.
첫 시험의 round-trip 부동소수점2.8e−17을 정확0으로 기대한 fixture만 절대허용1e−12로 수정했으며
관문/실험 계수는 변경하지 않았다. 개발 결과를 본 뒤 해상도·회복을 추가 조정하지 않는다.

## 개발 통과·새32 실행 전 동결

고정 구현 `86cdf6d1`을 push한 뒤 개발10을1회 실행했다. 시작 겹침4는 HOST_SETUP_ERROR,
유효6은 모두 참 B·거짓0·navigation_action_aborted0이었다. s4 두 건은179s/접촉0,
s5 두 건은107s/접촉0, s8 두 건은71s/접촉 각1 및 contact_replan 각1이다.
원 `verify_development`가 저장10개 원본과 source hash를 읽고 통과했다. s8 접촉2회는
그대로 남으며 본 탐색 기준의 충돌0 성공으로 해석하지 않는다.

[freeze.json](freeze.json)에 수치 소스·설정·원 I/J32 manifest·개발 source/results hash를 고정했다.
해상도/관문 재튜닝 없이 같은 후보로 미개봉 I/J×5701/5702 oracle static32를1회 실행한다.
이번 요청 범위는 그 정적 기준선 확인까지이며 후속 frontier/noisy를 자동 실행하지 않는다.

## 최종 결과: 개발6/6, 새 오라클 정적32/32

진단 `7f2b8f0c` → 후보 `86cdf6d1` → 개발1회 → 동결 `06d4af9e` → 새 확인1회를 완료했다.
사전 등록 해상도/설정/기준을 유지했고 추가 개발 반복이나 결과 후 수정은 없다.

| 개발 묶음 (각2 seed) | v4 → v5 참 B | v4 → v5 modeled s | v4 → v5 거리 m | v4 → v5 coverage | v5 접촉/재계획 |
|---|---:|---:|---:|---:|---:|
| s4/G | 0→2 | 125 실패→179 확인 | 4.6500→6.9975 | 39.49→63.26% | 0/0 |
| s5/G | 2→2 | 101→107 | 3.7866→4.1178 | 74.38→67.43% | 0/0 |
| s8/H | 2→2 | 74→71 | 1.4324→1.4874 | 46.55→32.88% | 각1/1 |

시작 겹침4건은 이전과 같은 HOST_SETUP_ERROR다. **유효6건 참 B4→6, 거짓0, action abort0**으로
기존 개발 verifier 통과. s4 v5는 collision prediction/recovery event도0이며 원 기하를 그대로 두고
경로를 이어 갔다. s5 시간/거리 증가·coverage 감소, s8 coverage 감소/접촉 잔존도 보존한다.
개발 성공을 모든 지표 개선이나 충돌0로 표현하지 않는다. [개별 전후](results/development-comparison.json).

![s4 v4와 v5의 실제 2D 평가 궤적, GT 기하는 평가 그림에만](figures/s4-v4-v5-path.png)

새 확인은 원 미개봉 I/J×5701/5702 코호트 bytes를 그대로 사용했다.
[32건 개별 표](results/confirmation-table.md), [원 요약](results/summary.json).

| 맵 | 참 B/4 | I / J 확인 modeled s (각2seed 동일) | 접촉 | 잘못된 문 |
|---|---:|---:|---:|---:|
| s1 | 4/4 | 116 / 98 | 0 | 0 |
| s2 | 4/4 | 74 / 71 | 0 | 0 |
| s3 | 4/4 | 83 / 77 | 0 | 0 |
| s4 | 4/4 | 158 / 188 | 0 | 0 |
| s5 | 4/4 | 77 / 74 | 0 | 0 |
| s6 | 4/4 | 116 / 71 | 0 | 0 |
| s7 | 4/4 | 74 / 71 | 0 | 0 |
| s8 | 4/4 | 71 / 107 | 0 | 0 |

**oracle static 관문 참 B≥30/32·거짓0을32/32·거짓0으로 통과했다.** 접촉0·잘못된 문0,
B 첫 확인까지 중앙77 modeled s/2.9463m, coverage 중앙51.13%다. 짝 seed가 oracle에서 같은
결정론적 궤적을 반복하므로32개 독립 확률 표본이라고 주장하지 않는다. 이전 다른 코호트22/32와
합산하거나 동일 코호트의 인과 개선율로 비교하지 않는다. 기준은 변경하지 않았다.

이것은 정적 지도/B가 주어진 **평가기 선행 관문**이다. B 구역에 실제 도착한 것, frontier 탐색의
기존5기준 통과, 현실 잡음/실물 성공을 뜻하지 않는다. coverage<40%인8건도 원표에 그대로 남긴다.
이번 요청 범위의 마지막 개발 반복을 완료했으며 frontier oracle0·현실 잡음0, 후속 성능은 미검증이다.

## 검증·보존

- 관련3파일 **24 passed**. v1–v4 runtime/source bytes 불변, default-off 객체 bytes 동일,
  명시 opt-in·0.05m map 계약·입력 좌표 round-trip, wall-boundary/padding-only 분류,
  frontier 실패→다음 후보/전부 blacklist 종료와 static B의 별도 종료를 검사했다.
- 개발 verifier가 실제10건 원본·소스 hash로 통과한 뒤에만 새32를 개봉했다.
  [verification](results/verification.json)은 동결 소스/설정, 원32개 ID·seed,
  개별 raw result/aggregate 동일 및 grid metadata0.05를 확인한다. 원 native 탐색 코어는 그대로다.
- [raw manifest](results/raw-manifest.json):388파일68,831,248bytes를 primary outputs에 로컬 보존.
  원본/과거 실패/사용자 미추적4파일 보존, raw 원격 백업 아님. 그림2장은179/55KiB로 experiments에 보존.
- `explore7-resolution`, `explore7-confirmation` 두 session은 정상 종료. 새 물리/MuJoCo/렌더/모델 호출0,
  속도 측정/잠금0, 새 의존성/venv0. PR #409 DRAFT·병합 금지. 다른 worktree/PR #405 변경0.

재현 명령은 기록용이며 이번에 개발/확인을 추가 실행하지 않는다. 새 출력 경로만 허용한다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-mapfree-s4-final/code/run_resolution.py --navigation public_ros_v5 --cohort diagnostic --output <new-development>
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-mapfree-s4-final/code/run_resolution.py --navigation public_ros_v5 --cohort confirmation --freeze experiments/2026-10-07-mapfree-s4-final/freeze.json --gate-development <new-development> --output <new-confirmation>
```
