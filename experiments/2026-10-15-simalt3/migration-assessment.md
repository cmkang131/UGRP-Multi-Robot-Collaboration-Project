# 미채택 후 남는 이식 범위 — 구현하지 않음

현재 물리/관측 동등성 실패로 착수하지 않는다. 아래10–17작업일은 adapter 범위만의 거친 추정이며, C3.12↔3.16 물리 차이·부분 투명도 결함 해결, 새 교사 관문·데이터·학습/평가 시간은 포함하지 않는다.

이 목록은 실행 중 동등성/처리량 판정과 별개인 소스 조사다. 기준은 실제 진단의 동결 교사 `6f057f7e`; 현행 다른 교사 브랜치 전체를 감사했다는 뜻은 아니다. 공수는 개발자 1명의 작업일 추정이며 실측/보장이 아니다.

| 변경 지점 | 필요한 변경과 검증 | 예상 작업일 | 주요 위험 |
|---|---|---:|---|
| `sim/session_scenes.py:62`, `scripts/simalt_physics_compare.py:33` | Scene 변환·setup 뒤 최종 MJCF/초기상태 export. world별 reset mask와 동일 자산/물리 해시. 이번 축소 장면을 전체 작업 장면으로 확대 | 1–2 | 동적 화물·주문·terrain·다른 로봇 제거가 포함된 축소 진단을 전체 backend로 오인 |
| `sim/masterpi_drive_friction_v7.py:52,211` | 명령 hysteresis 이전 방향을 `[world,robot,wheel]` 배열로 유지; 4000Hz physics tick마다 torque를 계산. reset 때 다른 world와 섞이지 않음 검증 | 1–2 | 한 world 명령이 다른 world의 마찰/래치를 변경; 일부 tick 누락 |
| `sim/camera_robot_port.py:196,255,275`, `sim/grasp_act_port.py:84,95` (6f057f7e) | wheel별 기한, lease, fractional servo accumulator, deadband/rate/반올림을 issued-command 상태로 배치화. 단일 integer tick/SIM clock 사용 | 1–2 | 10Hz마다 한번만 갱신해 pulse 폭·서보 궤적 변경; 측정 관절로 명령 상태를 대체 |
| `sim/multi_masterpi_production.py:840` 및 `sim/s2_realism_camera_binding.py:12` (6f057f7e) | 매 world 움직이는 팔 카메라의 v3 mount·K·주점·geomgroup을 보존. `refit_bvh`→render→RGB/동일 cv2 fisheye remap. C 저장 상태로 가림/색띠/가장자리 parity 확인 | 2–3 | XML에 없는 runtime camera binding 유실, RGB 방향/채널·재질/그림자 차이; readback/CPU remap 병목 |
| `scripts/run_solo_grasp_act_teacher.py:119,146,165,224,236,246,275,350,354,394` (6f057f7e) | MjData 직접 읽기를 world별 관측/평가 adapter로 분리. visible+not-held일 때만 상대 위치를 내보내고 평가는 별도 배열. 현재 teacher state machine은 host에 두는 첫 이식 가능 | 2–3 | visibility와 measured truth가 잘못된 world/프레임으로 연결; CPU 동기화로 배치 이득 상실 |
| `scripts/run_grasp_act_teacher.py:37–57,153–162,196–214,241–267` (6f057f7e) | 로봇/빔/접촉/관절 직접 읽기와 GO/ACK의 world별 시계를 분리. 통신 조건의 채널만 사용; partner hidden structured side channel 금지 | 1–2 | 다른 world/로봇 정보 누출, truth를 held cargo 입력에 전달 |
| `sim/grasp_act_solo_evaluation.py:15,34`, ACT inference/recorder 및 workflow registry | score/기록/부분 실패/10Hz 마지막10초 RGB ring/해시·funnel·cap_end를 batch index별 보존. PyTorch 입력은 자기 RGB·발행 이력·이산 지시만. 기존 C 최종 평가 경로 유지 | 2–3 | backend info/접촉을 학생 입력에 섞음; 종료된 world를 계속 step하거나 다른 world 결과로 완주 표시 |

합계는 단순 더하면 10–17 작업일이며 일부 병렬 작업/기존 코드 재사용이 가능하다. 먼저 1대+상자의 운영 adapter와 실제 RGB·교사 결정 비용까지 포함한 시험을 만들고, 그 다음 2대+빔 및 전체 장면으로 나눠야 한다. 정확한 일정은 backend 동등성·renderer 지원과 현재 최신 교사 브랜치 감사 뒤 다시 산정해야 한다. 이 문서는 구현 착수/기본값 전환 승인이 아니다.
