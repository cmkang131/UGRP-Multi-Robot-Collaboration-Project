| cohort | mode | n | B true/false | B distance/time median | coverage | collisions | wrong/door attempts |
|---|---|---:|---:|---|---:|---:|---:|
| seen_before_noisy | static_map | 32 | 0/0 | N/A | 15.84% | 31 | 0/0 |
| seen_before_noisy | own_frontier | 32 | 0/0 | N/A | 15.11% | 13 | 0/0 |
| seen_before_oracle | static_map | 32 | 20/0 | 4.816 m / 140.0 s | 40.32% | 12 | 0/36 |
| seen_before_oracle | own_frontier | 32 | 0/0 | N/A | 22.51% | 0 | 0/0 |
| seen_envfix_noisy | static_map | 32 | 0/0 | N/A | 17.11% | 31 | 0/0 |
| seen_envfix_noisy | own_frontier | 32 | 0/0 | N/A | 15.11% | 13 | 0/0 |
| seen_envfix_oracle | static_map | 32 | 20/0 | 4.816 m / 140.0 s | 40.32% | 12 | 0/36 |
| seen_envfix_oracle | own_frontier | 32 | 0/0 | N/A | 22.51% | 0 | 0/0 |
| development_v2_noisy | static_map | 16 | 0/0 | N/A | 47.89% | 12 | 0/4 |
| development_v2_noisy | own_frontier | 16 | 1/0 | 33.507 m / 134.0 s | 20.42% | 14 | 0/5 |
| development_v2_oracle | static_map | 16 | 11/0 | 2.786 m / 80.0 s | 21.62% | 4 | 0/14 |
| development_v2_oracle | own_frontier | 16 | 4/0 | 3.620 m / 105.5 s | 18.94% | 1 | 0/0 |
| fresh_v2_noisy | static_map | 32 | 0/0 | N/A | 23.47% | 24 | 1/2 |
| fresh_v2_noisy | own_frontier | 32 | 0/0 | N/A | 27.39% | 26 | 0/0 |
| fresh_v2_oracle | static_map | 32 | 8/0 | 6.061 m / 263.0 s | 25.34% | 8 | 0/12 |
| fresh_v2_oracle | own_frontier | 32 | 0/0 | N/A | 14.81% | 0 | 0/0 |

Modeled time; failed first-B values stay N/A. Cohorts are not pooled.
Door counts use issued_translation_v2 post-hoc scoring. Raw pre-command plan counters are preserved separately in summary/results.

| cohort | scenario | start | seed | mode | status | B distance/time | coverage | collision | wrong/doors |
|---|---|---|---:|---|---|---|---:|---:|---:|
| seen_before_noisy | s1 | B | 2701 | static_map | collision | N/A | 9.13% | 1 | 0/0 |
| seen_before_noisy | s1 | B | 2701 | own_frontier | collision | N/A | 8.16% | 1 | 0/0 |
| seen_before_noisy | s1 | B | 2702 | static_map | collision | N/A | 8.99% | 1 | 0/0 |
| seen_before_noisy | s1 | B | 2702 | own_frontier | search_exhausted | N/A | 8.58% | 0 | 0/0 |
| seen_before_noisy | s1 | D | 2701 | static_map | collision | N/A | 9.13% | 1 | 0/0 |
| seen_before_noisy | s1 | D | 2701 | own_frontier | collision | N/A | 9.27% | 1 | 0/0 |
| seen_before_noisy | s1 | D | 2702 | static_map | collision | N/A | 9.31% | 1 | 0/0 |
| seen_before_noisy | s1 | D | 2702 | own_frontier | collision | N/A | 25.52% | 1 | 0/0 |
| seen_before_noisy | s2 | B | 2701 | static_map | collision | N/A | 13.97% | 1 | 0/0 |
| seen_before_noisy | s2 | B | 2701 | own_frontier | collision | N/A | 12.33% | 1 | 0/0 |
| seen_before_noisy | s2 | B | 2702 | static_map | collision | N/A | 13.90% | 1 | 0/0 |
| seen_before_noisy | s2 | B | 2702 | own_frontier | search_exhausted | N/A | 12.68% | 0 | 0/0 |
| seen_before_noisy | s2 | D | 2701 | static_map | collision | N/A | 32.70% | 1 | 0/0 |
| seen_before_noisy | s2 | D | 2701 | own_frontier | search_exhausted | N/A | 49.20% | 0 | 0/0 |
| seen_before_noisy | s2 | D | 2702 | static_map | collision | N/A | 17.06% | 1 | 0/0 |
| seen_before_noisy | s2 | D | 2702 | own_frontier | search_exhausted | N/A | 54.13% | 0 | 0/0 |
| seen_before_noisy | s3 | B | 2701 | static_map | collision | N/A | 12.50% | 1 | 0/0 |
| seen_before_noisy | s3 | B | 2701 | own_frontier | collision | N/A | 8.92% | 1 | 0/0 |
| seen_before_noisy | s3 | B | 2702 | static_map | collision | N/A | 9.48% | 1 | 0/0 |
| seen_before_noisy | s3 | B | 2702 | own_frontier | search_exhausted | N/A | 9.27% | 0 | 0/0 |
| seen_before_noisy | s3 | D | 2701 | static_map | collision | N/A | 26.11% | 1 | 0/0 |
| seen_before_noisy | s3 | D | 2701 | own_frontier | search_exhausted | N/A | 46.35% | 0 | 0/0 |
| seen_before_noisy | s3 | D | 2702 | static_map | collision | N/A | 14.48% | 1 | 0/0 |
| seen_before_noisy | s3 | D | 2702 | own_frontier | search_exhausted | N/A | 51.63% | 0 | 0/0 |
| seen_before_noisy | s4 | B | 2701 | static_map | budget | N/A | 52.71% | 0 | 0/0 |
| seen_before_noisy | s4 | B | 2701 | own_frontier | collision | N/A | 12.25% | 1 | 0/0 |
| seen_before_noisy | s4 | B | 2702 | static_map | collision | N/A | 31.07% | 1 | 0/0 |
| seen_before_noisy | s4 | B | 2702 | own_frontier | search_exhausted | N/A | 12.67% | 0 | 0/0 |
| seen_before_noisy | s4 | D | 2701 | static_map | collision | N/A | 10.13% | 1 | 0/0 |
| seen_before_noisy | s4 | D | 2701 | own_frontier | collision | N/A | 9.43% | 1 | 0/0 |
| seen_before_noisy | s4 | D | 2702 | static_map | collision | N/A | 13.05% | 1 | 0/0 |
| seen_before_noisy | s4 | D | 2702 | own_frontier | collision | N/A | 26.41% | 1 | 0/0 |
| seen_before_noisy | s5 | B | 2701 | static_map | collision | N/A | 32.22% | 1 | 0/0 |
| seen_before_noisy | s5 | B | 2701 | own_frontier | collision | N/A | 14.76% | 1 | 0/0 |
| seen_before_noisy | s5 | B | 2702 | static_map | collision | N/A | 30.03% | 1 | 0/0 |
| seen_before_noisy | s5 | B | 2702 | own_frontier | search_exhausted | N/A | 15.10% | 0 | 0/0 |
| seen_before_noisy | s5 | D | 2701 | static_map | collision | N/A | 32.85% | 1 | 0/0 |
| seen_before_noisy | s5 | D | 2701 | own_frontier | search_exhausted | N/A | 49.55% | 0 | 0/0 |
| seen_before_noisy | s5 | D | 2702 | static_map | collision | N/A | 17.15% | 1 | 0/0 |
| seen_before_noisy | s5 | D | 2702 | own_frontier | search_exhausted | N/A | 54.72% | 0 | 0/0 |
| seen_before_noisy | s6 | B | 2701 | static_map | collision | N/A | 28.31% | 1 | 0/0 |
| seen_before_noisy | s6 | B | 2701 | own_frontier | collision | N/A | 14.76% | 1 | 0/0 |
| seen_before_noisy | s6 | B | 2702 | static_map | collision | N/A | 44.60% | 1 | 0/0 |
| seen_before_noisy | s6 | B | 2702 | own_frontier | search_exhausted | N/A | 15.11% | 0 | 0/0 |
| seen_before_noisy | s6 | D | 2701 | static_map | collision | N/A | 14.07% | 1 | 0/0 |
| seen_before_noisy | s6 | D | 2701 | own_frontier | search_exhausted | N/A | 48.63% | 0 | 0/0 |
| seen_before_noisy | s6 | D | 2702 | static_map | collision | N/A | 17.16% | 1 | 0/0 |
| seen_before_noisy | s6 | D | 2702 | own_frontier | search_exhausted | N/A | 53.14% | 0 | 0/0 |
| seen_before_noisy | s7 | B | 2701 | static_map | collision | N/A | 20.74% | 1 | 0/0 |
| seen_before_noisy | s7 | B | 2701 | own_frontier | collision | N/A | 14.89% | 1 | 0/0 |
| seen_before_noisy | s7 | B | 2702 | static_map | collision | N/A | 15.91% | 1 | 0/0 |
| seen_before_noisy | s7 | B | 2702 | own_frontier | search_exhausted | N/A | 15.24% | 0 | 0/0 |
| seen_before_noisy | s7 | D | 2701 | static_map | collision | N/A | 31.15% | 1 | 0/0 |
| seen_before_noisy | s7 | D | 2701 | own_frontier | search_exhausted | N/A | 47.76% | 0 | 0/0 |
| seen_before_noisy | s7 | D | 2702 | static_map | collision | N/A | 17.24% | 1 | 0/0 |
| seen_before_noisy | s7 | D | 2702 | own_frontier | search_exhausted | N/A | 52.56% | 0 | 0/0 |
| seen_before_noisy | s8 | B | 2701 | static_map | collision | N/A | 13.63% | 1 | 0/0 |
| seen_before_noisy | s8 | B | 2701 | own_frontier | collision | N/A | 11.85% | 1 | 0/0 |
| seen_before_noisy | s8 | B | 2702 | static_map | collision | N/A | 13.46% | 1 | 0/0 |
| seen_before_noisy | s8 | B | 2702 | own_frontier | search_exhausted | N/A | 12.20% | 0 | 0/0 |
| seen_before_noisy | s8 | D | 2701 | static_map | collision | N/A | 10.30% | 1 | 0/0 |
| seen_before_noisy | s8 | D | 2701 | own_frontier | collision | N/A | 41.08% | 1 | 0/0 |
| seen_before_noisy | s8 | D | 2702 | static_map | collision | N/A | 15.77% | 1 | 0/0 |
| seen_before_noisy | s8 | D | 2702 | own_frontier | search_exhausted | N/A | 52.12% | 0 | 0/0 |
| seen_before_oracle | s1 | B | 2701 | static_map | collision | N/A | 8.68% | 1 | 0/0 |
| seen_before_oracle | s1 | B | 2701 | own_frontier | search_exhausted | N/A | 8.78% | 0 | 0/0 |
| seen_before_oracle | s1 | B | 2702 | static_map | collision | N/A | 8.68% | 1 | 0/0 |
| seen_before_oracle | s1 | B | 2702 | own_frontier | search_exhausted | N/A | 8.78% | 0 | 0/0 |
| seen_before_oracle | s1 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 42.53% | 0 | 0/2 |
| seen_before_oracle | s1 | D | 2701 | own_frontier | search_exhausted | N/A | 35.07% | 0 | 0/0 |
| seen_before_oracle | s1 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 42.53% | 0 | 0/2 |
| seen_before_oracle | s1 | D | 2702 | own_frontier | search_exhausted | N/A | 35.07% | 0 | 0/0 |
| seen_before_oracle | s2 | B | 2701 | static_map | collision | N/A | 14.00% | 1 | 0/0 |
| seen_before_oracle | s2 | B | 2701 | own_frontier | search_exhausted | N/A | 12.93% | 0 | 0/0 |
| seen_before_oracle | s2 | B | 2702 | static_map | collision | N/A | 14.00% | 1 | 0/0 |
| seen_before_oracle | s2 | B | 2702 | own_frontier | search_exhausted | N/A | 12.93% | 0 | 0/0 |
| seen_before_oracle | s2 | D | 2701 | static_map | collision | N/A | 23.84% | 1 | 0/2 |
| seen_before_oracle | s2 | D | 2701 | own_frontier | search_exhausted | N/A | 50.03% | 0 | 0/0 |
| seen_before_oracle | s2 | D | 2702 | static_map | collision | N/A | 23.84% | 1 | 0/2 |
| seen_before_oracle | s2 | D | 2702 | own_frontier | search_exhausted | N/A | 50.03% | 0 | 0/0 |
| seen_before_oracle | s3 | B | 2701 | static_map | collision | N/A | 8.75% | 1 | 0/0 |
| seen_before_oracle | s3 | B | 2701 | own_frontier | search_exhausted | N/A | 9.51% | 0 | 0/0 |
| seen_before_oracle | s3 | B | 2702 | static_map | collision | N/A | 8.75% | 1 | 0/0 |
| seen_before_oracle | s3 | B | 2702 | own_frontier | search_exhausted | N/A | 9.51% | 0 | 0/0 |
| seen_before_oracle | s3 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 41.70% | 0 | 0/2 |
| seen_before_oracle | s3 | D | 2701 | own_frontier | search_exhausted | N/A | 47.57% | 0 | 0/0 |
| seen_before_oracle | s3 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 41.70% | 0 | 0/2 |
| seen_before_oracle | s3 | D | 2702 | own_frontier | search_exhausted | N/A | 47.57% | 0 | 0/0 |
| seen_before_oracle | s4 | B | 2701 | static_map | B_confirmed | 7.266 m / 215.0 s | 24.46% | 0 | 0/2 |
| seen_before_oracle | s4 | B | 2701 | own_frontier | search_exhausted | N/A | 12.87% | 0 | 0/0 |
| seen_before_oracle | s4 | B | 2702 | static_map | B_confirmed | 7.266 m / 215.0 s | 24.46% | 0 | 0/2 |
| seen_before_oracle | s4 | B | 2702 | own_frontier | search_exhausted | N/A | 12.87% | 0 | 0/0 |
| seen_before_oracle | s4 | D | 2701 | static_map | B_confirmed | 6.084 m / 188.0 s | 43.18% | 0 | 0/2 |
| seen_before_oracle | s4 | D | 2701 | own_frontier | search_exhausted | N/A | 29.54% | 0 | 0/0 |
| seen_before_oracle | s4 | D | 2702 | static_map | B_confirmed | 6.084 m / 188.0 s | 43.18% | 0 | 0/2 |
| seen_before_oracle | s4 | D | 2702 | own_frontier | search_exhausted | N/A | 29.54% | 0 | 0/0 |
| seen_before_oracle | s5 | B | 2701 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.31% | 0 | 0/0 |
| seen_before_oracle | s5 | B | 2701 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_before_oracle | s5 | B | 2702 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.31% | 0 | 0/0 |
| seen_before_oracle | s5 | B | 2702 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_before_oracle | s5 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 43.85% | 0 | 0/2 |
| seen_before_oracle | s5 | D | 2701 | own_frontier | search_exhausted | N/A | 51.01% | 0 | 0/0 |
| seen_before_oracle | s5 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 43.85% | 0 | 0/2 |
| seen_before_oracle | s5 | D | 2702 | own_frontier | search_exhausted | N/A | 51.01% | 0 | 0/0 |
| seen_before_oracle | s6 | B | 2701 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.33% | 0 | 0/0 |
| seen_before_oracle | s6 | B | 2701 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_before_oracle | s6 | B | 2702 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.33% | 0 | 0/0 |
| seen_before_oracle | s6 | B | 2702 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_before_oracle | s6 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 47.83% | 0 | 0/2 |
| seen_before_oracle | s6 | D | 2701 | own_frontier | search_exhausted | N/A | 48.98% | 0 | 0/0 |
| seen_before_oracle | s6 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 47.83% | 0 | 0/2 |
| seen_before_oracle | s6 | D | 2702 | own_frontier | search_exhausted | N/A | 48.98% | 0 | 0/0 |
| seen_before_oracle | s7 | B | 2701 | static_map | collision | N/A | 17.24% | 1 | 0/0 |
| seen_before_oracle | s7 | B | 2701 | own_frontier | search_exhausted | N/A | 15.49% | 0 | 0/0 |
| seen_before_oracle | s7 | B | 2702 | static_map | collision | N/A | 17.24% | 1 | 0/0 |
| seen_before_oracle | s7 | B | 2702 | own_frontier | search_exhausted | N/A | 15.49% | 0 | 0/0 |
| seen_before_oracle | s7 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.23% | 0 | 0/2 |
| seen_before_oracle | s7 | D | 2701 | own_frontier | search_exhausted | N/A | 49.02% | 0 | 0/0 |
| seen_before_oracle | s7 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.23% | 0 | 0/2 |
| seen_before_oracle | s7 | D | 2702 | own_frontier | search_exhausted | N/A | 49.02% | 0 | 0/0 |
| seen_before_oracle | s8 | B | 2701 | static_map | collision | N/A | 13.74% | 1 | 0/0 |
| seen_before_oracle | s8 | B | 2701 | own_frontier | search_exhausted | N/A | 12.44% | 0 | 0/0 |
| seen_before_oracle | s8 | B | 2702 | static_map | collision | N/A | 13.74% | 1 | 0/0 |
| seen_before_oracle | s8 | B | 2702 | own_frontier | search_exhausted | N/A | 12.44% | 0 | 0/0 |
| seen_before_oracle | s8 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.25% | 0 | 0/2 |
| seen_before_oracle | s8 | D | 2701 | own_frontier | search_exhausted | N/A | 47.53% | 0 | 0/0 |
| seen_before_oracle | s8 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.25% | 0 | 0/2 |
| seen_before_oracle | s8 | D | 2702 | own_frontier | search_exhausted | N/A | 47.53% | 0 | 0/0 |
| seen_envfix_noisy | s1 | B | 2701 | static_map | collision | N/A | 13.85% | 1 | 0/0 |
| seen_envfix_noisy | s1 | B | 2701 | own_frontier | collision | N/A | 8.16% | 1 | 0/0 |
| seen_envfix_noisy | s1 | B | 2702 | static_map | collision | N/A | 8.99% | 1 | 0/0 |
| seen_envfix_noisy | s1 | B | 2702 | own_frontier | search_exhausted | N/A | 8.58% | 0 | 0/0 |
| seen_envfix_noisy | s1 | D | 2701 | static_map | collision | N/A | 9.13% | 1 | 0/0 |
| seen_envfix_noisy | s1 | D | 2701 | own_frontier | collision | N/A | 9.27% | 1 | 0/0 |
| seen_envfix_noisy | s1 | D | 2702 | static_map | collision | N/A | 9.31% | 1 | 0/0 |
| seen_envfix_noisy | s1 | D | 2702 | own_frontier | collision | N/A | 25.52% | 1 | 0/0 |
| seen_envfix_noisy | s2 | B | 2701 | static_map | collision | N/A | 19.46% | 1 | 0/0 |
| seen_envfix_noisy | s2 | B | 2701 | own_frontier | collision | N/A | 12.33% | 1 | 0/0 |
| seen_envfix_noisy | s2 | B | 2702 | static_map | collision | N/A | 13.90% | 1 | 0/0 |
| seen_envfix_noisy | s2 | B | 2702 | own_frontier | search_exhausted | N/A | 12.68% | 0 | 0/0 |
| seen_envfix_noisy | s2 | D | 2701 | static_map | collision | N/A | 32.70% | 1 | 0/0 |
| seen_envfix_noisy | s2 | D | 2701 | own_frontier | search_exhausted | N/A | 49.20% | 0 | 0/0 |
| seen_envfix_noisy | s2 | D | 2702 | static_map | collision | N/A | 17.06% | 1 | 0/0 |
| seen_envfix_noisy | s2 | D | 2702 | own_frontier | search_exhausted | N/A | 54.13% | 0 | 0/0 |
| seen_envfix_noisy | s3 | B | 2701 | static_map | collision | N/A | 12.50% | 1 | 0/0 |
| seen_envfix_noisy | s3 | B | 2701 | own_frontier | collision | N/A | 8.92% | 1 | 0/0 |
| seen_envfix_noisy | s3 | B | 2702 | static_map | collision | N/A | 9.48% | 1 | 0/0 |
| seen_envfix_noisy | s3 | B | 2702 | own_frontier | search_exhausted | N/A | 9.27% | 0 | 0/0 |
| seen_envfix_noisy | s3 | D | 2701 | static_map | collision | N/A | 31.94% | 1 | 0/0 |
| seen_envfix_noisy | s3 | D | 2701 | own_frontier | search_exhausted | N/A | 46.35% | 0 | 0/0 |
| seen_envfix_noisy | s3 | D | 2702 | static_map | collision | N/A | 14.48% | 1 | 0/0 |
| seen_envfix_noisy | s3 | D | 2702 | own_frontier | search_exhausted | N/A | 51.63% | 0 | 0/0 |
| seen_envfix_noisy | s4 | B | 2701 | static_map | budget | N/A | 52.71% | 0 | 0/0 |
| seen_envfix_noisy | s4 | B | 2701 | own_frontier | collision | N/A | 12.25% | 1 | 0/0 |
| seen_envfix_noisy | s4 | B | 2702 | static_map | collision | N/A | 31.07% | 1 | 0/0 |
| seen_envfix_noisy | s4 | B | 2702 | own_frontier | search_exhausted | N/A | 12.67% | 0 | 0/0 |
| seen_envfix_noisy | s4 | D | 2701 | static_map | collision | N/A | 10.19% | 1 | 0/0 |
| seen_envfix_noisy | s4 | D | 2701 | own_frontier | collision | N/A | 9.43% | 1 | 0/0 |
| seen_envfix_noisy | s4 | D | 2702 | static_map | collision | N/A | 13.05% | 1 | 0/0 |
| seen_envfix_noisy | s4 | D | 2702 | own_frontier | collision | N/A | 26.41% | 1 | 0/0 |
| seen_envfix_noisy | s5 | B | 2701 | static_map | collision | N/A | 32.22% | 1 | 0/0 |
| seen_envfix_noisy | s5 | B | 2701 | own_frontier | collision | N/A | 14.76% | 1 | 0/0 |
| seen_envfix_noisy | s5 | B | 2702 | static_map | collision | N/A | 35.45% | 1 | 0/0 |
| seen_envfix_noisy | s5 | B | 2702 | own_frontier | search_exhausted | N/A | 15.10% | 0 | 0/0 |
| seen_envfix_noisy | s5 | D | 2701 | static_map | collision | N/A | 32.85% | 1 | 0/0 |
| seen_envfix_noisy | s5 | D | 2701 | own_frontier | search_exhausted | N/A | 49.55% | 0 | 0/0 |
| seen_envfix_noisy | s5 | D | 2702 | static_map | collision | N/A | 17.15% | 1 | 0/0 |
| seen_envfix_noisy | s5 | D | 2702 | own_frontier | search_exhausted | N/A | 54.72% | 0 | 0/0 |
| seen_envfix_noisy | s6 | B | 2701 | static_map | collision | N/A | 28.31% | 1 | 0/0 |
| seen_envfix_noisy | s6 | B | 2701 | own_frontier | collision | N/A | 14.76% | 1 | 0/0 |
| seen_envfix_noisy | s6 | B | 2702 | static_map | collision | N/A | 44.60% | 1 | 0/0 |
| seen_envfix_noisy | s6 | B | 2702 | own_frontier | search_exhausted | N/A | 15.11% | 0 | 0/0 |
| seen_envfix_noisy | s6 | D | 2701 | static_map | collision | N/A | 14.07% | 1 | 0/0 |
| seen_envfix_noisy | s6 | D | 2701 | own_frontier | search_exhausted | N/A | 48.63% | 0 | 0/0 |
| seen_envfix_noisy | s6 | D | 2702 | static_map | collision | N/A | 17.16% | 1 | 0/0 |
| seen_envfix_noisy | s6 | D | 2702 | own_frontier | search_exhausted | N/A | 53.14% | 0 | 0/0 |
| seen_envfix_noisy | s7 | B | 2701 | static_map | collision | N/A | 20.74% | 1 | 0/0 |
| seen_envfix_noisy | s7 | B | 2701 | own_frontier | collision | N/A | 14.89% | 1 | 0/0 |
| seen_envfix_noisy | s7 | B | 2702 | static_map | collision | N/A | 15.91% | 1 | 0/0 |
| seen_envfix_noisy | s7 | B | 2702 | own_frontier | search_exhausted | N/A | 15.24% | 0 | 0/0 |
| seen_envfix_noisy | s7 | D | 2701 | static_map | collision | N/A | 31.15% | 1 | 0/0 |
| seen_envfix_noisy | s7 | D | 2701 | own_frontier | search_exhausted | N/A | 47.76% | 0 | 0/0 |
| seen_envfix_noisy | s7 | D | 2702 | static_map | collision | N/A | 17.24% | 1 | 0/0 |
| seen_envfix_noisy | s7 | D | 2702 | own_frontier | search_exhausted | N/A | 52.56% | 0 | 0/0 |
| seen_envfix_noisy | s8 | B | 2701 | static_map | collision | N/A | 19.00% | 1 | 0/0 |
| seen_envfix_noisy | s8 | B | 2701 | own_frontier | collision | N/A | 11.85% | 1 | 0/0 |
| seen_envfix_noisy | s8 | B | 2702 | static_map | collision | N/A | 13.46% | 1 | 0/0 |
| seen_envfix_noisy | s8 | B | 2702 | own_frontier | search_exhausted | N/A | 12.20% | 0 | 0/0 |
| seen_envfix_noisy | s8 | D | 2701 | static_map | collision | N/A | 10.30% | 1 | 0/0 |
| seen_envfix_noisy | s8 | D | 2701 | own_frontier | collision | N/A | 41.08% | 1 | 0/0 |
| seen_envfix_noisy | s8 | D | 2702 | static_map | collision | N/A | 15.77% | 1 | 0/0 |
| seen_envfix_noisy | s8 | D | 2702 | own_frontier | search_exhausted | N/A | 52.12% | 0 | 0/0 |
| seen_envfix_oracle | s1 | B | 2701 | static_map | collision | N/A | 8.72% | 1 | 0/0 |
| seen_envfix_oracle | s1 | B | 2701 | own_frontier | search_exhausted | N/A | 8.78% | 0 | 0/0 |
| seen_envfix_oracle | s1 | B | 2702 | static_map | collision | N/A | 8.72% | 1 | 0/0 |
| seen_envfix_oracle | s1 | B | 2702 | own_frontier | search_exhausted | N/A | 8.78% | 0 | 0/0 |
| seen_envfix_oracle | s1 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 42.53% | 0 | 0/2 |
| seen_envfix_oracle | s1 | D | 2701 | own_frontier | search_exhausted | N/A | 35.07% | 0 | 0/0 |
| seen_envfix_oracle | s1 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 42.53% | 0 | 0/2 |
| seen_envfix_oracle | s1 | D | 2702 | own_frontier | search_exhausted | N/A | 35.07% | 0 | 0/0 |
| seen_envfix_oracle | s2 | B | 2701 | static_map | collision | N/A | 14.04% | 1 | 0/0 |
| seen_envfix_oracle | s2 | B | 2701 | own_frontier | search_exhausted | N/A | 12.93% | 0 | 0/0 |
| seen_envfix_oracle | s2 | B | 2702 | static_map | collision | N/A | 14.04% | 1 | 0/0 |
| seen_envfix_oracle | s2 | B | 2702 | own_frontier | search_exhausted | N/A | 12.93% | 0 | 0/0 |
| seen_envfix_oracle | s2 | D | 2701 | static_map | collision | N/A | 23.84% | 1 | 0/2 |
| seen_envfix_oracle | s2 | D | 2701 | own_frontier | search_exhausted | N/A | 50.03% | 0 | 0/0 |
| seen_envfix_oracle | s2 | D | 2702 | static_map | collision | N/A | 23.84% | 1 | 0/2 |
| seen_envfix_oracle | s2 | D | 2702 | own_frontier | search_exhausted | N/A | 50.03% | 0 | 0/0 |
| seen_envfix_oracle | s3 | B | 2701 | static_map | collision | N/A | 8.92% | 1 | 0/0 |
| seen_envfix_oracle | s3 | B | 2701 | own_frontier | search_exhausted | N/A | 9.51% | 0 | 0/0 |
| seen_envfix_oracle | s3 | B | 2702 | static_map | collision | N/A | 8.92% | 1 | 0/0 |
| seen_envfix_oracle | s3 | B | 2702 | own_frontier | search_exhausted | N/A | 9.51% | 0 | 0/0 |
| seen_envfix_oracle | s3 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 41.70% | 0 | 0/2 |
| seen_envfix_oracle | s3 | D | 2701 | own_frontier | search_exhausted | N/A | 47.57% | 0 | 0/0 |
| seen_envfix_oracle | s3 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 41.70% | 0 | 0/2 |
| seen_envfix_oracle | s3 | D | 2702 | own_frontier | search_exhausted | N/A | 47.57% | 0 | 0/0 |
| seen_envfix_oracle | s4 | B | 2701 | static_map | B_confirmed | 7.266 m / 215.0 s | 24.46% | 0 | 0/2 |
| seen_envfix_oracle | s4 | B | 2701 | own_frontier | search_exhausted | N/A | 12.87% | 0 | 0/0 |
| seen_envfix_oracle | s4 | B | 2702 | static_map | B_confirmed | 7.266 m / 215.0 s | 24.46% | 0 | 0/2 |
| seen_envfix_oracle | s4 | B | 2702 | own_frontier | search_exhausted | N/A | 12.87% | 0 | 0/0 |
| seen_envfix_oracle | s4 | D | 2701 | static_map | B_confirmed | 6.084 m / 188.0 s | 43.18% | 0 | 0/2 |
| seen_envfix_oracle | s4 | D | 2701 | own_frontier | search_exhausted | N/A | 29.54% | 0 | 0/0 |
| seen_envfix_oracle | s4 | D | 2702 | static_map | B_confirmed | 6.084 m / 188.0 s | 43.18% | 0 | 0/2 |
| seen_envfix_oracle | s4 | D | 2702 | own_frontier | search_exhausted | N/A | 29.54% | 0 | 0/0 |
| seen_envfix_oracle | s5 | B | 2701 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.31% | 0 | 0/0 |
| seen_envfix_oracle | s5 | B | 2701 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_envfix_oracle | s5 | B | 2702 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.31% | 0 | 0/0 |
| seen_envfix_oracle | s5 | B | 2702 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_envfix_oracle | s5 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 43.85% | 0 | 0/2 |
| seen_envfix_oracle | s5 | D | 2701 | own_frontier | search_exhausted | N/A | 51.01% | 0 | 0/0 |
| seen_envfix_oracle | s5 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 43.85% | 0 | 0/2 |
| seen_envfix_oracle | s5 | D | 2702 | own_frontier | search_exhausted | N/A | 51.01% | 0 | 0/0 |
| seen_envfix_oracle | s6 | B | 2701 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.33% | 0 | 0/0 |
| seen_envfix_oracle | s6 | B | 2701 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_envfix_oracle | s6 | B | 2702 | static_map | B_confirmed | 2.877 m / 83.0 s | 40.33% | 0 | 0/0 |
| seen_envfix_oracle | s6 | B | 2702 | own_frontier | search_exhausted | N/A | 15.35% | 0 | 0/0 |
| seen_envfix_oracle | s6 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 47.83% | 0 | 0/2 |
| seen_envfix_oracle | s6 | D | 2701 | own_frontier | search_exhausted | N/A | 48.98% | 0 | 0/0 |
| seen_envfix_oracle | s6 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 47.83% | 0 | 0/2 |
| seen_envfix_oracle | s6 | D | 2702 | own_frontier | search_exhausted | N/A | 48.98% | 0 | 0/0 |
| seen_envfix_oracle | s7 | B | 2701 | static_map | collision | N/A | 18.36% | 1 | 0/0 |
| seen_envfix_oracle | s7 | B | 2701 | own_frontier | search_exhausted | N/A | 15.49% | 0 | 0/0 |
| seen_envfix_oracle | s7 | B | 2702 | static_map | collision | N/A | 18.36% | 1 | 0/0 |
| seen_envfix_oracle | s7 | B | 2702 | own_frontier | search_exhausted | N/A | 15.49% | 0 | 0/0 |
| seen_envfix_oracle | s7 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.23% | 0 | 0/2 |
| seen_envfix_oracle | s7 | D | 2701 | own_frontier | search_exhausted | N/A | 49.02% | 0 | 0/0 |
| seen_envfix_oracle | s7 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.23% | 0 | 0/2 |
| seen_envfix_oracle | s7 | D | 2702 | own_frontier | search_exhausted | N/A | 49.02% | 0 | 0/0 |
| seen_envfix_oracle | s8 | B | 2701 | static_map | collision | N/A | 13.77% | 1 | 0/0 |
| seen_envfix_oracle | s8 | B | 2701 | own_frontier | search_exhausted | N/A | 12.44% | 0 | 0/0 |
| seen_envfix_oracle | s8 | B | 2702 | static_map | collision | N/A | 13.77% | 1 | 0/0 |
| seen_envfix_oracle | s8 | B | 2702 | own_frontier | search_exhausted | N/A | 12.44% | 0 | 0/0 |
| seen_envfix_oracle | s8 | D | 2701 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.25% | 0 | 0/2 |
| seen_envfix_oracle | s8 | D | 2701 | own_frontier | search_exhausted | N/A | 47.53% | 0 | 0/0 |
| seen_envfix_oracle | s8 | D | 2702 | static_map | B_confirmed | 4.816 m / 140.0 s | 49.25% | 0 | 0/2 |
| seen_envfix_oracle | s8 | D | 2702 | own_frontier | search_exhausted | N/A | 47.53% | 0 | 0/0 |
| development_v2_noisy | s1 | A | 1701 | static_map | collision | N/A | 9.17% | 1 | 0/0 |
| development_v2_noisy | s1 | A | 1701 | own_frontier | collision | N/A | 10.97% | 1 | 0/0 |
| development_v2_noisy | s1 | C | 1701 | static_map | collision | N/A | 48.61% | 1 | 0/0 |
| development_v2_noisy | s1 | C | 1701 | own_frontier | collision | N/A | 22.05% | 1 | 0/0 |
| development_v2_noisy | s2 | A | 1701 | static_map | collision | N/A | 46.77% | 1 | 0/0 |
| development_v2_noisy | s2 | A | 1701 | own_frontier | collision | N/A | 14.11% | 1 | 0/0 |
| development_v2_noisy | s2 | C | 1701 | static_map | collision | N/A | 52.29% | 1 | 0/1 |
| development_v2_noisy | s2 | C | 1701 | own_frontier | collision | N/A | 21.40% | 1 | 0/0 |
| development_v2_noisy | s3 | A | 1701 | static_map | budget | N/A | 51.22% | 0 | 0/0 |
| development_v2_noisy | s3 | A | 1701 | own_frontier | collision | N/A | 12.08% | 1 | 0/0 |
| development_v2_noisy | s3 | C | 1701 | static_map | collision | N/A | 47.88% | 1 | 0/0 |
| development_v2_noisy | s3 | C | 1701 | own_frontier | collision | N/A | 20.38% | 1 | 0/0 |
| development_v2_noisy | s4 | A | 1701 | static_map | collision | N/A | 17.05% | 1 | 0/0 |
| development_v2_noisy | s4 | A | 1701 | own_frontier | collision | N/A | 12.11% | 1 | 0/0 |
| development_v2_noisy | s4 | C | 1701 | static_map | budget | N/A | 50.00% | 0 | 0/0 |
| development_v2_noisy | s4 | C | 1701 | own_frontier | collision | N/A | 20.46% | 1 | 0/0 |
| development_v2_noisy | s5 | A | 1701 | static_map | budget | N/A | 55.03% | 0 | 0/0 |
| development_v2_noisy | s5 | A | 1701 | own_frontier | collision | N/A | 12.08% | 1 | 0/0 |
| development_v2_noisy | s5 | C | 1701 | static_map | collision | N/A | 14.72% | 1 | 0/0 |
| development_v2_noisy | s5 | C | 1701 | own_frontier | collision | N/A | 30.28% | 1 | 0/0 |
| development_v2_noisy | s6 | A | 1701 | static_map | budget | N/A | 67.97% | 0 | 0/0 |
| development_v2_noisy | s6 | A | 1701 | own_frontier | budget | N/A | 20.94% | 0 | 0/0 |
| development_v2_noisy | s6 | C | 1701 | static_map | collision | N/A | 51.41% | 1 | 0/1 |
| development_v2_noisy | s6 | C | 1701 | own_frontier | B_confirmed | 33.507 m / 134.0 s | 59.74% | 0 | 0/5 |
| development_v2_noisy | s7 | A | 1701 | static_map | collision | N/A | 17.87% | 1 | 0/0 |
| development_v2_noisy | s7 | A | 1701 | own_frontier | collision | N/A | 13.03% | 1 | 0/0 |
| development_v2_noisy | s7 | C | 1701 | static_map | collision | N/A | 47.90% | 1 | 0/1 |
| development_v2_noisy | s7 | C | 1701 | own_frontier | collision | N/A | 28.14% | 1 | 0/0 |
| development_v2_noisy | s8 | A | 1701 | static_map | collision | N/A | 12.79% | 1 | 0/0 |
| development_v2_noisy | s8 | A | 1701 | own_frontier | collision | N/A | 13.00% | 1 | 0/0 |
| development_v2_noisy | s8 | C | 1701 | static_map | collision | N/A | 47.84% | 1 | 0/1 |
| development_v2_noisy | s8 | C | 1701 | own_frontier | collision | N/A | 28.04% | 1 | 0/0 |
| development_v2_oracle | s1 | A | 1701 | static_map | collision | N/A | 10.14% | 1 | 0/0 |
| development_v2_oracle | s1 | A | 1701 | own_frontier | budget | N/A | 9.79% | 0 | 0/0 |
| development_v2_oracle | s1 | C | 1701 | static_map | B_confirmed | 6.165 m / 173.0 s | 46.08% | 0 | 0/2 |
| development_v2_oracle | s1 | C | 1701 | own_frontier | budget | N/A | 20.59% | 0 | 0/0 |
| development_v2_oracle | s2 | A | 1701 | static_map | B_confirmed | 1.212 m / 38.0 s | 20.40% | 0 | 0/0 |
| development_v2_oracle | s2 | A | 1701 | own_frontier | B_confirmed | 2.617 m / 80.0 s | 21.47% | 0 | 0/0 |
| development_v2_oracle | s2 | C | 1701 | static_map | B_confirmed | 2.817 m / 80.0 s | 54.69% | 0 | 0/2 |
| development_v2_oracle | s2 | C | 1701 | own_frontier | budget | N/A | 20.01% | 0 | 0/0 |
| development_v2_oracle | s3 | A | 1701 | static_map | collision | N/A | 14.97% | 1 | 0/0 |
| development_v2_oracle | s3 | A | 1701 | own_frontier | budget | N/A | 9.79% | 0 | 0/0 |
| development_v2_oracle | s3 | C | 1701 | static_map | B_confirmed | 6.165 m / 173.0 s | 45.76% | 0 | 0/2 |
| development_v2_oracle | s3 | C | 1701 | own_frontier | budget | N/A | 20.56% | 0 | 0/0 |
| development_v2_oracle | s4 | A | 1701 | static_map | collision | N/A | 18.20% | 1 | 0/0 |
| development_v2_oracle | s4 | A | 1701 | own_frontier | budget | N/A | 9.81% | 0 | 0/0 |
| development_v2_oracle | s4 | C | 1701 | static_map | budget | N/A | 21.54% | 0 | 0/0 |
| development_v2_oracle | s4 | C | 1701 | own_frontier | budget | N/A | 22.69% | 0 | 0/0 |
| development_v2_oracle | s5 | A | 1701 | static_map | B_confirmed | 4.037 m / 110.0 s | 37.26% | 0 | 0/2 |
| development_v2_oracle | s5 | A | 1701 | own_frontier | budget | N/A | 9.76% | 0 | 0/0 |
| development_v2_oracle | s5 | C | 1701 | static_map | collision | N/A | 14.79% | 1 | 0/0 |
| development_v2_oracle | s5 | C | 1701 | own_frontier | collision | N/A | 21.81% | 1 | 0/0 |
| development_v2_oracle | s6 | A | 1701 | static_map | B_confirmed | 1.257 m / 38.0 s | 21.71% | 0 | 0/0 |
| development_v2_oracle | s6 | A | 1701 | own_frontier | B_confirmed | 1.580 m / 47.0 s | 20.88% | 0 | 0/0 |
| development_v2_oracle | s6 | C | 1701 | static_map | B_confirmed | 2.817 m / 80.0 s | 54.36% | 0 | 0/2 |
| development_v2_oracle | s6 | C | 1701 | own_frontier | budget | N/A | 19.94% | 0 | 0/0 |
| development_v2_oracle | s7 | A | 1701 | static_map | B_confirmed | 1.257 m / 38.0 s | 18.96% | 0 | 0/0 |
| development_v2_oracle | s7 | A | 1701 | own_frontier | B_confirmed | 4.622 m / 131.0 s | 17.94% | 0 | 0/0 |
| development_v2_oracle | s7 | C | 1701 | static_map | B_confirmed | 2.786 m / 80.0 s | 52.73% | 0 | 0/2 |
| development_v2_oracle | s7 | C | 1701 | own_frontier | budget | N/A | 12.44% | 0 | 0/0 |
| development_v2_oracle | s8 | A | 1701 | static_map | B_confirmed | 1.257 m / 38.0 s | 18.96% | 0 | 0/0 |
| development_v2_oracle | s8 | A | 1701 | own_frontier | B_confirmed | 4.622 m / 131.0 s | 17.95% | 0 | 0/0 |
| development_v2_oracle | s8 | C | 1701 | static_map | B_confirmed | 2.786 m / 80.0 s | 52.65% | 0 | 0/2 |
| development_v2_oracle | s8 | C | 1701 | own_frontier | budget | N/A | 12.34% | 0 | 0/0 |
| fresh_v2_noisy | s1 | E | 3701 | static_map | collision | N/A | 28.58% | 1 | 0/0 |
| fresh_v2_noisy | s1 | E | 3701 | own_frontier | collision | N/A | 33.72% | 1 | 0/0 |
| fresh_v2_noisy | s1 | E | 3702 | static_map | collision | N/A | 53.09% | 1 | 0/0 |
| fresh_v2_noisy | s1 | E | 3702 | own_frontier | budget | N/A | 30.49% | 0 | 0/0 |
| fresh_v2_noisy | s1 | F | 3701 | static_map | collision | N/A | 17.95% | 1 | 0/0 |
| fresh_v2_noisy | s1 | F | 3701 | own_frontier | collision | N/A | 33.68% | 1 | 0/0 |
| fresh_v2_noisy | s1 | F | 3702 | static_map | budget | N/A | 15.24% | 0 | 0/0 |
| fresh_v2_noisy | s1 | F | 3702 | own_frontier | collision | N/A | 11.70% | 1 | 0/0 |
| fresh_v2_noisy | s2 | E | 3701 | static_map | collision | N/A | 30.47% | 1 | 0/0 |
| fresh_v2_noisy | s2 | E | 3701 | own_frontier | collision | N/A | 30.65% | 1 | 0/0 |
| fresh_v2_noisy | s2 | E | 3702 | static_map | collision | N/A | 31.34% | 1 | 0/0 |
| fresh_v2_noisy | s2 | E | 3702 | own_frontier | budget | N/A | 32.35% | 0 | 0/0 |
| fresh_v2_noisy | s2 | F | 3701 | static_map | collision | N/A | 17.62% | 1 | 0/0 |
| fresh_v2_noisy | s2 | F | 3701 | own_frontier | collision | N/A | 21.47% | 1 | 0/0 |
| fresh_v2_noisy | s2 | F | 3702 | static_map | budget | N/A | 15.53% | 0 | 0/0 |
| fresh_v2_noisy | s2 | F | 3702 | own_frontier | collision | N/A | 14.18% | 1 | 0/0 |
| fresh_v2_noisy | s3 | E | 3701 | static_map | collision | N/A | 30.14% | 1 | 0/0 |
| fresh_v2_noisy | s3 | E | 3701 | own_frontier | collision | N/A | 23.99% | 1 | 0/0 |
| fresh_v2_noisy | s3 | E | 3702 | static_map | collision | N/A | 54.24% | 1 | 0/0 |
| fresh_v2_noisy | s3 | E | 3702 | own_frontier | budget | N/A | 32.74% | 0 | 0/0 |
| fresh_v2_noisy | s3 | F | 3701 | static_map | collision | N/A | 17.95% | 1 | 0/0 |
| fresh_v2_noisy | s3 | F | 3701 | own_frontier | budget | N/A | 41.01% | 0 | 0/0 |
| fresh_v2_noisy | s3 | F | 3702 | static_map | budget | N/A | 15.24% | 0 | 0/0 |
| fresh_v2_noisy | s3 | F | 3702 | own_frontier | collision | N/A | 11.70% | 1 | 0/0 |
| fresh_v2_noisy | s4 | E | 3701 | static_map | collision | N/A | 27.70% | 1 | 0/0 |
| fresh_v2_noisy | s4 | E | 3701 | own_frontier | collision | N/A | 23.94% | 1 | 0/0 |
| fresh_v2_noisy | s4 | E | 3702 | static_map | budget | N/A | 49.44% | 0 | 0/0 |
| fresh_v2_noisy | s4 | E | 3702 | own_frontier | collision | N/A | 29.40% | 1 | 0/0 |
| fresh_v2_noisy | s4 | F | 3701 | static_map | collision | N/A | 24.29% | 1 | 0/0 |
| fresh_v2_noisy | s4 | F | 3701 | own_frontier | collision | N/A | 16.04% | 1 | 0/0 |
| fresh_v2_noisy | s4 | F | 3702 | static_map | collision | N/A | 15.52% | 1 | 0/0 |
| fresh_v2_noisy | s4 | F | 3702 | own_frontier | collision | N/A | 13.08% | 1 | 0/0 |
| fresh_v2_noisy | s5 | E | 3701 | static_map | collision | N/A | 31.28% | 1 | 0/0 |
| fresh_v2_noisy | s5 | E | 3701 | own_frontier | collision | N/A | 34.76% | 1 | 0/0 |
| fresh_v2_noisy | s5 | E | 3702 | static_map | budget | N/A | 55.38% | 0 | 0/0 |
| fresh_v2_noisy | s5 | E | 3702 | own_frontier | collision | N/A | 32.92% | 1 | 0/0 |
| fresh_v2_noisy | s5 | F | 3701 | static_map | collision | N/A | 17.95% | 1 | 0/0 |
| fresh_v2_noisy | s5 | F | 3701 | own_frontier | budget | N/A | 41.01% | 0 | 0/0 |
| fresh_v2_noisy | s5 | F | 3702 | static_map | budget | N/A | 15.24% | 0 | 0/0 |
| fresh_v2_noisy | s5 | F | 3702 | own_frontier | collision | N/A | 13.06% | 1 | 0/0 |
| fresh_v2_noisy | s6 | E | 3701 | static_map | collision | N/A | 29.73% | 1 | 0/1 |
| fresh_v2_noisy | s6 | E | 3701 | own_frontier | collision | N/A | 27.02% | 1 | 0/0 |
| fresh_v2_noisy | s6 | E | 3702 | static_map | collision | N/A | 22.65% | 1 | 0/0 |
| fresh_v2_noisy | s6 | E | 3702 | own_frontier | collision | N/A | 27.75% | 1 | 0/0 |
| fresh_v2_noisy | s6 | F | 3701 | static_map | collision | N/A | 16.19% | 1 | 0/0 |
| fresh_v2_noisy | s6 | F | 3701 | own_frontier | collision | N/A | 12.54% | 1 | 0/0 |
| fresh_v2_noisy | s6 | F | 3702 | static_map | collision | N/A | 10.52% | 1 | 0/0 |
| fresh_v2_noisy | s6 | F | 3702 | own_frontier | collision | N/A | 10.52% | 1 | 0/0 |
| fresh_v2_noisy | s7 | E | 3701 | static_map | collision | N/A | 29.15% | 1 | 0/0 |
| fresh_v2_noisy | s7 | E | 3701 | own_frontier | collision | N/A | 34.72% | 1 | 0/0 |
| fresh_v2_noisy | s7 | E | 3702 | static_map | collision | N/A | 34.62% | 1 | 1/1 |
| fresh_v2_noisy | s7 | E | 3702 | own_frontier | collision | N/A | 32.87% | 1 | 0/0 |
| fresh_v2_noisy | s7 | F | 3701 | static_map | collision | N/A | 15.70% | 1 | 0/0 |
| fresh_v2_noisy | s7 | F | 3701 | own_frontier | collision | N/A | 16.26% | 1 | 0/0 |
| fresh_v2_noisy | s7 | F | 3702 | static_map | budget | N/A | 13.95% | 0 | 0/0 |
| fresh_v2_noisy | s7 | F | 3702 | own_frontier | collision | N/A | 12.65% | 1 | 0/0 |
| fresh_v2_noisy | s8 | E | 3701 | static_map | collision | N/A | 29.13% | 1 | 0/0 |
| fresh_v2_noisy | s8 | E | 3701 | own_frontier | budget | N/A | 34.21% | 0 | 0/0 |
| fresh_v2_noisy | s8 | E | 3702 | static_map | collision | N/A | 34.56% | 1 | 0/0 |
| fresh_v2_noisy | s8 | E | 3702 | own_frontier | collision | N/A | 32.77% | 1 | 0/0 |
| fresh_v2_noisy | s8 | F | 3701 | static_map | collision | N/A | 14.48% | 1 | 0/0 |
| fresh_v2_noisy | s8 | F | 3701 | own_frontier | collision | N/A | 13.49% | 1 | 0/0 |
| fresh_v2_noisy | s8 | F | 3702 | static_map | budget | N/A | 13.95% | 0 | 0/0 |
| fresh_v2_noisy | s8 | F | 3702 | own_frontier | collision | N/A | 12.65% | 1 | 0/0 |
| fresh_v2_oracle | s1 | E | 3701 | static_map | B_confirmed | 6.225 m / 263.0 s | 71.04% | 0 | 0/2 |
| fresh_v2_oracle | s1 | E | 3701 | own_frontier | budget | N/A | 19.34% | 0 | 0/0 |
| fresh_v2_oracle | s1 | E | 3702 | static_map | B_confirmed | 6.225 m / 263.0 s | 71.04% | 0 | 0/2 |
| fresh_v2_oracle | s1 | E | 3702 | own_frontier | budget | N/A | 19.34% | 0 | 0/0 |
| fresh_v2_oracle | s1 | F | 3701 | static_map | budget | N/A | 13.99% | 0 | 0/0 |
| fresh_v2_oracle | s1 | F | 3701 | own_frontier | budget | N/A | 11.49% | 0 | 0/0 |
| fresh_v2_oracle | s1 | F | 3702 | static_map | budget | N/A | 13.99% | 0 | 0/0 |
| fresh_v2_oracle | s1 | F | 3702 | own_frontier | budget | N/A | 11.49% | 0 | 0/0 |
| fresh_v2_oracle | s2 | E | 3701 | static_map | collision | N/A | 27.76% | 1 | 0/0 |
| fresh_v2_oracle | s2 | E | 3701 | own_frontier | budget | N/A | 21.72% | 0 | 0/0 |
| fresh_v2_oracle | s2 | E | 3702 | static_map | collision | N/A | 27.76% | 1 | 0/0 |
| fresh_v2_oracle | s2 | E | 3702 | own_frontier | budget | N/A | 21.72% | 0 | 0/0 |
| fresh_v2_oracle | s2 | F | 3701 | static_map | collision | N/A | 14.00% | 1 | 0/0 |
| fresh_v2_oracle | s2 | F | 3701 | own_frontier | budget | N/A | 11.54% | 0 | 0/0 |
| fresh_v2_oracle | s2 | F | 3702 | static_map | collision | N/A | 14.00% | 1 | 0/0 |
| fresh_v2_oracle | s2 | F | 3702 | own_frontier | budget | N/A | 11.54% | 0 | 0/0 |
| fresh_v2_oracle | s3 | E | 3701 | static_map | B_confirmed | 6.036 m / 263.0 s | 71.98% | 0 | 0/2 |
| fresh_v2_oracle | s3 | E | 3701 | own_frontier | budget | N/A | 21.28% | 0 | 0/0 |
| fresh_v2_oracle | s3 | E | 3702 | static_map | B_confirmed | 6.036 m / 263.0 s | 71.98% | 0 | 0/2 |
| fresh_v2_oracle | s3 | E | 3702 | own_frontier | budget | N/A | 21.28% | 0 | 0/0 |
| fresh_v2_oracle | s3 | F | 3701 | static_map | budget | N/A | 13.99% | 0 | 0/0 |
| fresh_v2_oracle | s3 | F | 3701 | own_frontier | budget | N/A | 11.49% | 0 | 0/0 |
| fresh_v2_oracle | s3 | F | 3702 | static_map | budget | N/A | 13.99% | 0 | 0/0 |
| fresh_v2_oracle | s3 | F | 3702 | own_frontier | budget | N/A | 11.49% | 0 | 0/0 |
| fresh_v2_oracle | s4 | E | 3701 | static_map | budget | N/A | 46.73% | 0 | 0/0 |
| fresh_v2_oracle | s4 | E | 3701 | own_frontier | budget | N/A | 18.06% | 0 | 0/0 |
| fresh_v2_oracle | s4 | E | 3702 | static_map | budget | N/A | 46.73% | 0 | 0/0 |
| fresh_v2_oracle | s4 | E | 3702 | own_frontier | budget | N/A | 18.06% | 0 | 0/0 |
| fresh_v2_oracle | s4 | F | 3701 | static_map | budget | N/A | 23.59% | 0 | 0/0 |
| fresh_v2_oracle | s4 | F | 3701 | own_frontier | budget | N/A | 11.52% | 0 | 0/0 |
| fresh_v2_oracle | s4 | F | 3702 | static_map | budget | N/A | 23.59% | 0 | 0/0 |
| fresh_v2_oracle | s4 | F | 3702 | own_frontier | budget | N/A | 11.52% | 0 | 0/0 |
| fresh_v2_oracle | s5 | E | 3701 | static_map | B_confirmed | 6.085 m / 263.0 s | 73.06% | 0 | 0/2 |
| fresh_v2_oracle | s5 | E | 3701 | own_frontier | budget | N/A | 24.31% | 0 | 0/0 |
| fresh_v2_oracle | s5 | E | 3702 | static_map | B_confirmed | 6.085 m / 263.0 s | 73.06% | 0 | 0/2 |
| fresh_v2_oracle | s5 | E | 3702 | own_frontier | budget | N/A | 24.31% | 0 | 0/0 |
| fresh_v2_oracle | s5 | F | 3701 | static_map | budget | N/A | 13.99% | 0 | 0/0 |
| fresh_v2_oracle | s5 | F | 3701 | own_frontier | budget | N/A | 11.56% | 0 | 0/0 |
| fresh_v2_oracle | s5 | F | 3702 | static_map | budget | N/A | 13.99% | 0 | 0/0 |
| fresh_v2_oracle | s5 | F | 3702 | own_frontier | budget | N/A | 11.56% | 0 | 0/0 |
| fresh_v2_oracle | s6 | E | 3701 | static_map | B_confirmed | 2.561 m / 71.0 s | 34.07% | 0 | 0/0 |
| fresh_v2_oracle | s6 | E | 3701 | own_frontier | budget | N/A | 18.20% | 0 | 0/0 |
| fresh_v2_oracle | s6 | E | 3702 | static_map | B_confirmed | 2.561 m / 71.0 s | 34.07% | 0 | 0/0 |
| fresh_v2_oracle | s6 | E | 3702 | own_frontier | budget | N/A | 18.20% | 0 | 0/0 |
| fresh_v2_oracle | s6 | F | 3701 | static_map | budget | N/A | 14.41% | 0 | 0/0 |
| fresh_v2_oracle | s6 | F | 3701 | own_frontier | budget | N/A | 11.01% | 0 | 0/0 |
| fresh_v2_oracle | s6 | F | 3702 | static_map | budget | N/A | 14.41% | 0 | 0/0 |
| fresh_v2_oracle | s6 | F | 3702 | own_frontier | budget | N/A | 11.01% | 0 | 0/0 |
| fresh_v2_oracle | s7 | E | 3701 | static_map | collision | N/A | 27.47% | 1 | 0/0 |
| fresh_v2_oracle | s7 | E | 3701 | own_frontier | budget | N/A | 21.86% | 0 | 0/0 |
| fresh_v2_oracle | s7 | E | 3702 | static_map | collision | N/A | 27.47% | 1 | 0/0 |
| fresh_v2_oracle | s7 | E | 3702 | own_frontier | budget | N/A | 21.86% | 0 | 0/0 |
| fresh_v2_oracle | s7 | F | 3701 | static_map | budget | N/A | 12.09% | 0 | 0/0 |
| fresh_v2_oracle | s7 | F | 3701 | own_frontier | budget | N/A | 8.55% | 0 | 0/0 |
| fresh_v2_oracle | s7 | F | 3702 | static_map | budget | N/A | 12.09% | 0 | 0/0 |
| fresh_v2_oracle | s7 | F | 3702 | own_frontier | budget | N/A | 8.55% | 0 | 0/0 |
| fresh_v2_oracle | s8 | E | 3701 | static_map | collision | N/A | 27.09% | 1 | 0/0 |
| fresh_v2_oracle | s8 | E | 3701 | own_frontier | budget | N/A | 21.84% | 0 | 0/0 |
| fresh_v2_oracle | s8 | E | 3702 | static_map | collision | N/A | 27.09% | 1 | 0/0 |
| fresh_v2_oracle | s8 | E | 3702 | own_frontier | budget | N/A | 21.84% | 0 | 0/0 |
| fresh_v2_oracle | s8 | F | 3701 | static_map | budget | N/A | 12.09% | 0 | 0/0 |
| fresh_v2_oracle | s8 | F | 3701 | own_frontier | budget | N/A | 8.55% | 0 | 0/0 |
| fresh_v2_oracle | s8 | F | 3702 | static_map | budget | N/A | 12.09% | 0 | 0/0 |
| fresh_v2_oracle | s8 | F | 3702 | own_frontier | budget | N/A | 8.55% | 0 | 0/0 |
