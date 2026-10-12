# E2E 13차 속도 측정
12차 A, seed 61001, DEV PR #433.
프로파일 60 SIM초: py-spy native/speedscope, cProfile, mjData.timer.
번들 horizon과 물리·카메라·증거 주기를 유지하고 외부 측정 한도로 종료한다.
후보는 측정 상위 중복 계산을 토글로 나눠 비교한다.
동시 on/off 60 SIM초의 명령·RGB·RBPF 해시 전체 일치가 채택 조건이다.
성능은 같은 VM의 wall/SIM 및 CPU/SIM으로 판정한다.
원본은 Azure 영속 디스크 → ARM 해시 검증, Mac은 가벼운 기록만.
