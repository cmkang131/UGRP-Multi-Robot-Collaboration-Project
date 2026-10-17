# warp1 — ACT solo 교사 MJWarp 배치 경로

DEV / 검증 진행 중. 기본 off `physics_backend=mjwarp_batch_v1`. PR #524 `142dbf04` 위에 쌓으며 기존 C 실행기 파일은 변경하지 않는다. 상태·수치의 최종 근거는 완료 시 summary/rejection_table에 기록한다. 장면 선택과 ≥95%·최소40회 자체 교사 관문은 HOLD_SCENE·미승인이다.

[이식 설계와 직접 MjData 읽기 목록](design.md) · [공식 자료와 확인 범위](references.md) · [초기 거부 분포](rejection-before-runtime.json).

물리/명령/RGB transport는 배치화한다. 교사 상태기계·IK·C ray 가시성 adapter에는 세계별 Python 루프가 남는다. 성공 평가는 GPU contact force와 별도 Score이며 teacher로 반환하지 않는다. 자기 RGB·발행 이력·visible+not-held 대상 상대량 경계를 유지하고 close~open 구간 lazy read를 차단한다. 학습 기록·ACT 학생 통합은 별도 미완료이며 미승인 기록은 거부한다.

장면은 현재 `grasp_act_scene_v1 / floor_light_v1 / v3 runtime camera / real_v1 stiffness / native v7 / mesh rollers / weld off`이다. scenetex5는 아직 적용하지 않는다. 반투명 구역의 C/Warp RGB 차이는 보존·보고하고 장면을 숨기거나 바꾸지 않는다.

## 실행 경계

Mac에서는 비물리 시험만 한다. 실제 실행은 `ugrp-sim-b-1014` / `ugrp-act-l4-gcp2` 및 CPU 비교 `ugrp-sim-gcp2`만 쓰며 임대 파일을 먼저 만든다. L4 4시간 상한, 기존8h STOP·idle20분·budget-stop 유지. 다른 작업 임대/프로세스가 있으면 VM을 정지하지 않는다. raw 분석/영상 생성은 gcp2, Mac은 요약·몽타주·검토 영상만 회수한다.

표준 catalog ID `warp-act-teacher`는 `scripts.run_warp_act_teacher` 어댑터를 가리킨다. 직접 CLI의 `--physics-backend` 기본은 off이며 macOS·다른 프로젝트/VM을 simulator import 전에 거부한다. 실제 명령·소스 SHA는 각 실행 summary의 reproduce에 보존한다.

```sh
python -m scripts.run_warp_act_teacher --physics-backend mjwarp_batch_v1 \
  --teacher-source /home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e \
  --plan /home/ugrp/ugrp-sim/pilot-plans.json --episode 0 --nworld 16 \
  --compiled-reference-v1 /home/ugrp/ugrp-sim/runs/warp1/export-osmesa-seed0/compiled-312.json \
  --compiled-geometry-312-v1 /home/ugrp/ugrp-sim/runs/warp1/export-osmesa-seed0/compiled-geometry312.npz \
  --cap-s 60 --vm-hourly-usd 1.096 --out /home/ugrp/ugrp-sim/runs/warp1/NEW_UNIQUE_RUN
```

`--world-episodes`는 세계별 plan index를 받는다. 같은 정적 XML에서 free-joint 초기 pos/quat 선언만 다른 세계를 묶고 정적 지도·재질·카메라·기하가 다르면 거부한다. 같은 seed를 복제한 처리량 world를 독립 성공률 표본으로 세지 않는다. 부분 world reset/새 모델 교체는 이 초기 transport에 구현하지 않았다.
