# 놓기 교사: 근거 없음 메시지의 종류 오류 수정

실패 소스는 `ff8f11efc4309320225f6c63a3522bf017074ee8`이다. GCP 진단
`release-command-diagnostic-00..02-ff8f11ef`는 3/3 `HOST_ERROR`, EXIT 1이며,
놓기 성공은 미측정이다. 집기 prefix는 3/3 held였고 관문 40회는 시작하지 않았다.
원본별 위치·크기·sha256과 마지막 원장은 [요약 JSON](release-none-error-offline-summary.json)에 보존했다.

## 생성 원인

위 실패 SHA의 `scripts/run_grasp_act_release.py:281`은 `command_relative_v1`에서
지도 위치를 알 수 없으므로 `handoff_pose_estimate=None`을 준다.
`sim/grasp_act_release_teacher.py:171-174`는 이에 따라 지도 prior를 만들지 않는다.
자기 바닥 scan도 근거를 주지 않으면 같은 파일 `:262`가 **`prior/None`을 생성**한다.
이 분기는 `2e13f24fb4cba13f6adcfd938bafa313bc7e309f`에서 들어왔다.
파랑 끝 기억 수정 `ff8f11ef`는 이 분기를 바꾸지 않았다.

세 실행 모두 r1·r2 마지막 원장이 `t=10.8`, `await_look`,
`report={phase:look, kind:prior, margin_m:null}`이다. 생성된 보고는 실행기의
`:382-385`를 거쳐 `PairReleaseCode.interval()`의 `:110`에 도착한다.
`prior`는 수치 경계이므로 뺄셈에서 TypeError가 난다. 기존 시험 `:224`도
잘못된 `prior/None`을 기대했고, 실제 전달·판단 경로를 실행하지 않았다.
이 분석은 traceback·명령 원장에 근거한 코드 오류 분석이며 물리 실패 원인이나
영상 기반 파지 평가를 주장하지 않는다.

## 수정과 검증

- 생성 측은 지도 위치 미확인·scan 근거 없음에서 `none/None`을 보낸다
  (`sim/grasp_act_release_teacher.py:267`). 실제 prior의 수치 경계는 유지한다.
- 놓은 뒤 재관측도 `none`을 근거 부족으로 처리한다
  (`scripts/run_grasp_act_release.py:457`). 완료 수락은 계속 시각 근거를 요구한다.
- 수정 후 가짜 실행에서 추가로 확인한 JSON 저장 오류도 고쳤다. 제약이 없는
  구간의 계산에는 ±∞를 쓰되, 판단 기록의 무한 경계는 null로 저장한다
  (`sim/grasp_act_release_teacher.py:143`). 엄격 JSON writer를 그대로 검증했다.

`tests/test_grasp_act_release_run.py`는 실제 진단 계획 3개의 프로필을 그대로
`run()`에 전달한다. scene·world·시계·port·prefix·가시성·평가만 가짜로 바꾸고,
교사·메시지 생성/전달/판단·arm scheduler·lookaround v2는 실제 코드다.
가짜 world는 숫자 시계만 움직이며 JPEG는 합성 빈 영상이다.
수정 전 같은 TypeError를 3/3 재현했고, 수정 뒤 각 3초 상한 실행에서 놓기
15틱 이상과 판단 이후의 `lower`를 확인했다. 22초 가짜 실행은 둘러보기와
네 번의 재관측 pan, `map_pose_unknown`, 근거 없는 완료 거부를 확인했다.
이 시험은 실제 집기·놓기 성공 검증이 아니다.

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_grasp_act_release_teacher.py tests/test_grasp_act_release_run.py \
  tests/test_lookaround_localization.py
```

관련 3개 파일 **44/44 통과**(2.06초). pyflakes 4.0.3은 변경 코드·시험 4개
파일에서 EXIT 0, 정의 안 된 이름 0개다. 미사용 import·변수도 정리했다.
Mac 물리·렌더 실행, 모델 호출, 원격 제출, 학습 데이터 생성은 모두 0이다.

새 소스 SHA는 push 후 대체 대기열에 고정한다. 진단 3개를 먼저 검토한 뒤
관문 40개를 여는 순서를 유지한다. 이전 3개 오류 원본은 보존하며 새 결과와
합산하지 않는다. 50개 기록 큐는 기록 어댑터와 같은 프로필 관문 증명이 없어
`ready=false` 초안으로 유지한다. PR #491의 head는 `claude/grasp-act-release`이고,
이번 수정은 요청된 `claude/grasp-act-probes` 연속 브랜치에 push한다.

## 참고 자료

[Python Optional 문서](https://docs.python.org/3/library/typing.html#typing.Optional)의
값 없음과 수치 구분을 메시지 종류에도 적용했다. 수치 대체나 비교 분기의 예외
회피를 추가하지 않고 근거를 생성하는 곳에서 종류를 바로잡았다.
[Pyflakes 공식 저장소](https://github.com/PyCQA/pyflakes)의 정적 검사와 실제 실행
회귀를 함께 사용했다. 이 자료는 코드 오류 수정 절차의 참고이며 로봇 제어
성능의 근거로 사용하지 않는다.
