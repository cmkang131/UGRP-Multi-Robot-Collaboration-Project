# warp8 — gcp3 빔 짝·release MJWarp 관문 (R1 HOST_ERROR, R2 실행 중)

warp6와 같은 `codex/warp6`, PR #557 DRAFT에서 이어간다. gcp2 R3의 CUDA700은
gcp3 단독·MPS off·원래 graph 25.3 SIM초에서 **단독 환경에서 미재현**이었다.
공유 GPU/MPS 다중 client와 양립하지만 원인을 확정하지 않는다.
새 CUDA700 발생 시 해당 시드만 memcheck로 재현하고 같은 결함 3라운드면 중단한다.

빔40세계 한 배치, release A40·B40을 계획한다. release A40의 단일 배치 참조 초기화는 `canonical model free-root names differ`로
거부됐다. 서로 다른 모델 topology를 유지해 A/B 각각 S1 14·S3 13·S6 13으로
분리한다. 각 시나리오의 A/B plan은 바이트가 아닌 JSON 값으로 전수 동일함을 확인했고
참조는 실제 XML SHA로 엄격하게 대조한다. 메모리 부족은 세계 수를 줄여 실측을 기록한다.
판정 속도 = 배치 wall / (배치 SIM초 × 세계 수)다. 완료 세계의 padding도 이 물리 처리량 분모에 포함한다.
완료 시각을 반영한 실제 작업 처리량은 별도로 기록하며 판정에 섞지 않는다.
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
그 뒤 완료 세계 padding을 판정 분모에서 빼려던 기록 변경은 사용자 지정 식과 달라
채택하지 않았다. 후속 실제 실행은 지정 식을 명시한 소스35e94d5d 이후를 쓴다.
진행 중 빔 소스와 원래 기록은 유지하고, 원본으로 물리 처리량과 실제 작업 처리량을
각각 다시 센다. 제어·물리는 불변이며 관련 비물리11PASS다.

## R1 관문 중단과 R2 후보

`beam40-r1`은 control225/+22.5SIM까지 정상 저장 뒤 step226에서 world008/seed8318706의
NVMAX bit128로 중단됐다. 완료 성공1(world028, task17.4SIM), cap_end0, 미완료 HOST_ERROR39다.
물리 실패0이라는 뜻이 아니라39건의 물리 결과를 모른다는 뜻이다. CUDA700은 미재현이다.
첫30SIM은 미완료라 속도 관문 통과로 보고하지 않는다. [원본 거부표](beam-r1-rejection_table.json).

실제 초기110→할당128, 마지막 활성156, 총 nv222다. 기본off `full_active_dof_workspace_v1`로
공식 기본 방식인 정확한 전체 nv를 할당하는 후보를 만들었다([근거](references.md)). NoSlip10,
dt, 접촉·마찰·m.opt solver 설정과 행동 경로는 유지한다. upstream compact 정규화의 pad/ctol은
할당 크기에 따라 바뀌므로 기록하며 바이트 동등성을 주장하지 않는다. 관련 비물리30PASS다.
R2는 새 실패seed8318706을 맨 앞에 놓고 원래 canonical XML과40건의 참조를 재사용한다.
R1과 R2는 합산하지 않는다. R2는08:38:49UTC 제출했고 아직 완료되지 않았다. release는 미제출이다. R2 고정 소스는 `175281c8922453465f8bf32707e22988e78b8812`다.

성공1개·HOST_ERROR1개의 원본 재계수와 대표 영상을 회수했다. full2Hz의 초기0.5SIM 동기화 오류는
native NPZ로 고쳐 중복174/221행 qpos가 비트 일치함을 확인했다. 수정본 전체2Hz36/46장과
마지막10SIM/10Hz 각100장을 전부 봤다. [대표 영상·검증](representative-native-sync.json),
[영상 검토](playback-review.md). 원래 파생본은 보존하고 수정본을 최종 대표 영상으로 쓴다.

R2 제출 전 실제 VM scheduling에서8h 필드가 제거된 것을 확인했다. warp8의 명시적8h 유지 지시에 따라
타 lease/GPU client 부재 확인 후 gcp3만 정지했고, maxRunDuration28800/STOP을 복원·조회했다.
재시작으로 VM 상한 기준 시각이 바뀌어도 이 작업의 기존 정리 시한14:05UTC는 연장하지 않는다.
[설정 복원 기록](scheduling-restored.json). gcp2는 변경하지 않았다.

R1의별도재계수는실제`claude-haiku-4-5-20251001`이생성한독립판정코드를gcp2 CPU에서실행해확인했다.
작업자가상태명complete·누락감사필드·SHA메타타입만스키마에맞췄으며물리계산은바꾸지않았다.
결과complete1/HOST_ERROR39,175평가행·연속hold3.0000000000000036초·교사2/2,
원본과불일치0·오류0·입력감사0값40건(전체1/prefix39)으로기존계수와같다.
[R1 Haiku코드실행결과](R1-haiku-counter-result.json), [코드/보정근거](R1-haiku-counter-provenance.json).
모델의문장응답은원본증거로쓰지않았고,잘못된상태분류/소스불일치지적을거부했다.
