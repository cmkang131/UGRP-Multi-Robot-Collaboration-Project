# E2E 13차 속도 측정
DEV, seed 61001, PR #433, 실행 소스 ae1a7028 (프로파일 7821864a).
12차 A 60 SIM초: py-spy native/speedscope, cProfile, mjData.timer로 계측.
v200: 격자 정수 연산 벡터화·스칼라 셀 변환·불변 기하 캐시·검증 최적화(각 기본 off).
동등성 6/6: 비교마다 명령·이미지 900장·RBPF 900상태·지도 trace 일치, 관련 시험 95개 통과.
동시 3쌍 중앙값 wall/SIM 15.486→13.301초, CPU/SIM 20.648→18.435초(상태 해시 비용 포함).
60 SIM초 mapping 구간의 DEV 증거이며 B 경계·전체 E2E 완주 근거는 아니다.
10회 원본 ARM 10,010파일 해시 일치, Mac 경량 회수 10/10, VM deallocated 확인(약 72분).
summary.json에 판정·원본 위치·출처·SHA-256; 상세 비교·해시 목록·실행 절차는 JSON.zst.
