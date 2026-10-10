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
  송신 측 Git tree manifest의 SHA-256을 명령에 고정하고 실제 source/설정/지도/
  asset의 Git blob 및 Python 파일 목록을 매 arm 앞뒤에 대조한다.
  adapter의 두 capture 메서드만 명시적으로 같은 공통 함수에 연결한다.
  하나의 구현 SHA에서 A=eager, B=lazy-v1 순서 **ABBA**, S3 다음 ego.
  각 arm 새 프로세스, LP_NUM_THREADS=4, OMP_NUM_THREADS=1, OSMesa.
- Oracle에서 진행 중 연구 실행이 있으면 종료를 기다린다(각 대기 최대1시간).
  모든 arm은 연구 worker가 없고 MemAvailable≥6GiB, 1분 load≤2.0일 때
  시작한다. 이전 작업 종료 직후의 부하 잔류도 기다리며 admission 표본을 보존한다.
  다른 작업 종료0회, 우선순위 변경0회. 서버 agent_lock과 각 arm loadavg
  1초 표본을 보존한다. 부하 판정은 인접 A/B 두 쌍과 A/B 집계 모두
  `abs(A-B) <= max(0.5, 0.25*min(A,B))`. 실패하면 절감률 null.
  단독 arm은 실제 부모 PID와 살아 있는 공용 lease를 검증해야 시작한다.
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
렌더 로그는 생성/소비/기록 강제 횟수를 기록한다. `consumer`는 lazy 값 접근으로
생성한 횟수이므로 eager의 consumer=0을 제어기 미소비로 해석하지 않는다.
원본 압축·삭제0회.
이 구형 adapter는 선택한 physics timer hook을 우회한다. `physics_calls=0`은
물리 비용0이 아니라 미계측이며 `timer_coverage`로 명시한다. 렌더와 전체 wall은 실측이다.
기본 eager는 기존 bound method/체크포인트 객체 구조를 유지한다. lazy-v1의
동기 wrapper는 이 진단의 새 실행에만 검증하며 checkpoint resume 경로는 미검증이다.
Oracle 첫 archive는 oracle_run으로 전송했다. 후속 archive의 변하지 않은 파일은
서버에서 읽기 전용 hardlink로 공유하고 바뀐 파일만 새 inode로 쓴 뒤 **모든 추적
파일의 Git blob**을 검증하여 원자적으로 게시했다. 과거 archive를 수정하지 않는다.
서버의 기존 Oracle adapter처럼 실행 전 2GiB 디스크 여유를 확인한다. raw는 삭제하지 않는다.

## 참고 자료

- [MuJoCo visualization](https://mujoco.readthedocs.io/en/stable/programming/visualization.html):
  mjv_updateScene은 현재 mjModel/mjData를 읽는다. 따라서 나중 시각의 상태를
  과거 프레임으로 렌더하면 안 된다. 이 구현은 상태 복원 대신 동기 호스트 경계를 사용한다.
- [Python Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping):
  키 조회와 값 접근 분리. membership이 기본 __getitem__을 호출하지 않도록 명시한다.
- [기존 정합·캐시·무손실 기록 근거](../2026-10-10-sim-speed-ctrl2/README.md):
  Olson/Cartographer/AMCL와 Thrun 목차 검증 범위는 그대로 유지한다.

## 예비 확인과 부하 충돌

Oracle 5SIM 확인(`90a467ac`)은 S3 ABBA4회와 ego 첫 A를 마친 뒤 연구 순번을
위해 활성 물리 자식이 없는 부모 큐만 종료했다. S3의 명령·JPEG·프레임 원장은
동일했지만 `student_record.json`의 실제 inference_wall_ms 18값과 bundle 키 순서가
달랐다. 엄격한 원본 byte 증명은 실패이며 양쪽 렌더300회·생략0이다.
[예비 시험·실패 원본 요약](preliminary-checks.json)은 CLI 오입력(exit2, 물리0)과
초기 시험 fixture 실패도 보존한다. 수정 후 Oracle 대상3파일61PASS를 확인했다.

60SIM 첫 시도 `1f8bb9ca`는 선행 S3 종료 후 1분 load0.49에서 시작했으나
실행 도중 S4 6개와 egomap65 batch가 진입했다. 첫 A는 60SIM을 완료
(wall/SIM5.485794, mean1minload10.9243, 렌더3600회)하고 다음 arm 전 큐를
종료했다. 외부 프로세스에 신호를 보내지 않았고 lease를 반환했다. 이 부분 실행은
동일 부하 ABBA 속도 증거로 채택하지 않는다. 후속은 모든 arm에 위 admission을 적용한다.

기존 Mac 재생과 Oracle 예비·중단 결과21개는 primary
`outputs/tensorboard/1010-speedctrl-partial-v1`에 새 snapshot으로 보존했다.
EventAccumulator에서 수치·원본 해시21개를 다시 확인했고 실제 TensorBoard의
고정 카드/실행 선택/열(case·policy·outcome·source_sha·seed) 표시를 확인했다.
종료된 예비·시험·부분 실행9개의 **모든 원본 JPEG를 포함한 5,132파일,
156,821,337바이트**를 primary `outputs/oracle-runs/`로 회수했다. Oracle에서
만든 파일 목록의 크기·SHA-256과 전부 대조했다([회수 확인](fetch-verification.json)).
Oracle 원본도 보존한다. 진행 중인 최종 cb4b ABBA는 이 회수 집계에서 제외한다.
MP4 생성/등록0회. 전체60SIM ABBA는 대기 중이며 기본 eager다.

최종 구현 `cb4b872c451de99c883fde13026deb24923ddf6c`는 Oracle 변경 모듈
`tests/test_lazy_camera.py` 18PASS다. 독립 source review의 잔여 P0/P1/P2는
없으며([검토 범위](review-final.json)), 이는 실행·동등성·성능 통과를 뜻하지 않는다.
이 SHA의 전체 CI에서 새 workflow의 명시적 plan 시험 인자 누락1건이 발견됐다.
기존 catalog 전수 검사에 필요한 네 인자를 추가했고 해당 시험 파일21PASS를
확인했다. 이 시험은 임시 CLI fixture만 쓰며 Mac 물리·렌더·성능 측정이 아니다.
[실패 기록](ci-regression.json)을 보존하고 수정 후 전체 CI는 원격에서 다시 수행한다.
