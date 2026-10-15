# 프레임 띠 직접 검토

화면 앱/브라우저/QuickTime을 열지 않았다. C renderer 복원과 ffmpeg/ffprobe는 gcp2 L4에서만 실행했다. r2는 축소 장면에 없고 검정 패널이다. 이 영상은 자기 카메라의 실제 장착/K/D/fisheye를 유지한 저장 상태 복원이며 Warp renderer 동등성 결과가 아니다.

## 직접 읽은 범위

- simalt3 양성 C3.12 grip: 전체 2Hz 0.5–43.0 SIM초(86시점), 마지막 10Hz 33.5–43.4(100시점), 6개 띠.
- simalt3 실패 Warp grip/turn: grip 전체86시점·dense100시점, turn 전체8시점·dense40시점, 8개 띠. 세부 범위는 simalt3/playback-review.md와 원본 review.json에 있다.
- simalt4 C3.16 grip 실패: 전체 2Hz 0.5–43.0(86시점), 첫 hold 표본23.8을 기준으로 직전10초 13.9–23.8의100시점, 6개 띠를 직접 읽었다. MP4 4배속, 약64KiB, ffprobe 원장 보존.
- simalt4 Warp 버퍼 넘침: 전체 2Hz 0.5–14.5(29시점), 중단 직전 10Hz 4.6–14.5의100시점, 4개 띠를 직접 읽었다. MP4 약32KiB, ffprobe 원장 보존.

실행 재생의 시계는 fixture 시작을0으로 둔다. 원래 발행 trace는 첫 clock에 오프셋이 있으며 단계 시작은 hold tick237=23.7 SIM초, 평가 표본은23.8–26.7의30개다. simalt3에서 쓴 failure anchor25.1은 이 재생의 첫 hold 표본을 뜻하지 않는다. 원본 단계명이나 절대 command clock을 상대 재생 clock과 혼동하지 않는다. trace-stage-review.json에 원본 단계 전환·발행 명령을 보존했다.

## 시간순 관측과 해석의 경계

0.5–3.5초에는 준비/정렬로 화면 방향이 바뀌고 상자가 화면에서 나갔다 돌아온다. 4.0–10.5초에는 상자가 커지며 화면 아래로 이동한다. 10.5–14.5초에는 팔 자세가 바뀌며 자기 카메라가 대부분 바닥을 본다. Warp의 버퍼 넘침 순간14.44925초 자체는 이 작은 영상에서 시각 판정할 수 없고, 4kHz 기록의 overflow bit로 판정했다. dense4.6–14.5에서 큰 왕복 진동을 확인하지는 못했다.

C3.16에서는 20.5초 이후 청록 상자가 자기 화면 위쪽으로 다시 크게 들어오며 머문다. 양성 C3.12에서는 아래쪽 청록 띠만 남는 모습과 다르다. 개요에서는 상자가 팔 가까이 있는 것처럼 보이므로 듬성한 프레임이나 hold 위치 정지만으로 파지 유지 성공을 선언할 수 없다. 양쪽 접촉과 힘·높이는 별도 수치 기록으로 판단한다. 30초 이후 열기/후퇴/둘러보기 발행 명령은 재생되지만 앞의 파지 실패를 성공으로 바꾸지 않는다.

새 리뷰의 원본 경로는 `/home/ugrp/ugrp-sim/runs/simalt4/review-c316-grip-osmesa/`, `review-warp-overflow-osmesa/`이고 Mac에는 `outputs/e2e18-admin/playback/simalt4/`의 요약 영상과 띠만 회수했다. 처음 GUI 없는 GL backend를 지정하지 못한2회는 프레임0의 검토 도구 오류였으며 `*-osmesa`로 새 경로에서 재실행했다. 이 오류는 파지 실패 표본과 합산하지 않는다.
