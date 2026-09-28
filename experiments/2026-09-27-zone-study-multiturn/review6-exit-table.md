# 검토 6 종료·반환·예외 추적

가짜 전송·시계만 사용. 모델 호출·물리 step 0회. 상세 기록은 review6-exit-traces.json.gz.

검토 5의 179행을 다시 실행하고 검토 6의 세 연쇄를 4조건, 회계/재질문 계약 2행과 합쳐진 새 사건 계보 1행에 추가했다. 과거 파일은 보존했다.

## 종료 표

| 경로 | 조건/상태 | 호출 시작 시각 | 종료 사유/처리 | 예외 |
|---|---|---|---|---|
| normal | absent | 6.1 | wake | - |
| normal | held | 6.1 | wake | - |
| normal | just_received | 6.1 | wake | - |
| normal | during_call | 6.1, 8.1 | wake | - |
| invalid_reply | absent | 6.1 | wake | - |
| invalid_reply | held | 6.1 | wake | - |
| invalid_reply | just_received | 6.1 | wake | - |
| invalid_reply | during_call | 6.1, 8.1 | wake | - |
| error_reply | absent | 6.1 | wake | - |
| error_reply | held | 6.1 | wake | - |
| error_reply | just_received | 6.1 | wake | - |
| error_reply | during_call | 6.1, 8.1 | wake | - |
| timeout_reply | absent | 6.1 | wake | - |
| timeout_reply | held | 6.1 | wake | - |
| timeout_reply | just_received | 6.1 | wake | - |
| timeout_reply | during_call | 6.1, 8.1 | wake | - |
| error_submit_after_send | absent | 6.1 | wake | - |
| error_submit_after_send | held | 6.1 | wake | - |
| error_submit_after_send | just_received | 6.1 | wake | - |
| error_submit_after_send | during_call | 6.1, 8.1 | wake | - |
| not_sent_after_send | absent | 6.1 | wake | - |
| not_sent_after_send | held | 6.1 | wake | - |
| not_sent_after_send | just_received | 6.1 | wake | - |
| not_sent_after_send | during_call | 6.1, 8.1 | wake | - |
| retry_exhausted | absent | 6.1, 8.1 | wake | - |
| retry_exhausted | held | 6.1, 8.1 | wake | - |
| retry_exhausted | just_received | 6.1, 8.1 | wake | - |
| retry_exhausted | during_call | 6.1, 8.1 | wake | - |
| zero_reply_error | absent | 6.1 | wake | - |
| zero_reply_error | held | 6.1, 8.1 | wake | - |
| zero_reply_error | just_received | 6.1, 8.1 | wake | - |
| zero_reply_error | during_call | 6.1, 8.1 | wake | - |
| zero_reply_not_sent | absent | 6.1 | wake | - |
| zero_reply_not_sent | held | 6.1, 8.1 | wake | - |
| zero_reply_not_sent | just_received | 6.1, 8.1 | wake | - |
| zero_reply_not_sent | during_call | 6.1, 8.1 | wake | - |
| zero_request_store | absent | 6.1 | wake | - |
| zero_request_store | held | 6.1, 8.1 | wake | - |
| zero_request_store | just_received | 6.1, 8.1 | wake | - |
| zero_request_store | during_call | 6.1, 8.1 | wake | - |
| zero_wire_budget | absent | 6.1 | wake | - |
| zero_wire_budget | held | 6.1, 8.1 | wake | - |
| zero_wire_budget | just_received | 6.1, 8.1 | wake | - |
| zero_wire_budget | during_call | 6.1, 8.1 | wake | - |
| zero_submit_error | absent | 6.1 | never_pending | - |
| zero_submit_error | held | 6.1, 8.1 | never_pending | - |
| zero_submit_error | just_received | 6.1, 8.1 | never_pending | - |
| zero_submit_error | during_call | 6.1, 6.2 | never_pending | - |
| zero_submit_not_sent | absent | 6.1 | never_pending | NotSent |
| zero_submit_not_sent | held | 6.1, 8.1 | never_pending | NotSent |
| zero_submit_not_sent | just_received | 6.1, 8.1 | never_pending | NotSent |
| zero_submit_not_sent | during_call | 6.1, 6.2 | never_pending | NotSent |
| actor_call_budget | absent | 없음 | refuse | - |
| actor_call_budget | held | 없음 | refuse | - |
| actor_call_budget | just_received | 없음 | refuse | - |
| actor_call_budget | during_call | 없음 | refuse | - |
| actor_http_budget | absent | 없음 | refuse | - |
| actor_http_budget | held | 없음 | refuse | - |
| actor_http_budget | just_received | 없음 | refuse | - |
| actor_http_budget | during_call | 없음 | refuse | - |
| team_http_budget | absent | 없음 | refuse | - |
| team_http_budget | held | 없음 | refuse | - |
| team_http_budget | just_received | 없음 | refuse | - |
| team_http_budget | during_call | 없음 | refuse | - |
| episode_call_budget | absent | 없음 | refuse | - |
| episode_call_budget | held | 없음 | refuse | - |
| episode_call_budget | just_received | 없음 | refuse | - |
| episode_call_budget | during_call | 없음 | refuse | - |
| external_budget | absent | 없음 | refuse | - |
| external_budget | held | 없음 | refuse | - |
| external_budget | just_received | 없음 | refuse | - |
| external_budget | during_call | 없음 | refuse | - |
| cancel_submit | absent | 6.1 | stop | KeyboardInterrupt |
| cancel_submit | held | 6.1 | stop | KeyboardInterrupt |
| cancel_submit | just_received | 6.1 | stop | KeyboardInterrupt |
| cancel_submit | during_call | 6.1 | stop | KeyboardInterrupt |
| cancel_submit_after_send | absent | 6.1 | stop | KeyboardInterrupt |
| cancel_submit_after_send | held | 6.1 | stop | KeyboardInterrupt |
| cancel_submit_after_send | just_received | 6.1 | stop | KeyboardInterrupt |
| cancel_submit_after_send | during_call | 6.1 | stop | KeyboardInterrupt |
| cancel_reply | absent | 6.1 | stop | CancelledError |
| cancel_reply | held | 6.1 | stop | CancelledError |
| cancel_reply | just_received | 6.1 | stop | CancelledError |
| cancel_reply | during_call | 6.1 | stop | CancelledError |
| episode_pending | absent | 6.1 | close | - |
| episode_pending | held | 6.1 | close | - |
| episode_pending | just_received | 6.1 | close | - |
| episode_pending | during_call | 6.1 | close | - |
| episode_charged | absent | 6.1 | close | - |
| episode_charged | held | 6.1 | close | - |
| episode_charged | just_received | 6.1 | close | - |
| episode_charged | during_call | 6.1 | close | - |
| episode_zero_send | absent | 6.1 | close | - |
| episode_zero_send | held | 6.1 | close | - |
| episode_zero_send | just_received | 6.1 | close | - |
| episode_zero_send | during_call | 6.1 | close | - |
| snapshot_error | absent | 6.1 | never_pending | - |
| snapshot_error | held | 6.1, 8.1 | never_pending | - |
| snapshot_error | just_received | 6.1, 8.1 | never_pending | - |
| snapshot_error | during_call | 6.1, 6.2 | never_pending | - |
| transport_failure | absent | 6.1 | wake | - |
| transport_failure | held | 6.1 | wake | - |
| transport_failure | just_received | 6.1 | wake | - |
| transport_failure | during_call | 6.1, 8.1 | wake | - |
| declared_mismatch | absent | 6.1 | wake | - |
| declared_mismatch | held | 6.1 | wake | - |
| declared_mismatch | just_received | 6.1 | wake | - |
| declared_mismatch | during_call | 6.1, 8.1 | wake | - |
| attempts_overreported | absent | 6.1 | wake | - |
| attempts_overreported | held | 6.1 | wake | - |
| attempts_overreported | just_received | 6.1 | wake | - |
| attempts_overreported | during_call | 6.1, 8.1 | wake | - |
| attempts_underreported | absent | 6.1 | wake | - |
| attempts_underreported | held | 6.1 | wake | - |
| attempts_underreported | just_received | 6.1 | wake | - |
| attempts_underreported | during_call | 6.1, 8.1 | wake | - |
| reply_without_send | absent | 6.1 | wake | - |
| reply_without_send | held | 6.1, 8.1 | wake | - |
| reply_without_send | just_received | 6.1, 8.1 | wake | - |
| reply_without_send | during_call | 6.1, 8.1 | wake | - |
| wrong_reply_type | absent | 6.1 | stop | TypeError |
| wrong_reply_type | held | 6.1 | stop | TypeError |
| wrong_reply_type | just_received | 6.1 | stop | TypeError |
| wrong_reply_type | during_call | 6.1 | stop | TypeError |
| emit_wrong_sender | absent | 6.1 | stop | ValueError |
| emit_wrong_sender | held | 6.1 | stop | ValueError |
| emit_wrong_sender | just_received | 6.1 | stop | ValueError |
| emit_wrong_sender | during_call | 6.1 | stop | ValueError |
| action_callback_error | absent | 6.1 | stop | ValueError |
| action_callback_error | held | 6.1 | stop | ValueError |
| action_callback_error | just_received | 6.1 | stop | ValueError |
| action_callback_error | during_call | 6.1 | stop | ValueError |
| constructor_ledger | held | 4.0 | validation_then_wake | TypeError |
| constructor_bus | held | 4.0 | validation_then_wake | ValueError |
| attempts_query | held | 4.0 | validation_then_wake | - |
| trigger_label | held | 4.0 | validation_then_wake | ValueError |
| trigger_past | held | 4.0 | validation_then_wake | ValueError |
| event_invalid | held | 4.0 | validation_then_wake | ValueError |
| reask_label | held | 4.0 | validation_then_wake | ValueError |
| reask_nonfinite | held | 4.0 | validation_then_wake | ValueError |
| reask_past | held | 4.0 | validation_then_wake | ValueError |
| reask_accept_skip | held | 4.0 | validation_then_wake | - |
| observe_invalid | held | 4.0 | validation_then_wake | ValueError |
| delivery_query | held | 4.0 | validation_then_wake | - |
| contract_query | held | 4.0 | validation_then_wake | - |
| unknown_actor | held | 4.0 | validation_then_wake | KeyError |
| clock_past | held | 4.0 | validation_then_wake | AssertionError |
| wire_unknown | held | 4.0 | validation_then_wake | - |
| reserve_settled | held | 4.0 | validation_then_wake | ValueError |
| reserve_accept | held | 0.0, 4.0 | validation_then_wake | - |
| reserve_refuse | held | 0.0, 4.0 | validation_then_wake | - |
| wire_settled | held | 0.0, 4.0 | validation_then_wake | - |
| emit_missing_id | held | 4.0 | validation_then_wake | ValueError |
| invalid_envelope | held | 4.0 | validation_then_wake | AssertionError |
| timer_return | held | 0.0, 4.0 | validation_then_wake | - |
| retry_refund | peer_ko | 0.0, 0.0, 0.0, 6.1, 6.1, 8.1, 10.1 | chained_refund | - |
| retry_refund | leader_ko | 0.0, 0.0, 0.0, 6.1, 6.1, 8.1, 10.1 | chained_refund | - |
| retry_refund | structured | 0.0, 0.0, 0.0, 6.1, 6.1, 8.1, 10.1 | chained_refund | - |
| retry_held_refund | peer_ko | 0.0, 0.0, 0.0, 6.1, 6.1, 6.2, 8.2, 10.2 | chained_refund | - |
| retry_held_refund | leader_ko | 0.0, 0.0, 0.0, 6.1, 6.1, 6.2, 8.2, 10.2 | chained_refund | - |
| retry_held_refund | structured | 0.0, 0.0, 0.0, 6.1, 6.1, 6.2, 8.2, 10.2 | chained_refund | - |
| boundary_refund | peer_ko | 0.0, 0.0, 0.0, 7.0, 7.2, 9.0, 11.0 | chained_refund | - |
| boundary_refund | leader_ko | 0.0, 0.0, 0.0, 7.0, 7.2, 9.0, 11.0 | chained_refund | - |
| boundary_refund | structured | 0.0, 0.0, 0.0, 7.0, 7.2, 9.0, 11.0 | chained_refund | - |
| reservation_refund | peer_ko | 0.0, 0.0, 0.0, 5.5, 6.0, 6.4 | chained_refund | - |
| reservation_refund | leader_ko | 0.0, 0.0, 0.0, 5.5, 6.0, 6.4 | chained_refund | - |
| reservation_refund | structured | 0.0, 0.0, 0.0, 5.5, 6.0, 6.4 | chained_refund | - |
| reservation_episode | refund | 0.0, 0.4 | resume | - |
| reservation_episode | pending_send | 0.0 | terminal_spend | - |
| reservation_episode | already_sent | 0.0 | terminal_spend | - |
| reservation_team_http | refund | 0.0, 0.4 | resume | - |
| reservation_team_http | pending_send | 0.0 | terminal_spend | - |
| reservation_team_http | already_sent | 0.0 | terminal_spend | - |
| reservation_actor_http | refund | 0.0, 0.4 | resume | - |
| reservation_actor_http | pending_send | 0.0 | terminal_spend | - |
| reservation_actor_http | already_sent | 0.0 | terminal_spend | - |
| reservation_actor_call | refund | 0.0, 0.4 | resume | - |
| reservation_actor_call | pending_send | 0.0 | terminal_spend | - |
| reservation_actor_call | already_sent | 0.0 | terminal_spend | - |
| separate_roots | no_comm | 0.0, 0.0, 0.0, 5.5, 7.5 | sim_horizon | - |
| separate_roots | peer_ko | 0.0, 0.0, 0.0, 5.5, 6.1, 7.5, 9.5, 11.5 | sim_horizon | - |
| separate_roots | leader_ko | 0.0, 0.0, 0.0, 5.5, 6.1, 7.5, 9.5, 11.5 | sim_horizon | - |
| separate_roots | structured | 0.0, 0.0, 0.0, 5.5, 6.1, 7.5, 9.5, 11.5 | sim_horizon | - |
| timer_reservation | no_comm | 0.0, 0.0, 0.0, 5.2, 15.3 | budget_exhausted | - |
| timer_reservation | peer_ko | 0.0, 0.0, 0.0, 5.2, 15.3 | budget_exhausted | - |
| timer_reservation | leader_ko | 0.0, 0.0, 0.0, 5.2, 15.3 | budget_exhausted | - |
| timer_reservation | structured | 0.0, 0.0, 0.0, 5.2, 15.3 | budget_exhausted | - |
| refund_horizon | no_comm | 0.0, 0.0, 0.0, 6.0 | sim_horizon | - |
| refund_horizon | peer_ko | 0.0, 0.0, 0.0, 6.0, 6.4, 6.4 | sim_horizon | - |
| refund_horizon | leader_ko | 0.0, 0.0, 0.0, 6.0, 6.4, 6.4 | sim_horizon | - |
| refund_horizon | structured | 0.0, 0.0, 0.0, 6.0, 6.4, 6.4 | sim_horizon | - |
| coalesced_fresh_root | old_retry_and_fresh | 0.0, 0.4, 2.4, 4.4 | retry_fresh_only | - |
| account_preconditions | none | 없음 | reject | ValueError,AssertionError,RuntimeError |
| reask_confirmed_call_cap | no_comm | 0.0, 0.0, 0.0 | budget_exhausted | - |

## 반환·raise·except 목록 (암시적 정상 반환 포함)

코어 스케줄러·회계 객체·DecisionScheduler와 통합의 재질문/종료 판정을 AST로 열거했다. 실행 근거 없는 지점은 명시하며, 이 표는 모든 boolean 조합의 증명이 아니다.

| 위치 | 함수 | 분기 | 실행 근거 |
|---|---|---|---|
| harness/zone_event_scheduler.py:394 | call_count | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:399 | call_limit_reached | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:409 | confirmed_usage | Return | actor_call_budget/held, actor_call_budget/just_received |
| harness/zone_event_scheduler.py:416 | exhausted | Return | actor_call_budget/held, actor_call_budget/just_received |
| harness/zone_event_scheduler.py:414 | exhausted | Return | separate_roots/no_comm, separate_roots/peer_ko |
| harness/zone_event_scheduler.py:420 | used_total | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:423 | outstanding | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:435 | remaining | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:447 | reserve | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:441 | reserve | Raise | account_preconditions/none |
| harness/zone_event_scheduler.py:445 | reserve | Return | actor_http_budget/absent, actor_http_budget/held |
| harness/zone_event_scheduler.py:463 | commit | Raise | account_preconditions/none |
| harness/zone_event_scheduler.py:472 | _assert_thread | Raise | account_preconditions/none |
| harness/zone_event_scheduler.py:475 | to_dict | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:553 | __init__ | Raise | constructor_ledger/held |
| harness/zone_event_scheduler.py:584 | __init__ | Raise | constructor_bus/held |
| harness/zone_event_scheduler.py:637 | _attempts_total | Return | attempts_query/held |
| harness/zone_event_scheduler.py:642 | now | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:651 | holding | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:657 | trigger | Raise | trigger_label/held |
| harness/zone_event_scheduler.py:660 | trigger | Raise | trigger_past/held |
| harness/zone_event_scheduler.py:674 | event | Return | normal/held, normal/just_received |
| harness/zone_event_scheduler.py:668 | event | Raise | event_invalid/held |
| harness/zone_event_scheduler.py:689 | calls_spent | Return | reservation_episode/refund, reservation_episode/pending_send |
| harness/zone_event_scheduler.py:723 | arm_reask | Return | reask_accept_skip/held, retry_refund/peer_ko |
| harness/zone_event_scheduler.py:712 | arm_reask | Raise | reask_label/held |
| harness/zone_event_scheduler.py:714 | arm_reask | Raise | reask_nonfinite/held |
| harness/zone_event_scheduler.py:716 | arm_reask | Raise | reask_past/held |
| harness/zone_event_scheduler.py:719 | arm_reask | Return | reask_accept_skip/held, reservation_refund/peer_ko |
| harness/zone_event_scheduler.py:728 | reask_pending | Return | reask_accept_skip/held |
| harness/zone_event_scheduler.py:734 | arm_observations | Raise | observe_invalid/held |
| harness/zone_event_scheduler.py:743 | inbox | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:748 | delivery_log | Return | delivery_query/held |
| harness/zone_event_scheduler.py:752 | undelivered | Return | delivery_query/held, separate_roots/no_comm |
| harness/zone_event_scheduler.py:761 | trace | Return | delivery_query/held, separate_roots/no_comm |
| harness/zone_event_scheduler.py:803 | contract_log | Return | contract_query/held |
| harness/zone_event_scheduler.py:845 | run | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:922 | _check_actor | Raise | unknown_actor/held |
| harness/zone_event_scheduler.py:934 | _advance | Raise | clock_past/held |
| harness/zone_event_scheduler.py:969 | _resolve_due | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:955 | _resolve_due | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1032 | _reply_of | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1013 | _reply_of | Return | zero_reply_error/absent, zero_reply_error/held |
| harness/zone_event_scheduler.py:1036 | _violation | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1060 | _fetch_reply | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1053 | _fetch_reply | Return | error_submit_after_send/absent, error_submit_after_send/held |
| harness/zone_event_scheduler.py:1056 | _fetch_reply | ExceptHandler | error_reply/absent, error_reply/held |
| harness/zone_event_scheduler.py:1059 | _fetch_reply | Raise | wrong_reply_type/absent, wrong_reply_type/held |
| harness/zone_event_scheduler.py:1057 | _fetch_reply | Return | error_reply/absent, error_reply/held |
| harness/zone_event_scheduler.py:1086 | _failure_reply | Return | error_reply/absent, error_reply/held |
| harness/zone_event_scheduler.py:1080 | _failure_reply | Return | transport_failure/absent, transport_failure/held |
| harness/zone_event_scheduler.py:1109 | _release_unsent | Return | zero_submit_error/absent, zero_submit_error/held |
| harness/zone_event_scheduler.py:1127 | _schedule_key | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1130 | _outstanding | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1177 | _refuse_event_inputs | Return | actor_call_budget/absent, actor_call_budget/held |
| harness/zone_event_scheduler.py:1192 | _on_call_start | Return | normal/held, normal/just_received |
| harness/zone_event_scheduler.py:1218 | _on_call_start | Return | normal/during_call, invalid_reply/during_call |
| harness/zone_event_scheduler.py:1247 | _on_call_start | Return | external_budget/absent, external_budget/held |
| harness/zone_event_scheduler.py:1253 | _on_call_start | Return | actor_call_budget/absent, actor_call_budget/held |
| harness/zone_event_scheduler.py:1261 | _on_call_start | Return | actor_http_budget/absent, actor_http_budget/held |
| harness/zone_event_scheduler.py:1294 | _on_call_start | Return | zero_submit_error/absent, zero_submit_error/held |
| harness/zone_event_scheduler.py:1212 | _on_call_start | Return | normal/held, invalid_reply/held |
| harness/zone_event_scheduler.py:1233 | _on_call_start | Return | normal/during_call, invalid_reply/during_call |
| harness/zone_event_scheduler.py:1324 | _submit | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1325 | _submit | ExceptHandler | error_submit_after_send/absent, error_submit_after_send/held |
| harness/zone_event_scheduler.py:1342 | _submit | ExceptHandler | cancel_submit/absent, cancel_submit/held |
| harness/zone_event_scheduler.py:1341 | _submit | Return | zero_submit_error/absent, zero_submit_error/held |
| harness/zone_event_scheduler.py:1345 | _submit | Raise | cancel_submit/absent, cancel_submit/held |
| harness/zone_event_scheduler.py:1328 | _submit | Return | error_submit_after_send/absent, error_submit_after_send/held |
| harness/zone_event_scheduler.py:1340 | _submit | Raise | zero_submit_not_sent/absent, zero_submit_not_sent/held |
| harness/zone_event_scheduler.py:1380 | _authorize_send | Return | wire_unknown/held, wire_settled/held |
| harness/zone_event_scheduler.py:1369 | _authorize_send | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1397 | _reserve_more | Return | reserve_accept/held |
| harness/zone_event_scheduler.py:1391 | _reserve_more | Raise | reserve_settled/held |
| harness/zone_event_scheduler.py:1395 | _reserve_more | Return | reserve_refuse/held |
| harness/zone_event_scheduler.py:1494 | _emit | Raise | emit_wrong_sender/absent, emit_wrong_sender/held |
| harness/zone_event_scheduler.py:1497 | _emit | Raise | emit_missing_id/held |
| harness/zone_event_scheduler.py:1531 | _retry | Return | invalid_reply/absent, invalid_reply/held |
| harness/zone_event_scheduler.py:1563 | _on_message | Raise | invalid_envelope/held |
| harness/zone_study_integration.py:410 | decision_budget_spent | Return | separate_roots/no_comm, separate_roots/peer_ko |
| harness/zone_study_integration.py:419 | decision_end_reason | Return | separate_roots/no_comm, separate_roots/peer_ko |
| harness/zone_study_integration.py:426 | finish | Return | separate_roots/no_comm, separate_roots/peer_ko |
| harness/zone_study_integration.py:514 | _arm_reask | Return | reask_confirmed_call_cap/no_comm |
| harness/zone_event_scheduler.py:387 | __init__ | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:391 | start_call | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:451 | release | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:466 | commit | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:472 | _assert_thread | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:632 | __init__ | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:662 | trigger | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:684 | available | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:696 | timer | ImplicitReturn | timer_return/held, retry_held_refund/peer_ko |
| harness/zone_event_scheduler.py:738 | arm_observations | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:916 | _censor_outstanding | ImplicitReturn | episode_pending/absent, episode_pending/held |
| harness/zone_event_scheduler.py:922 | _check_actor | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:929 | _push | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:937 | _advance | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:940 | _log | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1044 | _violation | ImplicitReturn | not_sent_after_send/absent, not_sent_after_send/held |
| harness/zone_event_scheduler.py:1118 | _release_unsent | ImplicitReturn | zero_reply_error/absent, zero_reply_error/held |
| harness/zone_event_scheduler.py:1123 | _dispatch | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1145 | _restore_inputs | ImplicitReturn | zero_reply_error/absent, zero_reply_error/held |
| harness/zone_event_scheduler.py:1167 | _resume_deferred | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1184 | _refuse_event_inputs | ImplicitReturn | actor_call_budget/held, actor_call_budget/just_received |
| harness/zone_event_scheduler.py:1307 | _on_call_start | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1414 | _defer | ImplicitReturn | normal/held, normal/during_call |
| harness/zone_event_scheduler.py:1482 | _on_call_done | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1522 | _emit | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1544 | _retry | ImplicitReturn | retry_exhausted/absent, retry_exhausted/held |
| harness/zone_event_scheduler.py:1583 | _on_message | ImplicitReturn | normal/held, normal/just_received |
| harness/zone_event_scheduler.py:1595 | _on_timer | ImplicitReturn | timer_return/held, retry_held_refund/peer_ko |
| harness/zone_event_scheduler.py:1602 | _on_observe | ImplicitReturn | normal/absent, normal/held |
| harness/zone_study_decisions.py:31 | __init__ | ImplicitReturn | normal/absent, normal/held |
| harness/zone_study_integration.py:518 | _arm_reask | ImplicitReturn | retry_refund/peer_ko, retry_refund/leader_ko |
