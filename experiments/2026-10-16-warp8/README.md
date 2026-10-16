# warp8 — gcp3 단독 빔 짝·release MJWarp 관문 (진행 중)

warp6와 같은 `codex/warp6`, PR #557 DRAFT에서 이어간다. gcp2 R3의 CUDA700은
gcp3 단독·MPS off·원래 graph 25.3 SIM초에서 **단독 환경에서 미재현**이었다.
공유 GPU/MPS 다중 client와 양립하지만 원인을 확정하지 않는다.
새 CUDA700 발생 시 해당 시드만 memcheck로 재현하고 같은 결함 3라운드면 중단한다.

빔40세계 한 배치, release A40·B40을 계획한다. release A40의 단일 배치 참조 초기화는 `canonical model free-root names differ`로
거부됐다. 서로 다른 모델 topology를 유지해 A/B 각각 S1 14·S3 13·S6 13으로
분리한다. 각 시나리오의 A/B plan은 바이트가 아닌 JSON 값으로 전수 동일함을 확인했고
참조는 실제 XML SHA로 엄격하게 대조한다. 메모리 부족은 세계 수를 줄여 실측을 기록한다.
속도 = 배치 wall / 누적 세계 SIM초(동일 길이는 SIM초 × 세계 수)다.
기존 >6 차단을 실행당 환산값에 적용하는 것은 **조정자 결정, 사용자 미확인**이다.
첫30SIM은 본 실행에서 측정하며 setup/compile 비용은 따로 적는다.
물리·NoSlip·시간 간격·성공식·교사 제어를 바꾸지 않는다.

새 후보는 placement_graspable_filter_v1 ON, weld OFF, held_world_reads=0,
학습RGB OFF, 모델호출0, 기존 계산량 예산 ON이다. 실패10SIM/10Hz 디스크 ring을
유지하고 cap_end·HOST_ERROR를 분리한다. CPU beampair7/release25·다른 호스트와 합산하지 않는다.
입력은 warp6 준비본의 알려진 실패 시드 우선 순서를 유지한다.

호스트는 gcp3 / ugrp-sim-c-1016 / ugrp-act-l4-gcp3 / L4 단독이다.
8h STOP·유휴20분·budget-stop을 유지하고 작업 종료 후 타작업 부재를 확인해 정지한다.
gcp2 L4·gcp1을 건드리지 않는다. VM에 모델키·에이전트 자격증명은 보내지 않는다.
실패 분석은 gcp2 CPU에서 lease를 사용한다. Mac 회수는 요약·몽타주·실패 프레임과
8MB 이하 대표 성공1·실패1 영상이며 GUI를 열지 않는다.

원래 빔 관문 소스는 `f75e3442957e8e00c4ed894056b3e06ee32399f0`로 고정했다.
후속 `bcf8241082cb4edf0ff69109481eb781d7483758`은 먼저 완료한 세계의 padding 시간을
속도 분모에서 빼는 기록 수정만 포함한다(제어/물리 불변). 빔의 첫30SIM/전체 속도도
종료 원본으로 재계산하고 원래 기록을 보존한다. 관련 비물리11PASS다.
