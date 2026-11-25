import math, random, sys, subprocess, os
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1920, 1080, 30
BG = (7, 11, 20)
CY = (34, 211, 238); RED = (244, 63, 94); GRN = (52, 211, 153); AMB = (251, 191, 36)
VIO = (167, 139, 250); PINK = (236, 72, 153); WHT = (236, 242, 255); MUT = (148, 163, 189)
DIM = (52, 66, 92); PANEL = (13, 20, 35)
FD = '/usr/share/fonts/opentype/inter/'


@lru_cache(None)
def F(size, w='Regular'):
    if w == 'Mono':
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', size)
    if w == 'MonoB':
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', size)
    return ImageFont.truetype(FD + f'Inter-{w}.otf', size)


def clamp(x): return max(0.0, min(1.0, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def ramp(t, s, dur=0.5): return ease((t - s) / dur)
def mix(c, a, bg=BG):
    a = clamp(a); return tuple(int(bg[i] + (c[i] - bg[i]) * a) for i in range(3))
def tint(c, k=0.16): return tuple(int(BG[i] * 0.8 + c[i] * k) for i in range(3))


def T(d, xy, s, size, w='Regular', c=WHT, a=1.0, anchor='la', slide=18):
    if a <= 0.01: return
    x, y = xy
    d.text((x, y + (1 - a) * slide), s, font=F(size, w), fill=mix(c, a), anchor=anchor)


def wrap(s, font, maxw):
    lines, cur = [], ''
    for word in s.split():
        tst = (cur + ' ' + word).strip()
        if font.getlength(tst) <= maxw: cur = tst
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines


def TW(d, xy, s, size, w, c, a, maxw, lh=1.3, anchor='la'):
    f = F(size, w); y = xy[1]
    for ln in wrap(s, f, maxw):
        T(d, (xy[0], y), ln, size, w, c, a, anchor=anchor)
        y += size * lh
    return y


def panel(d, box, a, edge=CY, fill=PANEL, r=16, width=2):
    if a <= 0.01: return
    d.rounded_rectangle(box, r, fill=mix(fill, a), outline=mix(edge, a * 0.85), width=width)


def pill(d, x, y, s, size, col, a, anchor='l', w='SemiBold', padx=16, solid=False):
    if a <= 0.01: return 0
    f = F(size, w); tw = f.getlength(s); h = size + 18
    if anchor == 'c': x -= (tw + 2 * padx) / 2
    y += (1 - a) * 12
    box = [x, y - h / 2, x + tw + 2 * padx, y + h / 2]
    d.rounded_rectangle(box, h / 2, fill=mix(col if solid else tint(col), a), outline=mix(col, a * 0.9), width=2)
    d.text((x + padx, y), s, font=f, fill=mix(BG if solid else col, a), anchor='lm')
    return tw + 2 * padx


def arrow(d, p1, p2, col, a, width=3, head=12):
    if a <= 0.01: return
    d.line([p1, p2], fill=mix(col, a), width=width)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    pts = [p2, (p2[0] - head * math.cos(ang - 0.45), p2[1] - head * math.sin(ang - 0.45)),
           (p2[0] - head * math.cos(ang + 0.45), p2[1] - head * math.sin(ang + 0.45))]
    d.polygon(pts, fill=mix(col, a))


def check(d, cx, cy, col, a, r=16):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=mix(tint(col, 0.3), a), outline=mix(col, a), width=2)
    d.line([(cx - 7, cy), (cx - 2, cy + 6), (cx + 8, cy - 6)], fill=mix(col, a), width=3)


def bang(d, cx, cy, col, a, r=16):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=mix(tint(col, 0.3), a), outline=mix(col, a), width=2)
    d.text((cx, cy + 1), '!', font=F(22, 'Bold'), fill=mix(col, a), anchor='mm')


# ---------- background ----------
def make_bg():
    y = np.linspace(0, 1, H)[:, None]; x = np.linspace(0, 1, W)[None, :]
    base = np.zeros((H, W, 3), np.float32)
    top = np.array([6, 10, 20], np.float32); bot = np.array([10, 17, 32], np.float32)
    base[:] = top + (bot - top) * y[..., None]
    grid = np.zeros((H, W), np.float32)
    grid[::60, :] = 1; grid[:, ::60] = 1
    base += grid[..., None] * np.array([6, 9, 14], np.float32)
    v = ((x - 0.5) ** 2 + (y - 0.5) ** 2)
    base *= (1 - 0.55 * v)[..., None]
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


BGIMG = make_bg()

rng = random.Random(7)
NODES = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(-22, 22), rng.uniform(-15, 15), rng.random() < 0.13)
         for _ in range(72)]


def network(d, t, a, clear=True, ry=300, rx=860, cyy=520):
    pts = []
    for x, y, vx, vy, bad in NODES:
        pts.append(((x + vx * t) % W, (y + vy * t) % H, bad))

    def fac(mx, my):
        if not clear: return 1
        e = ((mx - 960) / rx) ** 2 + ((my - cyy) / ry) ** 2
        return clamp((e - 0.55) / 0.5)
    R = 230
    for i in range(len(pts)):
        x1, y1, b1 = pts[i]
        for j in range(i + 1, len(pts)):
            x2, y2, b2 = pts[j]
            dd = (x1 - x2) ** 2 + (y1 - y2) ** 2
            if dd < R * R:
                k = (1 - math.sqrt(dd) / R) * 0.5 * a * fac((x1 + x2) / 2, (y1 + y2) / 2)
                if k > 0.02:
                    col = RED if (b1 or b2) else CY
                    d.line([(x1, y1), (x2, y2)], fill=mix(col, k), width=1)
    for px, py, bad in pts:
        f = fac(px, py) * a
        if f < 0.03: continue
        if bad:
            r = 5 + 2.5 * math.sin(t * 5 + px)
            d.ellipse([px - r - 6, py - r - 6, px + r + 6, py + r + 6], outline=mix(RED, f * 0.5), width=1)
            d.ellipse([px - r, py - r, px + r, py + r], fill=mix(RED, f))
        else:
            d.ellipse([px - 3.5, py - 3.5, px + 3.5, py + 3.5], fill=mix(CY, f * 0.9))


def header(d, t, num, title, col=CY):
    a = ramp(t, 0.05, 0.5)
    T(d, (90, 64), num, 28, 'Bold', col, a)
    T(d, (90 + F(28, 'Bold').getlength(num) + 22, 64), title, 28, 'SemiBold', WHT, a)
    d.line([(90, 112), (90 + (W - 180) * ease(t / 1.0), 112)], fill=mix(DIM, a), width=1)


def footer(d, t, idx, n=8):
    a = ramp(t, 0.1, 0.5)
    T(d, (90, 1020), 'TELECOM SECURITY  ·  THE AI ERA', 18, 'SemiBold', DIM, a, slide=0)
    T(d, (W - 90, 1020), f'{idx:02d} / {n:02d}', 18, 'SemiBold', DIM, a, anchor='ra', slide=0)


# ---------- scenes ----------
def s_title(d, t, dur):
    network(d, t, ramp(t, 0, 1.2))
    a = ramp(t, 0.4, 0.8)
    k = 'AN INNOVATIVE SECURITY ENGINEER’S FIELD GUIDE'
    T(d, (960, 330), k, 24, 'SemiBold', CY, a, anchor='ma')
    f = F(124, 'Black'); w1 = f.getlength('TELECOM '); w2 = f.getlength('UNDER SIEGE'); x0 = 960 - (w1 + w2) / 2
    a2 = ramp(t, 0.8, 0.8)
    T(d, (x0, 390), 'TELECOM ', 124, 'Black', WHT, a2, slide=30)
    a3 = ramp(t, 1.2, 0.8)
    T(d, (x0 + w1, 390), 'UNDER SIEGE', 124, 'Black', RED, a3, slide=30)
    T(d, (960, 560), 'Security in the age of AI: why platforms hold your data,', 34, 'Regular', MUT, ramp(t, 2.0, 0.8), anchor='ma')
    T(d, (960, 606), 'how attackers get to it, and how engineers fight back.', 34, 'Regular', MUT, ramp(t, 2.2, 0.8), anchor='ma')
    tags = [('5G CORE', CY), ('SS7 / DIAMETER', VIO), ('CLOUD DATA', AMB), ('APIs', PINK), ('AI AGENTS', GRN)]
    f2 = F(20, 'SemiBold'); ws = [f2.getlength(s) + 32 for s, _ in tags]; gap = 18
    x = 960 - (sum(ws) + gap * (len(ws) - 1)) / 2
    for i, (s, c) in enumerate(tags):
        pill(d, x, 712, s, 20, c, ramp(t, 3.0 + i * 0.18, 0.5)); x += ws[i] + gap


def s_paradox(d, t, dur):
    header(d, t, '01', 'THE PARADOX', CY); footer(d, t, 1)
    have = ['AI-driven, self-optimizing networks', 'Cloud-native 5G cores & automation',
            'The most skilled security workforce ever', 'Billions invested in security tooling']
    face = ['AI-written phishing & deepfake voices', 'Nation-state hackers inside carrier cores',
            'Mass theft of call records & customer PII', 'SIM-swap fraud draining bank accounts']
    for side, (x0, col, ttl, items, icon, st) in enumerate([
            (90, GRN, 'WHAT WE HAVE', have, check, 0.4), (990, RED, 'WHAT WE STILL FACE', face, bang, 1.6)]):
        a = ramp(t, st, 0.6)
        panel(d, [x0, 160, x0 + 840, 690], a, col)
        T(d, (x0 + 40, 195), ttl, 26, 'Bold', col, a)
        for i, s in enumerate(items):
            ai = ramp(t, st + 0.4 + i * 0.3, 0.5); y = 290 + i * 98
            if ai > 0.01:
                icon(d, x0 + 58, y + 18, col, ai)
                T(d, (x0 + 96, y + 2), s, 31, 'Medium', WHT, ai)
    a = ramp(t, 4.6, 0.7)
    panel(d, [90, 730, 1830, 960], a, AMB, fill=(20, 18, 14))
    T(d, (960, 762), 'WHY?', 24, 'Bold', AMB, a, anchor='ma')
    parts = [('MORE DATA', CY), ('  +  ', MUT), ('MORE CONNECTIVITY', VIO), ('  +  ', MUT), ('MORE AI', GRN),
             ('  =  ', MUT), ('BIGGER ATTACK SURFACE', RED)]
    f = F(38, 'Black'); tot = sum(f.getlength(s) for s, _ in parts); x = 960 - tot / 2
    for i, (s, c) in enumerate(parts):
        T(d, (x, 812), s, 38, 'Black', c, ramp(t, 5.2 + i * 0.22, 0.5)); x += f.getlength(s)
    T(d, (960, 890), 'Attackers now use the same AI, automation and cloud scale that defenders do.', 28, 'Regular',
      MUT, ramp(t, 7.0, 0.6), anchor='ma')


def s_incidents(d, t, dur):
    header(d, t, '02', 'THIS IS NOT THEORETICAL', AMB); footer(d, t, 2)
    xs = [300, 740, 1180, 1620]
    d.line([(150, 330), (150 + 1620 * ease(t / 1.6), 330)], fill=mix(DIM, 1), width=3)
    ev = [('2021', 'T-Mobile (US)', 'Attacker got in through an exposed router; personal data of ~76M people — incl. SSNs and IMEIs — exposed.'),
          ('2024', 'AT&T (US)', 'Call & text records of nearly all wireless customers stolen from a third-party cloud data platform using stolen credentials.'),
          ('2024', 'Salt Typhoon', 'State-backed hackers inside multiple US carriers — including the lawful-intercept (wiretap) systems.'),
          ('2025', 'SK Telecom (KR)', 'Malware on core servers exposed USIM data of ~27M subscribers, forcing mass SIM replacements.')]
    for i, (yr, name, txt) in enumerate(ev):
        a = ramp(t, 0.8 + i * 1.0, 0.6); x = xs[i]
        if a <= 0.01: continue
        r = 13 + 3 * math.sin(t * 4 + i)
        d.ellipse([x - r - 8, 330 - r - 8, x + r + 8, 330 + r + 8], outline=mix(RED, a * 0.4), width=2)
        d.ellipse([x - 11, 319, x + 11, 341], fill=mix(RED, a))
        T(d, (x, 190), yr, 64, 'Black', AMB, a, anchor='ma')
        panel(d, [x - 200, 390, x + 200, 740], a, RED)
        T(d, (x - 172, 420), name, 32, 'Bold', WHT, a)
        TW(d, (x - 172, 480), txt, 25, 'Regular', MUT, a, 344, 1.42)
    a = ramp(t, 5.6, 0.7)
    panel(d, [150, 790, 1770, 930], a, CY, fill=(10, 22, 32))
    T(d, (960, 815), 'The common thread', 24, 'Bold', CY, a, anchor='ma')
    T(d, (960, 860), 'Attackers went after the data carriers keep — and the trust between their systems.', 32, 'SemiBold', WHT, a, anchor='ma')
    T(d, (960, 965), 'Based on public company disclosures and US/Korean government statements, 2021–2025.', 18, 'Regular', DIM, ramp(t, 6.0, 0.6), anchor='ma', slide=0)


def s_data(d, t, dur):
    header(d, t, '03', 'WHY PLATFORMS COLLECT YOUR DATA — AND WHAT', VIO); footer(d, t, 3)
    cx, cy = 520, 580
    items = [('Identity & KYC', CY), ('SIM keys · IMSI · IMEI', VIO), ('Location (every tower ping)', AMB),
             ('Call & SMS records', RED), ('Payment & billing', GRN), ('Browsing & DNS metadata', PINK),
             ('Device & app telemetry', CY), ('Chats with AI agents', AMB)]
    a0 = ramp(t, 0.3, 0.6)
    for rr in (150, 300):
        d.ellipse([cx - rr, cy - rr * 0.92, cx + rr, cy + rr * 0.92], outline=mix(DIM, a0 * 0.8), width=1)
    pos = []
    for i, (s, c) in enumerate(items):
        ang = -math.pi / 2 + i * 2 * math.pi / 8
        px = cx + 330 * math.cos(ang); py = cy + 300 * math.sin(ang) + 4 * math.sin(t * 1.5 + i)
        pos.append((px, py))
        a = ramp(t, 0.8 + i * 0.25, 0.5)
        if a > 0.01:
            d.line([(cx, cy), (px, py)], fill=mix(c, a * 0.35), width=2)
            for k in range(2):
                ph = ((t * 0.45 + k * 0.5 + i * 0.13) % 1.0)
                qx = px + (cx - px) * ph; qy = py + (cy - py) * ph
                d.ellipse([qx - 4, qy - 4, qx + 4, qy + 4], fill=mix(c, a))
    for i, (s, c) in enumerate(items):
        a = ramp(t, 0.8 + i * 0.25, 0.5)
        pill(d, pos[i][0], pos[i][1], s, 20, c, a, anchor='c')
    r = 74 + 3 * math.sin(t * 3)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=mix((18, 30, 52), a0), outline=mix(CY, a0), width=3)
    T(d, (cx, cy - 16), 'YOU', 34, 'Black', WHT, a0, anchor='mm', slide=0)
    T(d, (cx, cy + 22), 'subscriber', 18, 'Medium', MUT, a0, anchor='mm', slide=0)

    x0 = 1060
    T(d, (x0, 160), 'WHY THEY KEEP IT', 26, 'Bold', VIO, ramp(t, 2.6, 0.5))
    why = [('OPERATIONS', CY, 'Run the network: routing, roaming, billing'),
           ('REGULATORY', VIO, 'Lawful intercept & data-retention mandates'),
           ('SECURITY', GRN, 'Fraud, spam & SIM-swap detection'),
           ('AI', AMB, 'Train AI for network tuning & support bots'),
           ('REVENUE', RED, 'Personalization, ads & data partnerships')]
    for i, (tag, c, s) in enumerate(why):
        a = ramp(t, 3.0 + i * 0.45, 0.5); y = 230 + i * 116
        panel(d, [x0, y, 1830, y + 96], a, c, r=12)
        pw = pill(d, x0 + 24, y + 48, tag, 17, c, a, solid=True, padx=12)
        T(d, (x0 + 24 + max(pw, 150) + 24, y + 32), s, 26, 'Medium', WHT, a)
    a = ramp(t, 6.0, 0.6)
    T(d, (x0, 838), 'Every record kept is a record', 40, 'Black', WHT, a)
    T(d, (x0, 890), 'that can be stolen.', 40, 'Black', RED, ramp(t, 6.3, 0.6))


def s_map(d, t, dur):
    header(d, t, '04', 'THE ATTACK SURFACE MAP', RED); footer(d, t, 4)
    N = {'dev': (210, 390, 'Devices & SIMs', 'phones · IoT · eSIM'),
         'ran': (570, 390, 'RAN / 5G towers', 'gNB · O-RAN'),
         'edge': (930, 390, 'Edge routers & VPN', 'transport · internet edge'),
         'core': (1300, 390, '5G CORE', 'AMF · SMF · UPF · UDM'),
         'roam': (1680, 390, 'Roaming partners', 'SS7 · Diameter · GTP'),
         'ai': (210, 690, 'AI support agents', 'chatbots · voice bots'),
         'api': (570, 690, 'Customer apps & APIs', 'web · mobile · retail'),
         'lake': (1300, 690, 'Data lake & OSS/BSS', 'CDRs · billing · CRM'),
         'ven': (1680, 690, 'Vendors & cloud', 'SaaS · MSPs · contractors')}
    links = [('dev', 'ran'), ('ran', 'edge'), ('edge', 'core'), ('core', 'roam'), ('core', 'lake'),
             ('ai', 'api'), ('api', 'lake'), ('lake', 'ven'), ('dev', 'api')]
    threats = {'dev': 'SIM swap · smishing · malware', 'ran': 'Rogue base stations · 2G downgrade',
               'edge': 'Unpatched CVEs · default creds', 'core': 'Lateral movement · LI abuse',
               'roam': 'Location tracking · SMS intercept', 'ai': 'Prompt injection · PII leaks',
               'api': 'BOLA · credential stuffing', 'lake': 'Stolen creds · bulk exfiltration',
               'ven': 'Supply chain · shared access'}
    order = ['dev', 'ran', 'edge', 'core', 'roam', 'ai', 'api', 'lake', 'ven']
    bw, bh = 300, 104
    al = ramp(t, 0.6, 0.8)
    for a_, b_ in links:
        p1 = N[a_][:2]; p2 = N[b_][:2]
        d.line([p1, p2], fill=mix(DIM, al), width=3)
        for k in range(3):
            ph = (t * 0.35 + k / 3 + hash(a_ + b_) % 7 / 7) % 1
            q = (p1[0] + (p2[0] - p1[0]) * ph, p1[1] + (p2[1] - p1[1]) * ph)
            d.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], fill=mix(CY, al * 0.8))
    # attack path highlight
    path = [N['edge'][:2], N['core'][:2], N['lake'][:2]]
    ap = ramp(t, 8.2, 0.6)
    if ap > 0.01:
        for p1, p2 in zip(path, path[1:]):
            d.line([p1, p2], fill=mix(RED, ap), width=6)
        segs = [(path[0], path[1]), (path[1], path[2])]
        for k in range(4):
            ph = (t * 0.5 + k / 4) % 1 * 2
            si = int(ph); f = ph - si
            p1, p2 = segs[min(si, 1)]
            q = (p1[0] + (p2[0] - p1[0]) * f, p1[1] + (p2[1] - p1[1]) * f)
            d.ellipse([q[0] - 8, q[1] - 8, q[0] + 8, q[1] + 8], fill=mix(RED, ap))
    for i, key in enumerate(order):
        x, y, name, sub = N[key]
        a = ramp(t, 0.2 + i * 0.12, 0.5)
        hot = key in ('edge', 'core', 'lake') and ap > 0.01
        edge = RED if hot else (CY if key != 'core' else VIO)
        panel(d, [x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2], a, edge, width=3 if hot or key == 'core' else 2)
        T(d, (x, y - 14), name, 25, 'Bold', WHT, a, anchor='mm', slide=0)
        T(d, (x, y + 20), sub, 18, 'Medium', MUT, a, anchor='mm', slide=0)
    for i, key in enumerate(order):
        x, y = N[key][:2]
        a = ramp(t, 2.2 + i * 0.55, 0.5)
        if a <= 0.01: continue
        top = y < 550
        ty = y - bh / 2 - 34 if top else y + bh / 2 + 34
        pill(d, x, ty, threats[key], 18, RED, a, anchor='c', padx=12)
        rr = bw / 2 + 10 + 18 * clamp((t - 2.2 - i * 0.55) / 0.8)
        fa = a * (1 - clamp((t - 2.2 - i * 0.55) / 0.8))
        if fa > 0.02:
            d.rounded_rectangle([x - rr, y - bh / 2 - (rr - bw / 2), x + rr, y + bh / 2 + (rr - bw / 2)], 20,
                                outline=mix(RED, fa), width=2)
    T(d, (960, 900), 'Typical intrusion:  edge device  →  5G core  →  customer data', 30, 'Bold', RED,
      ramp(t, 8.6, 0.6), anchor='ma')


def s_chains(d, t, dur):
    header(d, t, '05', 'HOW THE ATTACKS ACTUALLY FLOW', RED); footer(d, t, 5)
    lanes = [('SIM-SWAP + AI VOICE', AMB, ['Scrape victim’s social media', 'Deepfake voice call to support',
                                           'Number ported to attacker’s SIM', 'Intercept SMS one-time codes', 'Drain bank & crypto accounts']),
             ('SIGNALING ABUSE', VIO, ['Abuse roaming interconnect access', 'Send SS7 / Diameter queries',
                                       'Locate a phone by its number', 'Redirect calls & SMS', 'Silent surveillance']),
             ('EDGE-DEVICE APT', RED, ['Exploit unpatched router or VPN', 'Implant + steal device configs',
                                       'Live off the land, move laterally', 'Reach core & intercept systems', 'Long-term espionage']),
             ('CLOUD DATA THEFT', CY, ['Infostealer harvests credentials', 'Log in to vendor cloud — no MFA',
                                       'Bulk-query the data warehouse', 'Exfiltrate call & text records', 'Extortion & resale']),
             ('AI AGENT ABUSE', PINK, ['Prompt injection via chat or email', 'Agent calls account tools',
                                       'Leaks PII or swaps the SIM', 'Repeat at machine speed', 'Fraud at scale'])]
    y0, lh = 160, 162
    cw, gap, x0 = 254, 30, 420
    for i, (name, col, steps) in enumerate(lanes):
        st = 0.5 + i * 2.4; y = y0 + i * lh; cyy = y + 66
        a = ramp(t, st, 0.5)
        if a <= 0.01: continue
        d.rounded_rectangle([90, y + 10, 96, y + 122], 3, fill=mix(col, a))
        T(d, (118, y + 22), f'PATH {i + 1}', 18, 'Bold', MUT, a)
        TW(d, (118, y + 50), name, 27, 'Black', col, a, 270, 1.15)
        for j, s in enumerate(steps):
            aj = ramp(t, st + 0.3 + j * 0.32, 0.45)
            if aj <= 0.01: continue
            x = x0 + j * (cw + gap)
            last = j == len(steps) - 1
            fill = tint(RED, 0.35) if last else PANEL
            panel(d, [x, y + 14, x + cw, y + 118], aj, RED if last else col, fill=fill, r=12)
            lines = wrap(s, F(21, 'SemiBold'), cw - 36)
            yy = cyy - len(lines) * 13 + 2
            for ln in lines:
                T(d, (x + 18, yy), ln, 21, 'SemiBold', WHT, aj, slide=8); yy += 27
            if j > 0:
                arrow(d, (x - gap + 4, cyy), (x - 6, cyy), col, aj, 3, 10)


def s_exposure(d, t, dur):
    header(d, t, '06', 'WHERE THE DATA GETS EXPOSED', AMB); footer(d, t, 6)
    tiles = [('Over-collection', 'Data kept “just in case” for years becomes the breach payload.', AMB),
             ('Legacy signaling', 'SS7 was built on trust between carriers — with almost no authentication.', VIO),
             ('Edge devices', 'Unpatched internet-facing routers & VPNs are a favourite front door.', RED),
             ('Third-party cloud', 'Vendor platforms & data lakes without MFA or monitoring.', CY),
             ('Shadow APIs', 'Undocumented, over-permissive endpoints that return other users’ data.', PINK),
             ('Weak identity', 'SMS codes, shared admin accounts, no phishing-resistant MFA.', AMB),
             ('Flat networks', 'Once inside IT, attackers pivot to OSS, the core and intercept systems.', RED),
             ('Over-privileged AI', 'LLM agents wired to account tools with no guardrails or human approval.', GRN)]
    tw_, th, gx, gy = 412, 340, 30, 30
    for i, (ttl, txt, c) in enumerate(tiles):
        r, cidx = divmod(i, 4)
        x = 90 + cidx * (tw_ + gx); y = 160 + r * (th + gy)
        a = ramp(t, 0.4 + i * 0.32, 0.5)
        panel(d, [x, y, x + tw_, y + th], a, c)
        T(d, (x + 30, y + 26), f'{i + 1:02d}', 60, 'Black', mix(c, 0.55), a)
        T(d, (x + 30, y + 122), ttl, 32, 'Bold', WHT, a)
        TW(d, (x + 30, y + 178), txt, 25, 'Regular', MUT, a, tw_ - 60, 1.4)


def s_defense(d, t, dur):
    header(d, t, '07', 'THE DEFENSE PATH', GRN); footer(d, t, 7)
    stages = [('MINIMIZE', CY, ['Data inventory & classification', 'Tokenize / encrypt PII', 'Short retention by default']),
              ('IDENTITY', VIO, ['FIDO2 passkeys for all staff', 'SIM-swap & port-out locks', 'Step-up checks on account changes']),
              ('NETWORK', AMB, ['SS7 / Diameter / GTP firewalls', 'Segment IT ↔ core ↔ intercept', 'Patch & harden edge gear fast']),
              ('PIPELINE', PINK, ['SAST · DAST · SCA in CI/CD', 'IaC & container scanning', 'SBOM + signed artifacts']),
              ('AI GUARD', GRN, ['Least-privilege agent tools', 'Input / output filtering', 'Human approval for risky actions']),
              ('DETECT', RED, ['Signaling anomaly analytics', 'UEBA + threat hunting', 'Map to MITRE ATT&CK & FiGHT'])]
    n = len(stages); cw = 270; gap = (1740 - n * cw) / (n - 1)
    cx = [90 + i * (cw + gap) + cw / 2 for i in range(n)]
    ly = 240
    pl = ease(t / 3.2)
    d.line([(cx[0], ly), (cx[0] + (cx[-1] - cx[0]) * pl, ly)], fill=mix(GRN, 0.6), width=4)
    if t > 3.2:
        for k in range(3):
            ph = (t * 0.18 + k / 3) % 1
            q = cx[0] + (cx[-1] - cx[0]) * ph
            d.ellipse([q - 7, ly - 7, q + 7, ly + 7], fill=mix(GRN, 1))
    for i, (nm, c, ctl) in enumerate(stages):
        a = ramp(t, 0.3 + i * 0.5, 0.5); x = cx[i]
        if a <= 0.01: continue
        r = 46
        d.ellipse([x - r, ly - r, x + r, ly + r], fill=mix(tint(c, 0.35), a), outline=mix(c, a), width=3)
        T(d, (x, ly), str(i + 1), 36, 'Black', c, a, anchor='mm', slide=0)
        T(d, (x, ly + 72), nm, 26, 'Black', c, a, anchor='ma')
        bx = x - cw / 2
        panel(d, [bx, 360, bx + cw, 690], a, c)
        y = 388
        for j, s in enumerate(ctl):
            aj = ramp(t, 0.6 + i * 0.5 + j * 0.2, 0.45)
            check(d, bx + 32, y + 16, c, aj, 12)
            y = TW(d, (bx + 56, y), s, 22, 'Medium', WHT, aj, cw - 76, 1.3) + 26
    a = ramp(t, 4.8, 0.7)
    panel(d, [90, 750, 1830, 900], a, GRN, fill=(10, 26, 22))
    T(d, (960, 778), 'Zero trust is not a product.', 36, 'Black', GRN, a, anchor='ma')
    T(d, (960, 834), 'It is every one of these layers verifying every request — automatically, in the pipeline.', 28, 'Regular', WHT, ramp(t, 5.2, 0.6), anchor='ma')


def s_tools(d, t, dur):
    header(d, t, '08', 'THE SECURITY ENGINEER’S TOOLKIT', CY); footer(d, t, 8)
    cats = [('RECON & EXPOSURE', CY, ['Nmap', 'Shodan', 'Amass', 'Nuclei']),
            ('TELECOM / 5G LABS', VIO, ['Open5GS', 'UERANSIM', 'srsRAN', 'Wireshark']),
            ('SIGNALING TESTING', AMB, ['SigPloit', 'SS7MAPer', 'Diameter & GTP dissectors']),
            ('APPS & APIs', PINK, ['Burp Suite', 'OWASP ZAP', 'Postman', '42Crunch']),
            ('CODE & PIPELINE', GRN, ['Semgrep', 'Snyk', 'Trivy', 'Checkov', 'Gitleaks']),
            ('CLOUD POSTURE', CY, ['Prowler', 'ScoutSuite', 'Wiz', 'Defender for Cloud']),
            ('DETECT & RESPOND', RED, ['Zeek', 'Suricata', 'Falco', 'Splunk', 'Sentinel']),
            ('AI RED TEAMING', AMB, ['Garak', 'PyRIT', 'Promptfoo', 'OWASP LLM Top 10']),
            ('FRAMEWORKS', VIO, ['MITRE ATT&CK', 'MITRE FiGHT', 'NIST CSF 2.0', 'GSMA FS-series'])]
    cw, ch, gx, gy = 560, 205, 30, 24
    for i, (nm, c, tools) in enumerate(cats):
        r, k = divmod(i, 3)
        x = 90 + k * (cw + gx); y = 150 + r * (ch + gy)
        a = ramp(t, 0.3 + i * 0.35, 0.5)
        panel(d, [x, y, x + cw, y + ch], a, c)
        T(d, (x + 28, y + 24), nm, 24, 'Black', c, a)
        px, py = x + 28, y + 104
        f = F(21, 'Mono')
        for j, s in enumerate(tools):
            w_ = f.getlength(s) + 28
            if px + w_ > x + cw - 24:
                px = x + 28; py += 56
            pill(d, px, py, s, 21, WHT, ramp(t, 0.6 + i * 0.35 + j * 0.12, 0.4), w='Mono', padx=14)
            px += w_ + 12
    a = ramp(t, 4.6, 0.6)
    bang(d, 470, 893, AMB, a, 16)
    T(d, (500, 878), 'Run offensive tools only against systems you own or are explicitly authorized to test.', 26, 'Medium', AMB, a)


def s_outro(d, t, dur):
    network(d, t + 20, ramp(t, 0, 1.0) * 0.8, ry=520, rx=760, cyy=580)
    T(d, (960, 200), 'THE INNOVATIVE SECURITY ENGINEER’S MINDSET', 26, 'Bold', CY, ramp(t, 0.2, 0.6), anchor='ma')
    lines = [('Collect less.', WHT), ('Assume breach.', WHT), ('Watch the signaling.', WHT),
             ('Give AI least privilege.', WHT), ('Automate the guardrails.', GRN)]
    for i, (s, c) in enumerate(lines):
        T(d, (960, 268 + i * 92), s, 70, 'Black', c, ramp(t, 0.7 + i * 0.45, 0.55), anchor='ma', slide=26)
    a = ramp(t, 3.6, 0.7)
    T(d, (960, 780), 'Security isn’t a layer you add on top — it’s how the platform is built.', 32, 'Regular', MUT, a, anchor='ma')
    a2 = ramp(t, 4.4, 0.7)
    if a2 > 0.01:
        d.line([(860, 860), (1060, 860)], fill=mix(DIM, a2), width=1)
    T(d, (960, 885), 'Ramya Kanderi', 30, 'Bold', WHT, a2, anchor='ma')
    T(d, (960, 928), 'AI Applications & Web Security  ·  AppSec & DevSecOps', 22, 'Medium', MUT, a2, anchor='ma')


SCENES = [('s01', s_title, 8), ('s02', s_paradox, 10), ('s03', s_incidents, 11), ('s04', s_data, 11),
          ('s05', s_map, 13), ('s06', s_chains, 16), ('s07', s_exposure, 10), ('s08', s_defense, 12),
          ('s09', s_tools, 12), ('s10', s_outro, 9)]
FADE = 0.4
BLACK = Image.new('RGB', (W, H), BG)


def frame(fn, t, dur):
    img = BGIMG.copy(); d = ImageDraw.Draw(img)
    fn(d, t, dur)
    k = min(clamp(t / FADE), clamp((dur - t) / FADE))
    if k < 1: img = Image.blend(BLACK, img, k)
    return img


def render(name):
    for nm, fn, dur in SCENES:
        if nm != name: continue
        tmp = f'out/{nm}.tmp.mp4'
        p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                              '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                              '-pix_fmt', 'yuv420p', tmp], stdin=subprocess.PIPE)
        for i in range(int(dur * FPS)):
            p.stdin.write(frame(fn, i / FPS, dur).tobytes())
        p.stdin.close()
        if p.wait() == 0: os.replace(tmp, f'out/{nm}.mp4')
        else: sys.exit(1)


if __name__ == '__main__':
    os.makedirs('out', exist_ok=True); os.makedirs('prev', exist_ok=True)
    if sys.argv[1] == 'preview':
        for nm, fn, dur in SCENES:
            frame(fn, dur - FADE - 0.3, dur).save(f'prev/{nm}.png')
    else:
        render(sys.argv[1])
