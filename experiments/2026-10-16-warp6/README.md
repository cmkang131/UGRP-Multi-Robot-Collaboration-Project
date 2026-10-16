# warp6 — gcp3 단독 MJWarp 진단 / NOT_READY

warp4 R3의 CUDA700·release SIGSEGV를 조사했다. **최초 실패 커널·버퍼와 수정안은 확보하지 못했다. 빔40·release A40/B40은 모두 미제출**이다. CPU beampair7·release25와 합산하지 않았다. [PR #557](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/557)은 DRAFT이며 병합하지 않았다. `codex/warp6`는 `claude/warp4`의 `0a733c80615f1b72ff300c96777c4f0b2fc3700f` 위에 쌓았다.

## 확인한 결과

| gcp3 단독 진단 | 세계 수 | 진행·종료 | 해석 |
|---|---:|---|---|
| R1 Compute Sanitizer memcheck | 4 | 초기화274.5wall초 뒤 첫 제어스텝 미완료, 감독 TERM/exit15 | CUDA 재현·배제 아님 |
| R2 Warp debug | 4 | CCD 컴파일 RSS12.4GB, warmup 전 TERM/exit−15 | 기존 결함 재현 아님 |
| R3 launch별 verify+버퍼 기록 | 4 | 완료25틱/2.5SIM, TERM/exit−15 | nacon≤112/128, nefc≤157/256, awake≤110/128, 기록10,201행에 overflow0 |
| 원래 graph 빔 prefix | 4 | 15틱/1.5SIM, exit0 | diagnostic_prefix_complete, 교사 완주0 |
| 원래 graph release S1 prefix | 6 | 15틱/1.5SIM, exit0 | diagnostic_prefix_complete, 교사 완주0 |
| 원래 graph release S3 prefix | 2 | 15틱/1.5SIM, exit0 | diagnostic_prefix_complete, 교사 완주0 |
| 원래 graph 빔 연장 | 4 | 253틱/25.3SIM, 감독 INT/exit−2 | 속도 수용 불가, CUDA 오류 미재현, 교사 완주0 |
| NXN 커널 비용 측정 | 4 | 폐기 warmup 1step+진단1틱, exit0 | 성능 원인 탐색용, 교사 완주0 |

각 시도는 별도 모집단이다. 모든 시도에서 교사 성공·완주·cap_end는0이다. 감독 중단4개는 외부 receipt와 원래 summary를 보존하고 HOST_ERROR·진단 중단으로 분리했다. **동일 CUDA 결함이 세 번 재현된 것이 아니다.** memcheck/debug의 비용 문제와 원래 graph의 속도 수용 불가 때문에 추가 실행을 내지 않았다.

원래 R3 마지막 완료틱은 빔10·release S1 6·S3 14라서 비교 prefix 예산은 최댓값14+다음1틱=15로 정했다. 기존60/180SIM 상한을 바꾸지 않았다. 빔 연장은 원래60SIM 상한으로 시작했으나 +25.3SIM까지 loop1,372.735wall초를 썼다. 남은 SIM이 즉시 끝나도 첫30SIM의 wall/SIM 하한은 **45.758**이어서 기존 중단 기준6을 넘는다. 첫30SIM 완료 측정치·중앙값으로 보고하지 않는다.

## 원인 조사와 한계

- [일차 참고 자료](references.md)를 먼저 조사하고 [직전 R3 거부 분포](prior-rejection_table.json)를 저장했다. 기존 release SIGSEGV8세계·빔 CUDA7004세계는 물리 실패가 아니다.
- [기존 커널 로그](gcp2-r3-kernel-evidence.txt): 03:47:02UTC Xid31/MMU `FAULT_PDE ACCESS_TYPE_VIRT_READ`의 PID73446은 빔이다. release PID73447/73448은 같은 시각 `libcuda.so.580.178.04`에서 SIGSEGV였다. MPS의 fatal fault 전파와 양립하지만 MPS를 유일 원인으로 확정하지 않는다.
- 버퍼 초과·접촉 경계·graph capture·다중 client 사례를 대조했다. 설치본의 특정 upstream #1718 제안 guard는 없었고 해당 PR은 OPEN/미병합이었다. 이것만으로 결함 원인이나 패치 필요를 확정하지 않는다.
- [커널 측정](final/physics-cost-summary.json): 폐기 warmup 한 step의 총7.582ms 중 NoSlip 세 커널이5.548ms(73.17%), broadphase가0.0113ms(0.15%)였다. 정상 실행의 분포·CUDA 원인 증명이 아니다. 기존 SAP_SEGMENTED 선택지를 기본off로 노출했지만 후보 실행에는 적용하지 않았다. NoSlip·시간 간격·solver 반복·접촉·마찰·허용오차를 바꾸지 않았다.
- [영상 검토](playback-review.md): 기존 실패 prefix2개·CPU 성공1개와 새 gcp3 prefix2개·연장1개를 파일로 직접 봤다. 새 연장은 전체2Hz51장, 마지막10SIM초10Hz100장을 전부 검토했다. 새 MJWarp 성공 영상은 없다.

## 구현·검증 범위

`--gcp3-isolated-v1`는 정확한 프로젝트/VM/머신/zone을 검사하고 다른 GPU client·MPS를 거부한다. 신규 옵션은 기본off이며 새 진단에는 placement_graspable_filter_v1를 켰다. `--warp-debug-v1`, `--warp-verify-cuda-v1`, `--warp-workspace-trace-v1`, `--physics-profile-v1`, `--diagnostic-ticks`를 추가했다. verify는 graph를 풀되 기존400 물리substep·명령순서를 유지하고 전역 설정을 복원한다. 진단 종료는 교사 완주·cap_end와 별도 상태다. 기존 실패 직전10SIM초/10Hz 기록 옵션을 유지했다.

관련 **비물리37PASS**: 호스트 입장·모델 구성·명령 스케줄·예외 시 verify 설정 복원. 새 테스트2파일의 CI 등록 및8개 shard/674파일 중 정확히1회 포함을 확인했다. 전체 CI·물리 임무 통과는 별도다.

모든 저장 prefix에서 `held_world_reads=0`, `invisible_measurements=0`, weld off, 모델 호출0, 학습RGB off를 확인했다. 들기·release 완주가 없어 held 구간 전체 감사 통과로 보고하지 않는다. 기존 release25의 특권 setup prefix도 새 visible-only 성공으로 취급하지 않는다.

## 기록·재현·다음 관문

- [최종 요약](final/diagnosis.json), [funnel·거부표](final/rejection_table.json), [대기열](teacher-gate-queue.json). 대기열은 NOT_READY, runs=[], submitted=false이며 절대경로 rejection_table과 SHA를 연결했다.
- 원본: `gcp3:/home/ugrp/ugrp-sim/runs/warp6/`. 시도별 `.command.json`/`.receipt.json`과 거부표에 소스·설정·재현 명령이 있다. 원래 graph 소스는 `82a623ee37c166ac7a9f8eaef7216c905ac1c816`, profile은 `400cdb0da18b538ae94e6bd42c8b0c45d7091d9f`다. 나머지 전체 SHA는 최종 요약에 있다.
- [무결성 검증](final/integrity-verification.json): 4,882파일/91,445,625bytes SHA 전수 일치. 종료된 큰 JSON/JSONL12개는 zstd 후 해제SHA를 확인했다([압축 목록](final/compression-manifest.json)). 원본 해시 인덱스·상세 요약도 해제SHA를 검증했다. Mac 회수는 요약·해시 인덱스 약194KB와 작은 검토 영상·프레임만이다.
- gcp3=프로젝트 ugrp-sim-c-1016, VM ugrp-act-l4-gcp3, g2-standard-8/L4, MuJoCo/MJWarp3.16.0/Warp1.15.0. gcp2 L4의 프로세스·MPS·VM은 변경하지 않았다. gcp2 CPU에서만 영상 분석하고 타작업 lease를 보존했다. gcp1 접근0, 모델키/에이전트 자격증명 전송0.
- 자기 작업 종료·타lease/작업 부재를 확인하고 gcp3를 정지했다.8h STOP·유휴20분·budget-stop을 변경하지 않았다. 원본·공유 Git cache는 보존했다. [호스트 종료 기록](host-stop.json).

다음 실행에는 최초 CUDA 커널/버퍼의 재현 근거와 원인에 대응한 기본off 수정, 속도 수용 문제 해결이 필요하다. 그 뒤 알려진 실패 시드부터 빔40·release A40/B40을 gcp3로 별도 제출한다. 현재 대기열을 승인하거나 CPU 성공으로 대체하면 안 된다.
