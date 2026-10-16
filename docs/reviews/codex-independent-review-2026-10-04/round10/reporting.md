# 후속 검토 — 이미 종료한 실행 시도가 보고서에서 대기 상태가 됨

**P3 · 선택 Gemini visual-team 보고 경로.** child process가 첫 run artifact를 만들기 전에 실패하면 runner는 그 시도를 정확히 기록하지만, 자동 생성되는 보고서는 같은 시도를 `pending`, `attempted=False`로 표시한다. current pair/P06 또는 확증 분석의 분모 문제로 확대하지 않는다. 종료 실패가 runner 원장에서 사라진다는 주장도 아니다.

기준 main: `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`. 구현 변경·실제 실험·기존 run 원자료 열람 없이 새 합성 파일과 원본 함수로 검증했다.

## 실제 연결

[`evaluate_gemini_cohort.py:96–105`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/evaluate_gemini_cohort.py#L96-L105)는 cohort 아래의 `<run>.log`를 열어 child를 실행하고, `run_cohort` 다음에 `render_visual_team_report`를 자동 호출한다. child 시작/import 오류처럼 run 디렉터리의 `result.json`·control log·video를 만들기 전에 종료할 수 있는 실패가 적용 조건이다.

[`run_cohort:34–51`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/evaluate_gemini_cohort.py#L34-L51)는 nonzero exit를 `PROCESS_EXIT_1`로 기록하고, `attempted`와 `started_runs`에 넣은 뒤 나머지를 `not_started`로 남긴다. 이 원장은 올바르게 보존된다.

그러나 [`render:338–348`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/render_visual_team_report.py#L338-L348)는 `started_runs`를 미시작 판정에서 제외할 때만 사용한다. 이미 시작한 run이라도 네 가지 child artifact marker가 없으면 마지막 분기의 `pending`이 된다. [`summarize_run:196–199`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/render_visual_team_report.py#L196-L199)는 `complete or lifecycle == 'running'`만 attempted로 세므로 false가 되고, [`mode aggregate:363–369`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/render_visual_team_report.py#L363-L369)에 0회 시도로 전달된다.

## 합성 증인과 대조

실제 `run_cohort -> render`를 연결했다. `execute`만 새 fixture로 바꾸며 모델/물리/child process를 실행하지 않는다. real CLI와 같은 위치의 작은 cohort-level log를 남긴다.

| 입력 상황 | runner attempted | report attempted | 첫 run lifecycle | 나머지 미시작 |
|---|---:|---:|---|---:|
| exit 1, child artifact 없음 | 1 | **0** | **pending** | 2 |
| exit 0이나 result 없음 | 1 | **0** | **pending** | 2 |
| exit 1, 빈 control log 있음 | 1 | 1 | running | 2 |
| 정상 기록된 물리 task 실패 3개 | 3 | 3 | complete | 0 |

마지막 대조는 성공 수 0을 유지한다. artifact 유무가 알려진 시도 여부를 바꾼다는 것이 핵심이다. marker가 있는 종료 실패도 `running`으로 표시되지만 같은 lifecycle 투영 문제로 묶으며 발견 수를 늘리지 않는다.

`summary.json`의 mode별 `attempted_runs`와 개별 상태가 영향을 받는다. 성공 표는 명시적으로 `successful_runs/completed_runs`를 쓰므로, 이 반례를 그 표의 성공률 부풀림으로 주장하지 않는다. 실제 과거 실행에서 이러한 실패가 몇 번 있었는지 조사하지 않았다.

## 최소 수정 수용 기준

시도 여부는 authoritative cohort receipt의 `attempted`/`started_runs`에서 먼저 가져오고, 파일 marker는 receipt가 없는 legacy run의 보조 근거로 쓴다. 종료한 infrastructure failure는 pending/running과 구별하고 그 이유를 보존한다. 물리 verdict가 없으면 `success=None`을 유지하며 operational failure를 임의의 로봇 실패로 바꾸지 않는다. 아직 실행하지 않은 나머지 두 run은 계속 미시작이어야 한다.

기존 [`test_visual_team_report.py:65–87`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/tests/test_visual_team_report.py#L65-L87)는 started run에 빈 control log를 만들어 준다. 그래서 receipt는 존재하지만 child marker는 전혀 없는 경우를 검증하지 않는다.

## 재현

```sh
python evaluation-attempt-report-repro.py --repo /path/to/UGRP
```

`evaluation-attempt-report-repro.py`는 두 원본 파일의 pinned SHA256을 검사한 뒤 실제 원본 module을 import한다. 결과는 stdout JSON이며 `evaluation-attempt-report-result.json`에 보존했다. 새로운 임시 디렉터리만 읽고 생성하며 네트워크를 차단한다. 외부 subprocess, LLM, 시뮬레이션, 영상, 실제 raw 자료가 없다.

별도 검토자가 원본 두 파일의 exact Git object/hash, 실제 자동 renderer caller를 대조하고 재현을 독립 실행하여 보존 JSON과 완전 일치를 확인했다. Colab 회수 완료 오판이나 P06 horizon 불일치와는 별도 경로다.
