"""Scènes peintes procéduralement (ciel, relief, personnages) + texture 'huile' avant quantification."""
import colorsys, math, random
import numpy as np
import colorsys, io, math, random
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFilter, ImageOps

W, H = 720, 900
BASE = {"stress": (200, .38, .62), "tristesse": (222, .40, .55), "joie": (42, .80, .62), "nostalgie": (24, .60, .62),
        "colere": (8, .55, .52), "calme": (165, .38, .66), "douleur": (265, .32, .60)}
STYLES = ("doux", "vif", "terre")


def hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, min(.95, max(.05, l)), min(1, max(0, s)))
    return int(r * 255), int(g * 255), int(b * 255)


def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def palette(emotion, style, r):
    h, s, l = BASE.get(emotion, BASE["calme"]); h += r.uniform(-10, 10)
    if style == "doux": s *= .7; l += .07
    elif style == "vif": s = min(1, s * 1.25)
    else: h = h * .5 + 14; s *= .8; l -= .04
    g = 120 + (h - 120) * .25   # prairies/forêts restent vertes, teintées par l'émotion
    return dict(sky_t=hsl(h, s * .9, l + .05), sky_b=hsl(h + 22, s * .8, l + .25), sun=hsl(42, .9, .8),
                cloud=hsl(h + 10, s * .4, .93), far=hsl(g + 40, s * .6, l - .02), mid=hsl(g + 15, s * .7, l - .15),
                near=hsl(g - 5, s * .75, l - .25), acc1=hsl(h + 180, s * .9, l + .05), acc2=hsl(h + 150, .7, .62),
                dark=hsl(h + 20, s * .6, .2), light=hsl(h, .3, .95), water=hsl(h + 8, s * .9, l - .1),
                water2=hsl(h - 6, s * .8, l + .1), wood=hsl(28, .5, .3))


def hills(d, y, amp, col, r, n=3):
    ph = [r.uniform(0, 6) for _ in range(n)]
    pts = [(x, y + sum(amp / (i + 1) * math.sin(x / W * (i + 1) * 3.1 + ph[i]) for i in range(n))) for x in range(0, W + 30, 30)]
    d.polygon(pts + [(W, H), (0, H)], fill=col)


def sun(d, x, y, rad, P):
    for i in range(6, 0, -1):
        q = rad * (1 + i / 6); d.ellipse((x - q, y - q, x + q, y + q), fill=mix(P["sky_b"], P["sun"], (1 - i / 6) * .8))
    d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=P["sun"])


def cloud(d, x, y, s, c):
    for dx, dy, k in ((0, 0, 1), (.9, .25, .75), (-.9, .3, .7), (.3, -.4, .8)):
        a = s * k; d.ellipse((x + dx * s - a * 1.3, y + dy * s - a * .7, x + dx * s + a * 1.3, y + dy * s + a * .7), fill=c)


def tree(d, x, y, s, P):
    d.polygon([(x - 10 * s, y), (x + 10 * s, y), (x + 5 * s, y - 120 * s), (x - 5 * s, y - 120 * s)], fill=P["wood"])
    for dx, dy, k, c in ((0, -170, 70, "mid"), (-45, -130, 50, "near"), (45, -135, 52, "near"), (0, -215, 45, "mid")):
        d.ellipse((x + dx * s - k * s, y + dy * s - k * s, x + dx * s + k * s, y + dy * s + k * s), fill=P[c])


def flower(d, x, y, rad, pc, cc):
    for a in range(0, 360, 60):
        px, py, q = x + math.cos(math.radians(a)) * rad, y + math.sin(math.radians(a)) * rad, rad * .65
        d.ellipse((px - q, py - q, px + q, py + q), fill=pc)
    d.ellipse((x - rad * .5, y - rad * .5, x + rad * .5, y + rad * .5), fill=cc)


def pine(d, x, y, s, c):
    d.rectangle((x - 6 * s, y - 10 * s, x + 6 * s, y + 14 * s), fill=(70, 50, 40))
    for i in range(3):
        w, t = (60 - i * 12) * s, y - 10 * s - i * 45 * s
        d.polygon([(x - w, t), (x + w, t), (x, t - 85 * s)], fill=c)


def horse(d, x, y, s, P):
    T = lambda pts: [(x + a * s, y + b * s) for a, b in pts]
    col, dk = (150, 96, 60), (62, 40, 30)
    for lx, c in ((-.85, col), (-.65, dk), (.2, col), (.4, dk)):
        d.polygon(T([(lx, 0), (lx + .2, 0), (lx + .15, 1), (lx + .03, 1)]), fill=c)
    d.polygon(T([(-1.05, -.4), (-1.45, -.1), (-1.4, .5), (-1.25, .1), (-1.0, -.15)]), fill=dk)
    d.ellipse((x - 1.1 * s, y - .55 * s, x + .55 * s, y + .2 * s), fill=col)
    d.polygon(T([(.2, -.45), (.55, -1.1), (.85, -1.05), (.7, -.4)]), fill=col)
    d.polygon(T([(.55, -1.1), (.95, -1.3), (1.4, -.95), (1.35, -.8), (.95, -.85), (.75, -.95)]), fill=col)
    d.polygon(T([(.5, -1.12), (.62, -1.08), (.35, -.6), (.15, -.45), (.2, -.7)]), fill=dk)
    d.polygon(T([(.8, -1.3), (.88, -1.48), (.95, -1.3)]), fill=dk)
    d.ellipse((x + .98 * s, y - 1.12 * s, x + 1.04 * s, y - 1.06 * s), fill=dk)
    skin = (236, 190, 160)   # l'enfant sur le cheval
    d.polygon(T([(-.45, -.55), (-.1, -.55), (0, -.2), (-.15, -.2)]), fill=P["acc2"])
    d.polygon(T([(-.45, -.55), (-.2, -.55), (-.15, -1.1), (-.5, -1.1)]), fill=P["acc1"])
    d.polygon(T([(-.2, -1.0), (.2, -.75), (.25, -.68), (-.22, -.9)]), fill=skin)
    d.ellipse((x - .5 * s, y - 1.45 * s, x - .16 * s, y - 1.11 * s), fill=skin)
    d.pieslice((x - .52 * s, y - 1.47 * s, x - .14 * s, y - 1.09 * s), 180, 360, fill=dk)


def figure(d, x, y, s, c):
    d.polygon([(x - .1 * s, y - .85 * s), (x + .1 * s, y - .85 * s), (x + .2 * s, y), (x - .2 * s, y)], fill=c)
    d.ellipse((x - .1 * s, y - 1.05 * s, x + .1 * s, y - .85 * s), fill=c)
    d.ellipse((x - .06 * s, y - 1.12 * s, x + .06 * s, y - 1.0 * s), fill=c)


def s_cheval(d, P, r):
    sun(d, 520, 330, 60, P); cloud(d, 160, 170, 60, P["cloud"]); cloud(d, 540, 110, 45, P["cloud"])
    hills(d, 430, 40, P["far"], r); hills(d, 520, 30, P["mid"], r); hills(d, 640, 25, P["near"], r)
    tree(d, 110, 600, 1.1, P)
    for _ in range(45): flower(d, r.randint(0, W), r.randint(700, 880), r.randint(5, 11), P["acc" + str(r.randint(1, 2))], P["sun"])
    horse(d, 380, 690, 150, P)


def s_phare(d, P, r):
    sun(d, 190, 280, 55, P); cloud(d, 450, 130, 60, P["cloud"]); cloud(d, 120, 110, 45, P["cloud"]); cloud(d, 560, 330, 40, P["cloud"])
    for i in range(14):
        y = 520 + i * 28
        d.polygon([(x, y + 10 * math.sin(x / 40 + i)) for x in range(0, W + 20, 20)] + [(W, H), (0, H)], fill=mix(P["water"], P["light"], i / 14 * .55))
    d.polygon([(400, H), (460, 640), (500, 520), (560, 470), (W, 440), (W, H)], fill=P["dark"])
    d.polygon([(500, 520), (560, 470), (W, 440), (W, 470), (560, 505)], fill=P["near"])
    d.polygon([(585, 470), (635, 470), (625, 250), (595, 250)], fill=P["light"])
    for a, b in ((300, 345), (395, 440)): d.polygon([(594 + (a - 250) * .05, a), (626 - (a - 250) * .05, a), (628 - (b - 250) * .05, b), (592 + (b - 250) * .05, b)], fill=P["acc1"])
    d.rectangle((597, 215, 623, 250), fill=P["sun"]); d.polygon([(590, 215), (630, 215), (610, 180)], fill=P["dark"])
    for _ in range(18): x, y = r.randint(380, 560), r.randint(640, 880); d.ellipse((x - 30, y - 8, x + 30, y + 8), fill=P["light"])


def s_foret(d, P, r):
    sun(d, 360, 300, 70, P)
    for k, (y, c) in enumerate(((500, P["far"]), (610, P["mid"]), (730, P["near"]))):
        for x in range(-40, W + 40, r.randint(70, 95)): pine(d, x + r.randint(-20, 20), y, r.uniform(1, 1.3) + k * .4, c)
        d.rectangle((0, y + 12, W, H), fill=c)
    d.polygon([(300, H), (430, H), (385, 700), (350, 700)], fill=P["light"])


def s_fleurs(d, P, r):
    sun(d, 560, 200, 55, P); cloud(d, 180, 160, 55, P["cloud"])
    hills(d, 480, 35, P["far"], r); hills(d, 580, 30, P["mid"], r); hills(d, 700, 25, P["near"], r)
    for i in range(6):
        x, y, rad = 80 + i * 112 + r.randint(-20, 20), r.randint(430, 600), r.randint(42, 62)
        d.line((x, y, x + r.randint(-15, 15), H), fill=P["near"], width=9)
        d.ellipse((x - 50, y + 150, x, y + 180), fill=P["mid"]); flower(d, x, y, rad, P["acc" + str(1 + i % 2)], P["dark"])


def s_fruits(d, P, r):
    d.rectangle((0, 600, W, H), fill=P["wood"]); d.ellipse((40, 560, 680, 860), fill=P["light"])
    d.ellipse((110, 600, 610, 820), fill=mix(P["light"], P["sky_b"], .5))
    for x, y, k in ((250, 690, 95), (450, 700, 85), (350, 630, 70)):
        d.ellipse((x - k, y - k, x + k, y + k), fill=(245, 235, 215)); d.ellipse((x - k * .9, y - k * .9, x + k * .9, y + k * .9), fill=mix((236, 138, 38), P["acc1"], .15))
        for a in range(0, 360, 40): d.line((x, y, x + math.cos(math.radians(a)) * k * .88, y + math.sin(math.radians(a)) * k * .88), fill=(250, 200, 110), width=5)
        d.ellipse((x - k * .15, y - k * .15, x + k * .15, y + k * .15), fill=(250, 230, 170))
    for _ in range(14):
        x, y = r.randint(160, 560), r.randint(745, 800); d.ellipse((x - 16, y - 16, x + 16, y + 16), fill=(170, 30, 60)); d.ellipse((x - 7, y - 9, x - 1, y - 3), fill=(240, 170, 180))


def s_famille(d, P, r):
    sun(d, 360, 500, 90, P); cloud(d, 150, 200, 55, P["cloud"]); cloud(d, 560, 260, 45, P["cloud"])
    d.rectangle((0, 500, W, 700), fill=P["water"])
    for i in range(6): y = 520 + i * 30; d.polygon([(x, y + 6 * math.sin(x / 30 + i)) for x in range(0, W + 20, 20)] + [(W, y + 12), (0, y + 12)], fill=mix(P["water"], P["sun"], .08 + i * .06))
    d.polygon([(0, 700), (W, 680), (W, H), (0, H)], fill=mix(P["light"], P["sun"], .35))
    figure(d, 300, 840, 330, P["dark"]); figure(d, 440, 840, 190, mix(P["dark"], P["acc1"], .4))
    d.line((300 + .22 * 330, 840 - .5 * 330, 440 - .1 * 190, 840 - .45 * 190), fill=P["dark"], width=9)


def s_lever(d, P, r):
    cx, cy = 360, 560
    for a in range(-80, 81, 20):
        t1, t2 = math.radians(a - 90 - 5), math.radians(a - 90 + 5)
        d.polygon([(cx, cy), (cx + 1200 * math.cos(t1), cy + 1200 * math.sin(t1)), (cx + 1200 * math.cos(t2), cy + 1200 * math.sin(t2))], fill=mix(P["sky_b"], P["sun"], .3))
    sun(d, cx, cy, 80, P); hills(d, 590, 25, P["far"], r); hills(d, 680, 25, P["mid"], r); hills(d, 780, 20, P["near"], r)
    d.polygon([(335, 800), (385, 800), (372, 520), (348, 520)], fill=P["wood"])
    for (x0, y0, x1, y1) in ((360, 600, 230, 470), (365, 560, 500, 430), (360, 520, 300, 380), (368, 500, 430, 360)):
        d.line((x0, y0, x1, y1), fill=P["wood"], width=14)
        for dx, dy, k in ((0, 0, 42), (-30, 25, 30), (30, 25, 30)): d.ellipse((x1 + dx - k, y1 + dy - k, x1 + dx + k, y1 + dy + k), fill=P["acc2"] if dx else P["near"])


SCENES = dict(cheval=s_cheval, phare=s_phare, foret=s_foret, fleurs=s_fleurs, fruits=s_fruits, famille=s_famille, lever=s_lever)


def render(scene, emotion, style, seed):
    """CPU-bound : tourne dans un processus du pool."""
    r = random.Random(seed); P = palette(emotion, style, r)
    t = np.linspace(0, 1, H)[:, None, None]
    img = Image.fromarray(np.repeat(np.array(P["sky_t"]) * (1 - t) + np.array(P["sky_b"]) * t, W, 1).astype(np.uint8))
    SCENES[scene](ImageDraw.Draw(img), P, r)
    a, g = np.asarray(img).astype(np.float32), np.random.default_rng(seed)
    n1 = ndi.gaussian_filter(g.normal(0, 1, (H, W)), 7); n2 = ndi.gaussian_filter(g.normal(0, 1, (H, W)), (1.5, 14))
    a += ((n1 / n1.std()) * 9 + (n2 / n2.std()) * 6)[..., None]   # coups de pinceau
    return np.clip(a, 0, 255).astype(np.uint8)

def load_photo(data):
    """CPU-bound : photo envoyée -> image 720x900 prête pour la quantification."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img = ImageOps.fit(img, (W, H), Image.LANCZOS)      # recadrage centré, sans déformer
    return np.asarray(img.filter(ImageFilter.MedianFilter(5)))   # aplatit les textures 