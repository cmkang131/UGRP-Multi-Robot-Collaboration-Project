# 검토 4 종료·반환·예외 추적

가짜 전송·가짜 시계만 사용했다. 모델 호출·물리 step 0회. 상세 실행·ledger는 `review4-exit-traces.json`.

## 종료 표

| 경로 | 메시지 상태 | 재개 시작 시각 | 처리 | 예외 |
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

## 반환·raise·except 전수 목록 (암시적 정상 반환 포함)

각 행은 AST에서 직접 추출했다. 실행 근거 없음은 미실행이며 통과로 세지 않는다. 생성자·입력 검증·읽기 API는 호출 정산 경로와 구분한다.

| 위치 | 함수 | 분기 | 종료 표 실행 근거(대표) |
|---|---|---|---|
| harness/zone_event_scheduler.py:497 | __init__ | Raise | constructor_ledger/held |
| harness/zone_event_scheduler.py:528 | __init__ | Raise | constructor_bus/held |
| harness/zone_event_scheduler.py:578 | _attempts_total | Return | attempts_query/held |
| harness/zone_event_scheduler.py:583 | now | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:592 | holding | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:598 | trigger | Raise | trigger_label/held |
| harness/zone_event_scheduler.py:601 | trigger | Raise | trigger_past/held |
| harness/zone_event_scheduler.py:615 | event | Return | normal/held, normal/just_received |
| harness/zone_event_scheduler.py:609 | event | Raise | event_invalid/held |
| harness/zone_event_scheduler.py:627 | calls_spent | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:661 | arm_reask | Return | reask_accept_skip/held |
| harness/zone_event_scheduler.py:650 | arm_reask | Raise | reask_label/held |
| harness/zone_event_scheduler.py:652 | arm_reask | Raise | reask_nonfinite/held |
| harness/zone_event_scheduler.py:654 | arm_reask | Raise | reask_past/held |
| harness/zone_event_scheduler.py:657 | arm_reask | Return | reask_accept_skip/held |
| harness/zone_event_scheduler.py:666 | reask_pending | Return | reask_accept_skip/held |
| harness/zone_event_scheduler.py:672 | arm_observations | Raise | observe_invalid/held |
| harness/zone_event_scheduler.py:681 | inbox | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:686 | delivery_log | Return | delivery_query/held |
| harness/zone_event_scheduler.py:690 | undelivered | Return | delivery_query/held |
| harness/zone_event_scheduler.py:699 | trace | Return | delivery_query/held |
| harness/zone_event_scheduler.py:741 | contract_log | Return | contract_query/held |
| harness/zone_event_scheduler.py:783 | run | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:860 | _check_actor | Raise | unknown_actor/held |
| harness/zone_event_scheduler.py:872 | _advance | Raise | clock_past/held |
| harness/zone_event_scheduler.py:907 | _resolve_due | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:893 | _resolve_due | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:970 | _reply_of | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:951 | _reply_of | Return | zero_reply_error/absent, zero_reply_error/held |
| harness/zone_event_scheduler.py:974 | _violation | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:998 | _fetch_reply | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:991 | _fetch_reply | Return | error_submit_after_send/absent, error_submit_after_send/held |
| harness/zone_event_scheduler.py:994 | _fetch_reply | ExceptHandler | error_reply/absent, error_reply/held |
| harness/zone_event_scheduler.py:997 | _fetch_reply | Raise | wrong_reply_type/absent, wrong_reply_type/held |
| harness/zone_event_scheduler.py:995 | _fetch_reply | Return | error_reply/absent, error_reply/held |
| harness/zone_event_scheduler.py:1024 | _failure_reply | Return | error_reply/absent, error_reply/held |
| harness/zone_event_scheduler.py:1018 | _failure_reply | Return | transport_failure/absent, transport_failure/held |
| harness/zone_event_scheduler.py:1047 | _release_unsent | Return | zero_submit_error/absent, zero_submit_error/held |
| harness/zone_event_scheduler.py:1065 | _schedule_key | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1068 | _outstanding | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1111 | _on_call_start | Return | normal/held, normal/just_received |
| harness/zone_event_scheduler.py:1132 | _on_call_start | Return | normal/during_call, invalid_reply/during_call |
| harness/zone_event_scheduler.py:1156 | _on_call_start | Return | team_http_budget/absent, team_http_budget/held |
| harness/zone_event_scheduler.py:1162 | _on_call_start | Return | actor_call_budget/absent, actor_call_budget/held |
| harness/zone_event_scheduler.py:1170 | _on_call_start | Return | actor_http_budget/absent, actor_http_budget/held |
| harness/zone_event_scheduler.py:1195 | _on_call_start | Return | zero_submit_error/absent, zero_submit_error/held |
| harness/zone_event_scheduler.py:1126 | _on_call_start | Return | normal/held, invalid_reply/held |
| harness/zone_event_scheduler.py:1147 | _on_call_start | Return | normal/during_call, invalid_reply/during_call |
| harness/zone_event_scheduler.py:1224 | _submit | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1225 | _submit | ExceptHandler | error_submit_after_send/absent, error_submit_after_send/held |
| harness/zone_event_scheduler.py:1242 | _submit | ExceptHandler | cancel_submit/absent, cancel_submit/held |
| harness/zone_event_scheduler.py:1241 | _submit | Return | zero_submit_error/absent, zero_submit_error/held |
| harness/zone_event_scheduler.py:1245 | _submit | Raise | cancel_submit/absent, cancel_submit/held |
| harness/zone_event_scheduler.py:1228 | _submit | Return | error_submit_after_send/absent, error_submit_after_send/held |
| harness/zone_event_scheduler.py:1240 | _submit | Raise | zero_submit_not_sent/absent, zero_submit_not_sent/held |
| harness/zone_event_scheduler.py:1280 | _authorize_send | Return | wire_unknown/held, wire_settled/held |
| harness/zone_event_scheduler.py:1269 | _authorize_send | Return | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1297 | _reserve_more | Return | reserve_accept/held |
| harness/zone_event_scheduler.py:1291 | _reserve_more | Raise | reserve_settled/held |
| harness/zone_event_scheduler.py:1295 | _reserve_more | Return | reserve_refuse/held |
| harness/zone_event_scheduler.py:1392 | _emit | Raise | emit_wrong_sender/absent, emit_wrong_sender/held |
| harness/zone_event_scheduler.py:1395 | _emit | Raise | emit_missing_id/held |
| harness/zone_event_scheduler.py:1428 | _retry | Return | invalid_reply/absent, invalid_reply/held |
| harness/zone_event_scheduler.py:1456 | _on_message | Raise | invalid_envelope/held |
| harness/zone_event_scheduler.py:573 | __init__ | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:603 | trigger | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:622 | available | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:634 | timer | ImplicitReturn | timer_return/held |
| harness/zone_event_scheduler.py:676 | arm_observations | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:854 | _censor_outstanding | ImplicitReturn | episode_pending/absent, episode_pending/held |
| harness/zone_event_scheduler.py:860 | _check_actor | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:867 | _push | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:875 | _advance | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:878 | _log | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:982 | _violation | ImplicitReturn | not_sent_after_send/absent, not_sent_after_send/held |
| harness/zone_event_scheduler.py:1056 | _release_unsent | ImplicitReturn | zero_reply_error/absent, zero_reply_error/held |
| harness/zone_event_scheduler.py:1061 | _dispatch | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1082 | _restore_inputs | ImplicitReturn | zero_reply_error/absent, zero_reply_error/held |
| harness/zone_event_scheduler.py:1103 | _resume_deferred | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1207 | _on_call_start | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1312 | _defer | ImplicitReturn | normal/held, normal/during_call |
| harness/zone_event_scheduler.py:1380 | _on_call_done | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1420 | _emit | ImplicitReturn | normal/absent, normal/held |
| harness/zone_event_scheduler.py:1437 | _retry | ImplicitReturn | retry_exhausted/absent, retry_exhausted/held |
| harness/zone_event_scheduler.py:1476 | _on_message | ImplicitReturn | normal/held, normal/just_received |
| harness/zone_event_scheduler.py:1488 | _on_timer | ImplicitReturn | timer_return/held |
| harness/zone_event_scheduler.py:1495 | _on_observe | ImplicitReturn | normal/absent, normal/held |
| harness/zone_study_decisions.py:31 | __init__ | ImplicitReturn | normal/absent, normal/held |
