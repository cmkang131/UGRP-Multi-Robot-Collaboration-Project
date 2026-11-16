# 한국어 로봇 대화 효율 연구 — 평가 요약

- 생성: 2026-09-27T08:51:15+0900 (평가 전용 사후 분석)
- 시행 수: 30, 시나리오: s1_normal_mixed, s2_unmapped_blockage, s3_late_rendezvous, s4_narrow_door_standoff, s5_moved_dropped_item, s6_novel_relation
- 실패 가중치(PAR): 비성공 시행에 horizon × 2.0를 부과한다. 빠른 실패가 느린 성공보다 좋게 보이지 않는다.
- 선행 발화 탐색 창: 30.0초 (연관이며 인과가 아니다)
- 실행 번들 단일 여부: 아니오 — 혼재 필드: map_file_sha256, order_sheet_sha256, public_map_sha256

이 문서는 저장된 평가 로그만 읽는다. 시뮬레이션·모델 호출을 하지 않았고, 정답·TOP·심판 판정은 로봇 입력으로 되돌리지 않는다.

## 1. 조건별 효율

| 조건 | 시행 | 성공 | 성공률 | PAR makespan(SIM초) | 성공 makespan | 배송률 | 발화 비용(초) | idle(로봇초) | 충돌 | 교착 | 재계획 | 호출 | 토큰 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ① 무통신 | 6 | 0 | 0.000 | 600.0 | — | 0.000 | 0.0 | 232.9 | 0 | 0 | 0 | 68.5 | 545304 |
| ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 600.0 | — | 0.000 | 1.2 | 258.2 | 0 | 0 | 0 | 74.5 | 612578 |
| ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 600.0 | — | 0.000 | 1.6 | 248.6 | 0 | 0 | 0 | 71.5 | 583785 |
| ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 600.0 | — | 0.000 | 1.2 | 259.6 | 0 | 0 | 0 | 74.5 | 620300 |
| R 전지적 지휘 참조 상한 | 6 | 0 | 0.000 | 600.0 | — | 0.000 | 0.0 | 0.0 | 0 | 0 | 0 | 22.8 | 179913 |

PAR makespan은 실패·중단·시간 초과·예산 소진을 분모에 유지한 값이다. 성공 makespan 열은 성공한 시행만의 평균이므로 단독으로 조건을 비교하지 않는다.

## 2. 조건별 대화 지표

| 조건 | 발화 | 전달 edge | 한국어 준수 | 침묵 | 코드전환 | ID 손상 | 사실 | 거짓 | 확인불가 | 사실성 | 채널 위반 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ① 무통신 | 0 | 0 | — | 0 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| ② 자유 한국어 동료 대화 | 18 | 36 | 1.000 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| ③ 한국어 지휘 겸임 | 24 | 24 | 1.000 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| ④ 정형 메시지 대조 | 18 | 36 | — | 0 | 0 | 0 | 0 | 0 | 0 | — | 0 |
| R 전지적 지휘 참조 상한 | 0 | 0 | — | 0 | 0 | 0 | 0 | 0 | 0 | — | 0 |

한국어 준수는 literal ID·enum을 제외한 한글 비율이 0.9 이상인 발화의 비율이다. 침묵은 준수 성공으로 세지 않는다. 사실성은 발화 시각의 평가 로그와 대조한 결과이며 확인불가는 실패로 바꾸지 않는다.

### 행위 유형

| 조건 | order | report | request |
|---|---:|---:|---:|
| ① 무통신 | 0 | 0 | 0 |
| ② 자유 한국어 동료 대화 | 0 | 18 | 0 |
| ③ 한국어 지휘 겸임 | 12 | 24 | 0 |
| ④ 정형 메시지 대조 | 0 | 0 | 18 |
| R 전지적 지휘 참조 상한 | 0 | 0 | 0 |

PR 172(병합)의 세부 규칙 라벨을 재사용하고 지휘 조건용 `order`만 추가했다. 대응 규칙은 `docs/zone_study_metrics.md`에 있다.

### 결정 변경 직전 발화

| 조건 | 결정 변경 | 직전 수신 발화 있음 | 비율 | 선행 발화 행위 |
|---|---:|---:|---:|---|
| ① 무통신 | 0 | 0 | — | — |
| ② 자유 한국어 동료 대화 | 0 | 0 | — | — |
| ③ 한국어 지휘 겸임 | 0 | 0 | — | — |
| ④ 정형 메시지 대조 | 0 | 0 | — | — |
| R 전지적 지휘 참조 상한 | 0 | 0 | — | — |

## 3. 짝지은 seed 비교


**par_makespan_sim_s**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 600.000 | 600.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 600.000 | 600.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 600.000 | 600.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 600.000 | 600.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 600.000 | 600.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 600.000 | 600.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**success**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**delivery_rate**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**idle_robot_s**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 248.600 | 259.600 | 11.000 | [8.283, 13.800] | 2.763 | 1.000 | 6/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 232.950 | 248.600 | 15.650 | [12.833, 18.467] | 3.825 | 1.000 | 6/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 232.950 | 258.250 | 25.300 | [22.400, 28.100] | 6.323 | 1.000 | 6/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 232.950 | 259.600 | 26.650 | [23.000, 30.300] | 4.889 | 1.000 | 6/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 258.250 | 248.600 | -9.650 | [-9.900, -9.450] | -30.670 | -1.000 | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 258.250 | 259.600 | 1.350 | [-1.200, 4.000] | 0.361 | 0.600 | 3/6 |

**conflicts**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**deadlocks**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**replans**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 0.000 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**model_calls**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 71.500 | 74.500 | 3.000 | [3.000, 3.000] | — | 1.000 | 6/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 68.500 | 71.500 | 3.000 | [3.000, 3.000] | — | 1.000 | 6/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 68.500 | 74.500 | 6.000 | [6.000, 6.000] | — | 1.000 | 6/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 68.500 | 74.500 | 6.000 | [6.000, 6.000] | — | 1.000 | 6/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 74.500 | 71.500 | -3.000 | [-3.000, -3.000] | — | -1.000 | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 74.500 | 74.500 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

**tokens_total**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 583785.167 | 620300.500 | 36515.333 | [35400.000, 37865.500] | 21.038 | 1.000 | 6/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 545303.500 | 583785.167 | 38481.667 | [37386.000, 39792.500] | 22.728 | 1.000 | 6/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 545303.500 | 612578.500 | 67275.000 | [65010.000, 70044.000] | 18.972 | 1.000 | 6/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 545303.500 | 620300.500 | 74997.000 | [72786.000, 77658.000] | 21.873 | 1.000 | 6/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 612578.500 | 583785.167 | -28793.333 | [-30228.000, -27624.000] | -15.532 | -1.000 | 0/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 612578.500 | 620300.500 | 7722.000 | [7614.000, 7776.000] | 58.380 | 1.000 | 6/6 |

**talk_sim_cost_s**

| 기준 | 비교 | 짝 | 제외 짝 | 기준 평균 | 비교 평균 | 차이 | 95% 부트스트랩 구간 | dz | rank-biserial | 비교>기준 |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| ③ 한국어 지휘 겸임 | ④ 정형 메시지 대조 | 6 | 0 | 1.600 | 1.200 | -0.400 | [-0.400, -0.400] | — | -1.000 | 0/6 |
| ① 무통신 | ③ 한국어 지휘 겸임 | 6 | 0 | 0.000 | 1.600 | 1.600 | [1.600, 1.600] | — | 1.000 | 6/6 |
| ① 무통신 | ② 자유 한국어 동료 대화 | 6 | 0 | 0.000 | 1.200 | 1.200 | [1.200, 1.200] | — | 1.000 | 6/6 |
| ① 무통신 | ④ 정형 메시지 대조 | 6 | 0 | 0.000 | 1.200 | 1.200 | [1.200, 1.200] | — | 1.000 | 6/6 |
| ② 자유 한국어 동료 대화 | ③ 한국어 지휘 겸임 | 6 | 0 | 1.200 | 1.600 | 0.400 | [0.400, 0.400] | — | 1.000 | 6/6 |
| ② 자유 한국어 동료 대화 | ④ 정형 메시지 대조 | 6 | 0 | 1.200 | 1.200 | 0.000 | [0.000, 0.000] | — | — | 0/6 |

짝 수가 10개 미만인 비교가 있다(짝 [6]). 유의성 검정을 하지 않고 구간과 짝별 표만 읽는다. 차이 부호는 `비교 − 기준`이며 짝별 값은 `metrics.json`에 있다.

## 4. 입력 경계 감사

주 4조건의 모든 시행에서 금지 입력 key·미검증 payload·알 수 없는 입력 key·기록 계약 버전 위반·금지 근거 인용·채널 위반이 없었다.

시행 상태 집계: clean 24, unverified 6

R 조건 6개 시행은 설계상 전지적 참조 상한이며 추가 입력(—)을 받는다. 주 조건 경계 판정에 합산하지 않는다.

## 5. 원본

| 파일 | SHA-256 |
|---|---|
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/leader_ko-s1_normal_mixed-s601.json` | `dbed8214cd394e423477cd60f12b2d24281ddbeaba16569ee56fa0c0fd752396` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/leader_ko-s2_unmapped_blockage-s611.json` | `733b567241160fc9d00d04189f39001d9970c7e155fde4c2ce0070072774a0c3` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/leader_ko-s3_late_rendezvous-s621.json` | `90eab49e17584b12a0881115cf79139188bd18cb154883613f0de9cde99133e1` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/leader_ko-s4_narrow_door_standoff-s631.json` | `0dc855e27ffc0afdc406a654c941dbb4babd5bcfb0c4a8582e9b840863a6dc6a` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/leader_ko-s5_moved_dropped_item-s641.json` | `e5a86edd68a794dc1da2fd385027b6efe4129a3b47340120d8b7cd5c3e62cd91` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/leader_ko-s6_novel_relation-s651.json` | `8654394d9c32ebda1ed4de8ba342a5b318ebb87ec9d76886fa3f31930e31e2da` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/no_comm-s1_normal_mixed-s601.json` | `050f75d25a79f14482393b9951a201699921a25b98a8cf9618958b57dc7709ff` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/no_comm-s2_unmapped_blockage-s611.json` | `18bd78af82726eeb6f6abf356311d3fcd4f939cb83e32fcbacd8b082ca93e6d8` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/no_comm-s3_late_rendezvous-s621.json` | `7062fec575bb955648a3285d527a57f15a84c3cff12f4135b5d399f06b77e5b7` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/no_comm-s4_narrow_door_standoff-s631.json` | `7642d236137139f50a2c0cadc88247bdc2aa9f9ab576e4b050d6d8472a21f5f8` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/no_comm-s5_moved_dropped_item-s641.json` | `27082404d310a23a2b43783b3fbf0057b90ba32962290575eafe9e9e8973bbe2` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/no_comm-s6_novel_relation-s651.json` | `ed10b390e887af2a899740e7bb18c30f2dca4d09a86b43640e894a28d0fe891c` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/peer_ko-s1_normal_mixed-s601.json` | `fa2d0561640280b34eb4eff0bb1361d20b438fa3da7675f171cad67a059d61e3` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/peer_ko-s2_unmapped_blockage-s611.json` | `d91f3e08973903bae17a9b86164966a901cde039cfcc2750a912ec87667c7f5a` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/peer_ko-s3_late_rendezvous-s621.json` | `809fb3d8a3e92cadad165534cf93a1fb2ca8399185e7e3fb3f9d1b94d46513ad` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/peer_ko-s4_narrow_door_standoff-s631.json` | `7fcfe07bc931b598d0c47d3a757f371ec15a6193572d6fdaf5759fd18e4a5830` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/peer_ko-s5_moved_dropped_item-s641.json` | `6b4de35eb8af5f705523b458ca9599fb6616d25314a387425226b210d0bdb9e3` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/peer_ko-s6_novel_relation-s651.json` | `e5b71ac3649aae1de8cd8e4e82f9e0fd50682da3feab70b67f30e3070a6ad84b` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/reference_R-s1_normal_mixed-s601.json` | `756d28e7e33b859735c6cc869a18f278fa607cec1ccbd75d5a78761509f2390b` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/reference_R-s2_unmapped_blockage-s611.json` | `5e0878098323121ae02a7d904a0fbc422b0a99ee6521a707a20d08677a28d52f` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/reference_R-s3_late_rendezvous-s621.json` | `246ba4d4ad1b7c0dbed01672dd60a05369c9508343e1a81ed98967115e898816` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/reference_R-s4_narrow_door_standoff-s631.json` | `cecae541222754b16bbc0ab8d0f4288ab4b8a6783d2603fec438c1e03a3fe3f4` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/reference_R-s5_moved_dropped_item-s641.json` | `11fd4e80eaeff5426b93ce993831362f2eef04b816a3bf41fd8b5f043ef5a59b` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/reference_R-s6_novel_relation-s651.json` | `8dafdaa113b66f00a040ee9ab634508eeee40e85abb5d46561a20caf36796f7a` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/structured-s1_normal_mixed-s601.json` | `aad9262698e8ba317ea84547f28df47439b9943c2d3227bfacc83d6314482607` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/structured-s2_unmapped_blockage-s611.json` | `62c6d9ba7def740735bbfc65b8414fe78bee4bf8afefaeb7671cc3e8335bd3a6` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/structured-s3_late_rendezvous-s621.json` | `f9012f4c752801cacb918ee6c146e66245fabed1937495b2e4c7640b56c38e09` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/structured-s4_narrow_door_standoff-s631.json` | `862337e2367d737c53989acccd95abc219ea048eda131f712d94a1d51881e12e` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/structured-s5_moved_dropped_item-s641.json` | `bdcd8d44209909bb7bde09b148b1df5995c4400cd34d721a6a8a05900f60dc80` |
| `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/trial_records/structured-s6_novel_relation-s651.json` | `8b4ece94300793af0a47c357fd036907ada893c254f4f65663a02e82c34793ef` |

## 6. 남은 검증

- 이 보고서는 지표 계산의 정확성만 확인한다. 조건 간 우열은 사전 고정한 코호트를 실제로 실행한 뒤에만 주장한다.
- 로그 schema는 Package A(`harness/zone_study_contract.py`)가 소유한다. `ugrp.zone_study_trial.v1`는 A의 호출·메시지·행동 기록을 담고 A가 검증한다. 과거 파일럿 로그를 위해 `ugrp.zone_study_trial.provisional.v1`도 계속 읽는다.
