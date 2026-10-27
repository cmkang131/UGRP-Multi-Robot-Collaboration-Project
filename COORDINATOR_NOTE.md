
## 2026-10-16 coordinator: reloc21 인계
reloc21 CPU R1 끝, NOT_READY (place 0/6, 완주 0/6, cap_end 6, 재위치추정 소진 2). 원인표: /Users/changmin/projects/ugrp-wt/reloc21/experiments/2026-10-16-reloc21/root-cause.md, PR #547.
- 후보(progress/complete)는 위치 오차 악화로 미채택 — MJWarp로 옮길 때 기본 off 유지.
- 반복 제거 결함 수정(비물리 41 통과, 물리 미검증)은 MJWarp R에서 물리 확인.
- 남은 원인: 출발 enclosure 거부 1765·hold 29.7%, 목적지 색 획득 0. 거부 사유 분포 표부터.
- Mac 여유 ~15 GiB: Mac 회수는 요약·몽타주만.

## 2026-10-16 coordinator: gcp4 L4 (warp9)
사용자 "프로젝트 하나 더 만들어서 L4 하나 더 써" → 네 번째 프로젝트 ugrp-sim-d-1016, L4 `ugrp-act-l4-gcp4`(gcpctl 별칭 gcp4)를 gcp4setup이 준비 중. ops-alert에 "gcp4setup: READY"가 뜨면 warp9의 단독 측정은 gcp3 대기 대신 gcp4에서 한다(먼저 비는 쪽 사용). 호스트별로 표기하고 합산 금지. gcp4는 실행 상한 없음, 유휴20분·budget-stop 유지.

[조정자 19:48] mapbuild2가 MJWarp 전진 실제 0.402mm vs 예측 12.9mm(32배)·tilt 6° 측정. drivecheck 작업자가 C vs Warp 짝 비교 중. warp10의 첫 30 SIM초/운반 점검에서 변위가 비정상이면 처리량 결과와 분리해 기록하고 drivecheck 결과를 기다릴 것(추측 수정 금지).

[조정자 19:57] 사용자 '쳐낼 거' 기준: 지금 도는 첫 30 SIM초 점검만 끝내고, R1/R2 수정을 기본 off 토글로 커밋·push·draft PR(#550 위)로 묶은 뒤 추가 측정 없이 종료. gcp4 정지 확인. ops-alert에 'warp10: DONE ...' 한 줄.

[조정자 19:58] 앞 메모 취소: 사용자 재확인 '그래도 모두 MJWarp로 계속 옮겨'. 모든 흐름이 MJWarp에서 돌므로 처리량이 핵심 경로가 됨(warp8 N40 실행당 5.6, 차단 6.0 근접). 첫 30 SIM초 점검 뒤 종료하지 말고 계속: R1/R2 수정 커밋·push, 다음으로 실행당 wall/SIM 가장 큰 구간부터(표로 확인 후) 줄이기. 3라운드 상한 유지.

[조정자 19:59] noslip·접촉 설정 재설계는 warpfit(gcp6) 작업자가 맡음. warp10은 host 쪽(렌더·D2H·제어)만, 물리 옵션(noslip/cone/solver) 건드리지 말 것.

[조정자 20:04] 충돌 방지 규칙(필수): /Users/changmin/projects/ugrp/outputs/e2e18-admin/agent-ownership.md 를 읽고 따를 것. 자기 VM·자기 파일 범위 밖은 건드리지 말 것. 다음 ops-alert 보고 줄 끝에 'ownership-ack' 를 붙일 것.
