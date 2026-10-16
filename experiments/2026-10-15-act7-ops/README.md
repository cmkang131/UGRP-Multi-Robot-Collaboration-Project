ACT7 GCP 잡음 교사 관문은 접근 비수렴 제어 실패로 중단했다. 소스 `efb002ad9ecfda23b66c7f6b9c83d912765f8494`, 교사 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`, gcp1 n4-highcpu-64. 이전 교사 census/ACT6 HOST_ERROR와 합산하지 않았다.

계획 40회 중 29회 제출·전부 회수, 성공 28/29·실패 1·미제출 11 BLOCKED다. 계획 기준 성공 28/40이며 40회 성공률은 미측정, 관문 미통과다. training RGB OFF·weld OFF·입력 감사 29/29 inv0/held0·HOST_ERROR0. 기록·변환·학습·학생 폐루프는 제출하지 않았다.

8316627은 노란 상자를 계속 보면서 approach 600틱 동안 align에 진입하지 못하고 60.6 SIM초 phase_timeout. raw 원장 t24→60(상대22.7→58.7초)의 차체 순이동 8.64mm에도 바퀴 명령이 계속 발행됐다. 구동/접촉/경로/잡음 원인층은 미분리다. 개요+r1 자기 카메라 0/12/24/36/48/60초 12장 직접 확인; 다른 로봇의 직접 막힘은 확인되지 않았다. solo r1 실행이므로 r2 자기 카메라 스트림은 생성되지 않았다. 전체 직접 검토 5실행 60프레임(나머지 몽타주는 회수만 했다).

첫30 wall/SIM 중앙 2.746, 전체 2.811. 최초5개 직렬과 이후 최대8 동시의 속도는 summary에 나눠 기록했다. 잡음5180틱·명령 상한 투영4060틱·데드존1498틱(중복 가능), 가시성 임계값 상실→재획득2/2. 화면 가장자리 이탈이나 ACT 학생 회복 성공을 뜻하지 않는다.

원본3643파일·회수623파일·압축복원115건·정지마커58건 SHA 검증. source/noise/host/seed와 원본 결과 해시도 검증했다. 교사 내부 매니페스트의 결과 해시는 어댑터 메타데이터 추가 전 값이므로, 추가 전 JSON을 바이트 그대로 재구성해 대조했다. 원본은 GCP 영속 디스크에만 있으며 별도 원격 백업은 없다. 소유 PID/임대/예약0, VM RUNNING·idle20m/8h STOP 유지; 사용자의 지시에 따라 유휴 가드에 맡겼다.

전체 근거: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act7-efb002ad-ops`. 요약: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act7-efb002ad.json`, SHA256 `8459df46328d1b23a7f37ca83e5da474c89f9b33bb581d4cb8a2f2b33a21f829`. 수정 SHA와 새 큐가 필요하다.
