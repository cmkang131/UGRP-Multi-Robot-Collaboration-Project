# 2026-09-27 비전 자세 제공자 폐루프 dev 확인 (Kiro)

**dev closed-loop check, 연구 결과 아님.** `kiro/zone-vision-worker`(PR #237, `kiro/`는 Kiro 작업 표시), Refs #216, #223.

## 무엇을 확인했나

PR #233의 태그 없는 비전 위치 추정 학생(VIS3, 오프라인 게이트 G2 FAIL)을 자세 제공자 `vision_zero_tag_v1`(`harness/vision_pose_source.py`)로 만들어 자기 카메라 실행기(#206, `6fde2607` 병합)가 **추정으로 직접 주행**하게 했다. 분할 모델은 별도 torch worker(`scripts/vision_loc_worker.py`, 기존 `.venv-reference-act`)에서 돈다.

- 회차: VIS3 3차 **dev** `vl3-dev-s942`(seed 942, 출발 오프셋 설정 전용, 상자 → A2). v3 test seed 아님.
- 환경: `zone_wide_door` + walls_v3(0.40 m) + **태그 0개**(`TagFreeZoneScene`, 장면 tag_count 0). `sim/zone_*.py`는 v3 소스 `7cedb049`의 git blob을 실행 시 적재(해시는 `manifest.json`의 `code.v3_sim_overlay`), 해당 파일은 수정·병합하지 않음.
- 로봇 r2 한 대가 배송, r1·r3는 도크에서 hold. cargo_noslip_v1(noslip 10), weld OFF(max eq_active 0), SYNC SIM, no-LLM.
- 입력: 자기 손목 RGB, 자기 명령, 정적 태그 없는 지도, 고정 보정, 주문서, 시작 사전분포(정적 배치의 자기 도크 줄 (-0.85, -0.85, 0), ±15 cm·±10°; 설정 전용 오프셋은 주지 않음). GT는 `eval_only/`에만.
- 실행 소스 `93936d36`(깨끗한 트리), physics 잠금(`agent_lock.py`, owner kiro) 안에서 1 sim, `ugrp_session.py run`, 스레드 1. 부하 평균(1분) 시작 2.5 → 끝 7.4(도중 최대 약 36, 다른 작업). wall 1,220.6 s.

## 결과 (평가 전용 GT로 채점)

| 항목 | 값 |
|---|---|
| 배송 | **실패**: `CARRY_LEG_pose_uncertain` (461.55 SIM s). 상자는 들린 채(z 0.17 m) A2 중심에서 0.18 m |
| 문 통과 | **통과**(GT 궤적, 356.2 SIM s, 문 중심 대비 횡 −3.5 cm), 상자를 든 채 x 4.35 m까지 |
| SIM 시간 | 462.05 s (교사 283.7 s) |
| 위치 오차 전체(2,375 프레임) | p50 3.8 cm, p90 32.1 cm, 최대 61.8 cm; yaw p50 0.5°, p90 6.0° |
| 위치 오차 문 0.5 m 안(190 프레임) | p50 4.5 cm, p90 8.9 cm, 최대 9.8 cm |
| worker | 실패 0, 호출 1,375(측정 1,375, 미정착 건너뜀 1,000), 거절 프레임 0, 시작 1.9 s |
| 추론 wall 시간 | p50 157 ms, p90 202 ms, 최대 648 ms (SIM 시간에 부과 안 함) |
| 거짓 확인 | 0 (완료 확인 없음) |

시간대별로 보면 두 가지 문제가 드러났다(`eval_only/frames_eval.jsonl`).

1. **집기 구간의 과신 오차(90–150 SIM s):** 오차 p50 31–56 cm인데 추정 σ는 약 4 cm였다. 게이트는 이 추정을 믿었다. 150 s 뒤 스스로 회복했고(180–360 s 오차 p50 1–7 cm) 상자 집기는 자기 RGB 상자 인식으로 진행됐다. 오프라인 VIS3의 "길 잃음" 약점이 폐루프에서도 나타난 것으로 보인다. 원인 분석은 하지 않았다.
2. **목적 구역 앞 정지(420–461 s):** 오차는 약 7 cm였으나 운반 중 σ가 4.5–5.0 cm로 실행기의 운반 게이트(`GATE_LOADED`)를 넘어서 `pose_uncertain`이 7회 났고, 3회 보기로도 회복하지 못해 운반 구간이 실패했다.

단일 dev 회차이므로 성공률·일반화 결론을 내지 않는다.

## worker 결정성·재현

- CPU worker(1스레드, deterministic)가 오프라인 MPS 관측 캐시(`outputs/vision-loc-20260926/r3/obs-w6/vl3-dev-s942`)를 26프레임에서 그대로 재현했다(열 종류 일치 1.0, 경계 행 차이 0 px). 같은 프레임 반복 응답은 바이트 단위 동일. 일회성 확인 스크립트로 실행했다(부하 4.4).
- SIM 시간 부과: 설계(#223 비용 모형)는 LLM 생각·발화만 부과한다. 인식 추론은 wall 시간만 기록했다. 부과 여부는 **사용자 결정 필요**.

## 원본 위치 (로컬 전용, 원격 백업 아님)

`/Users/changmin/projects/ugrp/outputs/vision-worker-closed-loop-20260927/` (106 MB: `drive.sh`, `load.txt`, `run.log`, `vl3-dev-s942/`)

| 파일 | sha256 |
|---|---|
| `vl3-dev-s942/result.json` | `88b251eb9ac6c9d7e553201da6f3a9e24335f29aae8a27a7bb864c39b1f75fb6` |
| `vl3-dev-s942/manifest.json` | `10aeca8d624f972f844aaf0a680ff5398cdfc8b82d3bcbd875bc40b0f883de42` |
| `vl3-dev-s942/eval_only/frames_eval.jsonl` | `0776d4dd44be545060c78cf045da5feff317ee231f02aa8d650e2fa597a20f0a` |
| `vl3-dev-s942/robots/r2/vision_provider.json` | `fdb18d16f8a842438c1e91529f00bfa489774c0b67c2cf7a9276767e40b576bb` |
| `vl3-dev-s942/robots/r2/vision_timing.jsonl` | `cac2883c158aa3b6513ec27d46430d2b13dc0d26600194fa59c47aec1b442ee9` |

`manifest.json`의 `files`에 모든 json/jsonl의 해시가 있다. 모델 요청 이미지(자기 프레임 JPEG)는 `frames/r*/`에 그대로 보존했다.

## 하지 않은 것 / 남은 문제

- TensorBoard 스냅샷: 이번에 만들지 않았다(크레딧 한도). 원본과 해시는 위에 있다.
- #229 등록(`pose_providers.json`)과 `init_prior` 호출·`close()` 연결은 #229 쪽 작업이다(PR #237 본문의 제안 항목).
- 집기 구간 과신 원인과 운반 게이트 대 VIS3 σ 불일치의 조정은 dev 과제로 남긴다. 조정 없이 test 회차를 돌리지 않는다.

## 참고 자료

PR #237 본문의 "참고 자료"와 같다. 요약: Boniardi 외 IROS 2019(https://arxiv.org/abs/1903.01804), Fox·Burgard·Thrun 1998 Active Markov Localization, Thrun·Burgard·Fox *Probabilistic Robotics* 2005, Howard 외 ICCV 2019 MobileNetV3(https://arxiv.org/abs/1905.02244); PyTorch 2.11.0·torchvision 0.26.0(BSD-3), OpenCV 4.13/5.0(Apache-2.0), NumPy(BSD-3), PythonRobotics `b2020cd`(MIT, M1 PF 경유); 내부: PR #233 VIS3 모듈, PR #210 `markerless_probe.py`, M1 PF `22c84842`, ACT worker 패턴(`harness/recovery_act_client.py` 등), PR #206 실행기·host·테스트, PR #229 제공자 인터페이스, `harness/zone_sim_cost.py`.
