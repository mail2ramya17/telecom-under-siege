import sys
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.io import wavfile

SR = 44100
DUR = 112.0
N = int(SR * DUR)
t_all = np.arange(N) / SR
BPM = 120
BEAT = 60 / BPM
rng = np.random.default_rng(11)

BOUNDS = [0, 8, 18, 29, 40, 53, 69, 79, 91, 103, 112]
LEVELS = {
    'pad':  [1.0, 0.8, 0.8, 0.8, 0.7, 0.6, 0.7, 0.9, 0.8, 1.0],
    'arp':  [0.45, 0.7, 0.8, 0.8, 0.8, 1.0, 0.8, 0.9, 0.9, 0.55],
    'bass': [0.0, 0.8, 0.9, 0.9, 1.0, 1.0, 0.9, 0.9, 0.9, 0.0],
    'kick': [0.0, 0.0, 0.0, 0.7, 1.0, 1.0, 0.8, 0.9, 1.0, 0.0],
    'lead': [0.7, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.85, 0.75],
    'tom':  [0.0, 0.0, 0.0, 0.0, 0.8, 1.0, 0.6, 0.0, 0.0, 0.0],
    'heart':[0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    'hat':  [0.0, 0.6, 0.8, 0.8, 0.9, 1.0, 0.8, 0.9, 0.9, 0.0],
    'clap': [0.0, 0.0, 0.0, 0.0, 0.8, 1.0, 0.7, 0.8, 0.8, 0.0],
}


def level_env(vals, ramp=0.6):
    xs, ys = [0.0], [vals[0]]
    for i in range(1, len(vals)):
        b = BOUNDS[i]
        xs += [b - ramp, b + ramp]; ys += [vals[i - 1], vals[i]]
    xs.append(DUR); ys.append(vals[-1])
    return np.interp(t_all, xs, ys)


def section(t):
    for i in range(len(BOUNDS) - 1):
        if t < BOUNDS[i + 1]: return i
    return len(BOUNDS) - 2


def mtof(m): return 440.0 * 2 ** ((m - 69) / 12)


DARK = [(45, [57, 60, 64]), (41, [53, 57, 60]), (48, [55, 60, 64]), (43, [55, 59, 62])]   # Am F C G
TENSE = [(45, [57, 60, 64]), (46, [53, 58, 62]), (41, [53, 57, 60]), (40, [56, 59, 64])]  # Am Bb F E
BRIGHT = [(48, [60, 64, 67]), (43, [55, 59, 62]), (45, [57, 60, 64]), (41, [57, 60, 65])]  # C G Am F


def chord_at(t):
    s = section(t)
    prog = TENSE if s in (4, 5, 6) else BRIGHT if s in (7, 8, 9) else DARK
    return prog[int(t / (4 * BEAT * 2)) % 4]


def lp(x, f, order=2):
    return sosfilt(butter(order, f, 'low', fs=SR, output='sos'), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, 'high', fs=SR, output='sos'), x)


def add(buf, start, sig):
    i = int(start * SR)
    if i >= len(buf): return
    j = min(len(buf), i + len(sig)); buf[i:j] += sig[:j - i]


def saw(f, n, phase=0.0):
    tt = np.arange(n) / SR
    return 2 * ((tt * f + phase) % 1.0) - 1


# ---- pad ----
pad = np.zeros(N)
seg = 8 * BEAT
for k in range(int(DUR / seg) + 1):
    t0 = k * seg
    root, notes = chord_at(t0 + 0.01)
    n = int((seg + 1.2) * SR)
    sig = np.zeros(n)
    for m in notes + [root + 12]:
        for det in (-0.12, 0.0, 0.13):
            sig += saw(mtof(m + det), n, rng.random())
    tt = np.arange(n) / SR
    env = np.minimum(1, tt / 0.9) * np.clip((seg + 1.2 - tt) / 1.2, 0, 1)
    add(pad, t0, sig * env / 12)
pad = lp(pad, 1400)

# ---- bass (8ths) ----
bass = np.zeros(N)
step = BEAT / 2
for k in range(int(DUR / step)):
    t0 = k * step
    root, _ = chord_at(t0 + 0.001)
    n = int(step * SR)
    tt = np.arange(n) / SR
    sig = 0.6 * saw(mtof(root), n) + 0.8 * np.sin(2 * np.pi * mtof(root - 12) * tt)
    env = np.exp(-tt / 0.16) * np.minimum(1, tt / 0.004)
    add(bass, t0, sig * env)
bass = lp(bass, 520)

# ---- arp (16ths) ----
arp = np.zeros(N)
step = BEAT / 4
pat = [0, 2, 4, 3, 1, 5, 4, 2]
for k in range(int(DUR / step)):
    t0 = k * step
    _, notes = chord_at(t0 + 0.001)
    tones = notes + [x + 12 for x in notes]
    m = tones[pat[k % 8]] + 12
    n = int(0.3 * SR); tt = np.arange(n) / SR
    f = mtof(m)
    sig = np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt) + 0.12 * np.sin(6 * np.pi * f * tt)
    env = np.exp(-tt / 0.09) * np.minimum(1, tt / 0.003)
    acc = 1.0 if k % 4 == 0 else 0.7
    add(arp, t0, sig * env * acc)
arp = lp(arp, 4200)
# ping-pong delay
d = int(0.375 * SR)
arpL, arpR = arp.copy(), arp.copy()
for r in range(1, 5):
    g = 0.38 ** r
    sh = d * r
    tgt = arpL if r % 2 == 0 else arpR
    tgt[sh:] += arp[:-sh] * g

# ---- drums ----
kick = np.zeros(N); hat = np.zeros(N); clap = np.zeros(N); duck = np.zeros(N)
kn = int(0.45 * SR); tt = np.arange(kn) / SR
freq = 45 + 110 * np.exp(-tt / 0.035)
kick_s = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-tt / 0.16)
kick_s[:120] += rng.standard_normal(120) * 0.3 * np.linspace(1, 0, 120)
hn = int(0.06 * SR); th = np.arange(hn) / SR
hat_s = hp(rng.standard_normal(hn), 7000) * np.exp(-th / 0.018)
cn = int(0.25 * SR); tc = np.arange(cn) / SR
clap_s = sosfilt(butter(2, [900, 3500], 'band', fs=SR, output='sos'), rng.standard_normal(cn))
clap_env = np.exp(-tc / 0.07)
for o in (0.0, 0.011, 0.022):
    i = int(o * SR); clap_env[i:i + 60] += 0.6
clap_s *= clap_env
duck_s = np.exp(-np.arange(int(0.4 * SR)) / SR / 0.12)

kick_lv = level_env(LEVELS['kick'])
for k in range(int(DUR / BEAT)):
    t0 = k * BEAT
    add(kick, t0, kick_s); add(duck, t0, duck_s * kick_lv[min(N - 1, int(t0 * SR))])
    add(hat, t0 + BEAT / 2, hat_s)
    if section(t0) in (5,):
        add(hat, t0 + BEAT / 4, hat_s * 0.45); add(hat, t0 + 3 * BEAT / 4, hat_s * 0.45)
    if k % 2 == 1:
        add(clap, t0, clap_s)
duck = 1 - 0.55 * np.clip(duck, 0, 1)

# ---- transitions: risers + impacts ----
fx = np.zeros(N)
for b in BOUNDS[1:-1]:
    rn = int(1.6 * SR); tr = np.arange(rn) / SR
    noise = hp(rng.standard_normal(rn), 2500)
    add(fx, b - 1.6, noise * (tr / 1.6) ** 2.5 * 0.35)
    bn = int(1.8 * SR); tb = np.arange(bn) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 40 * np.exp(-tb / 0.08)) / SR) * np.exp(-tb / 0.6)
    add(fx, b, boom * 0.9)


# ---- lead melody ----
MOT = {
 'DARK':  [[76,None,74,72,71,None,72,None],[69,None,72,77,76,None,72,None],[79,None,76,72,74,None,76,None],[74,None,71,67,69,None,None,None]],
 'TENSE': [[76,None,77,76,72,None,69,None],[74,None,77,74,70,None,74,None],[72,None,77,72,69,None,72,None],[71,None,68,71,76,None,None,None]],
 'BRIGHT':[[72,None,76,79,77,None,76,None],[74,None,79,74,71,None,74,None],[72,None,76,81,79,None,76,None],[77,None,76,72,72,None,None,None]],
}
lead = np.zeros(N)
for k in range(int(DUR / BEAT)):
    t0 = k * BEAT; s_ = section(t0)
    name = 'TENSE' if s_ in (4,5,6) else 'BRIGHT' if s_ in (7,8,9) else 'DARK'
    ci = int(t0 / (8 * BEAT)) % 4; bi = k % 8
    m = MOT[name][ci][bi]
    if m is None: continue
    ln = 1
    while bi + ln < 8 and MOT[name][ci][bi + ln] is None and ln < 2: ln += 1
    durn = ln * BEAT * 0.95; n = int((durn + 0.3) * SR); tt = np.arange(n) / SR
    f = mtof(m - 12) * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * tt) * np.minimum(1, tt / 0.3))
    ph = np.cumsum(f) / SR
    sig = (2 * ((ph * 1.003) % 1) - 1) + (2 * ((ph * 0.997) % 1) - 1) + 0.8 * np.sin(2 * np.pi * ph)
    env = np.minimum(1, tt / 0.015) * np.clip((durn + 0.3 - tt) / 0.3, 0, 1) * (0.75 + 0.25 * np.exp(-tt / 0.2))
    add(lead, t0, sig * env)
lead = lp(lead, 2600)

# ---- toms ----
tom = np.zeros(N)
tn = int(0.7 * SR); tt = np.arange(tn) / SR
tom_s = np.sin(2 * np.pi * np.cumsum(62 + 50 * np.exp(-tt / 0.05)) / SR) * np.exp(-tt / 0.28)
tom_s += lp(rng.standard_normal(tn), 900) * np.exp(-tt / 0.05) * 0.5
for k in range(int(DUR / (4 * BEAT))):
    b0 = k * 4 * BEAT
    for o, g in ((0, 1.0), (1.5, 0.7), (2.5, 0.8), (3.0, 0.6), (3.5, 0.9)):
        add(tom, b0 + o * BEAT, tom_s * g)

# ---- heartbeat ----
heart = np.zeros(N)
hn2 = int(0.35 * SR); tt = np.arange(hn2) / SR
hb = np.sin(2 * np.pi * np.cumsum(48 + 30 * np.exp(-tt / 0.03)) / SR) * np.exp(-tt / 0.12)
for k in range(int(DUR / (2 * BEAT))):
    add(heart, k * 2 * BEAT, hb); add(heart, k * 2 * BEAT + 0.24, hb * 0.65)

# ---- reverb ----
irn = int(2.2 * SR); ti = np.arange(irn) / SR
ir = rng.standard_normal(irn) * np.exp(-ti / 0.55); ir = lp(ir, 5000); ir /= np.sqrt(np.sum(ir ** 2))


def verb(x, wet):
    return x + wet * fftconvolve(x, ir)[:N]


# ---- mix ----
L = level_env
padm = verb(pad * L(LEVELS['pad']) * duck, 0.5) * 0.24
bassm = bass * L(LEVELS['bass']) * duck * 0.34
arpLm = verb(arpL * L(LEVELS['arp']), 0.35) * 0.08
arpRm = verb(arpR * L(LEVELS['arp']), 0.35) * 0.08
kickm = kick * kick_lv * 0.6
hatm = hat * L(LEVELS['hat']) * 0.09
clapm = verb(clap * L(LEVELS['clap']), 0.4) * 0.16
fxm = verb(fx, 0.3) * 0.26
leadm = verb(lead * L(LEVELS['lead']), 0.6) * 0.11
tomm = verb(tom * L(LEVELS['tom']), 0.35) * 0.42
heartm = heart * L(LEVELS['heart']) * 0.7

left = padm + bassm + arpLm + kickm + leadm + tomm + heartm + hatm * 0.8 + clapm + fxm
right = padm + bassm + arpRm + kickm + leadm + tomm + heartm + hatm * 1.2 + clapm + fxm
mix = np.stack([left, right], 1)
mix = np.tanh(mix / np.max(np.abs(mix)) * 1.4) / np.tanh(1.4)
fade = np.minimum(1, t_all / 1.5) * np.clip((DUR - t_all) / 3.5, 0, 1)
mix *= fade[:, None] * 0.89
wavfile.write(sys.argv[1] if len(sys.argv) > 1 else 'music_cinematic.wav', SR, (mix * 32767).astype(np.int16))
print('ok', mix.shape, np.max(np.abs(mix)))
