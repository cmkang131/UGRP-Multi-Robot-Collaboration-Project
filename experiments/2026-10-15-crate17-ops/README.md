# crate17 운영 결과

소스 `4eb7d4724cf0b1ce316ab44655d78f6fbe3c4508`, gcp1 n4-highcpu-64. full 재현 성공0/5시도(완료실패4·감독중단1), no_clearance 성공0/5(완료실패5). 후보·과거SHA·호스트 간 합산 없음. 신규 진단은 후보별10회 전부 차단했다. 관문·기록·학습 미제출.

완료9건 모두 정렬 재관측3회 소진으로 파지 전에 종료했다. 10회×6시각×3시점=180프레임 파일을 직접 확인했고, 서로 다른 청록/파랑 끝으로 접근했다. 감사10/10 활성·invisible_measurements=0·held_world_reads=0. 마지막3초 원장에서는1–4ms 펄스 반복과 미미한 물리 응답이 보이지만 정확한 물리 원인은 아직 분해하지 않았다.

전체wall/SIM 중앙 full 4.072, no_clearance 4.041. 첫30초 자료는 각2/5만 있어 속도 관문 통과가 아니다. 원본·회수·복원·STOP 해시 검증 후 소유 PID/임대0·예약released. 원본은 GCP 영구디스크, Mac은 경량 원장·선별영상만 보존한다.

전체30행 기록·원본위치·결과해시: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/crate17-4eb7d472.json` (SHA256 `f92e2fcd5412b5d24a816547099caf0bf486f1ffbbf87d88d530b5e022718afa`). 수정SHA와 새 큐 필요.
