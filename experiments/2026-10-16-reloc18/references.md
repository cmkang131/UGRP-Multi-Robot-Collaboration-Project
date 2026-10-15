# 방법·출처·미확인 범위

- [Piché, Online tests of Kalman filter consistency, DOI 10.1002/acs.2571](https://onlinelibrary.wiley.com/doi/10.1002/acs.2571): 출판사 초록 확인. NIS로 예측 관측과 실제 관측의 정합성을 평가하며 온라인 평가에 정답이 필요 없다는 설명 확인. 전체 유료 본문의 식·가정은 **미확인**.
- Bar-Shalom, Li, Kirubarajan, *Estimation with Applications to Navigation and Tracking*, Wiley 2001: 서지사항을 아래 논문 참고문헌에서 확인. 책 본문·정확한 절 번호는 **미확인**.
- [Chen 등, Kalman Filter Auto-tuning through Enforcing Chi-Squared Normalized Error Distributions with Bayesian Optimization](https://arxiv.org/pdf/2306.07225): NIS/NEES 분포 기반 Q/R 조정과 χ² 시험만으로 올바른 튜닝을 보장할 수 없다는 범위를 확인. 우리 실험은 Bayesian optimization을 실행하지 않는다.
- [Nav2 AMCL 공식 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/): sigma_hit는 hit Gaussian의 표준편차, z_hit/z_rand는 혼합 가중치이며 사용 가중치 합은 1이다. update_min_d/a는 갱신을 요구하는 이동량이다. 기본 sigma_hit=.2 m를 RGB의 pose 표준편차로 그대로 쓰는 근거는 없다. RGB 원본 잔차에서 별도로 공분산을 맞췄다. AMCL 관측 원시 특징별 파라미터 전체 재최적화는 **미실행**.

사용한 식은 ν=q−p(yaw wrap), S=P+R, d²=νᵀS⁻¹ν,
K=PS⁻¹, x⁺=p+Kν, Joseph P⁺=(I−K)P(I−K)ᵀ+KRKᵀ다.
pose의 x/y/yaw 세 성분 관측이므로 자유도 3, 유의수준 .01(기존 99% 관측 관문과 일치)을
선택해 scipy.stats.chi2.ppf(.99,3)=11.344866730144373을 쓴다.
정규·독립 가정에서만 명목 1% 진짜 관측 거부율이라는 뜻이며 오수용률 보장이 아니다.

원본 두 DEV 시드의 모든 새 PF 후보(초기 미등록 후보 포함, 정답으로 이상치 제거 안 함)의
성분별 절대 잔차 p95 / Φ⁻¹(.975)를 대각 R 바닥으로 사용한다.
명령 적분의 초기 평가 정렬 뒤 오차/√SIM초의 p95로 Q/SIM초를 맞춘다.
이 값은 이미 본 두 시드의 탐색 보정이고 가우스성·독립성·새 시드 성능 보장은 **미확인**이다.
연속 PF posterior 잔차의 첫 양수 자기상관 합으로 추정한 시간만큼 관측을 솎는다.
이는 반복 융합 완화용 설계이며 완전한 독립성은 **미확인**이다.

근거리 파지 경로·place 판정 조건·카메라·물리·질감은 바꾸지 않는다.
