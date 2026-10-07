# 실험 인덱스

- [2026-10-07 v8 정지/관측 대기 어댑터 수정](2026-10-07-mapfree-v8-stop/RESULTS.md): PR #409. 2D 최종0속도 뒤 M1 잔류 적분을 차단하고 대기10Hz callback 연결. 같은 개발32쌍에서 대기 접촉14→0, B24→28/32·coverage64.81%, 전체 접촉6/잘못된 문2/거짓 후보8. 관문4/5 실패, 기존12사건·v5–v8 표만 기록하고 트랙 종료; 새32쌍/잡음/MuJoCo/모델0.

- [2026-10-07 public_ros_v8 기본 collision monitor·explore 설정](2026-10-07-mapfree-collision-monitor/RESULTS.md): PR #409. v7 M/N32 개발 한 번, B26→24/32·충돌2→16·거짓 후보14→10, 관문3/5 실패. B3s float 경계 수정은 분리 확인, 근거리 미관측·관측 대기 잔류 접촉이 남아 튜닝/새 확인/잡음 없이 중단.
- [2026-10-07 public_ros_v7 footprint·unknown 원본 정책](2026-10-07-mapfree-unknown-footprint/RESULTS.md): 기존 확인32쌍 frontier26/32·거짓B0·coverage70.11%, 충돌2·거짓 후보14로4/5. 기존 수치 보존.

- [2026-10-07 public_ros_v6 camera raytrace](2026-10-07-mapfree-raytrace/RESULTS.md): PR #409. 기존 K/L32 개발에서 연결36→1,351–2,130칸·NavFn 경로0→29,960후보로 복구. 첫3.54cm footprint 연결이 unknown에 걸려 최종 경로0/32, 추가 튜닝·새 확인·현실 잡음 없이 중단.


- [2026-10-07 동결 v5 frontier 오라클 새32쌍](2026-10-07-mapfree-frontier-oracle/RESULTS.md): PR #409. 새 K/L32에서 정적 B32/32, 자기 frontier0/32·coverage17.25%·기준1/5. 0.10m floor 표본→0.05m 자기 격자 단절, 목표 후보2,044개 모두 불통·첫 관측2s 종료. 튜닝 없이 중단, 현실 잡음 미실행.

- [2026-10-07 s4 마지막 개발·새32 확인](2026-10-07-mapfree-s4-final/README.md): PR #409. B/경로 중심은 free, 거부는0.1m 벽 경계2셀의 footprint 교차. 원 Nav2 bringup0.05m를 기본-off `public_ros_v5`로 적용, 개발 참 B6/6·거짓0 뒤 미개봉 oracle static32/32·충돌0·거짓0. frontier/현실 잡음은 미실행, 추가 개발 반복 종료.

- [2026-10-07 s4·s5 정지 기하·원본 footprint 검사](2026-10-07-mapfree-stop-geometry/README.md): PR #409. 통로0.50m/최대 padded 회전폭0.3688m, 정지 costmap·실제 벽·footprint 그림2장. Nav2 edge 검사만 기본-off `public_ros_v4`로 적용, 기존 개발 유효 B2/6→4/6·거짓0. s5 회복·s4 동일 소진으로 중단, 새32 미개봉.

- [2026-10-07 navigation 영속 장애물·진행 감시 v3](2026-10-07-mapfree-navigation-persistence/README.md): 원본 줄 대조와 opt-in 포트. 기존 실패10 B0→2(유효2/6), 접촉4·회복 소진4로 개발 관문 실패. 새32 미개봉, 튜닝 중단, #409 DRAFT.
- [2026-10-07 navigation 회복·유효 도크 평가 어댑터](2026-10-07-mapfree-navigation-recovery/README.md): Nav2 recovery 포트와 도크 기반 새32쌍 등록. 기존 실패10 재생 B0/10, 회복 소진4·맹점 충돌2 재발로 중단; 새 확인 미개봉, 기본 off, #409 DRAFT.
- [2026-10-07 공개 navigation 코어 이식·선행 관문](2026-10-07-mapfree-public-navigation/README.md): NavFn/explore_lite 원본 + PythonRobotics pursuit, 기본 off. 새 G/H32 oracle static B22/32로 ≥30/32 관문 실패; frontier/현실 잡음 미실행, 재튜닝 중단, #409 DRAFT.

- [2026-10-07 자기 지도 B/C/E: frontier·문·부분 경로](2026-10-07-mapfree-explore/README.md): 기본 off, MuJoCo/모델 없는 2D 개발16쌍→동결→확인32쌍. 확인 B 0/32, coverage15.11%, 충돌13, 문 시도0, 기준1/5로 미달. 구 벽 통계·v7 구조 사전 잡음의 모델 한계와 최초 관측 free 연결 실패를 기록; 물리 미실행, #409 DRAFT.

- [2026-10-07 지도 없는 목적지 D: 자기 RGB 바닥 색 B](2026-10-07-mapfree-goal-floor/README.md): v1/v2 보존, 기본 off의 v3 동결. 새 정적 확인 precision100%/recall79.41%(기준 실패), 기존 카메라 v3·legacy 녹화 거짓 확인0. 시간 누적 보완은 후속 검증 가설이며 기존 v3 코드/설정은 변경하지 않음; #408 DRAFT.

- [2026-10-06 벽 접촉 행·거리 치우침 원인 규명과 놓친 프레임 수정 (높이 없는 벽 검출 탐침, #216)](2026-10-05-ego-wall-map-probe/README.md): 행 +15.3 px·거리 −0.46 m 치우침은 검출기가 아니라 적재 판정(`servo[3]≥900`이 열린 그리퍼 탐색 자세를 운반으로 분류, 편향 −2.62° vs −1.07°)과 채점 기하였다. 분할 렌더 기준으로 검출기 행은 경계 −0.5 px. 놓친 101/247프레임은 전부 지평선이 프레임 밖(horizon 게이트), 바닥 조각 길이 0.81 m 검사로 0프레임, 열 recall 0.59→0.90, 정확한 접촉 0.64, 거짓 검출 677프레임 중 1접촉, 확인 시드 s912·s913 재현. 예전 카메라 기준이며 카메라 v3(#401)에서는 다시 재야 한다. 물리 0회. 이어서 면 단위로 쟀다: 지도에 쌓이는 면이 0.15 m 안인 비율은 옛 검출기 4%, 분할 창 + 처짐 보정 77%, 정착 게이트까지 걸면 88%(지도 원점은 섀시 원점, 팔 축 오프셋 0.0482 m는 기록만이 기본이고 더한 경우의 점수도 같이 적었다). 처짐 보정·자기 지도 C·메모리 D·D의 실행기 연결(`self_wall_memory=on_v1`, 새 모듈 `harness/coela_runtime_self_walls.py`, `source_manifest.json`의 새 번들)은 모두 옵션(기본 꺼짐, 끈 상태는 #405 이전과 같은 출력). 벽 기록을 채우는 쪽과 카메라 v3 재측정은 못 했다. 모델 호출 0회.

- [2026-10-05 S1 혼합 배치와 v4 지도 연결](2026-10-05-s1-placement/README.md): 최종 v3 지도 조회와 색 상자·catalogue 화물의 정적 혼합 배치. v4 8종 오프라인 검사, 소스 `35034c5b`의 dev_s1lite·전체 s1 각 30 SIM초 정지·렌더 DEV screen PASS. 유한 바닥 침투를 기록했으며 실제 운반·S1 물리 졸업·S2 제어기 연결은 미검증.

- [2026-10-05 S2 단독 cyan 최종 v3 후보 v106](2026-10-05-solo-cyan-v106/README.md): v98 벽 관측·입자 필터·partial-fix·호버 확인·blind close·하중 가림 재사용, 내려놓기 재관측·재집기. own RGB/정적 지도/자기 명령만. `setdown-relook-v3`, 하중 이동은 v102, 방향 결합 보정은 s911 탐색 모델. 소스 `dfec1f19`의 s912–914/3 slot에서 DEV 사후 잠정 기하 판정 3/3. `STAGE_REACHED_UNQUALIFIED`, `physical_success=null`, `research_result=false`; 정식 stop-ON·S2 전체 졸업·실물 성공은 미검증.

- [2026-10-05 시나리오 v4 (v3 여덟 종 + 최종 로봇 v3 지도로 지도 필드만 교체)](2026-10-05-scenarios-v4/README.md): 연구 시나리오 s1–s8의 `map_id`·`map_file_sha256`만 `*_v3` 지도로 바꿨다(지도 기하는 v2/final_v1과 같고 id·robot_model·version·parent 해시만 다름). 새 지도 없음, v2·v3 파일은 그대로. 오프라인 검증(validate·해시·기하 동일성·s7/s8 경로)만 했고 SIM·모델 호출 0회.
- [2026-09-29 시나리오 v3: 화물 목록 전체와 3대 운반](2026-09-29-zone-scenarios-v3/README.md): v2 여섯 종은 yellow와 3대 필요 화물 tri_frame을 쓰지 않았다. v2 여섯 종을 그대로 두고 삼자 결속 `s7`과 1·2·3대 혼합 `s8`을 더해 화물 종류 9개와 필요 인원 1/2/3을 모두 덮는 v3 여덟 종을 만들었다(두 문 지도, 사건 없음). 오프라인 검증만 했고 3대 자기 카메라 실행기는 아직 없어 실행하지 않았다.
- [2026-10-05 시나리오 E2E 격차 분석과 구축 계획 (문서 전용)](2026-10-05-scenario-e2e-gap/README.md): 연구 시나리오 s1–s8을 자기 카메라 E2E로 돌리기까지 무엇이 되고(빔 짝 운반 DEV 1회) 무엇이 없는지(최종 환경 단독 cyan, 3대·다중 주문 호스트, 크레이트·tri_frame 어댑터) 라벨로 정리하고, 시나리오 v4 결정(D1–D7)과 가장 짧은 구축 경로(S0–S5)를 적었다. 물리·렌더·모델 호출·pytest 0회, 수치는 모두 추정.
- [2026-10-05 적재 이득·시간상수 보정 v102 (DEV_PILOT, #363 옆 leg 7.2% 과주행)](2026-10-05-loaded-gain-calibration-v102/README.md): 표준 경로 SIM 수집 4건(옆 2·앞뒤 2), 보류 평가 VALIDATED_DEV(최대 오차 옆 0.36%·앞뒤 0.17%). 원인은 게인 곡선(아핀 데드존으로 교체), 지연·접촉 프로필 아님. fcc5215f 입력 재생(14ba8b5e 기준, 미완료): 옆 leg 54.9 -> 1.1 mm, 순수 추측항법 기준과 일부 구간 +5 mm 허용은 미충족. 7194637e 기준 재생·시험은 사용자 중단으로 미완료. #363용 diff 2개와 시험 포함. MEASURED_SIM 아님.
- [2026-10-03 높은 자세 공동 운반 후보 v96](2026-10-03-pair-carry-highpose/README.md): 기존 beam-relative 학생·OpenCV 위치 추정, #361 D5 실측 보정·승인 목록 관문(MEASURED_SIM 승인 비어 있음) + 정확한 sha256 하나만 받는 DEV_PILOT(FUNCTIONAL_DEV, 승격 불가), 중간 HIGH 유지, P03 cap 3×300 SIM초(사전 등록 개정, 하한 63.8/104.2/184.6초)(10/4 v98-cap-3: 3×900, 사용자 결정), grip 감시는 사용자 결정으로 첫 E2E에서 기록 전용(실행 중 놓침 감지·통보 없음, 실제 렌더 영상 테스트), 개발/확증 시작점 분리. v93은 미실행 은퇴.
- [2026-10-05 v98 시뮬레이션 wall 시간 감시와 비트 동일 가속 (DEV 진단, #363)](2026-10-05-sim-walltime-monitor/README.md): 창 단위 감시 장치(선택, 수면 보정 `clock_wall_s`), 가속 세트 `v98-exact-v6` 확정(v1 + PF 기하 공유 + OpenCV 기하 캐시, 오프라인 비트 동일). v1 전 구간 바이트 동일(15324/15328, 허용 목록), 정상 구간 속도 2.91 vs 2.88 wall/SIM(처음 보고한 4.53→2.27은 부하·프로파일러 혼입으로 철회). zsh BG_NICE nice 5 발견, 숨은 물체 분리(B7)는 비트 다름으로 버림.
- [2026-10-05 무하중 이득·시간상수 보정 v101 (DEV_PILOT, #363 PF 계통 오차 고전 보정)](2026-10-05-unloaded-gain-calibration-v101/README.md): 표준 경로 SIM 수집 6건, 적합 2 + 보류 4, 보류 평가 VALIDATED_DEV(이득 1.56/1.10/1.37, 지연 1.01/1.01/0.17 s). 재생에서 C(측정 이득+등록 잡음)가 사전 등록 규칙으로 선택(중앙 오차 r1 3 mm·r2 21 mm, HEAD 그대로 215/196 mm). #363용 diff(C, R1, R2, 통합)와 시험 포함. MEASURED_SIM 아님.
- [2026-10-03 v100 두 로봇 짝 운반 LLM 판단 층 가능성 시험 (배관 단계, 연구 결과 아님)](2026-10-03-pair-llm-viability/README.md): 번들 `zone-pair-llm-v100`(DRAFT_UNSEALED), 가짜 모델 배관과 실제 모델 스모크 1회(v99 기록), 정지 판단 어댑터. 운반 성공·모델 성능 결과 아님(Refs #219)
- [2026-10-03 v92 개발 파일럿 보정 DEV_PILOT_C0_ZERO_v1 (비확증) + B″ v-next 초안](2026-10-03-v92-dev-pilot/README.md): c0=0 고정 재적합, B″ 훈련·PRBS 36/36·퍼짐·쌍 모델 통과, 무하중 통합 프로필 10개 미충족. MEASURED_SIM 아님; 확증은 새 규칙 고정 뒤 재수집.
- [2026-10-03 v92 D5 측정 보정 조립 — PARTIAL](2026-10-03-v92-measured-assembly/README.md): 257953ec 고정 해시 일치, 1회 실행. 31개 미충족 = 무하중 통합 프로필 10(설계상) + 하중 공통 적합 거부(c0 세 축 하한 경계) 16 + 쌍 모델 미평가 5. fine B′·카메라 28자세·팬 통과. 오프라인 보정만.
- [2026-10-03 로봇 자기 카메라 VO 가능성 (#366, 탐색·물리 0회)](2026-10-03-vo-feasibility/README.md): 저장 프레임만 분석. 카메라만 쓰는 VO는 불가(v92 운반 자세 직진 유효율 17%·회전 0–2%, m1 주행 10초 오차 41 cm vs 명령 추측항법 5.4 cm). 명령 추측항법 중심 + VO 보조로 바꾸면 가능. ORB-SLAM3는 의존성 부재·특징점 부족으로 건너뜀.

- [2026-10-03 v92 적재 보정 일정](2026-10-03-v92-loaded-schedule/README.md): D1–D4에 따라 높은 운반 후보에서 loaded 측정, 새 B″·8초 구간 동결; [D2/D5 전용 조립기·HIGH 로더 계약](2026-10-03-v92-loaded-schedule/assembly/README.md), 실제 렌더 수집·인수는 조정자 범위.

- [2026-10-03 v91 빠른 guard·동시 SIM 슬롯](2026-10-03-calib-fast-guard/README.md): v90 일정·물리 보존, 완료 raw 무렌더링 동등성 및 오프라인 CPU 검사; 두 지도 새 수집은 별도.

- [2026-09-30 L0·L1 측면 끝점 모형 재검증 (탐색적 오프라인, 물리 0회, #221)](2026-09-30-l1-lateral-error/README.md): 기존 끝점 1,384개·원본 3,661파일 해시 감사. 배치 중복을 제거한 목표 30조건의 코호트 보류 L1 RMSE 19.08 mm, 60곳 조건부 기대 59.14/60(계수 90% 대역 58.32–59.85). 측면 ×1.5에서는 공유 잔차 가정의 48/60 미달 위험 7.05%. 정상 등록 재생 6/10의 가드 정지는 모형 밖이며 실제 완주율이 아니다. 새 탐색 6건 357.2 SIM초와 최소 가드 재확인 2건 125.6 SIM초 제안, 미실행.
