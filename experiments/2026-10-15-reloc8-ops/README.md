# reloc8 지정 대기열 운영 기록

- carry 0459c03c: 진단0/2(재획득실패1·감독중단1), 잔여9 차단.
- selfmap 66928f23: 30초기록1/1 후 첫180초 실행을97.7SIM초에서 회전 주기2 진동으로 감독중단. 93572 미제출 차단. 서로 다른 시간상한 결과를 성공률로 합산하지 않는다.
- 입력 감사: 제출4건 모두 invisible_measurements=0, held_world_reads=0.
- 원본은 GCP 영속 디스크, 회수 텍스트·선별 프레임은 기본 체크아웃 outputs/gcp1-runs와 outputs/e2e18-admin/gcp-reports/reloc8-0459c03c-66928f23-ops.
- summary JSON에 result/manifest 해시·검증·직접 본 영상·미검증 한계를 기록했다. carry의 원해상도 recovery RGB는 실행기에 보존되지 않았다.
- 관문·학습·새 학습용 기록 미실행. 로컬 기록이며 커밋·push·병합하지 않았다.
