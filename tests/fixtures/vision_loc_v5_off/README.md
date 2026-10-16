# VIS5 기본 OFF 회귀검사 기준

두 `.py.txt` 파일은 아래 Git blob을 **바이트 그대로** 보존한 테스트 전용 소스 fixture다.
합계 39,693 bytes로 1 MiB 미만이며 모델·관측·정답 자료를 포함하지 않는다.

| 파일 | 원본 커밋 | 원본 경로 | SHA-256 |
|---|---|---|---|
| `vision_pf_vis4.py.txt` | `137ba742493b1f09c68238525cfc44a57054ae48` (VIS4) | `experiments/2026-09-26-vision-loc/vision_pf.py` | `97a207dbda2fe31df32809b48baa4db1859ef0e1f30a196f5810b338c955b8f7` |
| `owncam_localizer_m1.py.txt` | `22c84842b507264de496b54b1e8c9217701b9b5c` (M1) | `harness/owncam_localizer.py` | `0304d7c491dfe6ae68cea6550f7a13e3c99e8e1d3f8e8b6c4b7b1d06893b1d63` |

추출 방법은 `git show <원본 커밋>:<원본 경로>`이며 추출 뒤 SHA-256을 대조했다.
실행 중에는 Git·네트워크·HEAD를 읽거나 fixture를 재생성하지 않는다. 파일 누락은
명확한 pytest 실패, 바이트 변경은 해시 불일치 실패이며 skip/fallback은 없다.
M1도 함께 고정하여 `markerless_probe.load_m1_localizer()`의 과거 Git 객체 의존성을
제거했다. 원 M1 로더의 공통 `wall_tags.py` 해시 검사는 유지한다.

검사 범위는 동일 seed=42·32입자·합성 관측 3시각에서 현재 PF의 옵션 생략 및 명시적
`enabled=False`를 VIS4 PF와 비교하는 것이다. 보고값 전체·입자·가중치·RNG를 정확히
대조하며, 현재 PF의 x 보고에만 +1 m를 주입하면 같은 검사가 실패해야 한다.
공통 `vision_loc`·`vision_motion`·`vision_sigma`와 정적 지도·보정은 작업 트리의 것을
양쪽에 똑같이 사용한다. 이는 VIS5 PF 변경의 OFF 불변 검사이지 전체 과거 실행 환경의
동결이나 새 위치 추정 성능·물리 성공 검증이 아니다.

얕은 clone에는 추가 fetch가 필요 없다. sparse checkout에는 `tests/test_vision_loc_v5.py`,
이 fixture 디렉터리, `experiments/2026-09-26-vision-loc`,
`experiments/2026-09-26-markerless-probe`, `harness`, `sim`, `scripts/robot_actions.py`를 포함한다.
필요한 파일이 없는 sparse checkout은 실패하므로 해당 경로를 복원해야 한다.
