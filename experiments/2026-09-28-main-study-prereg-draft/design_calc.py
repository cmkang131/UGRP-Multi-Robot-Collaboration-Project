# Design calculations for the DRAFT main-study preregistration. Pure standard library; no SIM/model/network.
# 1) N re-estimation rule: pilot within-block correlation rho -> planned blocks N_plan (clamped, multiple of 18).
# 2) Two-look group-sequential nominal levels (Lan-DeMets O'Brien-Fleming-type spending), two-sided,
#    for the local alpha levels that the graphical Holm procedure can assign to one hypothesis.
# All numbers are analytic ESTIMATES (normal approximation + Guenther correction, same as PR #252 power_estimate.py).
from math import atanh, ceil, exp, pi, sqrt, tanh
from statistics import NormalDist

N = NormalDist()
z = N.inv_cdf

D_TARGET = 0.40        # smallest effect of interest (pooled-SD d); see PREREG_DRAFT.md sec 3.3
ALPHA_FAMILY = 0.05
POWER = 0.80
N_PILOT = 18
LOWER_Q = 0.80          # use the one-sided 80% LOWER confidence bound of rho (conservative, Browne 1995 idea)
N_MIN, N_MAX, STEP = 36, 108, 18
RHO_CAP = 0.80


def n_paired(dz, alpha, power=POWER):
    za, zb = z(1 - alpha / 2), z(power)
    return ceil(((za + zb) / dz) ** 2 + za ** 2 / 2)


def rho_lower(rho_hat, n=N_PILOT, q=LOWER_Q):
    return tanh(atanh(rho_hat) - z(q) / sqrt(n - 3))


def n_plan(rho_hat):
    r = min(max(rho_lower(rho_hat), 0.0), RHO_CAP)
    dz = D_TARGET / sqrt(2 * (1 - r))
    n = n_paired(dz, ALPHA_FAMILY / 3)   # Holm worst case (first step)
    return r, dz, n, min(max(ceil(n / STEP) * STEP, N_MIN), N_MAX)


print('N re-estimation: d_target=%.2f, alpha=%.4f (Holm worst), power=%.2f, pilot n=%d, rho lower %d%% bound'
      % (D_TARGET, ALPHA_FAMILY / 3, POWER, N_PILOT, LOWER_Q * 100))
print('  rho_hat  rho_used  dz     n_raw  N_plan(blocks)  trials(4 cond)')
for rh in (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
    r, dz, n, npl = n_plan(rh)
    print(f'  {rh:6.2f}  {r:8.3f}  {dz:5.3f}  {n:5d}  {npl:14d}  {npl * 4:6d}')


def phi(x):
    return exp(-x * x / 2) / sqrt(2 * pi)


def obf_spend(t, alpha):
    # Lan-DeMets O'Brien-Fleming-type, two-sided
    return 2 - 2 * N.cdf(z(1 - alpha / 2) / sqrt(t))


def cross2(c1, c2, t, m=4000):
    # P(|Z1| < c1 and |Z2| >= c2), corr(Z1,Z2)=sqrt(t)
    a, b, h = -c1, c1, 2 * c1 / m
    s = 0.0
    for i in range(m + 1):
        x = a + i * h
        w = 1 if i in (0, m) else (4 if i % 2 else 2)
        mu, sd = sqrt(t) * x, sqrt(1 - t)
        p = N.cdf((-c2 - mu) / sd) + 1 - N.cdf((c2 - mu) / sd)
        s += w * phi(x) * p
    return s * h / 3


def boundaries(t, alpha):
    a1 = obf_spend(t, alpha)
    c1 = z(1 - a1 / 2)
    lo, hi = 0.5, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if cross2(c1, mid, t) > alpha - a1:
            lo = mid
        else:
            hi = mid
    c2 = (lo + hi) / 2
    return a1, c1, 2 * (1 - N.cdf(c2)), c2


print('\nGroup-sequential nominal two-sided p thresholds (2 looks, OBF-type spending)')
print('  local_alpha  t_interim  p1(interim)   z1     p2(final)   z2')
for alpha in (ALPHA_FAMILY / 3, ALPHA_FAMILY / 2, ALPHA_FAMILY):
    for t in (0.5, 0.6, 2 / 3):
        a1, c1, p2, c2 = boundaries(t, alpha)
        print(f'  {alpha:10.4f}  {t:9.3f}  {a1:11.6f}  {c1:5.3f}  {p2:10.6f}  {c2:5.3f}')

print('\nInterim position rule: smallest multiple of 18 >= N_plan/2')
for npl in range(N_MIN, N_MAX + 1, STEP):
    k = ceil(npl / 2 / STEP) * STEP
    print(f'  N_plan={npl:3d}  interim at {k:3d} blocks  t={k / npl:.3f}')
