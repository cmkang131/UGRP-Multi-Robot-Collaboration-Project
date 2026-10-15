# 실행·중단·출처 기록

- 작업 worktree: `/Users/changmin/projects/ugrp-wt/warp-flows`, `claude/warp-flows`. A 문서를 공통 조상142dbf04에서 작성한 뒤 커밋된 warp1 API를 병합했다. R3 물리 소스는 `521f258508ccc7d24d667a158a2b26a1b3740ee9`; 후속 문서/분석 커밋을 실행 소스로 바꿔 적지 않는다.
- 고정 teacher adapter `08f129213031255dd188e20df832bb6714dfca9a`, dependency `26f84d0f0ada1c33473c83cca2d3415ce51bd247`. C 비교 소스 `70553d2f4235b28648c188b26f9b2a03fa32a19d`, GPU R2 `54563a38ecd9c08523401e5c231667fef19ec08d`. C3.12 자산 준비의 실제 소스 `14fbdf6a4da4ca2793c9c0b2859be141a8fb6848`.
- VM은 기존 gcp2 n4/L4만 썼다. gcloud 시작/정지/복사/스냅샷은 실행하지 않았다. 초기 L4 임대 시각2026-10-15 18:24:38.739602 UTC, 누적3시간 마감21:24:38.739602 UTC를 라운드가 바뀌어도 유지했다. 임대와 GPU 메모리/CPU 실행 수를 먼저 확인했다. CPU는 최대16개 자기 프로세스, 전체40 이하 admission을 검사했다. GPU N256은1개 실행 프로세스의 세계 수다.
- 원격 소스는 직접 `/home/ugrp/ugrp-sim/git-shared.git`을 `git clone --reference … --shared --no-checkout …`로 참조했다. 다른 사본의 alternates를 사슬로 참조하지 않았다. 현재 snapshot의 누락 객체만 pack으로 전송하고, shallow HEAD·tracked clean·direct alternates를 검사했다. 전체 이력 복사·공유 저장소 gc/prune·원본 삭제는 없다.
- R1은 혼합 장면의 모델 차이를 발견해 **자기 coordinator/PID만** 중단했다. 실제 파지 실패가 아니다. R2 N1 성공이 저장된 뒤 watcher가 자기 coordinator9052의 후속 미시작 배치를 취소했다. 두 job의 원래 KeyboardInterrupt/cleanup은 보존했다. 완료 N1의 최종 summary·79개 파일 해시로 성공을 확인했다. 미시작 N16/64/256을 완료로 세지 않는다.
- R3는 N16 prefix 완료 뒤, 단일 공유 모델 제약과 실측 처리량 열세를 근거로19:44:31.839623 UTC에 자기 coordinator15876을 중단했다. 현재 조정 기록의 중단 방향과도 일치한다. N64 중단·N256/혼합6 미시작을 유지하며 GPU 작업을 추가하지 않았다. 별도 예산 watcher는 자기 임대가 사라진 뒤 정상 종료됐다.
- R3의 고정1 SIM초 처리량 구간은 N16→64→256, 이후 여섯 시드 N16 전체 교사다. 짧은 구간은 성공/실패 관문이 아니고 계획한 cap_end다. 전체 wall 예산으로 중단되면 별도 `cap_end/user_L4_wall_budget`로 정규화하며 원본 HOST_ERROR/KeyboardInterrupt는 삭제하지 않는다. 미완료 세계의 부분 SIM초를 완료 처리량으로 넣지 않는다.

## 작업 중 오류와 바로잡은 범위

1. `claude/warp-act` 원격 브랜치가 없어 Draft PR의 base는 `claude/simalt-pilot`이다. warp1의 원격 ref가 생기면 retarget할 수 있다. 다른 작업 브랜치를 대신 push하지 않았다. PR #531은 Refs #523, HOLD_SCENE/미승인이다.
2. partial shared 저장소에서 누락 객체를 `cat-file --batch-check`로 조회하자 lazy fetch가 걸렸다. 그때 확인한 자기 helper만 종료하고 `--batch-all-objects --batch-check`의 이미 있는 객체 목록과 비교하는 방식으로 바꿨다.
3. CPU shared 저장소에는 main ref가 없어 clone의 `--branch main`이 실패했다. 참조 저장소의 기본 ref를 가정하지 않고 snapshot SHA를 직접 고정했다.
4. 전부27.9초 전에 성공한 CPU 시드에서 first30 표본이 비어 median 계산이 실패했다. N=0/median=null로 기록하도록 분석만 고쳤다. 성공을30초까지 억지로 늘리거나 반복 표본을 만들지 않았다.
5. 자산 준비 helper에 첫8자리가 같은 잘못된 전체 SHA를 넘겼다. 실제 checkout과 export6개의 `summary.source_sha`는 모두 위14fbdf6a4d…였다. 원본 log/ERROR를 유지하고 [정정 원장](runtime/source-pin-correction.json)에 실제 HEAD와6개 summary 해시를 썼다. 이후 helper는 진행 전에 전체 SHA 일치를 assert한다. 자산6개 초기화는 각각 C1.3 SIM초이고 GPU teacher rollout0이다.
6. 직접 세계별 모델 배열로 합치는 preflight가 `dof_length` 차이를 거부했다. [수정 전 거부표](rejection_table-before-r3.json)를 기록하고, upstream에서 허용하지 않는 필드를 바꾸지 않는 정확한 모델 묶음 경로로 바꿨다. 같은 `WarpTransport`의 graph 제출/완료 단계만 나눴으며 새 physics 구현은 없다.
7. read-only 분석의 plain `result.json` 존재 검사 때문에 압축된5개 결과를 처음 건너뛰었다. `.zst`도 확인하고16개 전부 재분석했다. CPU 결과 본체·명령 비교·성공 수는 바뀌지 않았다.

Mac에서는 순수 비물리 테스트17개와 문서/AST/해시 검증만 수행했다. 물리·렌더·GUI·학습·모델 호출은0이다. gcp2에서 렌더한 프레임띠를 파일로 읽고 영상 확인에는 ffprobe만 사용했다. 프로젝트 결과는 로컬/GitHub에 보존했다.

최종 CPU/L4 점검에서 자기 활성 실행0·자기 임대0을 확인했다. CPU에는 warp1/beampair7/reloc16/gatesv5, L4에는 warp1/rl1b 임대가 남아 두 VM을 정지하지 않았다. L4 첫 임대부터 마지막 read-only 점검까지5160.44초로3시간 이하이다. 마지막 비물리 점검은17 passed/0.29s다. worktree 안에는 가상환경이 없어 첫 상대 경로 호출은 실패했고, 기존 primary의 `.venv-sim-worker-mac` 절대경로를 재사용했다. 중복 환경은 만들지 않았다.
