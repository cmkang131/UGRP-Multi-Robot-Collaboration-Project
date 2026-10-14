# solo4: b48ebdf1 RGB 들기 판정 — 회수 완료, 관측 근거 부족으로 실행 차단

최신 결과: 아래 **2차: 회수 후 검토** 참조. 아래 1차 기록은 회수 전 상태를 보존한 것이다.

## 1차: 회수 전 기록

2026-10-14. HEAD/PR #502 원격 HEAD는 `b48ebdf1672554a24511dd853617408308061a95`.
지정한 근거리 실행 지침, `~/.claude/CLAUDE.md`의 “막히면 레퍼런스 먼저”,
crate `b033e5f914a0d3e221eb77db455d84288104b004`의 `crate4.md`와 판정 코드를 읽었다.
사용자 지시 “프레임이 없으면 회수 요청 파일을 쓰고 멈춘다”에 따라 이 단계에서 중단한다.

## 원장·소스에서 확인한 범위

`outputs/gcp1-runs/solo-diag-{0..5}-b48ebdf1/raw`의 result/명령/평가/계획/장면
6파일씩 총 36개 SHA-256을 manifest와 대조했다. 압축 원장 12개의 decoded SHA도 일치한다.
평가상 lift_success는 **6/6**, 전체 작업 physical_success는 **2/6**(tile 2·5),
입력 감사 위반은 invisible_measurements **0**, held_world_reads **0**이다.
평가 필드는 제어에 전달하지 않았다. 상세 원본 경로·해시와 전체 6건은
[solo4-fetch-summary.json](solo4-fetch-summary.json)에 있다.

| 진단 | 종류 | 관측기 누적 yes/no/unknown | verify/hold 원장 판정 | 들기 전 색 면적 |
|---|---|---|---|---|
| 0 | cyan | 0/0/65 | unknown 50/50 | 0 px (`null`) |
| 1 | can | 0/50/16 | no 50/50 | 3,468 px, 1.12890625% |
| 2 | tile | 41/0/45 | yes 41/71, 대기 unknown 30/71 | 21.8974609375% |
| 3 | cyan | 0/0/66 | unknown 50/50 | 0 px (`null`) |
| 4 | can | 0/50/15 | no 50/50 | 29,171 px, 9.4957682292% |
| 5 | tile | 41/0/45 | yes 41/71, 대기 unknown 30/71 | 25.2447916667% |

관측기 누적 횟수에는 들기 명령 완료 전 호출도 들어간다. 원장의 `rgb_confirmation`
필드는 verify/hold에서만 채우므로 두 분모를 합치지 않는다.

- **큐브:** `sim/grasp_act_solo_rgb.py:69–73`은 hue_mask와 fisheye usable 영역의 교집합 하나만 요구한다.
  hue 범위는 `harness/zone_own_perception.py:82`의 84–100이고, 채도/명도 하한은 252–258행이다.
  `sim/rgb_lift_evidence.py:19–21`에서 픽셀이 없으면 `None`, 58–59행에서 즉시 unknown으로 반환한다.
  두 원본 모두 `before.cyan=null`이므로 단순히 1% 미만이 아니라 **교집합 0픽셀**이다.
  집게 가림, 근접 시야, 색/조명, usable 영역 제외 중 무엇인지는 이미지 없이는 결정할 수 없다.
- **캔:** 색 범위는 `harness/zone_own_perception.py:86`의 124–139다. 들기 전에는 1% 관문을 통과했다.
  `sim/rgb_lift_evidence.py:66–70`은 `parts={}`를 붙인 뒤, 완료 마스크 부재·1% 미만·잔존 40% 미만이면
  수치를 기록하는 74행 전에 반환한다. 따라서 **빈 parts는 완료 마스크 0픽셀의 증거가 아니다**.
  640×480에서 diag-1의 면적 통과 하한은 3,072 px, diag-4는 11,669 px이다.
  before 중심 y는 각각 451.5/423.25 px, 외곽은 279×20/517×81 px로 아래쪽에 치우친다.
  완료 표본에서 실제 면적이 얼마이고 왜 줄었는지는 회수 후 마스크로 확인해야 한다.

## 참고 구현·문헌과 적용 한계

crate b033e5f9의 새 판정은 `sim/crate_rgb_lift.py:147–197`의 `confirm_v3`에 있다.
172–174행은 동일 before 영상 재사용을 unknown으로 차단하고, 186–195행은 손잡이 강체 조건과
몸체 잔존/상대 하향 변화를 분리한다. 이 SHA에는 solo 공용 모듈이 아직 병합되지 않았다.
현재 solo의 `sim/rgb_lift_evidence.py`는 이전 crate v2 추출본이다.
회수 후 v3를 공용화하되 물건별 관측 부분을 실제 프레임으로 정하고 새 토글에서 검증한다.
crate의 분홍 몸체 정책을 단독 물건 전체에 그대로 적용하는 것은 검증된 이식이 아니다.

- [QT-Opt, Appendix D.3](https://proceedings.mlr.press/v87/kalashnikov18a/kalashnikov18a.pdf):
  내려놓기 전후 외부 영상 차분으로 학습 보상을 만든다. 놓기 허가에 앞서 필요한 손목 RGB 판정을
  직접 검증하는 방법이 아니며, 원문도 작은 물체의 거짓 음성을 보고한다.
- [GraspCheckNet, §IV](https://arxiv.org/html/2505.03046v1): 집게 관심영역 검출 뒤 물체 존재를 분류한다.
  국소 파지 근거와 물체 존재를 분리하는 구조를 참고한다. 학습된 검출기/분류기를 이식하거나
  그 논문이 여기의 색 마스크 임계값을 검증했다고 주장하지 않는다.

## 회수 요청과 중단 상태

manifest에 영상 338개가 있으나 로컬 영상은 **0/338**, 직접 본 프레임은 **0**이다.
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/fetch-requests/solo4.txt`에 crate4와 같은
`sha256  원격절대경로` 형식으로 **90장, 1,928,579 bytes**를 요청했다.
18장은 6건의 정확한 before_lift/lift_complete/settled_hold PNG이고,
72장은 각 실행 처음·중간·끝을 포함한 6시각의 review-own/review-top이다.
요청 해시 90/90을 manifest와 외부 SHA256SUMS 양쪽에 대조했다.
같은 사진 대조는 회수한 before를 두 후속 입력으로 재사용한다.

회수·영상 확인·수정·오프라인 재판정·시험·커밋/push·새 대기열·기존 대기열 superseded 변경·
PR 완료 코멘트는 아직 하지 않았다. 코드 HEAD는 그대로다. 다음 단계는 원본 이미지 해시 검증과
6건 시각 검토이며, 실패 4/4 회복·성공 2/2 유지·동일 사진 오탐 0/6을 실제로 확인한 후에만
지정 시험 1–3개 파일, push와 원격 SHA 확인, 대기열과 3줄 코멘트로 진행한다.
Mac 시뮬레이션·렌더·모델 호출·GCP 제출은 0회다.

## 2차: 회수 후 검토 (2026-10-14)

**not-ready.** 요청 90장 SHA-256 **90/90** 일치. 6건의 review-own/review-top을
처음·중간·끝 포함 각 6시각(72장), 정확한 before/complete/settled 18장과 함께
6개 비교판으로 직접 열었다. 큐브 diag-0 before, 캔 diag-1/4 complete는 원본
640×480 PNG도 별도로 열었다(중복이므로 90장에 더하지 않음).
각 실행 범위는 diag-0/4 1.3–22.3초, diag-1 1.3–20.3초, diag-2 1.3–38.3초,
diag-3 1.3–21.3초, diag-5 1.3–37.3초다. 최대 간격 8초이며 연속 영상 전체를
본 것은 아니다. [시각·파일·해시·마스크 수](solo4-visual-review.json).
top 영상과 평가 원장은 원인 확인 전용이며 판정 코어에는 넣지 않았다.

### 큐브: 색 정의가 아니라 확인 시점의 가시성 상실

기준 b48ebdf1 `sim/grasp_act_solo_rgb.py:69–73` 및
`harness/zone_own_perception.py:82,241–260`의 마스크를 그대로 실제 영상에 적용했다.
cyan은 9.3초 review-own에서 diag-0 **4,119px**, diag-3 **3,561px**로 잡힌다
(이 검토 JPG는 320×240이므로 아래 640×480 표와 면적비를 직접 비교하지 않음).
이후 14.3/13.3초에는 0px이며, before 시점 16.3/14.7초에는 둘 다 동일한 바닥
영상이다(전체 파일 SHA까지 같다). 들기 전·완료·유지 **6/6 PNG 모두 유효 cyan 0px**다.
before는 usable 영역을 적용하기 전에도 단 **3px**이고 모두 테두리 밖이다.
색 범위/최소 크기를 조금 바꿔 해결할 색 물체가 영상에 없다. 집게가 물체를
가렸다고 특정할 픽셀 근거도 없다. 검토상 접근 뒤 물체가 아래로 빠지고 바닥만
보이지만, 화면 밖/자체 가림의 정확한 기하학적 분리는 이 자료만으로 확정하지 않는다.

샘플은 `scripts/run_solo_grasp_act_teacher.py:290–294`의 close→lift 전환에서 찍힌다.
이미 물체가 안 보이는 low 자세의 프레임을 기준으로 삼아
`sim/rgb_lift_evidence.py:58–59`의 unknown을 반복한 것이 직접 확인된 원인이다.
가시성을 잃은 후 기억·명령만으로 들림을 선언할 수는 없다.

### 캔: 화면 아래 잘림과 조기 반환이 함께 발생

| 진단/종류 | before 유효 px | complete 유효 px | settled 유효 px | complete/before | settled/before |
|---|---:|---:|---:|---:|---:|
| 0 cyan | 0 | 0 | 0 | 정의 불가 | 정의 불가 |
| 1 can | 3,468 | 0 | 0 | 0 | 0 |
| 2 tile | 67,269 | 67,415 | 67,436 | 1.00217 | 1.00248 |
| 3 cyan | 0 | 0 | 0 | 정의 불가 | 정의 불가 |
| 4 can | 29,171 | 2,358 | 1,476 | 0.08083 | 0.05060 |
| 5 tile | 77,552 | 77,613 | 77,618 | 1.00079 | 1.00085 |

diag-1 before 캔은 화면 맨 아래의 얇은 보라색 조각이며 complete/settled는 바닥뿐이다.
diag-4는 큰 보라색 원형 윗면 일부가 before 아래에 있고, 이후 가는 조각만 남는다.
후속 중심 y는 **453.53/455.41px**, 외곽 높이는 **16/12px**다.
usable 영역을 없애도 후속 면적은 **3,293/2,253px**, before **31,217px** 대비
**10.55%/7.22%**뿐이다. 따라서 usable 영역 제외만으로 40% 잔존을 회복하지 못한다.
색 검출은 접근 중과 before에서 작동한다. 원통의 면적 기준만의 문제가 아니라
시야 경계에서 관측 부위가 없어지는 경우다.

기준 `sim/rgb_lift_evidence.py:66–74`는 부위 기록 전에 1% 최소 면적 또는 40%
잔존 조건으로 반환한다. diag-1 완료는 실제 0px이고, diag-4 완료는 **2,358px <
3,072px**, **8.08% < 40%**라 거부된다. 기존 빈 `parts`는 두 경우를 구별하지 못했다.
`not_confirmed`는 이 시각 규칙의 거부이며 실제 낙하 판정이 아니다.

### 이식한 코어와 바꾸지 않은 경계

crate **b033e5f914a0d3e221eb77db455d84288104b004**의 `confirm_v3`를
`sim/rgb_lift_evidence.py:80`의 공용 `confirm_parts_v3`로 추출했다. 전체 브랜치 병합이나
탐색/경로 커밋 cherry-pick은 하지 않았다. 이름별 강체 부위와 상대 몸체를 분리하고
명령 검증·최소 면적·잔존율·강체 한도·상대 하향 한도·같은 사진 거부를 유지한다.
차이는 반환 전에 두 표본의 모든 수치를 남기는 것으로, `after=null`도 명시한다.
상자 어댑터는 `names=('lug','pink'), relative_to={'pink':'lug'}`로 같은 정책을 쓸 수 있다.
다른 worktree는 수정하지 않았다.

새 토글 **solo_rgb_lift_v3**는 기본 off다. solo는 별도 색 손잡이가 없어
큐브=칠한 면, 캔=보라색 원통, tile=분홍 판이라는 단일 색 부위 정의를 사용한다.
몸체와 손잡이가 같은 마스크라고 꾸며 두 근거로 세지 않는다. 기존 v2와 hue/FOV는
그대로다. runner/teacher 연결 및 v3 결과 키를 추가했고 unknown/no의 놓기 차단을 유지한다.
카메라·외관·파지 경로·정답 입력·모델은 바꾸지 않았다.

QT-Opt Appendix D.3과 GraspCheckNet IV를 원문으로 다시 확인했다(위 출처 링크).
QT-Opt의 놓기 전후 차분은 해제 전 허가에 바로 쓸 수 없고 작은 물체의 거짓 음성도
보고한다. GraspCheckNet은 집게 관심영역에서 물체 존재를 판정한다. 관측 부위가
없는 이번 프레임을 성공으로 만드는 근거가 아니며, 그 학습 모델을 재현했다고 주장하지 않는다.

### 실제 재판정과 시험

원본 18 PNG와 **원장이 기록한 발행 명령**을 `tests/fixtures/solo_rgb_lift_v3/`에
고정했다(출처·파일/픽셀 SHA·명령 원장 compressed/decoded SHA 포함, 총 987,991 bytes).
명령은 runner처럼 첫 close→lift 행과 이후 직전 발행값/현재 관측시각을 복원했다.
평가의 lift_success, 좌표, 접촉은 비교 함수에 들어가지 않는다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_solo_lift \
  --out experiments/2026-10-14-act-solo-teacher/solo4-offline-summary.json --require-ready
```

실제 결과는 **exit 1 (수락 조건 미충족)**. [전체 6건](solo4-offline-summary.json):
실패 회복 **0/4**, 기존 성공 유지 **2/2**, 동일 사진 오탐 **0/6**.
v3 판정은 confirmed **2/6**, not_confirmed **2/6**, undetermined **2/6**다.
동일 사진 대조 unknown **6/6**이며 이를 정확한 낙하 판정으로 세지 않는다.
자료를 걸러 2/2 성공으로 보고하거나 과거 물리 lift 6/6을 v3 성공으로 대신하지 않는다.

지정 범위 3개 파일만 실행:
`test_grasp_act_solo_rgb.py`, `test_rgb_lift_evidence.py`,
`test_grasp_act_solo_run_path.py` — **33 passed, 0 failed, 0 skipped**.
공용 상자 몸체 회전/국소 강체/하향 이동·같은 사진·누락 비교 기록,
실제 6개 영상·스텁 runner의 v2/v3 연결·반복 사진의 놓기 차단을 검증했다.
Mac 물리/렌더·새 GCP 실행·학습 데이터 **0**. 새 물리 성공률은 미측정이다.

### 대기열과 남은 문제

새 SHA는 수정 코드와 실패 근거를 보존하기 위한 후보이며 실행 준비 완료가 아니다.
`20261014-solo-<sha8>.json`은 **blocked / ready=false / runs_enabled=false**로 만들고
기존 b48ebdf1은 **superseded / ready=false**로 바꾼다. 사용자가 요청한 ready=true는
앞서 요구한 실패 4/4 회복 조건을 통과하지 못해 발행하지 않는다.
진단 76900–76905, 관문 79500–79539 계획은 보존하되 제출은 차단한다.
[시드 확인](solo4-seed-check.json): main+열린 PR 17개 registry에서 겹침은 PR #502의
기존 예약뿐이다. 조정자 보고에는 관문 미제출, 로컬 회수 목록에도 해당 실행이 없다.
원격 실행 목록은 이번 세션에서 조회하지 않았으므로 실제 제출 전 다시 확인한다.

현재 영상만으로 필요한 물체 존재 근거를 만들 수 없다. 새 관측 동작/표본 설계가
필요하며, 사용자에게 범위 확장 여부를 물었다. 답변 전 그 동작을 구현하거나
실패가 알려진 같은 파지 경로를 GCP에 다시 제출하지 않는다.
