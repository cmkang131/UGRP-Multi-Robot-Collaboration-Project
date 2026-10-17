# beamdiag — A/B 원본 실패 분석

분석 전용 완료, 학생 NOT_READY 유지. 새 학습·정책 재추론·물리·시뮬레이터 렌더0. A20/B20과 TRAIN166시드60,023행을 gcp2 CPU에서 분석했다.

copycat 주원인은 미확정이다. 시작40주체 중30개가 학습의0.8m 로컬 범위 밖이며, 반대 끝 자리 먼저 방문은 A3/20·B8/20이다. 정렬 전 GO는 각각20/20이고 한쪽 done 뒤 복구가 끊긴다. A8329000 같은 끝 충돌 가설은 원본과 맞지 않고, B8329019는 배정 끝 교환 상태의 무배정 기준3.4초 들기가 기록돼 있다.

- [전 실행 요약·원본 SHA·측정 정의](summary.json)
- [관문/거부 표](rejection-table.json)
- [상세 한국어 보고서](/Users/changmin/projects/ugrp/outputs/e2e18-admin/research/beamdiag.md)
- 전체 JSON: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/research/beamdiag.json`
- 재현 분석 스크립트: `analysis/`; gcp2 배치 경로는 `/home/ugrp/ugrp-sim/analysis-tools/beamdiag/`.

원본 `/home/ugrp/ugrp-sim/ops-reviews/beamact3/{A,B}/heldout20-v1/`는 보존했다. 각 실행6시각×두 자기 카메라를 읽고 A0/A1/B1/B19와 교사8328003의 전체2Hz·tail10Hz 띠를 직접 읽었다. Mac GUI는 열지 않았다.

코드·제어·데이터·모델 변경 없음. 문서/분석 기록만 추가했고 다른 작업의 C1/C2 파일은 건드리지 않았다. 임대 해제 후 다른 작업 lease가 남아 VM은 정지하지 않았다.
