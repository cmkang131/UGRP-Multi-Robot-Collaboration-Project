# act16w3 — native contact에서 재관문

2026-10-16 사용자 noslip 해제 결정에 따라 **새 코호트**로 시작한다.
진행 중인 noslip10 VAL5×A/B(pid22076)는 그대로 마친 뒤 원본으로 재계수한다.
그 실행기는 validation 전용이며 h4/h5/최종40 자동 실행 코드가 없다.
기존 데이터·모델·Release는 noslip10 비교 기준으로 보존한다.

장면은 `walls_floor_contrast_v5_indigo110_s80 + no_mip_v1`이다.
물리는 warpfit `df5a1f86a`의 `sim/warp_native_contact.py`를 byte 그대로 가져온
`warp_native_contact_v1`(noslip0, elliptic, implicitfast, impratio5, Newton/LS80/50)이다.
SHA-256은 `a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`다.
추가 호환·용량·수치 프로필은 바꾸지 않았다. 공용 backend 파일도 수정하지 않았다.
ACT 전용 transport의 initialize는 `f0db6b1a`에서 복사하고 noslip 검사 두 곳을
0으로 바꿨으며, 실제 CPU/GPU 설정을 별도 receipt로 남긴다. AST 비교로 그 경계를 검사한다.

[사전 고정 protocol](protocol.json): 교사40개87220–87259와 기록40개87420–87459는
종류 cyan/red/green/yellow를 순환해 각각10개씩 사용한다. 호환그룹이나 결과로
시드를 빼지 않는다. 기록32TRAIN/8VAL은 인덱스 `%5==4`를 VAL로 고정한다.
DAgger는 각 종류 TRAIN의 앞5개씩20개다. 최종91620–91659는 모델 선택을 봉인한 뒤
한 번 평가하며 종류별 배정 item_id 성공과 같은 종류 아무 상자 성공을 구분한다.
기존86820–86869·warp1디버깅8317100–8317139와 겹치지 않는다.

교사 관문 ≥38/40, 학습 카메라OFF, 입력 감사0을 확인한 뒤 기록을 승인한다.
관문별 누적 통과·거부 표와 모든 실패/HOST_ERROR를 보존하고, 같은 결함3라운드면 멈춘다.
학생은 자기 RGB·자기 발행 이력·고정 작업 토큰만 받는다. 교사 경로로 대체·보조하지 않는다.
A/B → h4 → h5는 한 번에 한 요소씩 비교하며 완료되지 않은 단계는 미측정으로 남긴다.

실행·분석·영상 생성은 단독 소유 gcp2 L4 `ugrp-act-l4-gcp2`에서 한다.
CPU VM 시작0, Mac 물리/렌더/학습/화면앱0이다. Mac에는 요약·몽타주·실패 프레임만 회수한다.
wall 상한은 없고 idle20·budget-stop을 유지한다. 새 실행마다 임대와 디스크 여유를 확인한다.
교사 라이브러리`6f057f7e` → MJWarp controller`f0db6b1a` → 기록 API`0362037`의
관계를 유지하되 과거 noslip10 관문은 새 물리 관문으로 세지 않는다.

참고: [warpfit 프로필/실측 PR#562](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/562),
[act16a 실패 분석 PR#528](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/528),
[2회차 noslip10 기록](../resume2/summary.json), [접촉 어댑터 출처](contact-adapter-provenance.json).
Refs #523, Draft PR #539. native参照40개 생성 완료이며 교사 rollout0·학습 데이터 승인0이다.
`act16w-native-gate-r1`(PID51400, source8ad29c869)은 기존VAL 종료를 기다린다.
기존VAL 원장 재계수 후 native40을 실행하고 결과 검토 경계에서 멈춘다.
신규 실제 작업 이름을 유휴 판정에 등록했으며20분 기준·budget-stop은 유지했다.
