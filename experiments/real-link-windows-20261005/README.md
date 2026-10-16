# Windows 실물 팔 연결 진단 — 2026-10-05

## 판정과 검토 범위

이 기록은 1대 Pi에 대한 접속·카메라·팔 명령 변환의 개발 진단이다.
3대 협력 운반, SIM 계획의 REAL 실행, 자세 도달, 파지 성공을 검증하지 않았다.
실험 실행 소스는 `de05404108296650696a6532fdc9d92ca6ee9832`로 고정했다.
기존 Windows 실행 지원 커밋 위에서 실행했으며 최신 main으로 이관한 실행이 아니다.

- 변경 모듈 단위 테스트: `tests/test_real_robot_link.py`, 12개 통과. 장치를 모킹한 검사다.
- 실제 카메라 관측: 성공. 기존 로컬 SSH 카메라 터널의 JPEG만 사용했다.
- 실제 Pi 프로그램에 팔 명령 전달: **dry-run 성공**, 실제 서보 쓰기는 수행하지 않았다.
- 제어 프로그램 probe: 이번 실행에서 `ok=true`, `battery_mv=7745`.
- 앞선 별도 진단에서는 `65466 mV outside valid range` 오류가 있었다. 그 원인은
  미확정이며 이번 정상 응답만으로 해결되었다고 판단하지 않는다. 앞선 응답은 이
  세 결과 파일에 포함되지 않고 별도 터미널 진단에서 관찰된 것이다.
- 현장 안전 범위/배터리 사양은 미확인. 실물 `--execute` 시험을 수행하지 않았다.

## 환경과 설정

- 노트북: Windows PowerShell, Python 3.12.14(기존 번들 런타임).
- 확인 대상: 사용자 소유 Raspberry Pi 4 Model B Rev 1.2, aarch64, robot r1.
- 원격 제어 경로: 기존 `MasterPi/tools/masterpi_control.py`, legacy I2C 경로.
- 검토한 원격 파일 SHA256:
  `7d66aad709f2a7d099a0941940cb31f2068c70fe47a81ba47ff08793a7bcfe73`.
- dry-run 입력: `{"kind":"arm","servo_id":1,"pulse":1800}`, duration 0.5초.
- 로컬 기존 터널 snapshot으로 자기 RGB만 수신. 실제 top 카메라/카메라 보정 없음.
- 호스트 키 확인·전용 SSH 키 사용. 인증키는 Git에 포함하지 않았다.
- 제어 프로그램 교체, 카메라 재시작, 서비스 비활성화, 타 프로세스 종료 없음.
- 상시 서비스 시작 없음. 각 진단 명령은 반환되어 종료했다. 기존 사용자 SSH 터널은 유지했다.

## 전체 결과 및 원본 보관

원본은 이 저장소 로컬 체크아웃의 `outputs/`에만 있다. 원격 백업이 아니다.
실행 당시 체크아웃 위치는
`C:/Users/kevin/Documents/ChatGPT/UGRP/work/multi-robot-collaboration`이다.

| 원본 상대 경로 | SHA256 | 결과 |
|---|---|---|
| `outputs/real-link-20261005-observe-01/result.json` | `8414ebaa5e4424f9a18aa80e9518fafa935c3b5aa678cf7a794bc3c18c043512` | 카메라 수신 성공 |
| `outputs/real-link-20261005-dry-run-01/result.json` | `1b39d3a2a1dd634e708eb302da483bba2c73fa13c1e0a106449a8c11d2c03bfc` | 원격 dry-run exit 0 |
| `outputs/real-link-20261005-probe-01/result.json` | `0ab29f9ca548063415f27fc8281fcb905a98c9ae8dea62da4358a624f2f45945` | 7745 mV 응답 |

관측 파일은 JPEG 원문(base64)·영상 SHA256·노트북 HTTP 요청/수신 시각을 포함한다.
HTTP 시각은 노출 시각이 아니며 발행 PWM은 관절 상태가 아니다.
실물 동작 명령 수 0, dry-run 팔 명령 시도 수 1, 모델 호출/토큰/요금 0.
임무 성공률·실물 이동 시간·파지 성능은 측정하지 않았다.

## 남은 작업

1. 배터리 라벨·제어 보드 모델·전압 읽기 실패 원인을 현장 자료와 대조한다.
2. 간섭 없는 관절 안전 범위를 확인하고 단일 무부하 동작을 검증한다.
3. 실물 카메라/좌표계와 이동을 보정하고, 기존 스킬 실행 포트에 REAL 관측/행동을 연결한다.
4. 추가 2대와 실제 top 영상·동기화·정지 경로를 준비한 뒤 협력 운반을 검증한다.

이 새 진단은 TensorBoard로 변환하지 않았고 대시보드 표시도 검증하지 않았다.
