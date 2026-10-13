# E2E18 끝 배정 진단
- B cohort2 + C cohort3 + C cohort4 본 파지 24개, 게이트 제외.
- 제어기 대기 위치 = 봉 중심 ±(0.27+0.2032)m, 반경 0.25m에서 7 same / 5 opposite / 12 unreached.
- 이 집계는 각 로봇의 전체 궤적 최접근이며 동시 점유·의도적 파지 성공이 아니다.
- 원인: 첫 축 역전4, 접근 중 축 재배정2, B 탐색 중 우연 접근1.
- 정답은 audit/causes 평가에만 사용. 원본은 outputs/azure3-runs 및 ARM native-* 보존.
- c-cohort4-02 자기 RGB 시작·중간·끝 각 로봇3장 직접 확인, view-manifest.json.
- v415/v416 반대 끝 최접근2/3·3/3(기준1/3), 첫 시도 파지0/12; 기준만 재탐색 후 공동 파지1/12.
- v417/v418 B 독립 후보: 관련46시험·12동시 게이트 통과, 본 단계 진행 중. summary.json 참조.
