# 3차 BoxNet 실험과 로봇 간 상자 인계

로봇이 여럿일 때 한 번의 모델 호출에 몇 대의 계획을 맡길 수 있는지 조사한다. 이 폴더에는 텍스트 실험 1~21차의 코드, 완료한 개발 파일럿, MuJoCo 인계 시험과 설계 초안이 있다. 첫 계획 호출 756건과 상자 운반 54에피소드를 따로 기록했다. 인계는 두 코호트에서 각각 3/12, 9/12회 성공했다.

## 질문과 설계

1. 로봇 수가 늘 때 계획을 나누어 쓰면 출력 한도 안에서 더 많은 상자를 배달하는가?
2. 텍스트 보드는 1×3, 2×3, 3×3이다. 각 칸에 로봇 한 대를 둔다.
3. 한 단계마다 각 로봇은 상자 하나를 인접 칸이나 목적지로 옮기거나 쉰다. 모든 로봇이 함께 한 단계를 마친다.
4. CMAS는 한 명이 전체 계획을 쓴다. GROUP은 세 대씩 맡고 OWN은 각 로봇이 자기 계획을 쓴다.
5. `matched` 조건에서는 같은 상태에서 각 작성자가 앞으로 몇 단계의 계획을 쓴다. 계획 길이와 출력 토큰 상한을 따로 바꾼다.
6. 운반 파일럿은 로봇당 상자 두 개, 계획 길이 5로 진행했다. 배달한 상자와 엄격한 에피소드 성공을 센다.
7. 첫 계획 시험은 한 작성자에게 한 번만 묻는다. 출력 한도에 잘린 응답, 쓸 수 있는 응답, 토큰 수를 기록한다.
8. 출력 한도에는 모델 내부 추론과 화면에 보이는 답이 함께 들어간다. 답을 읽지 못한 경우와 출력이 잘린 경우는 각각 집계한다.
9. MuJoCo에서는 주는 로봇이 문 근처에 놓은 상자를 받는 로봇이 집어 목적지에 내려놓아야 성공한다.
10. 인계 12회 중 10회 성공이 다음 물리 실험의 기준이다. 세 로봇이 같은 규칙으로 수행하는 전체 실험은 설계 단계다.

세부 조건과 바뀐 제안은 날짜별 문단에 남아 있다. [설계 초안](docs/DESIGN-20261125.md) · [선행 과제 조사](docs/TASK-STEPS-SURVEY-20261125.md)

## 실행과 시험

아래 명령은 저장소의 `phase3_boxnet/`에서 실행한다. 검증 환경은 Linux, Python 3.12이다. 텍스트 시험은 NumPy를 쓴다. 인계 시험에는 NumPy, Pillow, PyYAML, GNU tar, zstd가 필요하다. 스크립트 모델은 자격 증명이 필요 없다.

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

`BOXNET_BRAIN_DIR`로 계획기 클라이언트 폴더를 지정할 수 있다. 기본값은 이 폴더의 `planner_client/`다. 회귀 시험은 `fixtures/regression/`에서 필요한 스크립트 입력을 임시 폴더에 풀어 과거 판과 비교한다. 과거 모의 전송 시험은 원래 SHA-256과 일치하는 `fixtures/planner-v1/llm.py`를 사용한다. Chen의 원본 세 파일과 MIT 고지를 함께 실었다. [원저작물](text_experiment/UPSTREAM.md)

## 실제 모델의 운반 결과

각 칸은 **배달한 상자 / 처음 놓인 상자**다. 구조마다 보드 세 종류와 시드 두 개(0, 1)를 조합해 6에피소드를 실행했다. V18의 두 실행은 출력 한도가 다르다. V20에서는 응답에 실패한 작성자를 그 라운드에 쉬게 하고 다음 라운드에 다시 계획을 맡겼다. 계속 계획하라는 문구도 추가했다. V18과 V20의 차이에는 두 설정의 영향이 함께 들어 있다.

| 완료 실행 | 출력 토큰 상한 | CMAS | GROUP | OWN | 전체 | 엄격 성공 에피소드 |
|---|---|---|---|---|---|---|
| [v18-pilot-r2](results/v18-pilot-r2/) | 8,192 | 9/72 | 25/72 | 30/72 | 64/216 | 6/18 |
| [v18-pilot-r2-16k](results/v18-pilot-r2-16k/) | 16,384 | 27/72 | 55/72 | 36/72 | 118/216 | 9/18 |
| [v20-idle-pilot-r2-8192](results/v20-idle-pilot-r2-8192/) | 8,192 | 72/72 | 72/72 | 72/72 | 216/216 | 18/18 |

각 실행의 `episodes.csv`에서 `correct_deliveries`, `box_count`, `strict_success`를 합산했다. `run.json`은 실행 당시 설정과 소스 해시이고 `summary.txt`는 해당 판의 요약 도구 출력이다.

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

## MuJoCo 인계

기준은 **10/12**다. FIX3은 3/12, FIX4는 9/12로 두 차례 모두 기준에 미달했다. `donor_pick`은 첫 로봇의 집기, `release`는 인계 지점에서 놓기, `receiver_pick`은 받는 로봇의 집기다. `sign_seen`은 목적지 표식 인식, `set_down`은 마지막 내려놓기다.

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

## 출처와 확인 범위

기준 저장소는 `240faec8244c5cee1c91fa69f3e0ff9a5471be94`다. 원본 작업 폴더는 `<work>/` 아래의 상대 경로로 표시했다. `<project-root>`와 `<home>`은 프로젝트 루트와 사용자 홈, `<project-id>`와 `<project-number>`는 클라우드 프로젝트의 이름과 번호다. `<account-1>`과 `<service-account>`는 사용자 계정과 서비스 계정, `<bucket>`은 저장 버킷, `<host>`는 호스트 또는 주소다. `<record-id>`는 운영 기록 식별자다. 문서에 남은 원본·리뷰 경로는 당시 기록의 위치를 가리킨다.

운반 설정에 기록된 코드 판은 V18 `ba217a48219a`, V20 `bc8ca8b14f1e`다. 첫 계획 여섯 폴더의 `source_sha256` 사전에서 계산한 판은 `c7d036b7af7f`다. 각 회차의 원본 실행 메타데이터에서 확인한 인계 실행기 커밋은 FIX3 `7ab759bb7d7c29a1c5eb2612c4c690f513612e0c`, FIX4 `d013eeabeeff4f228d9afb9ac107c4b0d1f7448a`다.

원 실험의 실행 근거는 파일럿의 모델·사용량 기록과 두 인계 코호트의 시뮬레이터 출력이다. 메인 세션이 인계 실험의 실행을 맡았다. 당시 작업자가 작성한 실험 보고서에는 버전별 검증과 당시의 미확인 항목이 함께 있다. 이번 사본을 만든 Codex는 로컬 원본으로 점수와 요약을 재계산하고 시험을 실행했다. 세 운반 CSV는 원본과 바이트가 일치했다. 첫 계획 756행은 원본 호출의 선택한 열 및 요약 분모와 대조했다.

텍스트 시험은 292개를 모두 통과했다. 인계 시험은 45개 중 43개를 통과했다. 설치된 ArUco 판독과 MuJoCo 장면에서의 손목 카메라 렌더링 시험 2개는 이 환경에서 건너뛰었다. 실행 래퍼 18개와 디스패처 17개가 통과했다. 실행기 훅 3개와 표식 검사 함수는 원본 Git 커밋의 파일과 바이트가 일치한다. 공통 모듈은 이 저장소의 `harness/`, `sim/`, `scripts/`에서 읽는다. 인계 작업서와 이전 검증 결과는 구현과 함께 있다. [인계 보고서](handover/REPORT-HANDOVER-GATE.md) · [실행 래퍼 보고서](handover/REPORT-HANDOVER-CLOUD.md)

<details>
<summary>선별한 원본 폴더와 해시</summary>

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

## 제외한 실행과 이유

- `v20-idle-pilot-r2-16384`는 의도적으로 중단했다. 완료된 에피소드는 17/18이다.
- `v20-idle-pilot-r2-4096`는 서버 재시작으로 11/18에서 끊겼다.
- `v20-idle-pilot-r2-2048`는 자료를 고를 때 11/18로 진행 중이었다. 이후 18/18로 끝났으나 이번에 지정한 세 실행에 포함되지 않아 싣지 않았다.
- 재시작한 `v20-idle-pilot-r2-4096b`도 자료를 정리하는 동안 시작했다. 이 사본을 위한 새 결과로 집계하지 않았다.

## 확인 안 됨 / 한계

실제 모델은 `z-ai/glm-5.3-flash` 하나다. 운반은 시드 0~1, 첫 계획은 0~3에서만 측정했다. 본 실험과 실물 로봇 검증은 아직 진행하지 않았다. 인계 기준 10/12에도 도달하지 못했다. 빨강과 파랑의 차이는 원인이 밝혀지지 않았다. 같은 설정에서도 실행마다 결과가 달라질 수 있다. 이 자료로 구조별 일반 성능이나 개선의 단일 원인을 확정할 수 없다.
