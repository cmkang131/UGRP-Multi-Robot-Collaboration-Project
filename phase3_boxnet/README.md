# 3차 BoxNet 실험과 로봇 간 상자 인계

로봇이 여럿일 때 한 번의 모델 호출에 몇 대의 계획을 맡길 수 있는지 조사한다. 이 폴더에는 텍스트 실험 1~22C의 코드(BoxNet1과 BoxNet2), 모델 파일럿의 결과, MuJoCo 인계 시험(FIX3~FIX6), 세 방 장면(`rooms3/`)과 설계·조사 문서가 있다. 인계의 FIX3 코호트는 3/12, FIX4 코호트는 9/12회 성공했다. FIX6에서 두 표가 기준 10/12를 넘었지만, 그 규칙은 결과를 본 뒤에 바뀌었다(아래 인계 절).

## 질문과 설계

1. 로봇 수가 늘 때 계획을 나누어 쓰면 출력 한도 안에서 더 많은 상자를 배달하는가?
2. BoxNet2 보드는 1×3, 2×3, 3×3이다. 각 칸에 로봇 한 대와 상자 한 개를 둔다. 상자 수는 로봇 수와 같다(`boxes_per_robot` 1).
3. 출력 토큰 상한은 1,024, 2,048, 4,096, 8,192로 두 배씩 올린다. 상한에는 모델의 내부 추론과 화면에 보이는 답이 함께 들어간다.
4. 한 단계마다 각 로봇은 상자 하나를 인접 칸이나 목적지로 옮기거나 쉰다. 모든 로봇이 함께 한 단계를 마친다.
5. CMAS는 한 명이 전체 계획을 쓴다. GROUP은 세 대씩 맡고, OWN은 각 로봇이 자기 계획을 쓴다.
6. 운반 파일럿은 계획 길이 5, 개발 시드 0과 1, 보드 세 종류로 진행했다. 배달한 상자와 엄격한 에피소드 성공(`strict_success`)을 센다.
7. 첫 계획 시험은 한 작성자에게 한 번만 묻는다. 출력 한도에 잘린 응답, 쓸 수 있는 응답, 토큰 수를 기록한다.
8. 단일 점수는 설계 규칙이다. 점수 = 완료율 × 효율(0~100)이고, 효율 = 같은 보드에서 가장 작은 배달 상자당 토큰 ÷ 이 칸의 배달 상자당 토큰이다. 완료율의 정확한 정의와 "같은 보드"의 범위는 원 작업서에 적혀 있지 않다. 그래서 이 사본은 점수를 계산하지 않았다.
9. MuJoCo에서는 주는 로봇이 문 근처에 놓은 상자를 받는 로봇이 집어 목적지에 내려놓아야 성공한다. 인계 12회 중 10회 성공이 다음 물리 실험의 기준이다.

세부 조건과 바뀐 제안은 날짜별 문단에 남아 있다. [설계 초안](docs/DESIGN-20261125.md) · [선행 과제 조사](docs/TASK-STEPS-SURVEY-20261125.md) · [난이도 조사](docs/DIFFICULTY-SURVEY-20261125.md)

## 실행과 시험

아래 명령은 저장소의 `phase3_boxnet/`에서 실행한다. 검증 환경은 Linux와 시스템 `python3`(3.12)이다. 텍스트 시험은 NumPy를 쓴다. 인계 시험에는 NumPy, Pillow, PyYAML, GNU tar, zstd가 필요하다. 스크립트 모델은 자격 증명이 필요 없다.

```sh
python3 -B -m unittest discover -s text_experiment -p 'test_chen2d*.py' -q
(cd handover && PYTHONPATH=.:exec python3 -B -m unittest discover -s handover/tests -q)
(cd handover && PYTHONPATH=.:exec python3 -B -m unittest discover -s cloudrun/handover -p test_handover_cloud.py -q)
(cd handover && python3 -B -m unittest discover -s cloudrun -p test_cr_dispatch_p3.py -q)
```

스크립트 모델로 지도 한 장에서 세 구조를 실행한다. 출력은 `text_experiment/runs/fake-smoke/`에 생긴다. 이 조건에서 각 구조가 상자 6개를 모두 배달했다.

```sh
python3 -B text_experiment/run_chen2d.py --model fake --protocol matched \
  --frameworks CMAS,GROUP,OWN --group-size 3 --sizes 1x3 --envs 0 \
  --map-set scaled:2 --conditions static --dropoff event --horizon 5 \
  --failed-writer idle --plan-note continue --max-output-tokens 8192 --out runs/fake-smoke
python3 -B text_experiment/summarize.py runs/fake-smoke --by planning
```

`BOXNET_BRAIN_DIR`로 계획기 클라이언트 폴더를 지정할 수 있다. 기본값은 이 폴더의 `planner_client/`다. 회귀 시험은 `text_experiment/fixtures/regression/`에서 필요한 스크립트 입력을 임시 폴더에 풀어 과거 판과 비교한다. 과거 모의 전송 시험은 원래 SHA-256과 일치하는 `fixtures/planner-v1/llm.py`를 사용한다. Chen의 원본 다섯 파일(BoxNet1 세 개, BoxNet2 두 개)과 MIT 고지를 함께 실었다. [원저작물](text_experiment/UPSTREAM.md)

아래 결과는 이 사본에서 다시 실행한 값이다.

| 시험 | 결과 | 확인 내용 |
|---|---|---|
| 텍스트 실험 `text_experiment` | 305개 중 **304개 통과**, 1개 생략, 실패 0 (398.9초) | 생략 1: `test_chen2d_v22.MapMeasurements`. 기준 파일 `review/chen2d-22/continuation/`이 공개 사본에 없다. |
| 인계 판정·정책 `handover/tests` | 49개 중 **46개 통과**, 3개 생략 | 생략 2: 설치된 OpenCV와 MuJoCo 장면 필요(업로드 1과 같음). 생략 1: FIX5 보관 회차의 바이트 비교. 보관 회차 폴더가 공개 사본에 없다. |
| 실행 래퍼 `cloudrun/handover` | 18개 중 **18개 통과** | 래퍼 파일은 업로드 1 상태다(한계 절). |
| 디스패처 `cloudrun/test_cr_dispatch_p3.py` | 17개 중 **17개 통과** | |
| 세 방 장면 `rooms3/tests` | 33개 중 **18개 통과**, 3개 생략, 12개 실패·오류 | 원인은 세 방 절에 적었다. 공개 사본에 없는 입력이 필요하다. |
| 저장소 고정 자료 `scripts/check_ci_fixtures.py` | 고정 자료 3개 확인, 종료 0 | |
| 빠른 경로 시험 `tests.test_ci_fast_path` | 10개 통과 | |

## 실제 모델의 운반 결과 (BoxNet1, V18·V20)

각 칸은 **배달한 상자 / 처음 놓인 상자**다. 구조마다 보드 세 종류와 시드 두 개(0, 1)를 조합해 6에피소드를 실행했다. V18의 두 실행은 출력 한도가 다르다. V20에서는 응답에 실패한 작성자를 그 라운드에 쉬게 하고 다음 라운드에 다시 계획을 맡겼다. 계속 계획하라는 문구도 추가했다. V18과 V20의 차이에는 두 설정의 영향이 함께 들어 있다.

| 완료 실행 | 출력 토큰 상한 | CMAS | GROUP | OWN | 전체 | 엄격 성공 에피소드 |
|---|---|---|---|---|---|---|
| [v18-pilot-r2](results/v18-pilot-r2/) | 8,192 | 9/72 | 25/72 | 30/72 | 64/216 | 6/18 |
| [v18-pilot-r2-16k](results/v18-pilot-r2-16k/) | 16,384 | 27/72 | 55/72 | 36/72 | 118/216 | 9/18 |
| [v20-idle-pilot-r2-8192](results/v20-idle-pilot-r2-8192/) | 8,192 | 72/72 | 72/72 | 72/72 | 216/216 | 18/18 |

각 실행의 `episodes.csv`에서 `correct_deliveries`, `box_count`, `strict_success`를 합산했다. `run.json`은 실행 당시 설정과 소스 해시이고 `summary.txt`는 해당 판의 요약 도구 출력이다.

## BoxNet2 파일럿: 출력 한도별 결과

원자료는 `results/bn2-pilot-r1-{1024,2048,4096,8192}/`의 `run.json`과 `episodes.csv`다. 요약 표 `results/bn2-pilot-r1-summary.csv`는 이 두 파일에서 계산했다. 36행은 한도 4 × 보드 3 × 구조 3이고, 각 칸은 시드 0과 1의 에피소드 두 개다.

| 한도 | 보드 | 구조 | 배달/전체 | 완료 에피소드 | 잘린 시도/시도 | 총 토큰 | 배달 상자당 토큰 | 충돌 | 유휴 로봇 라운드 (출력 한도 / 수리 후 응답 / 실행 불가) |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1,024 | 1x3 | CMAS | 6/6 | 2/2 | 1/5 | 7,869 | 1,311.5 | 0 | 0 / 0 / 0 |
| 1,024 | 1x3 | GROUP | 6/6 | 2/2 | 0/2 | 2,913 | 485.5 | 0 | 0 / 0 / 0 |
| 1,024 | 1x3 | OWN | 6/6 | 2/2 | 4/25 | 31,785 | 5,297.5 | 1 | 0 / 0 / 0 |
| 1,024 | 2x3 | CMAS | 0/12 | 0/2 | 18/18 | 45,225 | – | 0 | 36 / 0 / 0 |
| 1,024 | 2x3 | GROUP | 3/12 | 0/2 | 32/36 | 89,520 | 29,840.0 | 0 | 30 / 0 / 0 |
| 1,024 | 2x3 | OWN | 12/12 | 2/2 | 48/103 | 299,848 | 24,987.3 | 0 | 12 / 0 / 0 |
| 1,024 | 3x3 | CMAS | 0/18 | 0/2 | 18/18 | 61,848 | – | 0 | 54 / 0 / 0 |
| 1,024 | 3x3 | GROUP | 2/18 | 0/2 | 89/95 | 361,971 | 180,985.5 | 0 | 84 / 0 / 0 |
| 1,024 | 3x3 | OWN | 18/18 | 2/2 | 41/146 | 549,430 | 30,523.9 | 0 | 8 / 0 / 0 |
| 2,048 | 1x3 | CMAS | 6/6 | 2/2 | 3/11 | 23,678 | 3,946.3 | 2 | 0 / 0 / 0 |
| 2,048 | 1x3 | GROUP | 6/6 | 2/2 | 7/9 | 24,220 | 4,036.7 | 0 | 6 / 0 / 0 |
| 2,048 | 1x3 | OWN | 6/6 | 2/2 | 2/10 | 15,237 | 2,539.5 | 0 | 0 / 0 / 0 |
| 2,048 | 2x3 | CMAS | 12/12 | 2/2 | 14/17 | 59,654 | 4,971.2 | 0 | 18 / 0 / 0 |
| 2,048 | 2x3 | GROUP | 12/12 | 2/2 | 19/37 | 132,183 | 11,015.2 | 3 | 9 / 3 / 0 |
| 2,048 | 2x3 | OWN | 12/12 | 2/2 | 26/78 | 245,716 | 20,476.3 | 0 | 3 / 0 / 0 |
| 2,048 | 3x3 | CMAS | 9/18 | 1/2 | 11/14 | 60,634 | 6,737.1 | 0 | 27 / 0 / 0 |
| 2,048 | 3x3 | GROUP | 18/18 | 2/2 | 51/102 | 480,960 | 26,720.0 | 3 | 33 / 0 / 0 |
| 2,048 | 3x3 | OWN | 18/18 | 2/2 | 49/132 | 551,635 | 30,646.4 | 1 | 8 / 0 / 0 |
| 4,096 | 1x3 | CMAS | 6/6 | 2/2 | 2/7 | 30,001 | 5,000.2 | 0 | 0 / 0 / 0 |
| 4,096 | 1x3 | GROUP | 6/6 | 2/2 | 1/4 | 13,840 | 2,306.7 | 0 | 0 / 0 / 0 |
| 4,096 | 1x3 | OWN | 6/6 | 2/2 | 3/15 | 28,991 | 4,831.8 | 0 | 0 / 0 / 0 |
| 4,096 | 2x3 | CMAS | 6/12 | 1/2 | 11/23 | 105,953 | 17,658.8 | 0 | 18 / 6 / 0 |
| 4,096 | 2x3 | GROUP | 12/12 | 2/2 | 15/42 | 215,597 | 17,966.4 | 0 | 3 / 0 / 0 |
| 4,096 | 2x3 | OWN | 12/12 | 2/2 | 16/77 | 270,213 | 22,517.8 | 3 | 3 / 0 / 0 |
| 4,096 | 3x3 | CMAS | 18/18 | 2/2 | 13/21 | 116,370 | 6,465.0 | 0 | 27 / 0 / 9 |
| 4,096 | 3x3 | GROUP | 18/18 | 2/2 | 13/56 | 308,518 | 17,139.9 | 0 | 6 / 3 / 6 |
| 4,096 | 3x3 | OWN | 18/18 | 2/2 | 29/124 | 572,649 | 31,813.8 | 3 | 4 / 0 / 0 |
| 8,192 | 1x3 | CMAS | 6/6 | 2/2 | 0/2 | 11,688 | 1,948.0 | 0 | 0 / 0 / 0 |
| 8,192 | 1x3 | GROUP | 6/6 | 2/2 | 1/7 | 18,537 | 3,089.5 | 0 | 0 / 0 / 3 |
| 8,192 | 1x3 | OWN | 6/6 | 2/2 | 2/18 | 48,319 | 8,053.2 | 0 | 0 / 0 / 0 |
| 8,192 | 2x3 | CMAS | 12/12 | 2/2 | 1/7 | 36,704 | 3,058.7 | 0 | 0 / 6 / 0 |
| 8,192 | 2x3 | GROUP | 12/12 | 2/2 | 3/15 | 76,714 | 6,392.8 | 0 | 0 / 0 / 0 |
| 8,192 | 2x3 | OWN | 12/12 | 2/2 | 11/53 | 245,985 | 20,498.8 | 2 | 1 / 0 / 0 |
| 8,192 | 3x3 | CMAS | 18/18 | 2/2 | 0/5 | 23,185 | 1,288.1 | 0 | 0 / 0 / 0 |
| 8,192 | 3x3 | GROUP | 18/18 | 2/2 | 10/50 | 316,531 | 17,585.1 | 3 | 3 / 3 / 0 |
| 8,192 | 3x3 | OWN | 18/18 | 2/2 | 44/139 | 939,699 | 52,205.5 | 0 | 3 / 0 / 0 |

한도별 합계(같은 자료에서 계산):

| 한도 | 배달/전체 | 완료 에피소드 | 잘린 시도/시도 | 총 토큰 | 충돌 | 유휴 로봇 라운드 (출력 한도 / 수리 후 응답 / 실행 불가) |
|---:|---:|---:|---:|---:|---:|---|
| 1,024 | 53/108 | 10/18 | 251/448 | 1,450,409 | 1 | 224 / 0 / 0 |
| 2,048 | 99/108 | 17/18 | 182/410 | 1,593,917 | 9 | 104 / 3 / 0 |
| 4,096 | 102/108 | 17/18 | 103/369 | 1,662,132 | 6 | 61 / 9 / 15 |
| 8,192 | 108/108 | 18/18 | 72/296 | 1,717,362 | 5 | 7 / 9 / 3 |

열의 뜻은 다음과 같다.
- 완료 에피소드는 `finished`이고 `strict_success`인 에피소드다. `summarize.py`의 엄격 성공 기준과 같다.
- 잘린 시도는 `truncated_attempts`다. 빈 응답, 부분 응답, 미확인 잘림의 합과 실행마다 같았다. 시도는 `api_calls`다.
- 충돌은 `episode.json`의 `iterations[].collisions[]` 안에서 `"event": "collision"`인 항목 수다. `episode.json`은 공개 사본에 싣지 않았다. 이 열은 공개 파일만으로는 다시 셀 수 없다.
- 유휴 로봇 라운드는 `robot_rounds_blocked_by_cause`의 세 원인을 합한 값이다.
- 배달 상자당 토큰은 칸의 총 토큰을 배달 상자 수로 나눈 값이다. 배달이 0이면 빈칸이다.

확인한 사항은 다음과 같다.
- 네 실행 모두 에피소드 18개를 기록했다. 에피소드의 `api_calls` 합계는 로그의 "이번 실행이 만든 호출 수"와 같았다(448, 410, 369, 296). 중간에 이어 쓴 흔적은 없다.
- 1,024 실행의 로그에는 셸 래퍼의 `exit=` 줄이 없다. 에피소드 18개와 448 호출은 모두 기록되어 있다.
- 실행 설정은 모델 `z-ai/glm-5.3-flash`, 온도 0, 지도 `scaled:1`, 계획 길이 5, 충돌 정책 `skip`이다. 실행 당시 코드 판은 `a18c33ea887c`다. 공개 사본의 `LLM.py`는 계획기 경로 기본값 한 줄만 다르다.
- 4096 한도 폴더는 `bn2-pilot3.sh` 실행의 결과다(완료 표시 `bn2-pilot3.done`). `bn2-pilot2.sh`는 완료 표시 `bn2-pilot2.done` 없이 멈췄다. 32,768 한도 폴더는 스냅숏에 없다.
- 확인 시점에 `run_chen2d` 프로세스는 없었다. 진행 중인 실행은 이 표에 없다.

이 자료는 모델 하나, 시드 두 개, 보드 세 종류의 파일럿이다. 구조 간 차이나 한도 효과의 원인은 여기서 확정하지 않는다.

## 실제 모델의 첫 계획

각 칸은 **출력 한도에서 잘린 호출 / 전체 호출**이다. 모두 출력 상한 8,192토큰, 개발 시드 0~3, 호출당 한 번 시도 조건이다. `none`과 `continue`는 계속 계획하라는 문구의 유무다. 표의 비율은 호출 단위다.

| 첫 계획 실행 | 상자/로봇 | 계획 길이 | 문구 | CMAS | GROUP | OWN | 전체 |
|---|---|---|---|---|---|---|---|
| [simple-first-round-r1-h1](results/simple-first-round-r1-h1/) | 1 | 1 | continue | 6/12 | 2/24 | 0/72 | 8/108 |
| [simple-first-round-r1-h5](results/simple-first-round-r1-h5/) | 1 | 5 | continue | 3/12 | 15/24 | 19/72 | 37/108 |
| [simple-first-round-r2-h1](results/simple-first-round-r2-h1/) | 2 | 1 | continue | 6/12 | 7/24 | 0/72 | 13/108 |
| [simple-first-round-r2-h2](results/simple-first-round-r2-h2/) | 2 | 2 | continue | 8/12 | 10/24 | 1/72 | 19/108 |
| [simple-first-round-r2-h3](results/simple-first-round-r2-h3/) | 2 | 3 | continue | 8/12 | 9/24 | 7/72 | 24/108 |
| [chen2d-19-first-round-r2](results/chen2d-19-first-round-r2/) | 2 | 5 | none | 9/12 | 8/24 | 19/72 | 36/108 |
| [chen2d-19-first-round-r2](results/chen2d-19-first-round-r2/) | 2 | 5 | continue | 9/12 | 9/24 | 20/72 | 38/108 |

각 실행에 `config.json`, `summary.json`, `results-lite.csv`가 있다. CSV 한 행은 작성자 한 명의 호출이다. 응답 본문을 제거하고 잘림의 종류, 사용 가능 여부, 보이는 글자 수와 입력·생성·추론 토큰 수를 남겼다.

## MuJoCo 인계 (FIX3~FIX6)

기준은 **10/12**다. FIX3은 3/12, FIX4는 9/12였다. FIX5는 빨강과 파랑의 차이를 가르려고 같은 12개 배치의 색을 바꾼 표(`trials-swapped.csv`)로 실행해 8/12였다. FIX6은 FIX4와 FIX5에서 기울어진 채 멈춘 빨간 상자 네 회를 다시 실행했다.

`donor_pick`은 첫 로봇의 집기, `release`는 인계 지점에서 놓기, `receiver_pick`은 받는 로봇의 집기다. `sign_seen`은 목적지 표식 인식, `set_down`은 마지막 내려놓기다.

| 회차 | 상자 | FIX3 | FIX4 |
|---|---|---|---|
| 1 | 빨강 | 성공 | 성공 |
| 2 | 파랑 | `donor_pick` | 성공 |
| 3 | 파랑 | `donor_pick` | 성공 |
| 4 | 빨강 | `release` | `release` |
| 5 | 파랑 | `donor_pick` | 성공 |
| 6 | 빨강 | `sign_seen` | `set_down` |
| 7 | 빨강 | 성공 | 성공 |
| 8 | 파랑 | `donor_pick` | 성공 |
| 9 | 빨강 | `receiver_pick` | `receiver_pick` |
| 10 | 파랑 | `donor_pick` | 성공 |
| 11 | 파랑 | `donor_pick` | 성공 |
| 12 | 빨강 | 성공 | 성공 |

회차별 입력은 `trial.json`, 종료 상태는 `run.json`, 사건 순서는 `events.jsonl`에 있다. 원본 자세·프레임까지 읽어 재채점한 결과를 코호트별로 실었다. 공개 발췌본만으로 원본 전체 재채점에는 필요한 자세 기록과 모든 판정 프레임이 부족하다. [FIX3 점수](results/handover-fix3-20261125c/scores.txt) · [FIX4 점수](results/handover-fix4-Zc6HAKV9/scores.txt)

FIX4 2회차는 받는 로봇이 집어서 목적지에 놓았다. [받는 쪽 집게](results/handover-fix4-Zc6HAKV9/trial-02/0018-receiver-grasp-wrist.jpg) · [목적지에 놓인 상자](results/handover-fix4-Zc6HAKV9/trial-02/0030-set_down-settled.jpg)

FIX4 9회차는 받는 로봇이 두 번 모두 상자를 놓쳤다. [첫 번째 집기](results/handover-fix4-Zc6HAKV9/trial-09/0022-receiver-grasp-wrist.jpg) · [두 번째 집기](results/handover-fix4-Zc6HAKV9/trial-09/0027-receiver-grasp.jpg)

### FIX5: 색을 바꾼 표

공개 자료는 `results/handover-fix5-swap-yimHXMgy/`다. 회차 12개의 `trial.json`, `run.json`, `events.jsonl`과 점수 줄 `scores.txt`를 실었다. 결과는 **8/12**다. 실패는 2회차와 5회차(`set_down`, 사유는 "방출 지점에서 상자가 잡혀 있지 않음"), 9회차(`receiver_pick`), 11회차(`donor_pick`)다. 게이트 기준 10/12에 미달했다.

### FIX6: 기울어진 채 내려놓는 규칙

FIX4와 FIX5의 기울어진 멈춤은 네 회였다. 원래 색 4회(방출, 기울기 16.12°)와 6회(내려놓기, 10.81°), 바뀐 색 2회(내려놓기, 10.84°)와 5회(내려놓기, 10.71°)다. 네 상자는 모두 빨강이었다. 측정 뒤 사용자가 "기울어도 들고 있으면 내려놓게 하고, 실제로 표지 앞에 바르게 놓였는지로 채점"하는 방식을 골랐다. 구현은 `--station-tilt ignore` 옵션이다. 기본값은 기존 동작(`strict`)이라 옛 회차의 재채점은 바뀌지 않는다.

**이 규칙은 결과를 본 뒤에 정했다.** 따라서 아래 두 표의 통과는 사후 규칙 변경의 결과이고 확증 실험이 아니다. 재실행 네 회는 모두 성공했다. 원래 색 4회와 6회가 2/2, 바뀐 색 2회와 5회가 2/2였다. 합치면 **원래 색 11/12, 바뀐 색 10/12**다. 24개 중 20개는 앞선 코호트에서 왔다. FIX4의 10개와 FIX5의 10개다. 나머지 4개만 FIX6 재실행이다.

| 회차 | 원래 색 표 (출처 회차) | 결과 | 바뀐 색 표 (출처 회차) | 결과 |
|---:|---|---|---|---|
| 1 | FIX4 | 성공 | FIX5 | 성공 |
| 2 | FIX4 | 성공 | FIX6 재실행 | 성공 |
| 3 | FIX4 | 성공 | FIX5 | 성공 |
| 4 | FIX6 재실행 | 성공 | FIX5 | 성공 |
| 5 | FIX4 | 성공 | FIX6 재실행 | 성공 |
| 6 | FIX6 재실행 | 성공 | FIX5 | 성공 |
| 7 | FIX4 | 성공 | FIX5 | 성공 |
| 8 | FIX4 | 성공 | FIX5 | 성공 |
| 9 | FIX4 | 실패 (receiver_pick) | FIX5 | 실패 (receiver_pick) |
| 10 | FIX4 | 성공 | FIX5 | 성공 |
| 11 | FIX4 | 성공 | FIX5 | 실패 (donor_pick) |
| 12 | FIX4 | 성공 | FIX5 | 성공 |

- 점수 줄은 코호트마다 `scores.txt`에 있다. 24행 합산은 `results/handover-fix6-composite-scores.txt`다. 회차 경로는 공개 디렉터리명으로 줄였다.
- CLI 종료 코드 1은 실패가 있고 게이트를 통과하지 못했다는 뜻이다. FIX4와 FIX5가 1을 냈다. FIX6 재실행만의 결과는 게이트가 보류(PENDING) 상태다. 합산은 게이트를 통과했다.
- 인계 채점 코드와 실행 정책(`handover/criteria.py`, `layout.py`, `run_trial.py`, `score.py`, `exec/harness/handover_policy.py`)은 FIX6 상태다. 실행 래퍼(`cloudrun/handover/`)의 FIX5·FIX6 변경은 이 사본에 없다(한계 절).
- 실행 정책 파일의 고정값은 실행기 커밋 `ba0eb353…`(FIX6 이미지)에 맞춰 갱신했다. FIX3·FIX4 판(`d013eea…`, 정책 SHA-256 `7db86a74…`)은 `verification/exec-source.json`의 `previous_commit_fix4`에 남겼다.

## 세 방 MuJoCo 장면 (`rooms3/`)

세 장면(`scenes/seed-0`, `seed-3`, `seed-6`)은 지도 JSON, 지도 그림, MuJoCo XML, 표식 그림 12개로 이루어진다. 코드는 13개, 시험은 4개다. 작업서 `TASK-ROOMS3.md`와 보고서 `REPORT-ROOMS3.md`도 있다.

공개 사본에서 뺀 자료는 다음과 같다.
- `sim/assets/masterpi_drive_friction_v2/fuji_roller.stl`과 같은 바이트의 메쉬. 이 저장소에 이미 있다(SHA-256 `2bea3228…`, 크기 292,284바이트). 장면 XML은 `assets/fuji_roller.stl`을 가리킨다. 공개 사본에서 이 메쉬를 쓰려면 이 경로를 넣어야 한다.
- `verification/`(84개 파일, 약 2.2 MB)의 점검 기록과 목록. 클라우드 실행 기록과 `TASK-ROOMS3-DRAFT.md`도 뺐다.
- 클라우드 실행용 장면 입력 코드. 실행 래퍼의 `rooms3` 부분은 이 사본에 없다.

시험 33개의 결과와 원인은 다음과 같다.
- 18개 통과, 3개 생략(네이티브 MuJoCo 필요).
- 12개 실패·오류. 회차 기록 `cloudrun/runs/...`(FIX4·FIX6 회차 폴더)가 공개 사본에 없다: 4개.
- 옛 스냅숏 `20261124-chen2d-snap-v20`의 매니페스트가 공개 사본에 없다: 3개.
- 실행 중 임시 폴더 `.tmp/`가 없다: 3개. 공개 사본에는 빈 폴더를 둘 수 없다.
- 시험이 `SurveyApproach(survey_fast=…)`를 부른다. 공개 사본의 `exec/scripts/handover_world.py`(FIX4 판)에는 그 인자가 없다: 1개.
- 참조 자산이 있는지 확인하는 시험 1개가 실패했다. 빠진 파일이 위 메쉬인지는 확인하지 않았다.

## 출처와 확인 범위

기준 저장소는 `240faec8244c5cee1c91fa69f3e0ff9a5471be94`다. 원본 작업 폴더는 `<work>/` 아래의 상대 경로로 표시했다. `<project-root>`와 `<home>`은 프로젝트 루트와 사용자 홈, `<project-id>`와 `<project-number>`는 클라우드 프로젝트의 이름과 번호다. `<account-1>`과 `<service-account>`는 사용자 계정과 서비스 계정, `<bucket>`은 저장 버킷, `<host>`는 호스트 또는 주소다. `<record-id>`는 운영 기록 식별자다. 문서에 남은 원본·리뷰 경로는 당시 기록의 위치를 가리킨다.

코드 판은 두 가지다. 공개 사본의 BoxNet1 판은 `79f547d10c06`이고, 원본 스냅숏의 BoxNet1 판은 `6172cbfbac44`다. 차이는 `LLM.py`의 계획기 경로 기본값 한 줄뿐이다. BoxNet2 실행 기록의 판은 `a18c33ea887c`다. 운반 설정에 기록된 BoxNet1 판은 V18 `ba217a48219a`, V20 `bc8ca8b14f1e`다. 첫 계획 여섯 폴더의 `source_sha256` 사전에서 계산한 판은 `c7d036b7af7f`다. 각 회차의 원본 실행 메타데이터에서 확인한 인계 실행기 커밋은 FIX3 `7ab759bb7d7c29a1c5eb2612c4c690f513612e0c`, FIX4 `d013eeabeeff4f228d9afb9ac107c4b0d1f7448a`, FIX6 `ba0eb353ef00e376bfa64b3b17d7b26d77425973`이다.

원 실험의 실행 근거는 파일럿의 모델·사용량 기록과 인계 코호트의 시뮬레이터 출력이다. 이번 사본을 만든 작업은 로컬 원본으로 점수와 요약을 다시 계산하고 시험을 실행했다. 새 유료 호출이나 물리 실행은 하지 않았다.

[파일별 입력 목록](SOURCE-INPUTS.tsv)은 업로드 1 기준이다. 업로드 2의 선별 원본 해시는 아래 표에 따로 적었다. 각 행의 SHA-256은 원본 파일별로 `SHA256  상대경로\n`을 만들어 상대경로순으로 정렬한 뒤 이어 붙인 UTF-8 바이트의 해시다. 공개용으로 바꾸기 전 원본에서 계산했다.

| 원본 폴더 | 선별 범위 | 입력 파일 | 선별 원본 SHA-256 | 원본 Git 커밋 |
|---|---|---:|---|---|
| `20261124-chen2d-snap-v22` | 텍스트 코드·시험·작업서·보고서, `envs`·`envs-boxnet2`·`protocol_boxnet1` (`runs` 제외) | 1455 | `0073ebaf…` | — |
| `20261124-chen2d-snap-v22/runs/bn2-pilot-r1-{1024,2048,4096,8192}` | `run.json`, `episodes.csv` | 8 | `1282c577…` | — |
| `20261124-chen2d/review/chen2d-22/analysis-c` | 분석 파일 세 개(읽기 전용 복사) | 3 | `d1ee227e…` | — |
| `20261123-phase3 (FIX5·FIX6 변경)` | 인계 채점 코드·시험, 실행 정책, `REPORT-HANDOVER-GATE.md`, `TASK-HANDOVER-FIX6.md`, `score_fix6.py` | 11 | `1e621ee0…` | 정책 파일 `ba0eb353…` |
| `20261123-phase3/cloudrun/runs/handover-fix5-swap-yimHXMgy/trials` | 회차 12개의 `trial.json`, `run.json`, `events.jsonl` | 36 | `e2fd4301…` | `d013eea…` |
| `20261123-phase3/cloudrun/runs/handover-fix6-original-a117mixN/trials` | 회차 4·6의 `trial.json`, `run.json`, `events.jsonl` | 6 | `62058615…` | `ba0eb353…` |
| `20261123-phase3/cloudrun/runs/handover-fix6-swapped-s90Gr44E/trials` | 회차 2·5의 `trial.json`, `run.json`, `events.jsonl` | 6 | `11e8e323…` | `ba0eb353…` |
| `20261123-phase3/rooms3` | 코드·시험·장면 지도·MuJoCo XML·표식 그림 (메쉬 제외) | 62 | `4d866713…` | — |
| `20261123-phase3 (TASK-ROOMS3.md, REPORT-ROOMS3.md)` | 세 방 작업서·보고서 | 2 | `fda546cd…` | — |
| `20261123-plan3` | `DIFFICULTY-SURVEY-20261125.md` | 1 | `b3d8f33e…` | — |
| `20261113-l0-planning-env/refs/hmas` | BoxNet2 원본 두 개(`env2_create.py`, `prompt_env2.py`) | 2 | `39001b98…` | `024221d…` |

<details>
<summary>업로드 1의 선별 원본 폴더와 해시</summary>

각 행의 SHA-256은 원본 파일별로 `SHA256  상대경로\n`을 만들어 상대경로순으로 정렬한 뒤 이어 붙인 UTF-8 바이트의 해시다. 코드와 결과를 공개용으로 바꾸기 전에 계산했다. 원본 Git 커밋을 확인한 행에는 그 값도 적었다. FIX3·FIX4 행은 공개한 회차 파일과 사진의 원본을 대상으로 한다.

| 원본 폴더 | 선별 범위 | 입력 파일 | 선별 원본 SHA-256 | 원본 Git 커밋 |
|---|---|---|---|---|
| `20261124-chen2d` | 코드·시험·작업서·라이선스 | 81 | `d8ca38f55bdb6adeea5f1405b4302df0d6c7a7fb0ea24b5df8b3ec3fd2098b32` | — |
| `20261124-chen2d/envs` | 기존 지도 | 863 | `910c99b73e20256001346381c34b300a34e423443489dd3a22cb807c35f76bb5` | — |
| `20261124-chen2d/envs-scaled/r0.5` | 밀도별 지도 | 99 | `2b7c93162826d2ab693f2a11a198167913ac2691841a3f5cd21f3c15f1b3f9c7` | — |
| `20261124-chen2d/envs-scaled/r1` | 밀도별 지도 | 201 | `56eeefd33ef5d7cb337b8f5fb4f1c0ba733725703ff8d561bbe31e9a7bf74690` | — |
| `20261124-chen2d/envs-scaled/r2` | 밀도별 지도 | 99 | `b9b920296308055de0f20be79d59e44c56f2e84afc314412c2ef2733e6520fff` | — |
| `20261124-chen2d-snap-v18/envs-scaled/r2` | 파일럿의 새 보드 3종 | 102 | `7ecd907fc54b3049361bc5148ae499f04fa9d22841b660d4f5b11618f07f2c70` | — |
| `20261113-l0-planning-env/refs/hmas` | Chen 원본 3개 | 3 | `7067d69cfb7dc29fb13ec26041a80b04553f6261a3378f403e318349633caa9f` | `024221d36d520db67a8ee4e19f755789056255fa` |
| `20261123-phase3/link/brain` | 계획기 클라이언트 | 1 | `839ab3df9d1e9bca576a5e5ba6e41f6e402bb28589341b8872fd328d160a7255` | — |
| `20261124-chen2d/review` | 회귀 시험에 고정된 옛 llm.py 코드 구간 | 1 | `2af341459177490f36985b37b1297e37785ead8b986817676b4916f526e58a75` | — |
| `20261124-chen2d/review` | 스크립트 시험에 쓰인 입력·비교 코드만 선별 | 2957 | `f8488064cead2d0667afba0e836e6a511c3644d3763a45c9f89411b77be4757a` | — |
| `20261123-phase3/handover` | 인계 구현·시험·표·검증 기록 | 28 | `9df47f25c9f02eaaac578d01cbf5cd41c77b63d0916f22d2b556a157ad956985` | — |
| `20261123-phase3/cloudrun/handover` | 실행 래퍼·시험·검증 기록 | 23 | `7b789745fa0a687106a4185497730edfb4282e67532671eeb18075fb58e3eb35` | — |
| `20261123-phase3` | 인계 작업서·보고서 | 9 | `83ae6c1f6713f29f1e0d6025f771ea23b3950b2d86ddea681fec7ff53e98884f` | — |
| `20261123-phase3/exec` | 제어·장면·월드 및 표식 검증 함수 | 4 | `71254f52cce1262cdd9ac44d7d0cb310a5d24dab0b38fdb6026acf3d89afb4ed` | `d013eeabeeff4f228d9afb9ac107c4b0d1f7448a` |
| `20261123-phase3/exec` | 시험에 필요한 카메라·표식 모듈 | 2 | `8a3a3a03e3acd71864d61165c5f0880181ebed6de348e7d379ab4067379b2b13` | `d013eeabeeff4f228d9afb9ac107c4b0d1f7448a` |
| `20261123-phase3/cloudrun` | 디스패처와 시험 | 2 | `dfc2d001e7ac032a990cd4b4bb95d6dc11d645e01c4c7a182657c84978a8817d` | — |
| `20261123-phase3/tools` | 디스패처 시험의 목록 생성기·설정 | 3 | `3db41de279e7a367983a493ff7c1bd993e269b9e57111f66e09d94515f771ba6` | — |
| `20261123-phase3/manifests` | 디스패처 시험의 실행 목록 | 6 | `aa9ae2462e86623f46d0c47ef4139ce666b1aa2045c54a5f66c453d926060135` | — |
| `20261123-phase3/scenes` | 목록에서 해시를 검사하는 장면 | 12 | `7dada59a08e1fae3834fe7d60ccfca3b2c3c04c8bc602375a868f0071fdbfda9` | — |
| `20261123-phase3/tools/scenes-v11-static` | 정적 장면 시험 | 5 | `072a31332f6c40fc84e22896d06803086800b9786982ef7c1d1fc6f53307a1b8` | — |
| `20261115-batch` | 기반 디스패처 | 1 | `778e4531afa3304ddee3ae5313f3950d7549b826885d4bad4f25d2cc16ce3362` | — |
| `20261115-batch/cloudrun` | 기반 스케줄러 | 1 | `9c6c8c3d9874c59f0fd43367bbe9cd4c1b01dc47addbcb7a653a43092d8cabfb` | — |
| `20261118-cloudrun-p2` | 2차 실행 래퍼 | 1 | `8607e6653236de16d9975a299183e15c8918b91a84199722600ca2f8954389bb` | — |
| `20261118-cloudrun-p2/image/cr` | 오프라인 시험의 tar 함수 원본 | 1 | `8a932daca6da88a28e03e02a617ceca681edd00a20040d4488af1ce3ba0a97f1` | — |
| `20261118-cloudrun-p2/builds` | 부모 이미지 기록에서 커밋·다이제스트만 발췌 | 1 | `3b6de3f043bd86dcca21db5859e61d5288b73a85567bb55b02015d342de32da3` | — |
| `20261123-plan3/debate` | 설계 초안 | 1 | `8eaca821dd73212c4f5860348c085c03fe5cf856fc795823dcc6721d23d28d12` | — |
| `20261123-plan3` | 선행 과제 조사 | 1 | `c75a884c6efd349fc73848daf4367e7691c7926861ea9ffd7067b44020dc0bb5` | — |
| `20261124-chen2d-snap-v18/runs/v18-pilot-r2` | 실행 설정·에피소드 CSV | 2 | `3d1ad74c54ab5e832d8c1695967884e72b6f408b218ada8acbce0203aeafe3c4` | — |
| `20261124-chen2d-snap-v18/runs/v18-pilot-r2-16k` | 실행 설정·에피소드 CSV | 2 | `e5138b060e13ad30a1311288d46df33b841d5b53e1cc36b5d4351102fcb77819` | — |
| `20261124-chen2d-snap-v20/runs/v20-idle-pilot-r2-8192` | 실행 설정·에피소드 CSV | 2 | `3ef1e4fc84f7e4d396b8b067783aa87916109031634bcdc8bc52e7f54cf4f2ac` | — |
| `20261124-chen2d-snap-v19/runs/simple-first-round-r1-h1` | 설정·요약·원본 호출 행 | 3 | `ddd8b86dc4381e9df2aad87b6f880afa4e7e6292d7ad4b34502df3b1ed53f1c0` | — |
| `20261124-chen2d-snap-v19/runs/simple-first-round-r1-h5` | 설정·요약·원본 호출 행 | 3 | `44b1f996319ef4d0bdd0e5f2f889d2aa6b07b98af696ac1f9b70fe95c33b69c2` | — |
| `20261124-chen2d-snap-v19/runs/simple-first-round-r2-h1` | 설정·요약·원본 호출 행 | 3 | `341b1932fb770cf812be5682e942f09c5774cf4f69a8ce29ed9d08c21f1dae64` | — |
| `20261124-chen2d-snap-v19/runs/simple-first-round-r2-h2` | 설정·요약·원본 호출 행 | 3 | `2852e36c33a85d9df6070501fc0f7e950e04c2dd1e287670703bb9b1bb363579` | — |
| `20261124-chen2d-snap-v19/runs/simple-first-round-r2-h3` | 설정·요약·원본 호출 행 | 3 | `d7926df92438bce50ae3dd97d61be508b75be08358f95174759b585ee8868b45` | — |
| `20261124-chen2d-snap-v19/runs/chen2d-19-first-round-r2` | 설정·요약·원본 호출 행 | 3 | `54973705d87de5ee1b506019c852f61dc25cad83a5f55f63d2432ad5943a2a19` | — |
| `20261123-phase3/cloudrun/runs/handover-fix3-20261125c/trials` | 회차 기록과 선별 사진 | 36 | `2a420942956c7cf9993722546383a10a31a979ae624ee9ba7f02a83e5f4b1938` | — |
| `20261123-phase3/cloudrun/runs/handover-fix4-Zc6HAKV9/trials` | 회차 기록과 선별 사진 | 40 | `52ebb2280d398e331f6926609c8c6eb51c13704af233b35b9a58d2f1cf74d168` | — |

</details>

<details>
<summary>지도 패밀리와 크기</summary>

기존 보드의 지도·이벤트·목록은 회귀 시험이 해시로 확인한다. 파일럿에서 사용한 `r2`의 1×3, 2×3, 3×3은 V18 스냅숏에서 가져왔다. 세 폴더가 V19·V20에서도 같은 바이트인지 확인했다. 시험용 지도에는 개발 측정에 사용한 범위 밖의 시드도 있다.

| 지도 폴더 | 파일 수 | 바이트 |
|---|---|---|
| `envs/2x2` | 140 | 95,053 |
| `envs/2x4` | 568 | 420,160 |
| `envs/4x4` | 112 | 83,108 |
| `envs/4x8` | 40 | 31,845 |
| `envs` 목록·빈 잠금 파일 | 3 | 80,606 |
| `envs-scaled/r0.5/2x2` | 24 | 9,364 |
| `envs-scaled/r0.5/2x4` | 24 | 11,980 |
| `envs-scaled/r0.5/4x4` | 24 | 15,880 |
| `envs-scaled/r0.5/4x8` | 24 | 22,946 |
| `envs-scaled/r0.5` 목록·빈 잠금 파일 | 3 | 8,662 |
| `envs-scaled/r1/1x3` | 34 | 16,087 |
| `envs-scaled/r1/2x2` | 24 | 11,092 |
| `envs-scaled/r1/2x3` | 34 | 19,900 |
| `envs-scaled/r1/2x4` | 24 | 14,150 |
| `envs-scaled/r1/3x3` | 34 | 22,552 |
| `envs-scaled/r1/4x4` | 24 | 19,502 |
| `envs-scaled/r1/4x8` | 24 | 30,065 |
| `envs-scaled/r1` 목록·빈 잠금 파일 | 3 | 8,662 |
| `envs-scaled/r2/1x3` | 34 | 19,005 |
| `envs-scaled/r2/2x2` | 24 | 13,234 |
| `envs-scaled/r2/2x3` | 34 | 23,391 |
| `envs-scaled/r2/2x4` | 24 | 17,733 |
| `envs-scaled/r2/3x3` | 34 | 27,846 |
| `envs-scaled/r2/4x4` | 24 | 26,529 |
| `envs-scaled/r2/4x8` | 24 | 44,278 |
| `envs-scaled/r2` 목록·빈 잠금 파일 | 3 | 8,662 |

</details>

## 업로드 2에서 바꾼 것

- `text_experiment`: `20261124-chen2d-snap-v22`의 코드로 바꾸었다. 병합한 파일은 `REPORT-CHEN2D.md`와 `test_chen2d_v16.py`다. 나머지 변경 파일과 새 파일은 원본 바이트 그대로다. 다만 `test_chen2d_v22.py`는 아래 세 곳을 고쳤다. 업로드 1의 계획기 경로와 회귀 입력은 유지했다.
- `test_chen2d_v22.py`: 원본 Chen 파일 경로를 `fixtures/upstream/`으로 바꾸었다. 기준 파일이 없는 `MapMeasurements` 시험에는 건너뛰기 조건을 달았다. 코드 판을 확인하는 `LegacyBytes` 시험의 기대값은 `79f547d10c06`으로 바꾸었다. 이 값은 공개 사본에서 `LLM.py`를 바꾼 뒤 계산한 값이다.
- `fixtures/upstream/`에 `env2_create.py`와 `prompt_env2.py`를 추가했다. 두 파일은 커밋 `024221d…`의 원본과 바이트가 같다. `UPSTREAM.md`도 고쳤다.
- `results/`: BoxNet2 파일럿 네 실행의 `run.json`과 `episodes.csv`, 요약 표 `bn2-pilot-r1-summary.csv`, 분석 파일 세 개(`chen2d-22-analysis-c/`)를 넣었다. 분석 파일은 읽기 전용으로 복사했다. 인계 FIX5·FIX6 회차 기록과 점수 줄, 24행 합산 표를 넣었다.
- `handover/`: FIX6 상태의 채점 코드와 시험, 실행 정책, `REPORT-HANDOVER-GATE.md`(FIX6 절 추가), `TASK-HANDOVER-FIX6.md`, `verification/score_fix6.py`를 넣었다.
- `handover/cloudrun/handover/cloudbuild.yaml`: 업로드 1에서 빌더 이미지 이름 `gcr.io/cloud-builders/docker`가 `gcr.io/<project-id>/docker`로 잘못 바뀌어 있었다. 원래 이름으로 되돌렸다. 이에 맞춰 `verification/bundle-staged.sha256`의 해당 줄을 바꾸었다(`9257b0e5…` → `bf4f8725…`, 원본 FIX5·FIX6 기록과 같은 값).
- `handover/cloudrun/handover/verification/exec-source.json`과 `stage.py`: 실행기 커밋을 FIX6 이미지의 `ba0eb353…`으로 바꾸고 정책 파일 SHA-256을 `5d027d60…`으로 바꾸었다. 이전 값은 `previous_commit_fix4`에 남겼다.
- `handover/cloudrun/handover/verification/bundle-staged.sha256`: 바뀐 인계 파일 다섯 개(정책, `criteria.py`, `layout.py`, `run_trial.py`, `score.py`)와 생성된 `layer.json`의 값을 다시 고정했다. 다섯 파일의 새 값은 FIX6 기록의 `fix6-staged.sha256`과 같다. `layer.json` 값은 새 실행기 커밋으로 만든 값이다.
- `rooms3/`: 코드, 시험, 세 장면의 지도·XML·표식 그림, 작업서와 보고서를 넣었다. 작업서와 보고서는 공개 경로 치환과 UUID 치환을 거쳤다.
- `docs/DIFFICULTY-SURVEY-20261125.md`를 넣었다. 작업 루트 조각 `claude-work/`를 `<work>/`로 바꾸었다.
- `envs-boxnet2/`의 빈 `.env.lock` 세 개는 `.gitignore`의 `.env.*` 규칙 때문에 `git add -f`로 올렸다. 업로드 1의 `.env.lock` 네 개도 같은 방식이다.

## 제외한 실행과 이유

- `v20-idle-pilot-r2-16384`는 의도적으로 중단했다. 완료된 에피소드는 17/18이다.
- `v20-idle-pilot-r2-4096`는 서버 재시작으로 11/18에서 끊겼다.
- `v20-idle-pilot-r2-2048`는 자료를 고를 때 11/18로 진행 중이었다. 이후 18/18로 끝났으나 이번에 지정한 실행 목록에 없어 싣지 않았다.
- 재시작한 `v20-idle-pilot-r2-4096b`도 자료를 정리하는 동안 시작했다. 이 사본을 위한 새 결과로 집계하지 않았다.
- BoxNet1 주 실행 `main-r2-8192`는 사용자가 9개 에피소드에서 중단했다. 결과가 아니다.
- BoxNet2 한도 32,768 실행은 스냅숏에 폴더가 없다. 결과가 아니다.
- 실행 래퍼(`cloudrun/handover/`)는 업로드 1 판을 유지했다. 예외는 `stage.py`의 실행기 커밋과 계보 상수, `exec-source.json`, `bundle-staged.sha256`의 다섯 줄과 `cloudbuild.yaml`이다. `ops.py`, `fetch.py`, `worker.py`, `check_image.py`, `Dockerfile`, `test_handover_cloud.py`의 FIX5·FIX6 판은 넣지 않았다. 이 파일들의 FIX 변경은 세 방 클라우드 작업의 변경과 같은 줄에 있어서 분리하지 못했다.
- 인계 회차의 빌드 컨텍스트(`*-context/`), 스모크와 임시 폴더, `chassis.csv`, `scene.xml`, `cards/`, `driver.log`, `observations.jsonl`, `cloud-meta.json`은 싣지 않았다. 이번에 추가한 회차 사진은 두 장뿐이다(FIX6 원래 색 4회 `0008-release-settled.jpg`, 바뀐 색 2회 `0022-set_down-settled.jpg`).
- 전체 `runs/`·`review/` 트리, 실제 모델 프롬프트·응답, 시도 원장, 작업자 대화·메모리·리뷰 전사, 원시 에이전트 로그는 발췌 대상에서 뺐다.

## 확인 안 됨 / 한계

- 실제 모델은 `z-ai/glm-5.3-flash` 하나다. 운반은 시드 0~1, 첫 계획은 0~3에서만 측정했다. 개발 지도는 보드마다 두 장이다.
- 본 실험은 실행하지 않았다. 읽기 쪽 시험도 아직 실행하지 않았다.
- 단일 점수(완료율 × 효율)는 계산하지 않았다. 완료율의 정의와 "같은 보드"의 범위가 원 작업서에 없다.
- 충돌 수는 `episode.json` 없이 다시 셀 수 없다.
- FIX6의 11/12와 10/12는 결과를 본 뒤 정한 규칙의 결과다. 24개 중 20개는 앞선 코호트다. 실물 로봇에서는 확인하지 않았다.
- 실행 래퍼의 FIX5·FIX6 변경은 이 사본에 없다. 따라서 공개 사본에서 FIX6 이미지를 다시 만들거나 FIX6 명령을 실행할 수 없다. 래퍼 시험 18개는 업로드 1 상태에서 통과했다.
- 세 방 장면 시험 12개가 실패하고 3개가 생략되었다. 원인은 위 세 방 절과 같다. 메쉬가 빠진 자산 검사 한 건은 원인을 확정하지 않았다.
- 실행 사이에 결과가 달라질 수 있다. 같은 설정에서도 결과가 흔들린다. 이 자료로 구조별 일반 성능이나 개선의 단일 원인을 확정할 수 없다.
- 실물 로봇 검증은 아직 남아 있다.
