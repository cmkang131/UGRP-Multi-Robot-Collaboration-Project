# 재현과 다음 인수

완료한3라운드는 [summary.json](summary.json)에 각각 보존했다. **이번 작업에서 추가
물리 실행은 하지 않는다.** 아래는 후속 작업용이며 실행 승인/부품 인수를 대신하지 않는다.

## Mac 비물리 확인

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_e2e_warp.py
python3 -m compileall -q harness/e2e_warp_runtime.py harness/e2e_warp_mission.py harness/e2e_warp_components.py scripts/run_e2e_warp.py scripts/e2e_warp_physics.py scripts/e2e_warp_relay.py
python3 -m scripts.run_e2e_warp --output outputs/e2ewarp-preview
```

기본 출력은 execution_started=false다. `--prepare --mode mission --components
experiments/2026-10-17-e2ewarp/components.pending.json`은 DEPENDENCY_WAIT로 차단돼야 한다.
Mac에서 execute/step/render하지 않는다.

## 실제 R3의 정확한 범위

source `e0e1244839d993424cd232836c55357e49ac7d51`, gcp6
`/home/ugrp/ugrp-sim/src/<source>`; Python은 기존
`/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python`이다. 원본 런처/명령/lease 기록은
`/home/ugrp/ugrp-sim/ops-reviews/e2ewarp/launch-r3.py`, `launcher-r3.log`,
`launcher-r3-result.json`에 있다. 원본 queue는 [r3/queue.json](r3/queue.json).

```sh
python -m scripts.run_e2e_warp --prepare --round 3 --nworld 2 --condition peer_ko \
  --rejection-table /home/ugrp/ugrp-sim/ops-reviews/e2ewarp/r2-review-v3/rejection_table.json \
  --e2e-warp-batch on_v1 --output /home/ugrp/ugrp-sim/runs/e2ewarp-r3-admission

python -m scripts.sim_cli workflow run e2e-warp-batch-v446 \
  --record /home/ugrp/ugrp-sim/runs/e2ewarp-r3-managed -- \
  --e2e-warp-batch on_v1 --execute --round 3 --nworld 2 --condition peer_ko \
  --expected-source-sha e0e1244839d993424cd232836c55357e49ac7d51 \
  --queue /home/ugrp/ugrp-sim/runs/e2ewarp-r3-admission/queue.json \
  --host-receipt /home/ugrp/ugrp-sim/ops-reviews/e2ewarp-host-receipt.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-r3
```

이 명령은 이미 존재하는 출력 경로를 덮어쓰지 않는다. 새로운 재현은 새 run ID·인수
기록을 써야 한다. 원래 source의 old modulo 지도 삽입/키프레임0을 보존하며,
후속 elapsed_sim_v1의 성공 결과로 재분류하지 않는다.

Mac의 중계는 `python3 -m scripts.e2e_warp_relay --serve --output <새경로>`였다.
전용 SSH reverse tunnel `127.0.0.1:18627 → Mac127.0.0.1:18626`만 사용했다.
OpenRouter key는 기존 Mac Keychain에서만 읽었다. VM에 키/계정 자격 증명을 복사하지 않는다.
중계와 터널은 작업 종료 때 둘 다 종료했다. 새 배치 직전 endpoint_watch·잔액 확인과
idle20/budget-stop·임대·GPU/PID·저장 예산 점검을 다시 한다.

## 후속 후보의 구분

새 소스의 키프레임 후보는 prepare에 `--map-keyframe-admission elapsed_sim_v1`을
명시한다. 해당 queue의 map_keyframe_admission과 runtime-applied 값을 함께 남긴다.
예전 off와 결과를 합산하지 않고 지도 관문을 다시 잰다. 기록된 R3 frame funnel을
새 queue의 절대경로 rejection_table로 연결한다.

full mission에는 다음 hash-bound factory만 필요하다. E2E orchestration은 이미
`harness/e2e_warp_mission.py`에 있으며 다른 작업자에게 전체 제어기를 요구하지 않는다.

| factory | 입력 | 반환 객체/의무 |
|---|---|---|
| navigation_factory | robot_id, static | observe/frame; task_candidates; start/command; own RGB confirm_act; 채널 on_messages; accept_release_fix |
| release_factory | robot_id, static | start; 실제 자기 RGB observe/command; relocalized+static_map_registered 인수 |
| evaluator_factory | raw 디렉터리(제어 종료 뒤) | source SHA·evaluation-state SHA·정확한 world IDs·한 에피소드 처음→끝 실제 운반 판정 |

navigation의 evidence_revision은 의미 있는 자기 관측 사건에서만 바꾼다(매 프레임 시각으로
바꾸지 않는다). WAIT는 이 사건이나 허용 채널의 새 메시지에만 다시 LLM을 부른다.
ACT의 done만으로 phase를 넘기지 않고 자기 RGB 확인을 요구한다. release 관측 어댑터의
항상 accepted=false 결과를 위치 재획득 성공으로 해석하지 않는다.

native selected ACT의3파일 inventory/hash·adapter·완료10000 step provenance·native
contact 출처·선택 검증을 채운다. CUDA 추론/LeRobot pin 실제 로딩은 아직 인수하지 않았다.
checkpoint가 없거나 legacy 출처면 실행 계층을 교사로 대체하지 않고 차단한다.

## 원본 분석·무결성

원본 실행 호스트 gcp6 CPU에서만 다음을 실행했다.

```sh
python -m scripts.e2e_warp_inspect \
  --raw /home/ugrp/ugrp-sim/runs/e2ewarp-r3 \
  --output /home/ugrp/ugrp-sim/ops-reviews/e2ewarp/r3-review --playback
```

ffmpeg 영상은3배속이며 ffprobe JSON과 해시를 회수했다. 2Hz 전체/10Hz tail 띠는
gcp6에서 만들었고 Mac에서는 이미지 파일만 직접 읽었다. raw의 큰 JSON7개는 무손실
압축 후 해제 SHA를 전수 확인했다. packing.json의 original_sha256 및 원래 sha256.json을
검사한다. sealed-files.json은 현재 `.zst` 파일까지 포함한 별도 목록이다. 원격 manifest
자체의 SHA는 r3/remote-manifest-hashes.json에 보존했다.
