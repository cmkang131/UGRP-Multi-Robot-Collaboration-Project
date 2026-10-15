# reloc19 — 목적지 시각 획득

진행 중, 아직 READY 아님. 시작 reloc18 HEAD `d271566155d6946240b53c15ddb5eb1f8c42de99`.
기본off `destination_visual_acquire_v1`, `carry_relocalize_v1`를 분리한다. 지도 주행·목적지 탐색은 코드, 근거리교사는 기존 경로이며 ACT 대체 학생 성공으로 보고하지 않는다. 모델 호출·Mac 물리·렌더·GUI 없음. gcp2 CPU, 자체동시6≤8·lease합계≤40, 최대3라운드. 저장예산24회×250MB+분석1GB=7GB.

원인과 변경 전 거부 분포는 `prior-rejection-table.json`: reloc18 R3 실제 place 관문93프레임 중 기하93/93·목적지색0/93, advance/lower/open0. 운반후보 최종거부2/2는destination_floor_not_visible. 동일조건 성공원본이 없어 성공영상 비교 요건은미충족.

원본 93315 전체1.5–79.5초2Hz 및69.7–79.7초10Hz, 93266 전체1.5–145.0초2Hz 및135.2–145.2초10Hz 프레임띠를 직접 읽었다. 93315 초반빨간화물 접근·들기 뒤 바닥을보며 주행, 마지막회색바닥에서정지. 93266 노란화물접근·들기 후후반벽이확대, 마지막보라벽과회색바닥조각. 듬성한 프레임과달리 최종확인에서3초간 같은비목적지장면을보는지구분했다. 프레임 원본은primary outputs/e2e18-admin/playback/reloc18-r3-{93266,93315}/. 해당 gcp2 ffmpeg 파생영상과ffprobe 검증·해시는reloc18 기록에있다.

[방법 조사·미구현 범위·상수 근거](references.md). A는 목적지색 획득→바닥명목역투영 서보→기존 full-footprint RGB/FK gate .3초→기존 place. 색은호밍특징이며 실제place판정은분리한다. B는 구역크기에비해예측공분산이커지면들고몸회전해RGB보정기회확보, 보정실패를숨기지않는다.

짧은93584/93583은위치추정전용코호트, 긴93266/93315는전체운반계획으로따로보고한다. cap_end·알고리즘실패·HOST_ERROR 구분, 입력감사·원본sha·실패프레임6장이상·순차관문표를남긴다. 원본은gcp2디스크, Mac회수는요약·몽타주·실패프레임과8MB이하영상만. Google Drive사용안함.
