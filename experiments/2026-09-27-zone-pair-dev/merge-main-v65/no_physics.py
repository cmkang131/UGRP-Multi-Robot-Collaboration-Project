def pytest_sessionstart(session):
    import mujoco
    def forbidden(*args, **kwargs):
        raise AssertionError('PR240 validation forbids MuJoCo stepping')
    for name in ('mj_step', 'mj_step1', 'mj_step2'):
        setattr(mujoco, name, forbidden)
