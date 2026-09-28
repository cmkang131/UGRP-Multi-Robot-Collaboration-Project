# 협동 운반 선행 연구 요약 (v6 검토 3 반영용)

원 보고서: 기본 체크아웃 `outputs/lit-review-coop-transport-20260928.md`(2026-09-28, 코디네이터 요청 조사).
여기에는 v6 정렬·접근 설계에 직접 쓰는 부분만 요약한다. 원문 인용은 하지 않았고, 수치는 보고서가 적은 읽은 범위 그대로다.

## 핵심 결론

- 우리 센서 조건(손목 어안 단안 RGB, 표식·F/T·모캡 없음)에서 두 로봇이 빔을 들고 문을 통과한 선행 연구는 찾지 못했다.
  가장 가까운 사례는 JPL Robot Construction Crew다. 스테레오, fiducial, F/T를 썼다.
- 성공 사례의 파지 전 정렬은 거의 모두 **물체 기준 상대 측정 + 짧게 이동 → 정지 → 재관측 반복**이다.
  전역 위치로 정렬한 사례는 모캡이 있는 실험뿐이다.
- 따라서 정렬 구간은 전역 PF를 중단 조건에서 빼고 참고값으로 기록하는 것이 문헌과 맞다.
  충돌 방지는 정적 지도 keep-out과 빔 기준 추정으로 유지한다.
- 단안 깊이 모호성은 알려진 빔 치수로 줄인다. 빔 축 방향 이동만으로는 깊이 정보를 얻지 못한다.

## 1순위 레시피와 이번 반영 범위

| 단계 | 레시피 | 이번 검토 3에서의 처리 |
|---|---|---|
| 접근 | PF로 빔이 보이는 대기점까지만 간다. 도착은 빔 검출 성공으로 본다. 공분산이 크면 멈추고 둘러본다. | 벽 충돌 검사용 전역 envelope는 유지했다. 대신 이동 거리의 이중 합산을 없앴다. 예정 재관측은 HIGH 복구 예산과 분리해 등록했다. 도착 판정을 빔 검출로 바꾸는 일은 이번 범위 밖이다(남은 작업). |
| 정렬 | 알려진 폭·자기 쪽 빔 끝으로 상대 자세를 구한다. 짧게 이동 → 정지 → 재관측을 반복하고, M2의 두 번 연속 수렴 규칙으로 끝낸다. 끝이 안 보이면 축 방향 이동을 멈추고 팬 스캔으로 다시 찾는다. | 원거리 형상 식별 뒤 전진 전용 소폭 접근(close-in)을 추가했다. 재관측 view 시도 기록은 다중 뷰 창 만료와 relook 뒤에 초기화한다. 정렬 중 PF HIGH는 중단 조건에서 뺐다. 정적 빔 기준 bound(진입 fix + ready 상대 뷰)로 벽·팔 여유를 계속 검사한다. 두 번 연속 수렴 규칙은 그대로다. |
| 동시 파지·들기 | READY/GO 뒤 고정 궤적 파지. 들기는 작은 높이 증분 2–3단계로 나누고 단계마다 READY/GO. | 이번 범위 밖이다. 기존 M2 파지·들기 경로를 바꾸지 않았다. |

## 참고 링크

- Stroupe et al. 2006, JPL Robot Construction Crew: https://www-robotics.jpl.nasa.gov/media/documents/Stroupe_Sustainable06.pdf
- Wang & Schwager 2016, Force-ANTS: https://msl.stanford.edu/papers/wang_force-amplifying_2016.pdf
- Machado et al. 2019, attractor dynamics 공동 운반: https://repositorium.uminho.pt/handle/1822/69728
- Spica et al. 2014, 원통 시각 서보(알려진 치수): https://www.irisa.fr/lagadic/pdf/2014_tro_spica.pdf
- Johns 2021, Coarse-to-Fine 모방(bottleneck 이후 last-inch): https://arxiv.org/abs/2105.06411
- Zhang et al. 2020, 분산 DRL 막대 문 통과(GT 상태·부착 가정): https://arxiv.org/abs/2007.09243
- Krawciw et al. 2026, 다중 로버 화물 운반: https://arxiv.org/html/2510.18766
