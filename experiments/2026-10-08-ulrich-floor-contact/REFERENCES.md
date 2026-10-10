# 원문 대응과 재현 한계

[Ulrich & Nourbakhsh 2000, AAAI pp.866–871](https://www.cs.cmu.edu/~illah/PAPERS/abod.pdf)
원문6쪽을 확인했다. PDF p.2 §3: 열별 최하단 obstacle로 거리 과대 추정을 줄임.
p.3 §4: 5×5 Gaussian, HSI, 사다리꼴 H/I hist, 평균필터, H60/I80 count 판정.
p.4 §5: candidate/reference 큐, 18° 방향 폐기 우선 후1m 이동 승격, hist OR.
p.4 §6: assistive는 dynamic만, 최근10개. p.5 §7: blob filtering 추가 없음.

## 논문에서 정하지 않은 값

256 bin, histogram 평균5bin, I10/255·S.1, hue wrap/intensity zero padding은
기존 `harness/wall_floor_boundary.py:17–48`의 고정값이다. **논문에서 명시한 수치가 아니다.**
논문의 '형태학 처리'는 확인되지 않았고 결과 영상에는 추가 blob filtering이 없다고 명시했다.
이번에도 obstacle mask opening/closing/작은 성분 제거는 넣지 않았다.

## 코드 대응

- `harness/wall_floor_ulrich.py` CONFIG: 원문값과 미명시값을 구분해 README에 등록.
- `UlrichFloorState.update`: 두 큐와 순서, wrap된 각도, strict >18°/>1m,
  최근10개의 bin 수락을 OR. 각 참조의 hist를 합산하지 않음.
- `detect`: 320×260 분류 격자,5×5 Gaussian, 기존 HSI/hist 계산 재사용,
  해당 프레임의 미검증 hist로 fallback하지 않음. 같은 frame_id 중복 갱신 방지.
- `first_contacts`: 분류된 바닥부터 첫 비바닥까지, edge 연산 없음. mask 내부 무효
  틈/하단 obstacle/self 가림은 기권. 센서의 무효 테두리는5×5 Gaussian support를 제외.
  이는 입력 유효성 처리이며 장애물 형태학 후처리가 아님.
- `wall_contact_detector.detect`의 새 옵션을 `observe`와 `contact_points`가 공유.
  기존 옵션·기본off 경로 그대로. 높이없는 기존 wall cue를 새 외형 분류에 다시 적용하지 않음.
- 명령 DR은 저장된 자기 펄스 delta를 기존 `self_pose_graph.compose`로 누적.
  원문 encoder와 다르고 횡/후진은 원문 플랫폼의 진행 가정을 위반할 수 있음.
  GT·기존 정합 pose를 reference 승격에 전달하지 않음.
- RGB 크기/FOV와 명령 FK가 다른 플랫폼이므로 참조 폭은 기존±.30m,
  깊이는 원문1m로 고정; pixel-center 보정 intrinsic으로 참조를 투영.
  분류mask를 native 크기로 nearest 복원한 뒤 기존 카메라 투영/96열/4m/면 연결 재사용.

기존 egomap37은 §4의 single-frame basic만 사용했고 시간 참조 큐가 없었다.
egomap38은 appearance 분류 없이 edge run을 연결로 사용했다. 두 실패는 보존한다.
이번 구현은 §5–6의 시간 검증을 포함하며 bin 등 원문 미공개 사항까지 완전한
원본 코드 재현이라고 주장하지 않는다. 공개 원본 소스 코드는 이번에 확보하지 못했다.
