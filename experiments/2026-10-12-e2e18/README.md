# E2E18 (DEV)
- v216: v215 + speed4 권장값 + 부분 B 경계 2시점 합의 + standoff/native/replan/extent/navigation.
- VM3 seed61001–61006, VM4 seed61007–61012; 호스트당 최대6, 상한7시간. 재제출은 별도 r번호.
- 게이트: 동시6 ×30 SIM초, wall/SIM 중앙≤2.5. 초과 시 비용 축소 재점검(최대45분); 이후 상한3.0을 명시해 재판정.
- 판정: 동일 실행의 LLM 실제응답 / 자기 지도(B 포함) / 시작→끝 운반. 각 단계를 분리해 기록.
- 부분 추정은 complete=False 보존; 잔차≤3cm·크기0.8×1.4m·기존 적합 품질검사와 변위≥3cm 또는 회전≥3°인 신선한 두 시점 일치.
- raw: Azure ~/ugrp-sim/runs/e2e18-*; ARM 전체 해시 보관, Mac fetch-lite만. 모든 실패·재제출은 run-summary.json.
- 참고: [SciPy robust least squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html), [OpenCV fisheye](https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html), [AprilTag3 공개 구현](https://github.com/AprilRobotics/apriltag). 앞 두 방법을 재사용하고, 2시점 기준은 이 DEV의 설계값이며 논문 결과를 승계하지 않음.
