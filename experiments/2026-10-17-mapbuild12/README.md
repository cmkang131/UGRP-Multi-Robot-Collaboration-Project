# mapbuild12 — 자기 점유 지도와 AMCL 보강(진행 중)

같은6.461m 녹화/내려놓기418뷰의 원본 VM CPU 재생만 수행한다. 새물리0.
초기 거부 분포는 [prior-rejection_table.json](prior-rejection_table.json).
위치 정답은 예측 봉인 뒤 평가만 사용한다. 자기 지도는 정적 AMCL 미자격
제안에 조건부이며 입자별 지도나 완전 SLAM posterior가 아니다. 기본off
`selfmap_own_grid_v1`은 이전 프레임까지 쌓인 포화점유 셀을 정적 거리장과
합집합으로 보강해 기존 Nav2 likelihood를 한 번만 사용한다. 별도 독립
측정처럼 두 likelihood를 곱하지 않는다. 현재 scan 삽입은 측정 뒤다.

## 참고 자료와 고정 상수

- [Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/) 9장 log-odds 점유격자 재귀식. 출판사 서지 확인; 책 전체 신규 열람 주장은 아니다.
- [Cartographer 공식2D 설정](https://github.com/cartographer-project/cartographer/blob/master/configuration_files/trajectory_builder_2d.lua): 해상도.05m, hit.55/miss.49, 자유공간삽입. 상수를 그대로 사용하며 GT맞춤0.
- [확률값 범위](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/probability_values.h): .1–.9. 보강셀은 포화.9+최소ceil(logit(.9)/logit(.55))=11개 서로 다른 프레임hit. 이는 이번 후보의 파생 자격정책이며 upstream AMCL 기본 문턱은 아니다. 연속RGB 관측 독립성을 보장하지 않는다.
- [공식 삽입기](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/2d/probability_grid_range_data_inserter_2d.cc): hit우선/셀당 프레임1표. 기존 Amanatides–Woo DDA를 재사용했다. 미관측 방위를 최대거리free로 만들지 않는다. 관측은 기존 자기벽 가상scan이며 일반화된 물체검출은 확인 안 됨.
- [Cartographer pure localization](https://google-cartographer-ros.readthedocs.io/en/latest/tuning.html#pure-localization-in-a-given-map): 고정지도와 새 submap의 제약. 고정 정적지도를 보존하는 근거이며, 이 문헌이 이번 AMCL 합집합 정책의 정확성을 보장하는 것은 아니다. Cartographer 전체 이식·pose graph·loop closure를 구현했다고 주장하지 않는다.
- 위 Cartographer 소스는 Apache2.0. 알고리즘/설정값을 참고한 독립 log-odds 구현이며 C++코드를 vendor하지 않았다. 기존 Nav2 vendor LGPL고지는 유지한다.
