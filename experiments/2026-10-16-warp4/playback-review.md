# 실제 파일 검토

- beam non-MPS R2/world0: world1.7–3.9초(+0–2.2SIM). 전체2Hz5프레임과 terminal10Hz23프레임, native6시점 파일을 직접 확인했다. world1.7초 r2는 빔·양끝 띠를 본다.1.8–2.2초 pan에 따라 빔이 오른쪽으로 빠진다.2.3–2.8초 r1은 왼쪽 동료, r2는 화면 오른쪽 빔 끝을 본다.3.1–3.7초 두 자기 영상이 주로 단색 구역 바닥이고3.8–3.9초 r1 왼쪽에 동료가 다시 보인다. 집기/들기 완료 장면은 없다. 2Hz만 보면 짧은 화면 이탈 시점을 놓치며10Hz에서3.0→3.1초 전환을 확인했다.
- release S3 non-MPS R3-attempt2/world0: world1.7–2.9초(+0–1.2SIM). 전체2Hz3프레임·terminal10Hz13프레임을 직접 확인했다. 두 로봇은 빔 길이 방향을 마주 보고 있으며 초기 팬 후 팔/집게가 내려오는 prefix다. 실제 release 구간이나 공동 들기 성공을 보지 못했다.

두 영상은 gcp2에서 평가 qpos로 만든 개요와 실제 저장 r1/r2 JPEG를 나란히 붙인3배속이다. 개요만 평가 카메라를 맞췄고 제어 입력에 넣지 않았다. ffprobe 정상,16381/11489바이트, 두 회수 MP4의 SHA가 remote meta와 일치했다.

Mac: `outputs/e2e18-admin/playback/warp4-beampair-short-r2/`, `outputs/e2e18-admin/playback/warp4-release-s3-short/`. 새 MJWarp 성공 영상은 없어 성공1개 비교 미완료다. 제어 실패 원인으로 단정하지 않는다.
