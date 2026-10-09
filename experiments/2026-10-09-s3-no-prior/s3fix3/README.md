# S3 s3fix3 — 공동 운반 예외와 공통 명령 계약 (2026-10-09)

사용자 확정: **두 로봇이 함께 빔을 드는 구간은 heading 제외, 기존 옆걸음 경로 유지**. 단독·접근은 heading 기본ON, 집기·놓기·문 정렬 lateral은 최종0.10m만 허용한다. 기존 GO 상호 확인·실제 물리/실행 오류는 정지하며 DEV σ/관측/충돌 가드는 기록 후 계속한다.

공통 최소 명령 길이·단일 축 수정은 main 대상 PR #422 (`6ffa74df`)로 먼저 분리한 뒤 S3에 merge했다(`93f648a3`, rebase0). 같은 `zone_solo_cyan_path_heading` 선택기와 v145 factory를 사용하며 S3 전용 duration 보정을 만들지 않는다. 0.06초 제안은 늘리거나 합성하지 않고 생략한다. 유효한 최종 lateral이 없으면 기존3cm 반경까지 회전·전진 후 최종 yaw; 기존 도착/σ 문턱 그대로다. [저장 명령/회귀/표준 근거](../../2026-10-09-heading-command-contract/README.md).

`HEADING_EXCEPTIONS`의 유일한 항목은 `coupled_beam_carry`다. r1/r2 자기 집기 명령 이력·carry 단계·살아 있는 peer carry enum을 요구하고 기존 GO를 우회하지 않는다. 승인된 기존 route/연속 축 혼합/시간 schedule은 바꾸지 않는다. 호스트는 두 자기 발행 gripper 명령이 닫힌 경우 기존 CameraRobotPort의 명령 경로를 사용한다. 실제 파지 여부는 제어에 몰래 넣지 않고 기존 독립 물리 판정으로 검사한다.

r1/r2 PF는 같은 posterior와 AMCL odometry 적분을 유지하며 자기 집기/놓기 명령 시각에만 S2 pulse ↔ 기존 pair 연속 모델을 전환한다. loaded 모델은 `door_schedule`과 같은 정적 pair calibration을 사용하고, 새 보정·측정이라고 주장하지 않는다. S2 loaded pulse 전용 flow buffer는 공동 연속 운반에 사용하지 않는다. 자기 RGB wall update와 카메라 보정은 유지한다. r3/S2 및 옵션off는 이 예외를 적용하지 않는다. v7 공동 loaded 정확도는 여전히 미인수다.

새 실행 전 고정: 전체 main/열린 PR의 최대147/7.40 확인 후 **v148/7.41.0**. seed14201 고정, DEV1회, SIM1800/wall10800초, 원본3GiB+10GiB reserve, ENOSPC=HOST_ERROR. v3 호스트 binding·heading on·main #420 relay-cache on. S3 정확 posterior 캐시/JSONL 버퍼ON은 이전442프레임의 명령·상태·RNG 동일성에 근거하고, cProfile을 먼저 끝낸 후 실제 profiler 없이 wall/SIM을 측정한다. 입자/seed/수렴 문턱은 바꾸지 않는다. 임계값이나 활성화 결정을 새 smoke 결과를 본 뒤 바꾸지 않는다. [등록](registration.json), [번호 확인](reservation.json).

사전 회귀: 공통2파일30 PASS; S3 관련2파일18 PASS + 표준 카탈로그 plan1 PASS. 공통 원본 명령3개 계약 거부→수정 출력3개 허용은 모터 stub 오프라인이며 물리 성공이 아니다. S3 예외는 역할/자기 grasp/peer enum 거부 경로, native motor 값/만료의 기존 일치, 실제 PF의 loaded 혼합→release→unloaded pulse 전환, off 포즈/입자/RNG 동일성을 확인했다.

이 문서를 기록한 시점의 새 물리 실행은0회다. cProfile와 새 smoke 결과는 별도 파일로 추가하며 원본 v147 및 s3fix2 비교는 덮어쓰지 않는다.
