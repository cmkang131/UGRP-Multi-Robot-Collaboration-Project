# Token/call measurement from saved raw model requests/responses + budget PROJECTION (estimate).
# Pure standard library. Reads raw files read-only. No SIM, no model call, no network.
#
# Measured: first-call usage of the v63 adapter pilot (outputs/zone-study-adapter-pilot-r10, 16 accepted
#   calls; preflight-01 v62 excluded because it is a different source and was rejected).
# Reference only: ZC2 (teacher executor, different pipeline) calls per trial from committed results.json.
# Everything after "PROJECTION" is an ESTIMATE: multi-turn calls per trial and per-call growth are unmeasured
# for the own-camera v69 multi-turn runner.
import glob, hashlib, json, os, sqlite3, statistics as st, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10'
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RUNS = ('preflight-02-v63', 'cohort-01-v63')


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


rows = []
for run in RUNS:
    for resp in sorted(glob.glob(os.path.join(ROOT, run, '*', 'wire', '*-response.json'))):
        req = resp.replace('-response.json', '-request.json')
        r, q = json.load(open(resp)), json.load(open(req))
        u = r['usage']
        text_chars = img_b64 = n_img = 0
        for m in q['messages']:
            c = m['content']
            if isinstance(c, str):
                text_chars += len(c)
                continue
            for part in c:
                if part['type'] == 'text':
                    text_chars += len(part['text'])
                elif part['type'] == 'image_url':
                    n_img += 1
                    img_b64 += len(part['image_url']['url'])
        cond = resp.split(os.sep)[-3]
        rows.append(dict(run=run, cond=cond, prompt=u['prompt_tokens'], completion=u['completion_tokens'],
                         total=u['total_tokens'], reasoning=u['total_tokens'] - u['prompt_tokens'] - u['completion_tokens'],
                         text_chars=text_chars, n_img=n_img, img_b64=img_b64,
                         resp_sha=sha(resp), req_sha=sha(req), resp=os.path.relpath(resp, ROOT)))

print('MEASURED first-call usage (raw wire responses, v63, accepted calls)')
print(f'  calls={len(rows)}  runs={RUNS}')
for k in ('prompt', 'completion', 'reasoning', 'total', 'text_chars', 'n_img'):
    v = [r[k] for r in rows]
    print(f'  {k:11s} mean={st.mean(v):9.1f} sd={st.pstdev(v):7.1f} min={min(v):6d} max={max(v):6d}')
by = {}
for r in rows:
    by.setdefault(r['cond'], []).append(r['total'])
for c in ('no_comm', 'peer_ko', 'leader_ko', 'structured'):
    print(f'  total by condition {c:10s} n={len(by[c])} mean={st.mean(by[c]):8.1f}')
TOK_CALL = st.mean(r['total'] for r in rows)
print(f'  sum total={sum(r["total"] for r in rows)} (README v63 16 calls: 174,385)')

# Remaining pilot budget (read-only)
db = os.path.join(ROOT, 'budget.sqlite')
con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
used_tok, used_att, n_send = con.execute('select sum(tokens), sum(attempts), count(*) from sends').fetchone()
meta = json.loads(con.execute('select value from meta').fetchone()[0])
cap_tok, cap_att = meta.get('token_cap'), meta.get('attempt_cap')
print('\nREMAINING pilot budget DB (read-only)', os.path.relpath(db, ROOT), 'sha256', sha(db))
print(f'  cap tokens={cap_tok} attempts={cap_att}  used tokens={used_tok} attempts={used_att} sends={n_send}')
if cap_tok is not None:
    print(f'  remaining tokens={cap_tok - used_tok} attempts={cap_att - used_att}')

# Reference: ZC2 calls/trial (teacher executor, zone_wide, gemini-3.8-flash) -- NOT the study pipeline
zc2 = json.load(open(os.path.join(REPO, 'experiments/2026-09-25-zone-communication/results.json')))['runs']
calls = [r['llm_calls'] for r in zc2]
tpc = [(r['prompt_tokens'] + r['completion_tokens']) / r['llm_calls'] for r in zc2]
print('\nREFERENCE ZC2 (different pipeline): calls/trial mean=%.1f min=%d max=%d; tokens/call mean=%.0f' %
      (st.mean(calls), min(calls), max(calls), st.mean(tpc)))

print('\nPROJECTION (ESTIMATE). tokens/trial = calls/trial x tokens/call x growth')
CALLS = {'low(ZC2 mean 15)': 15, 'mid(10/robot) 30': 30, 'cap(90/trial)': 90}
GROWTH = {'x1.0': 1.0, 'x1.5': 1.5}  # later calls carry inbox + own command history (unmeasured)
# Trial counts (see prereg_main_DRAFT.json). Main = 4 conditions x blocks; replicate 1/3 of blocks;
# diagnostics: yoked-wake 36, scale=0 4x36=144, branch replay 72 partial trials (counted as 0.5 trial).
def trials_main(blocks):
    return blocks * 4 + (blocks // 3) * 4
DIAG = 36 + 144 + 36  # yoked + scale0 + branch(72 x 0.5)
plans = [('pilot 18 blocks (72 + no replicate)', 72), ('main N=36', trials_main(36)), ('main N=54', trials_main(54)),
         ('main N=72', trials_main(72)), ('main N=108 (N_max)', trials_main(108)), ('diagnostics (all arms)', DIAG),
         ('TOTAL pilot + N_max + diagnostics', 72 + trials_main(108) + DIAG)]
hdr = '  %-36s %7s' % ('plan', 'trials') + ''.join('  %18s' % f'{c}{g}' for c in CALLS for g in GROWTH)
print(hdr)
for name, n in plans:
    cells = ''
    for c, cv in CALLS.items():
        for g, gv in GROWTH.items():
            cells += '  %17.1fM' % (n * cv * TOK_CALL * gv / 1e6)
    print('  %-36s %7d' % (name, n) + cells)
print('\n  model calls (= HTTP attempts if no retry) for TOTAL: ' +
      ', '.join(f'{c}: {(72 + trials_main(108) + DIAG) * cv:,}' for c, cv in CALLS.items()))
print('  USD: provider cost_usd=null (subscription proxy); USD = tokens x unit price, unit price not recorded.')
print('\nper-file sha256 (raw inputs):')
for r in rows:
    print(' ', r['resp'], r['resp_sha'][:16], 'req', r['req_sha'][:16])
