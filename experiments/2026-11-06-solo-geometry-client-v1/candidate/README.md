# Solo geometry client candidate

This opt-in candidate connects a geometry predictor launcher to the archived
SoloStudentClient transport. It is an experiment snapshot, not the complete
runner or a portable deployment package. The original wire and gates remain
unchanged. Geometry weights/forward, ACK completion and physical transport
have not been measured by this work.

## Required environment

prepare_only.py records the exact external source paths and literal SHA256
pins used on the research host. Those archived/staging files and the geometry
checkpoint are not bundled here. On a checkout without them, preparation
refuses with missing-source/checkpoint diagnostics. run_client_check.py also
requires that pinned host environment; its synthetic test is not a generic
clean-checkout test. No model is loaded by prepare-only.

## Checks and interpretation

The research-host synthetic suite passed six propose/issue rounds and 36
negative checks after scope correction. This is not a learned model result.
The parent pin checks disk bytes at CLAIMED module/base file paths. It does
not authenticate loaded Python code: a pre-seeded sys.modules module with a
forged pinned __file__ can still pass. loaded_code_verified is always false.
child_process_verified is a legacy name for a Popen instance type predicate;
child_is_popen_instance is the explicit alias. Neither authenticates PID,
executable, interpreter or loaded code. Injected callables may return unrelated
Popen instances. The record includes process_verification_scope.

Base pin names cannot be resubmitted, even with identical values. Additional
pins are checked against actual bytes; checkpoint/config gates remain required.
The worker SHA is an independent literal in solo_geometry_client.py. A worker
byte change requires independent digest calculation, review, literal repinning
and repeating preparation, negative checks and synthetic child tests.

This candidate intentionally uses the archived client's entry TEST SEAM.
The launcher reuses the pinned worker serve path; production runner/environment
integration remains incomplete. GO and READY_withdrawn_rearm were observed;
ACK was not observed. No GPU, simulator transport or real robot success is
claimed. The separate syntax workflow only compiles the four Python files
without importing them; it does not exercise archived dependencies.
