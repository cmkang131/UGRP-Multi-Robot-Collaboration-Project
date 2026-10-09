# 시뮬레이션 동료 대화 관찰

`ThreeRobotRuntime`은 검증된 모델 응답의 `message`가 다른 로봇의 inbox에 실제 추가된 직후 `team/conversation.jsonl`에 전달 영수증을 덧붙인다. 각 행에는 발신자, 수신자, 턴, 계획/실행 단계, 시뮬레이션 시각, 요청 ID, 원문 및 `llm`/`fixture` 출처가 있다. `reason`은 로봇의 판단 설명으로 `decision_explanation`, `accept`와 제안 ID는 `proposal_vote`로 따로 기록한다. 모터 명령은 동료 대화에 포함하지 않는다.

터미널의 `peer_delivery` 행에는 전달 원문 전체가 JSON 문자열로 출력된다. 제어 문자와 줄바꿈은 터미널 안전을 위해 이스케이프하지만 UTF-8 JSONL의 `text` 값은 원문을 보존한다. `team/latest-dialogue.json`은 최근 실제 모델 메시지 최대 3개와 누적 건수를 담는 8 KiB 이하의 원자적 교체 파일이다. 오래된 메시지와 전체 문장은 JSONL에서 확인한다. 최신 파일은 새 메시지나 fixture에서 실제 모델로 전환될 때만 갱신한다.

`--viewer`의 MuJoCo 관찰 창은 이 최신 파일만 5 Hz 이하로 읽어 최근 대화와 전체 로그 위치를 작은 이미지로 표시한다. `--realtime-control`에서는 독립 프로세스의 복제 모델, 기본 비실시간 실행에서는 기존 복제 모델의 창에 표시한다. 두 창 모두 팀 생성·계획 협상 전에 열린다. Headless 실행은 터미널·JSONL 기록을 제공한다. macOS Apple SD Gothic Neo 또는 Linux Noto/Nanum 한글 폰트를 사용한다. 폰트가 없으면 창은 영문 안내로 돌아가며 원문은 UTF-8 터미널과 JSONL에서 볼 수 있다. 관찰용 이미지/파일은 로봇 RGB, 물리 상태, 판단 요청으로 되돌아가지 않는다. 별도 웹 UI나 추가 모델 요청은 없다.

MuJoCo 3.12의 이미지 overlay는 3D 렌더 뒤 `glDrawPixels`를 쓰므로, 관찰창에 짧은 ASCII 헤더를 먼저 설정해 2D 그리기 상태를 초기화한다. 이후 1000×330 RGB 패널에 최근 세 메시지를 각각 수신자 한 줄과 원문 최대 두 줄로 표시한다. 잘린 문장에는 줄임표를 붙이고 전체 원문 위치를 아래에 표시한다. 이 과정은 관찰창 내부에서만 실행한다.

`--plan-replay`의 합의 투표는 scripted fixture다. 이때 새 자연어 메시지 수는 0으로 표시한다. fixture가 시험용 문장을 inbox에 전달하더라도 `fixture_peer_message`로 기록하고 실제 모델 대화 건수에는 넣지 않는다. 저장 계획의 RGB 물리 실행도 새로운 자연어 대화를 만들어내지 않는다.

TensorBoard의 현재 generic export는 이 JSONL을 Text 카드로 변환하지 않는다. 완료된 실행을 별도 불변 snapshot으로 내보낼 때 `peer_message`와 `fixture_peer_message`를 분리해 Text event를 추가할 수 있다. 실시간 관찰의 기준 원본은 계속 JSONL이다.

실제 저장 LLM 대화를 새 호출 없이 창에서 확인하려면, 물리 실험이 종료된 뒤 아래의 유한한 관찰 전용 명령을 저장소 루트에서 실행할 수 있다. 이 명령은 저장된 `team.json`의 마지막 세 문장을 **기록 재생**으로 표시한다. 실행 결과와 최신 sidecar를 건드리지 않고 원본 SHA-256·건수·폰트 상태를 새 감사 파일에 기록한다.

```bash
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/mjpython -m scripts.smoke_communication_overlay \
  --source outputs/simulation-runs/20260923-161558-dispatch-cca0ae6c/artifacts/team/team.json \
  --audit outputs/communication-observer/saved-dialogue-native-smoke.json \
  --duration-s 10
```

만약 MuJoCo 창에서 패널이 보이지 않으면 새 `--audit` 경로로 `--diagnostic --duration-s 30`을 실행한다. 이 모드는 관찰창 viewport를 기록하고 ASCII 텍스트 및 밝은 중앙 RGB 표식을 함께 요청하며, 정지 복제 모델에만 full viewer sync를 수행한다. 표식이 실제 화면에 나타나는지는 창 캡처로 별도 확인해야 한다.

## 말풍선 오버레이 (`observer_overlay=speech_bubbles_v1`, 기본 OFF)

2026-10-08 사용자 요청("LLM 통신할 때 말풍선 뜨게", "로봇 머리 바로 위에")으로 추가한 **관찰 영상 전용** 표시다. 로봇이 서로 보낸 실제 모델 메시지(`team/conversation.jsonl`의 `peer_message`; `fixture_peer_message`는 제외)를 말한 로봇의 머리 위에 둥근 말풍선과 꼬리로 보여 준다. 위의 대화 상자와 따로 켜고 끈다.

```bash
.venv-sim-worker-mac/bin/python -m scripts.render_speech_bubble_video RUN_DIR OUT.mp4 \
  --observer-overlay speech_bubbles_v1 --receipts --speed 4 --zoom 1.5 --window 0:75 --window 174:180
```

- `RUN_DIR`은 `replay/`(기록된 qpos)와 `team/conversation.jsonl`이 있는 실행 폴더다. 물리를 다시 돌리지 않고 기록된 상태를 `mj_forward`로 놓아 관찰 카메라(`replay/view.json`의 자유 카메라)로 그린다. `.png` 출력과 `--still-sim-s`는 한 장만 만든다. `--observer-overlay`를 생략하면(`none`/`off`) 말풍선 없이 같은 영상만 나오고 대화 파일도 읽지 않는다. 영상은 기본 60초를 넘으면 시작하지 않는다(`--max-video-seconds`).
- 말풍선: 말한 로봇의 색(r1 노랑, r2 파랑, r3 빨강), 보낸 쪽과 받는 쪽 표시, 최대 3줄과 줄임표, 보낸 뒤 `--bubble-seconds`(기본 5초) 동안 표시하고 앞뒤로 흐려진다. 같은 로봇의 새 메시지는 이전 말풍선을 바로 대체한다. 로봇이 가까우면 옆·위로 비켜 겹치지 않게 하고, 프레임 안으로 자르며, 머리가 프레임 위쪽이면 아래에 둔다. `--receipts`는 받은 로봇 머리 옆에 작은 "받음" 표시를 잠깐 띄운다. 한글은 `KOREAN_FONTS`를 그대로 쓰며 폰트가 없으면 영문 안내로 돌아간다.
- **기록된 시각:** 모델이 답하는 동안 SIM 시계는 멈춰 있어 여러 메시지가 같은 `sim_time_s`를 갖는다. 영상은 그 시각에 장면을 멈추고 기록 순서대로 `--beat-seconds`(기본 2초) 간격으로 말풍선을 띄운 뒤 `--linger-seconds`(기본 2.5초) 더 보여 준다. 좌상단에 "대화 중 (시뮬레이션 일시정지)"가 표시된다. 지연은 영상 시계에만 있고 로그의 시각은 그대로다. `--no-dialogue-pause`는 멈추지 않고 SIM 시계대로 표시한다. 결과 옆의 `*.render.json`에 메시지별 로그 시각과 영상 시작 시각, 입력 해시를 남긴다.
- **경계:** 말풍선은 관찰용 프레임의 복사본에만 그린다. 로봇 자기 카메라(`*__robot_cam`)와 제어기가 읽는 공용 top RGB(`cctv_top*`)는 `ObserverCamera`가 이름으로 거부하며, 이 모듈을 가져오는 곳은 관찰 렌더러 하나뿐임을 시험이 확인한다. 머리 위치는 기록된 정답 qpos(자유 관절 위치 + 0.27 m)이며, 사람이 보는 그림에만 쓰는 표시·평가 용도로 허용한다. 제어·계획·판정·모델 요청에는 아무것도 되돌아가지 않는다.
- **한계:** 실행 중인 MuJoCo 관찰창(`dispatch_native_view`, `dispatch_native_process`)에는 아직 연결하지 않았다. 그 파일과 `communication_overlay.py`는 실행 번들(v63 등)에 해시로 고정돼 있어 바꾸면 번들이 어긋난다. MuJoCo 3.12 `set_images`는 알파 없는 RGB라서 둥근 말풍선을 그대로 얹을 수도 없다. 라이브 연결은 새 번들 ID가 필요한 별도 작업이다. 머리 높이 0.27 m는 팔을 접은 자세 기준의 근삿값이라 팔을 들면 말풍선 꼬리가 머리에서 조금 떨어져 보일 수 있다.
