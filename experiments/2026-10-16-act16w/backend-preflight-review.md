# 서로 다른 시작 상태 보존 — 정적 검토

검토 SHA `e9c97e2eb6ea994e37cf82d0ebe391c517f81be7` (`claude/warp-act`, 03:36 KST).
실행·GPU·물리·렌더0. 실제 런타임 영향은 미측정이며 기존 실패의 원인으로 주장하지 않는다.

P1: `scripts/warp_act_backend.py:120-134`에서 최초 `put_data(m,d,nworld=N)`
이후 각 context의 qpos/qvel을 쌓아 GPU에 복사하지만, 워밍업 뒤 134행에서
동일한 첫 world의 `d`로 다시 `put_data`를 호출하여 `self.wd`를 바꾼다.
그 뒤 렌더/첫 스텝 전에 per-world qpos/qvel을 재복사하는 경로가 없다.
서로 다른 시작 qpos를 가진 context0/context1이 있어도 두 번째 생성에는 context1이
전달되지 않는다. 복제 시작 파일럿에서는 가려질 수 있어 새40 평가 전에 확인해야 한다.

확인 대상: 워밍업 폐기 뒤 실제 wd.qpos/qvel과 각 context의 시작 상태 대응,
첫 자기 RGB/첫 mirror의 world별 대응. 초기 복사와 검증은 정상 physics forward의
파생 상태·접촉 warmstart와도 일치해야 한다. 임의 상태를 새 학생 입력으로 전달하지 않는다.

참고: [공식 MJWarp put_data 소스](https://github.com/google-deepmind/mujoco_warp/blob/main/mujoco_warp/_src/io.py)
는 단일 host MjData를 받아 nworld로 tile한다. 이는 웹 main의 소스 확인이며 설치된
버전의 해시·실제 N16 검증을 대신하지 않는다.

재현 검토: `git show e9c97e2eb6ea994e37cf82d0ebe391c517f81be7:scripts/warp_act_backend.py`.
수정은 warp1의 소유 checkout에 하지 않았다. 시작 조건 대기를 유지한다.
