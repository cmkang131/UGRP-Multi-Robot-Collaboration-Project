# 2차 실험 코드 묶음 (여러 번 나르기, 3대)

2차 실험(로봇 3대, 여러 번 나르기, 구조 비교)에 쓰는 실행층과 계획기의 코드다. 저장소의 `harness/`, `scripts/`, `team/` 는 1차 판(실행층 v37)이며, 이 폴더의 같은 이름 파일은 그 뒤에 고친 2차 판이다. 둘을 섞지 않으려고 따로 두었다([solo_pipeline](../solo_pipeline/README.md)와 같은 방식).

## 출처

| 부분 | 출처 | 기준 |
|---|---|---|
| 실행층 (`harness/`, `scripts/`, `tests/`) | 작업 저장소 브랜치 `phase2/exec-opt` | 커밋 `fce952399d056940216c57ea8449e718da152d22` (브랜치 `phase2/act-done-exit`와 같은 커밋) |
| 계획기 (`team/`) | 작업 폴더의 계획기 사본(git 저장소가 아니라 커밋이 없다) | `.py` 16개의 `sha256sum` 목록을 다시 해시한 값 앞 16자 `605d7cd52096bffd` |
| 도구 (`tools/`) | 같은 작업 폴더의 도구 | 아래 「들어 있지 않은 것」 참고 |

- 이 폴더를 얹는 기준 저장소 커밋은 `origin/main` `240faec8244c5cee1c91fa69f3e0ff9a5471be94` 이다.
- 실행층은 1차 때 저장소에 올린 개발 브랜치 커밋 `676768a` 에서 `fce9523` 까지 48커밋의 변경이다. 작업 저장소의 실행층 파일 3,109개 중 3,032개는 이미 저장소 `main` 과 바이트가 같고, 이 폴더에는 달라진 것 중 실행 코드와 시험만 넣었다.
- 실행층 파일 8개의 주석·도움말에 있던 작업 폴더 이름은 `a work record` 로 바꿨다. 바뀐 줄은 주석, 문서 문자열, 도움말뿐이다(원본과 줄 단위로 비교해 확인).
- 계획기 사본은 같은 방식으로 주석의 작업 폴더 이름만 바꿨다. 계획기 시험 두 개(`test_free_talk.py`, `test_star_route.py`)는 실행 목록 CSV를 읽는 부분을 3구조 목록에 맞게 고쳤다. 목록이 없으면 건너뛴다.

## 놓는 법

`main` 위에 덮어쓰는 방식이다. `harness/`, `scripts/`, `tests/` 는 저장소 루트에, `team/` 은 저장소의 `team/` 위에 복사한다. 새 파일이 아닌 것은 같은 이름의 1차 파일을 바꾼다. 1차 결과를 다시 만들 일이 있으면 이 폴더를 얹지 않은 `main` 을 쓴다.

```bash
cp -r phase2_pipeline/harness phase2_pipeline/scripts phase2_pipeline/tests .
cp -r phase2_pipeline/team/. team/
```

## 2차 실행 스위치

모두 기본값은 꺼짐이다(기본 실행은 바뀌지 않는다). 실행 목록에 쓰는 실행층 옵션은 다음과 같다.

| 옵션 | 하는 일 |
|---|---|
| `--robot-tags --overhead` | 로봇 번호 표식과 천장 카메라 자세 측정 |
| `--regrasp-max 1` | 빈 집게 확인 뒤 다시 둘러보고 한 번 더 집는다 |
| `--look-around-option` | 집기 결정에서 "다시 둘러보기"를 고를 수 있다 |
| `--held-check-edge-fix` | 든 상자 확인이 렌즈 가장자리를 바닥의 상자로 읽지 않는다 |
| `--stop-failed-body` | 계획기가 로봇 고장으로 답하면 몸도 멈춘다 |
| `--multi-carry` | 하차 뒤 다음 상자를 가지러 돌아갈 수 있다(다중 운반) |
| `--zone-confirm-close` | 목적지 표식을 가까이서 다시 확인한 뒤에만 접근·하차 |
| `--zone-close-fix`, `--zone-close-far` | 근접 확인이 윗부분이 잘린 표식을 받아들이고, 처음 가까이 보는 거리·판독 거리를 늘린다 |
| `--door-lane-fix` | 문에서 마주친 두 로봇의 교착을 번호가 큰 쪽이 물러나 푼다 |
| `--return-pose-fallback` | 천장 카메라가 1.5초 읽지 못하면 계산한 자세로 돌아간다 |
| `--act-done-exit` | 집기 모델의 끝 신호가 10초 이어지는데 끝 규칙이 안 걸리면 집기 실패로 본다 |
| `--render-cull --wheel-deadlines --overhead-empty-tiles --render-segments 12 --overhead-every 10` | 결과가 같은 속도 스위치 |
| `--act-hold-short --dest-listen-zero` | 대기 시간을 줄이는 속도 스위치(차이 없음을 확인) |
| `--oracle-return-face`, `--oracle-wide-pick` | 정답 계획(`--fixed oracle`) 실행에서만 동작 |
| `--cap-s 1200 --wall-cap-s 57600` | 시뮬 상한과 실제 시계 상한 |

계획기(`team/brain_server.py`)의 2차 스위치: `--talk free`, `--no-message-budget`, `--say-*`, `--read-*`, `--msg-delay-s`, `--multi-carry`, `--leader-election --leader-seed`, `--leader-authority`, `--leader-bind --hold-s`, `--leader-route star`. 동등(P)은 `--team T1`, 팀장 구조는 `--team T2` 다. 실행당 호출 상한은 `--max-calls`(로봇당 150)의 3배인 450이다.

## 확인한 것

저장소 `main`(`240faec`) 위에 덮어쓴 사본에서 다음을 돌렸다. 시뮬레이션, 모델 호출, VM 실행은 하지 않았다.

- `.py` 55개 컴파일: 실패 0.
- 실행층 시험 14개 파일(`tests/test_act_done_exit.py` 등): 작업 저장소 원본과 같은 결과. 시험 수는 파일마다 같고 모두 통과(OpenCV·MuJoCo가 필요한 일부는 건너뜀, 이 서버에 없음).
- 계획기 시험 287개: 통과 283, 건너뜀 4(실행 목록 CSV와 동결 참조가 이 저장소에 없음).
- 가짜 모델 브리지 스모크(`tools/smoke_bridge.py`, 3대 장면 한 개): 28건 중 이상 0.
- 계획기 동일성 검사(스위치를 끈 계획기의 프롬프트·결정·기록이 동결 참조와 바이트 동일, `tools/identity_check.py`): 작업 폴더에서 `IDENTICAL: True`. 이 저장소에는 동결 참조가 없어 여기서는 돌리지 않았다.

## 들어 있지 않은 것, 한계

- 실행 목록(CSV)과 목록 생성기(`make_phase2.py`, `exec_config.json`): 2차 설계가 바뀌는 중이라 넣지 않았다. 실행층 커밋과 옵션은 위 표와 출처가 기준이다.
- `harness/approach_servo_v1.py`, `harness/gaze_correction.py`: `--approach-code-v1`, `--gaze-code-v1` 에서만 쓰며 2차 실험은 쓰지 않는다. 1차 올림과 같은 이유로 넣지 않았다.
- 개인 호스트 식별자가 들어 있는 설정과 큐 스크립트(`configs/`, `scripts/queue_*`, `scripts/grasp_act_training_guard.py` 등), 속도 측정 기록 문서, 컴파일된 `.pyc` 는 넣지 않았다.
- 실행기는 시작할 때 `scripts/grasp_act_training_guard.py` 의 호스트 확인을 부른다(1차 올림과 같은 한계). 다른 호스트에서 돌리려면 소유자가 방식을 정해야 한다.
- `tools/` 의 `smoke_bridge.py`, `identity_check.py` 는 장면 파일·동결 참조를 인자로 받고, `make_manifest_leader.py` 는 환경 변수 `P2_*` 로 장면·배치 스케줄러 경로를 받는다. 그 입력은 이 저장소에 없다.
- ACT 모델, 장면 묶음, actor 환경, 모델 공급자 키는 이 저장소에 없다. 이 코드가 실제 시뮬레이션에서 끝까지 도는지는 이 올림에서 확인하지 않았다.
