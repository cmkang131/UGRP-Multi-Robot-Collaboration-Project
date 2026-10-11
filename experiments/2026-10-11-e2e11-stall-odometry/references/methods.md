# 적용한 표준 방법과 제약

- OpenCV pyramidal Lucas–Kanade와 공식 `lk_track.py`의 전후방 일치 검사를 사용한다. S2의 기존 LK 마스크·특징 수(6개), 공간 셀(2개), 전후방 1px, 중앙 1px·p90 2px 기준을 재사용했다. 흑색 경계·고채도 짐을 제외한다. 이미지 평균 차이도 판정과 별개로 기록한다.
- OpenVINS의 disparity-based stationary detector는 특징점 움직임이 작을 때 정지를 판정한다. 여기서는 IMU·encoder를 쓰지 않으므로 OpenVINS 전체 필터나 metric VO를 재현했다고 주장하지 않는다. RGB 장면의 독립적 이동·미세 운동·무늬 부족에 취약하다. 무늬 부족은 unknown이고 명령 평균을 그대로 예측한다.
- 후보 `rgb_gate_v1`: 별도 비차단 명령 predictor에서 ≥5cm의 이동이 예상되는 최대 1.4초 창으로 LK를 비교한다. 후보 `rgb_pulse_gate_v1`: ≥1cm 창에서 3회 연속 stationary를 요구한다. 두 후보는 이번에 본 저장 자료에서 선택한 DEV 비교이며 확증 자료가 아니다. 현재 RGB로 아직 반영하지 않은 명령 구간의 평균만 0으로 한다. 과거 지도·위치를 소급 이동하지 않고 공분산을 0으로 줄이지 않는다. 이 별도 predictor가 게이트 해제를 판정하므로 자기 동결이 영구 동결로 이어지지 않는다.
- Nav2 `SimpleProgressChecker`의 0.5m/10s 기존 기준과 `BackUp`의 유한 거리·시간 종료를 사용한다. 기존 명령 예측이 progress를 거짓 통과시키는 경로를 RGB 게이트가 줄인다. progress timeout 시 즉시 blacklist하던 기존 경로를 후진 완료/10초 timeout → blacklist/재계획 순서로 연결한다. 추가 연속 visual stall 10초도 같은 후진을 요청한다. 후진 거리는 Nav2 BT의 0.30m, 명령은 이 저장소에서 이미 보정한 -0.35/0.10s 펄스다. ROS의 연속 0.15m/s를 미보정 명령으로 복사하지 않았다. DEV에서는 기존 보수적 충돌 가드를 기록하고 실제 물리 실패 경계는 유지한다.
- Nav2 AMCL omni의 squared-motion alpha 식을 따른다. suspect/unknown 프레임에서 nominal alpha .2→2.0의 추가 Q만 RBPF pending covariance, 명령 predictor, REP105 reporter에 각각 전달한다. 기존 Q는 보존하고 재귀 곱셈·정답 잔차 fitting은 하지 않는다. 상태별 10배 선택은 우리 DEV 토글이며 Nav2가 제공하는 자동 적응 정책은 아니다. gate가 평균을 0으로 하더라도 비차단 명령 크기로 Q를 계산한다.
- 2022 `Visual-Inertial Odometry with Online Calibration of Velocity-Control Based Kinematic Motion Models`(arXiv:2204.06776)는 encoder 없이 발행 제어와 시각 정보를 결합하는 관련 방법이다. 초록을 확인했다. IMU·온라인 운동모델 보정을 쓰는 전체 기법은 이 실행의 허용 센서·범위와 달라 적용하지 않았다. 2025 VIWO slip 논문은 검색 초록만 확인했고 본문이 접근 차단되어 구현 근거로 쓰지 않았다.
- Python `copy` 문서에 따라 predictor의 데이터만 복제하고 bound callback은 복제하지 않는다. 전체 callback 소유 RBPF를 복제하면 순환 참조가 발생하는 반례를 실제 integration 시험에서 수정했다.

URL·열람 시각·본문 SHA-256은 [sources.json](sources.json)에 있다. 단순 source 열람, 고정 명령 재생, 새 폐루프 실행의 근거는 서로 구분한다.
