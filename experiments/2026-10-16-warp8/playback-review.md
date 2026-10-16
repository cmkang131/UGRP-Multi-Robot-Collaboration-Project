# 진행 중 prefix 검토 — 성공/실패 판정 아님

두 알려진 실패 시드의 **새 gcp3 실행 prefix**를 검토했다. CPU 성공을 새 성공으로 세지 않는다.
검토 범위는 각 +0.0–7.0 SIM초, 전체2Hz 각15장(30장 전부)이다. 아직 terminal10Hz 검토가 아니며
진동·빠른 왕복·물리 실패 원인을 주장하지 않는다. ffmpeg3배속 영상 두 개는 gcp2에 남기고
ffprobe H.264/960×270/6fps/15프레임을 확인했다. Mac에는 몽타주와 메타데이터만 회수했다.

- world000/seed8318711: +0–1초 r1은 동료·바닥, r2는 빔을 본다. +1.5–2초에는 둘 다
  바닥 중심 화면이 된다. +2.5–4초 r2는 빔 파랑 끝을 다시 보고, r1은 둘러보는 동안 맡은 끝이
  화면에 거의 없다. +4.5–7초에도 r1은 바닥·벽, r2는 빔을 반복해서 본다. 평가 개요에서 빔은
  바닥에 있고 두 로봇은 접근 중이다. 들기 완료나 실패로 판정하지 않는다.
- world001/seed8318728: +0–1초 r2는 빔, r1은 주로 바닥이다. +1.5–2초 둘 다 바닥,
  +2.5–3.5초 r1 화면 아래쪽에 청록 끝이 들어온다. +4–5.5초 두 자기 화면에 빔이 반복해서
  보이고 r1이 청록 끝에 가까워진다. +6–7초 청록 끝이 r1 화면 가장자리로 이동하고 r2는
  빔 파랑 쪽을 본다. 평가 개요에서 접근·회전이 이어지고 빔은 바닥에 있다.

원래 자기 RGB를 그대로 썼다. 개요는 동일 시각 evaluator `joints/qpos`로 CPU에서
`mj_kinematics`만 호출해 복원했다. qvel=0은 렌더에 쓰이지 않으며 물리 step은0이다.
미완료 snapshot에서 evaluator 행이 아직 flush되지 않은 RGB 시각은 파생 영상에서 제외했고,
원본 snapshot은 보존했다. 처음 preview의 asset 상대경로 오류와 검증 guard 실패는 보존하고,
warp6 메타데이터에 기록된 정확한 adapter835ccef2 asset root로 해결했다. gcp3 제어 경로는 불변이다.

원본: gcp2 `/home/ugrp/ugrp-sim/runs/warp8-prefix-0713/beam40-r1/`.
파생 영상: gcp2 `/home/ugrp/ugrp-sim/ops-reviews/warp8/playback/warp8-prefix-0713/v3-world-000/`,
`v3-world-001/`. Mac 몽타주: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/warp8-prefix-0713/`.
최종 실패1–2개·성공1개의 전체2Hz/마지막10SIM초10Hz와 대표 영상 회수는 아직 미완료다.
