# 초안 표본 계획의 검정력 계산

2026-10-06. [사전 등록 초안](PREREG_DRAFT.md) §6–7의 **계획 계산**이다. 실제 연구 결과·파일럿 추정·시뮬레이션이 아니다. source/bundle/model hash를 고정하지 않는다.

## 가정과 계산

- 주 비교 하나: peer_nl − no_comm의 PAR-2, 양측 α=0.05, 목표 power=0.80.
- N은 세 조건을 포함한 독립 블록 수. 8개 고정 시나리오마다 m=N/8블록. 같은 블록의 두 조건 차이를 분석한다.
- 계획상 모든 층에서 짝 차이는 독립 정규분포·같은 SD를 가진다고 가정한다. 시나리오별 평균은 달라도 된다. 이때 층화 SE는 pooled SD/√N, 자유도는 N−8이고 비중앙성은 `d_z*sqrt(N)`이다.
- 실제 분석은 층별 분산이 다를 수 있어 Welch–Satterthwaite 근사를 사용한다. 아래는 공통 분산 특수 경우의 검정력이며 실패 벌점이 많이 쌓이는 분포의 검정력을 보장하지 않는다.
- 실용 차이 후보 180초와 짝 차이 SD 가정 720초에서 d_z=0.25. **720초는 관측값이 아니다.** 동일 180초라도 SD=900이면 d_z=0.20, SD=1200이면 d_z=0.15가 되어 표본이 더 필요하다. paired SD를 쓰므로 조건 사이 상관을 따로 가정하거나 두 번 반영하지 않는다.

`c = t.ppf(0.975, N−8)`일 때:

```text
power = P(T_nct < −c) + P(T_nct > c)
T_nct ~ noncentral_t(df=N−8, nc=d_z*sqrt(N))
```

조건 순서를 균형 배정하려면 m이 6의 배수여야 하므로 N은 48의 배수다. d_z=.25에서 8의 배수로는 N=128이 처음 80%를 넘고, 6순서 균형으로 올린 N=144를 제안한다. p값을 보면서 늘리는 순차 계획이 아니다.

| d_z | 80% 이상 최소 N (8의 배수) | 80% 이상 최소 N (48의 배수) | N=144 power |
|---:|---:|---:|---:|
| .15 | 352 | 384 | .431542 |
| .20 | 200 | 240 | .663881 |
| .25 | 128 | 144 | .845848 |
| .30 | 96 | 96 | .946790 |
| .40 | 56 | 96 | .997491 |

H1 외 성공률·시나리오별 분석·17개 보조 검정은 이 검정력의 대상이 아니다. 본 연구에서 새 seed가 좌표를 새로 만드는 것은 아니므로 고정 시나리오 밖의 일반화 검정력으로도 읽지 않는다.

## 재현 코드와 확인 결과

기존 Mac 환경의 Python **3.12.13**, SciPy **1.17.1**로 아래 산술만 실행했다. 프로젝트 모듈·MuJoCo·모델 클라이언트를 import하지 않는다. 무작위 표본을 생성하지 않는다. 문서 전용 PR이므로 실행 코드는 Markdown 안에만 둔다.

```python
import math
from scipy.stats import t, nct

def power(n, d):
    df = n - 8
    critical = t.ppf(0.975, df)
    nc = d * math.sqrt(n)
    return float(nct.cdf(-critical, df, nc) + nct.sf(critical, df, nc))

for d in (0.15, 0.20, 0.25, 0.30, 0.40):
    n8 = next(n for n in range(16, 2001, 8) if power(n, d) >= 0.8)
    n48 = next(n for n in range(48, 2017, 48) if power(n, d) >= 0.8)
    print(f"{d:.2f} {n8} {n48} {power(144, d):.6f}")

assert abs(power(144, 0) - 0.05) < 1e-12
assert abs(power(144, 0.25) - 0.845848) < 5e-7
assert 8 * 18 == 144 and 144 * 3 == 432
assert 144 * 2 * 90 == 25920
assert 432 * 1800 / 3600 == 216
```

출력:

```text
0.15 352 384 0.431542
0.20 200 240 0.663881
0.25 128 144 0.845848
0.30 96 96 0.946790
0.40 56 96 0.997491
```

이 값은 분석적 꼬리 확률 계산이다. 검정력 표를 맞췄다는 사실과 등록 준비·실제 로봇 완주는 별개의 검증이다. 참고: [Lakens (2022), 표본 크기 근거](https://online.ucpress.edu/collabra/article/8/1/33267/120491/Sample-Size-Justification), [SciPy nct](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html).
