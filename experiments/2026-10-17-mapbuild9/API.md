# mapbuild9 API 계약

`harness.mapbuild_amcl.StaticAMCL(static_map, calibration, requirements, option="off", method="static_amcl_v1", profile=...)`.
새 방식은 `selfmap_map_correction_v1` 선택일 때만 켠다. 입력은 자기 명령+LK에서
얻은 상대 SE2 증분, 자기 RGB 가상 벽 scan/원래96열, 발행 servo, 허용 정적 지도다.
초기 전역 위치/측정 관절/화물 정답/접촉/top 영상은 받지 않는다.

`step(t, frame_id, delta, scan, servo=...)`는 posterior 제안·분산·ESS·관측/재표본화
원장을 돌려준다. 현재 모든 profile은 실제 경로 자격이 없어 `runtime_qualified=false`,
`ready_for_handoff=false`, `adopted_pose=null`이다. `converged`는 분포 모양/ESS
기준 통과일 뿐 위치 정답이나 실제 운반 허가가 아니다. 실제 소스/해시는
[api-sha256.json](api-sha256.json), 수용 실패는 [summary.json](summary.json).

자기 관측 지도는 `local_map` 키프레임으로 별도 저장하고 정적 위치 보정의
참조로 쓰지 않는다. static global candidate를 미등록 pose/identity/spawn fallback으로
채택하지 않는다. 기존 `SelfMapCorrection`이나 live capture/ACT/LLM 실행기에는
이 새 방식을 아직 연결하지 않았다. 실제 인계/적재/내려놓기 제출은 거부한다.

CPU/MJWarp 접촉·카메라 배치/FOV·기구는 이 API가 바꾸지 않는다. 정적 지도
scan 분포 및 운동 분산의 적재 자격은 확인 안 됨이다.
