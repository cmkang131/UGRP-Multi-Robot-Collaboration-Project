# 원본 소스의 noslip 참조 분포

기준 SHA `c8dc1e6545124ed69a996618bd11df684d233969`. 정적 참조 수이며 물리 실패 분포가 아니다. 물리 실행/실패 분석은 이 작업 범위 밖이다.

| 범주 | 참조 행 수 |
|---|---:|
| scripts | 208 |
| configs | 78 |
| sim | 24 |
| harness | 22 |

재현: `git grep -n -i noslip c8dc1e6545124ed69a996618bd11df684d233969 -- sim harness scripts configs`. 원본 목록은 `baseline_noslip_refs.txt`.
