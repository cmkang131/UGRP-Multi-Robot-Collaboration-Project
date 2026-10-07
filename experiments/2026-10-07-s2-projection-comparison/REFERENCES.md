# 투영 경로 출처·줄 단위 대조

PR #406은 **dc65cf6f**에 고정했다. [sources.json](sources.json)의 Git blob SHA256과
[sources/](sources/)의 원문 사본을 대조하며, 원 worktree/파일은 수정하지 않았다.
새 외부 패키지·라이선스 의존성은 없다. 프로젝트 원문의 관련 함수 AST를 변경 없이 실행하고
Runtime/PF/worker는 생성하지 않는다. 평가용 shim은 [code/s2_path.py](code/s2_path.py)다.
GT 카메라·차체는 이 shim에 전달하지 않는다.

## 실제로 갈리는 곳

| 항목 | #405 (`675ca181`) | #406 (`dc65cf6f`) | 동일 프레임에서의 판정 |
|---|---|---|---|
| 자기 입력 | `v3_confidence_replay.py:42–48` own commanded_servo allowlist | `vision_pose_source_highpose.py:71–78` 자기 servo와 PF command-load state | 이번 무하중 프레임의3/4/5/6 PWM을 그대로 공급. 실제 관절/GT 사용0 |
| 표 선택 | `harness/wall_camera_calibration.py:15–17,33–43`: hash 고정21자세 **unloaded**, closed/unknown 거부 | `zone_solo_cyan_real_carry_dev.py:21–43`:22자세 unloaded 복사, **loaded에만** optical-right 회전−0.02711rad | 공통21개 entry 전체가 동일. 달라진 것은 real carry 1자세 추가와 loaded 사본 |
| floor 좌표 | `wall_camera_calibration.py:42` → `zone_final_pair_camera.py:31–44` | `zone_final_pair_contract.py:79–93` → 동일 `floor_camera` | 두 함수 파일 Git bytes도 동일. floor 높이 합성/회전 방향 차이 없음 |
| pan yaw | #405 PnP transform 직접 사용 | `vision_pose_source_highpose.py:74–77`, `vision_loc.py:181–184` | 표 pan_base_yaw는 loaded/unloaded 모두0; 이번 차이0 |
| 투영 ColumnModel | `v3_confidence_replay.py:65–72`, `markerless_probe.py:197–225` | `vision_pose_source_final.py:26–60`의 `measured_column_model` | 같은 transform에서 q0/d/alpha/beta/gamma bytes 동일. 고정 픽셀 ray 교점과 차이≤1.97e−14m |
| pitch의 출처 | 보정표의 회전행렬. 별도 egomap11 Euler 분해는 **평가용** | 같은 회전행렬; loaded에만 원문 `rotation @ delta` 추가 | SEARCH unloaded의 pitch는 둘 다−18.18099958°. GT 오차를 fit하는 분기 없음 |
| s1050 표본 선택 | #405 관문은 기존 무하중 정착·수동 주석36프레임 | `audit_s1050_projection.py:42–56`: carry71.0–236.8s, `at_carry`, **models['loaded']**,1Hz166프레임 | 명령자세·하중 모델·평가 분모가 다름. 이 차이를 같은 프레임 투영 개선으로 해석할 수 없음 |

#405 원문: [wall calibration](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/675ca1817a114c51c02f19a3311a15264a78f5c5/harness/wall_camera_calibration.py#L28),
[replay geometry](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/675ca1817a114c51c02f19a3311a15264a78f5c5/experiments/2026-10-05-ego-wall-map-probe/code/v3_confidence_replay.py#L51).
#406 원문: [loaded table construction](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/dc65cf6f/harness/zone_solo_cyan_real_carry_dev.py#L21),
[provider column model](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/dc65cf6f/harness/vision_pose_source_highpose.py#L71),
[s1050 evaluator](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/dc65cf6f/experiments/2026-10-06-s2-realism/audit_s1050_projection.py#L37).
위 줄 번호는 실제 읽은 고정 blob 기준이다.

## 표·자세·조건

- 기존 table SHA256 `dc3157dbf77d5df5ab7ee63145e5c2cf7f5e8c0fbfc2231dd60712e26bc77b8c`.
  #406 새 표 L1609–1634에 parent hash, 추가 자세 측정 source `b6a54e3e`,
  unloaded checkerboard fit/holdout, loaded sag는 **실측이 아닌 고정 근사**라는 provenance가 있다.
- 같은 SEARCH key `740,2320,1320,1500`은 두 표 모두 L457, HIGH key `896,2035,1894,1500`은 L996.
  새 real carry key `600,2200,1400,1500`은 #406 표 L1045에만 있다. 원21개를 교체한 개선표가 아니다.
- s1050 실물식 carry는 `zone_solo_cyan_real_carry.py:19–24`의 자기 명령1/3/4/5/6=
  1500/600/2200/1400/1500이다. `approximate`의 loaded pitch−28.661989°를 쓴다.
  egomap11 SEARCH−18.180999° 또는 s1045–1047 HIGH−29.902435°와 혼용하지 않는다.
- `measured_column_model`와 #405 pinhole plane 교점은 같은 수학이다. 새 투영 공식·pitch 보정·
  강체/처짐 fit을 추가하지 않았다. 표준 좌표 관례는 [egomap11 REFERENCES](../2026-10-07-camera-pose-projection/REFERENCES.md)에 보존되어 있다.
- s1050은 `linspace(8,631,96)`의 자동 검출·GT 가시성 분모, 이번 관문은 기존 #405 96열과
  수동 주석 분모다. 비교에서는 **기존 #405 열을 양쪽에 동일하게 주어** 이 차이를 통제했다.
  원 s1050 수치는 저장 column의 재집계와 원본 hash 확인만 했으며 새 시행으로 세지 않는다.
