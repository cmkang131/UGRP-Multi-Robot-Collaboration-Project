# speedctrl3: Oracle 지연 렌더 인수

사용자 speedctrl3 지시로 Mac 물리·렌더·속도 측정은 중단한다. 기존 Mac 작업은
2026-10-10 11:53 UTC 확인 때 프로세스와 잠금이 없었다. 과거 원본은 보존한다.
이 기록은 개발 속도 진단이며 연구 코호트/임무 성공 증거가 아니다.

## 고정 비교

- 공통 `sim.lazy_camera.capture_robot_frames`: `UGRP_CAMERA_RENDER=eager` 기본,
  `lazy-v1`은 로봇 키의 값을 처음 읽을 때 원래 포트에서 JPEG를 생성한다.
  키 나열·길이·멤버십은 렌더하지 않는다. 물리 진행·명령·리셋·다음 캡처·종료
  전에 아직 읽지 않은 **기존 기록 대상 전부**를 원래 시각에서 저장한다.
  RGB/해시·원장·물리·카메라 해상도·압축 품질·관측 주기는 바꾸지 않는다.
- S3 s3fix15 adapter `4e19382d59a9bb2bbf351a7fca1356cdf480e8a0`, cyan c0,
  seed14201, stopped_base_arm_v1, 60SIM초. 원래 fixture·물리 감독을 그대로 쓴다.
- ego adapter `2cfe8852ba3b8db8045bb946d45d5f678d134e86`, egomap59
  seed55001의 초기 지도 작성 60SIM초 DEV 구간. 같은 명령/mapper,
  dev_light 및 원래 물리 실패 정지. libm_ulps_v1 자산 검증은 양쪽 동일.
- 구현 archive SHA와 adapter SHA/실제 Python 지문을 별도로 기록한다.
  adapter의 두 capture 메서드만 명시적으로 같은 공통 함수에 연결한다.
  하나의 구현 SHA에서 A=eager, B=lazy-v1 순서 **ABBA**, S3 다음 ego.
  각 arm 새 프로세스, LP_NUM_THREADS=4, OMP_NUM_THREADS=1, OSMesa.
- Oracle에서 진행 중 연구 실행이 있으면 종료를 기다린다(각 대기 최대1시간).
  다른 작업 종료0회, 우선순위 변경0회. 서버 agent_lock과 각 arm loadavg
  1초 표본을 보존한다. 부하 판정은 인접 A/B 두 쌍과 A/B 집계 모두
  `abs(A-B) <= max(0.5, 0.25*min(A,B))`. 실패하면 절감률 null.
- 모든 명령·제어 원장·**소비 프레임을 포함한 전체 원본 JPEG/프레임 원장**을
  직접 바이트 비교한다. 원래 제어 JSON의 숫자/시각 필드를 정규화하지 않는다.
  wall/load/source/설정 출처 receipt는 행동 비교 밖에 별도 보존한다.
  중단·물리 실패·부하 실패·불일치는 채택으로 보고하지 않는다.

현재 S3 루프는 `assert_frame_commands(frames.items())`와 on_frames에서
세 카메라를 모두 읽는다. ego도 매 관측의 RGB를 읽는다. 모든 기존 JPEG와
원장 행이 보존 대상이므로 예상 렌더 생략은 0이다. 지연만으로 얻는 가속을
가정하지 않으며, 관측/기록 주기를 줄이는 변경은 이 후보에 넣지 않는다.

## 실행과 보존

표준 카탈로그 `lazy-camera-abba`와 `scripts.benchmark_lazy_camera`를 등록했다.
사용자 제공 oracle_run.sh가 커밋 archive를 전송한다. 모든 raw는 Oracle의
`~/ugrp-sim/runs/<name>`에 새로 쓰고 fetch 후 로컬 primary outputs에 보존한다.
새 bundle 번호/성공 판정은 발급하지 않고 기존 실험 adapter의 파생 진단으로
구분한다. 렌더 비용은 구간 타이머, 전체 비용은 initialization 포함 wall/SIM이다.
렌더 로그는 생성/소비/기록 강제 횟수를 기록한다. 원본 압축·삭제0회.

## 참고 자료

- [MuJoCo visualization](https://mujoco.readthedocs.io/en/stable/programming/visualization.html):
  mjv_updateScene은 현재 mjModel/mjData를 읽는다. 따라서 나중 시각의 상태를
  과거 프레임으로 렌더하면 안 된다. 이 구현은 상태 복원 대신 동기 호스트 경계를 사용한다.
- [Python Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping):
  키 조회와 값 접근 분리. membership이 기본 __getitem__을 호출하지 않도록 명시한다.
- [기존 정합·캐시·무손실 기록 근거](../2026-10-10-sim-speed-ctrl2/README.md):
  Olson/Cartographer/AMCL와 Thrun 목차 검증 범위는 그대로 유지한다.

결과: 아직 Oracle 비교 전. 기본 eager, 성능 채택 미결정.
