"""Opt-in seal validation guard: no blinded raw/inventory, physics or rendering."""
import sys

COUNTS = {'blinded_access_attempts': 0, 'physics_or_render_attempts': 0}


def pytest_sessionstart(session):
    def audit(event, args):
        if event in ('open', 'os.listdir', 'os.scandir') and args:
            if '/outputs/v6h1-confirm-' in str(args[0]):
                COUNTS['blinded_access_attempts'] += 1
                raise AssertionError('recorded raw and real inventory are forbidden')
    sys.addaudithook(audit)
    import mujoco
    def forbidden(*args, **kwargs):
        COUNTS['physics_or_render_attempts'] += 1
        raise AssertionError('seal validation forbids physics and rendering')
    for name in ('mj_forward', 'mj_inverse', 'Renderer'):
        setattr(mujoco, name, forbidden)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line('Seal offline guard: ' + repr(COUNTS))
