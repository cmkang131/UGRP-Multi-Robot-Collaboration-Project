# s3fix21 — 단계 시작 계약 (DEV, oracle-x86)
1. 사전 등록: `registration.json`; v170, pair c0–c5·cyan c0/c3/c4/c5 × 시작 계약 off/on =20.
2. 두 군 모두 A 내려놓기·정수12 on; 기존20의 초기조건·seed 유지, 새 요인 하나만 비교.
3. 기존 정수군: 시작 편차25.6–36.1mm + 운반 오차10.8–15.9mm = 끝점24.5–36.5mm(벡터).
4. fixture x=1.2749149와 공용 경로 x=1.3 불일치25.085mm; run별 분해·원본 SHA는 등록 JSON.
5. 기본 off 옵션은 호스트 초기 장면만 강체 평행이동(빔+r1/r2); 상대 자세·seed·목표·20mm 문턱 불변.
6. 제어기 생성 전 합성 시작 설정이며 실행 중 GT·PF 사전정보 없음; 전체 임무 위치오차 해결 근거 아님.
7. x86 영속 runs/·LP4·dev_light·60 SIM초; load<51/mem≥6GiB 동시 제출,180wall초 초기 점검·완료 즉시 회수.
8. 정수12·끝점·정착6/6, cyan4/4, 낙하/기울기/HOST0이면 기존 등록3경로를 바로 실행.
9. [표준 단계 시작/목표 상태 계약](https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html); 결과·초기 점검·원본/해시는 `summary.json`.
