# 코디네이터용 VIS4 렌더 요청 — 아직 실행하지 않음

현재 dev 비교는 기존 RGB/라벨/관측 캐시만으로 가능하다. **추가 dev 렌더 0개**.
아래는 새 독립 test의 준비 목록이며, 결과를 보고 경로나 seed를 고르는 용도가 아니다.
추가 VISW σ 작업도 기존 자기 추정/명령/평가 기록만 사용해 완료했다. VISW에는
column 관측 캐시가 없어 VISW 자체 오라클은 재생하지 않았다. 새 모델 호출이나
렌더가 필요하다고 묵시적으로 확장하지 않는다. 다음 폐루프 dev는 별도 계획에서
full raw/reported covariance와 적용 관측 시각을 기록하도록 worker를 연결해야 한다.

1. `episodes_v4_DRAFT.json`의 primary 8회. 필요할 때만 표에 고정한 reserve 순서로
   최대 4회 추가한다. 새 seed·(출발 줄, 상자 칸)·(상자 칸, 슬롯) 쌍은 기존
   train/dev/test 31회와 모두 다르다. metadata 설계이며 궤적 독립성은 아직 모른다.
2. 태그 0개, walls_v3, 기존 카메라·FOV·로봇·접촉 프로필·weld OFF,
   동일한 교사 `7cedb049`를 유지한다. 교사 편향과 출발 perturbation은
   episode 표의 setup-only 필드다. 학생의 도크 prior는 기존 값 그대로다.
3. 추정 후보·물리 게이트·source/map/config/model/motion 해시와 test 목록을
   커밋한 뒤 DRAFT를 정식 prereg/episode 파일로 승격한다. 현재 사용자의
   **커밋 금지** 지시 때문에 여기서는 이 단계를 수행하지 않았다.
4. `gates_v4.md`의 static-route C(s)≥0.06 m와 문 중심 이탈≤0.02 m 조건을
   확인한다. 기존 planner margin은 0.02 m라 충족 여부를 먼저 검토해야 한다.
   planner를 바꾸면 dev에서 검증하고 별도 실행 버전으로 등록한다. 기존
   성공이나 VIS4 dev 비교가 변경 경로의 검증을 대신하지 않는다.

정식 등록 뒤, 코디네이터가 자기 세션/공용 슬롯을 관리하며 실행할 명령 형식:

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1
export UGRP_V3_SOURCE=/Users/changmin/projects/ugrp-wt/kiro-vision-loc-v3src
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
VIS=/Users/changmin/projects/ugrp-wt/codex-vision-loc-v4/experiments/2026-09-26-vision-loc
OUT=/Users/changmin/projects/ugrp-wt/codex-vision-loc-v4/outputs/vision-loc-v4/render
EPISODES=vl4-test-s1002,vl4-test-s1008,vl4-test-s1009,vl4-test-s1010,vl4-test-s1011,vl4-test-s1015,vl4-test-s1021,vl4-test-s1023
# EPISODES는 위 primary 8회 그대로 정식 등록 시 고정한다.
# prereg_v4.json / episodes_v4.json은 아직 없으므로 현재 실행 불가.
"$PY" scripts/ugrp_session.py run vis4-test-render -- \
  "$PY" scripts/sim_slots.py run --owner codex --label vis4-test-render -- \
  "$PY" "$VIS/run_vl_teacher_render.py" \
  --episodes "$VIS/episodes_v4.json" --only "$EPISODES" --output "$OUT"
```

실행 관리 도구는 코디네이터의 최신 checkout에서 확인한다. 여기 브랜치에 없는
`sim_slots.py`를 있다고 가정하지 않는다. `--allow-dirty`나 smoke 우회로 dataset을 만들지 않는다.
`--owner`는 실제 실행을 소유하는 코디네이터의 에이전트명으로 바꾼다.
renderer의 `OWN_FILES`는 v3까지만 나열하므로 정식 v4 표·prereg·지도 해시 검사는
코디네이터가 승격 시 추가해야 한다. VIS4 test 추정/채점은 기존 `vision_loc_io.ROUNDS`에
등록되지 않아 현재 거부된다. 새 test 한 번 채점 guard와 source hash guard도 승격 때
함께 등록·검증한다. 기존 scorer는 새 결합 기하 게이트·yaw p99·연속 초과 시간·episode
bootstrap을 구현하지 않으므로, 이 계산과 회차별 판정도 새 test 전에 구현·검증해야 한다.
**이 초안을 바로 실행하는 명령은 제공하지 않는다.**

렌더 후·분할 모델/필터 실행 전에 할 중복 감사:

- 새 audit 입력 폴더에 기존 원본과 새 렌더를 가리키는 읽기 전용 용도 symlink를
  만든다. 기존 원본 디렉터리는 수정하지 않는다.
- VISW r2는 추가 reference `VISW-vl3-dev-s942-r2`로 포함한다. seed 942는 이미
  금지 목록에 있지만 폐루프의 RGB/궤적도 비교해야 한다. VISW의
  `robots/r2/inputs`, r2 평가 행, 실제 JPEG 경로를 기존 `overlap_check.py` 입력
  형식으로 바꾸는 adapter가 아직 없다. worktree outputs에 정규화한 복사/manifest를
  만들고 실제 JPEG byte 해시·시각·frame 연결을 검증한 뒤 아래 형식으로 실행한다.
  원본 폴더 symlink만으로 VISW 형식이 호환된다고 가정하지 않는다.
- `overlap_check.py --render-root <audit-inputs> --candidates <새 목록> --references
  <이전 31회 + VISW r2 + 새 목록> --output <새 audit JSON> --fail`로 후보 자신을 제외한
  모든 old/new 쌍을 검사한다. 바이트 JPEG 중복, 같은 발행 팔 자세에서
  1 mm/0.1° 이내 프레임, 같은 길이 정렬 궤적 중복 중 하나라도 있으면 제외한다.
- 후보끼리 겹치면 관련 회차를 **모두** 제외한다. 단일 교차 프레임도 예외로
  완화하지 않는다. 2 cm/2° 근접 비율은 전체/문 구간에 따로 보고한다.
- 충돌·교사 실패·끼임·시간 초과와 필터 실패를 구분한다. 교사 실패는 성능을
  보고한 뒤 제외할 이유가 아니며 모든 등록 회차를 보존한다. independence
  탈락/렌더 파일 불완전만 예비 회차로 대체하고, 예비도 모든 old/new와 감사한다.
- 최소 6개의 독립·완전 회차가 없거나 문/배치 표본이 부족하면
  INSUFFICIENT_DATA로 끝낸다. 추가 seed 탐색이나 임계값 조정은 금지한다.
