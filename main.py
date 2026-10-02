#!/usr/bin/env python3
"""IRON STORM - 3D FPS (raycasting) with 12 weapons. Requires: pygame-ce

v2 - realistic animation pass
  * enemies: 12-frame walk cycle, wind-up/strike attacks, hit-stagger + knockback,
    multi-frame death fall, blood pools, rise-from-ground spawn, visible projectiles
  * weapon: spring recoil, mouse-lag sway, figure-8 walk bob, sprint pose, switch
    lower/raise, per-gun reload (mag drop / insert, support hand, slide / pump),
    minigun spin-up, rail-gun charge glow, muzzle flash + light, shell casings
  * world: blood / spark / debris / smoke particles, bullet decals, tracers,
    rocket flight + explosion shock-ring, camera kick, head-bob, death fall
"""
import math, random, sys, os
from array import array
import pygame

W, H = 960, 600
CW = 4                      # column width (px) per ray
NR = W // CW
FOV = math.radians(66)
PROJ = (W / 2) / math.tan(FOV / 2)
MAXD = 30.0
MW = MH = 28
PMAX = 300                   # max look up / down (screen px the horizon can shift, ~23 deg)

# ---------------------------------------------------------------- helpers
def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v
def lerp(a, b, t): return a + (b - a) * t
def smooth(t): t = clamp(t, 0, 1); return t * t * (3 - 2 * t)
def sstep(x, a, b): return smooth((x - a) / (b - a))
def shade(c, k): return tuple(int(clamp(v * k, 0, 255)) for v in c)

def rot_blit(dst, src, pivot, dest, ang):
    """Rotate src by ang degrees (CCW) about its local `pivot`, placing pivot at `dest`.
    Returns a function mapping local src points -> dst points."""
    w, h = src.get_size()
    rs = pygame.transform.rotate(src, ang) if abs(ang) > .05 else src
    r = math.radians(ang if abs(ang) > .05 else 0)
    cr, sr = math.cos(r), math.sin(r)
    def rotv(vx, vy): return vx * cr + vy * sr, -vx * sr + vy * cr
    rx, ry = rotv(pivot[0] - w / 2, pivot[1] - h / 2)
    rect = rs.get_rect(center=(dest[0] - rx, dest[1] - ry))
    dst.blit(rs, rect)
    def tf(q):
        a, b = rotv(q[0] - w / 2, q[1] - h / 2)
        return rect.centerx + a, rect.centery + b
    return tf

# ---------------------------------------------------------------- map
def build_map():
    g = [[0] * MW for _ in range(MH)]
    for i in range(MW):
        g[0][i] = g[MH - 1][i] = g[i][0] = g[i][MW - 1] = 1

    def box(x0, y0, x1, y1, t, doors):
        for x in range(x0, x1 + 1):
            g[y0][x] = g[y1][x] = t
        for y in range(y0, y1 + 1):
            g[y][x0] = g[y][x1] = t
        for dx, dy in doors:
            g[dy][dx] = 0
    box(4, 4, 10, 9, 2, [(7, 9), (10, 6)])
    box(17, 4, 23, 10, 3, [(17, 7), (20, 10)])
    box(4, 18, 10, 23, 4, [(7, 18), (10, 21)])
    box(17, 18, 23, 24, 2, [(20, 18), (17, 21)])
    rng = random.Random(11)
    n = 0
    while n < 22:
        x, y = rng.randint(2, MW - 3), rng.randint(2, MH - 3)
        if abs(x - 14) < 3 and abs(y - 14) < 3:
            continue
        if g[y][x] == 0 and all(g[y + j][x + i] == 0 for i in (-1, 0, 1) for j in (-1, 0, 1)):
            g[y][x] = rng.randint(1, 4)
            n += 1
    return g

MAP = build_map()
WALL_COL = {1: (150, 150, 160), 2: (170, 70, 60), 3: (60, 120, 170), 4: (90, 150, 80)}

def cast(px, py, ang):
    dx, dy = math.cos(ang), math.sin(ang)
    mx, my = int(px), int(py)
    ddx = abs(1 / dx) if dx else 1e30
    ddy = abs(1 / dy) if dy else 1e30
    if dx < 0: sx, sdx = -1, (px - mx) * ddx
    else:      sx, sdx = 1, (mx + 1 - px) * ddx
    if dy < 0: sy, sdy = -1, (py - my) * ddy
    else:      sy, sdy = 1, (my + 1 - py) * ddy
    while True:
        if sdx < sdy: sdx += ddx; mx += sx; side = 0
        else:         sdy += ddy; my += sy; side = 1
        if not (0 <= mx < MW and 0 <= my < MH):
            return MAXD, 0, 0, 0.0
        t = MAP[my][mx]
        if t:
            d = (sdx - ddx) if side == 0 else (sdy - ddy)
            if d >= MAXD:
                return MAXD, 0, 0, 0.0
            wx = (py + d * dy) if side == 0 else (px + d * dx)
            return d, side, t, wx - math.floor(wx)

def walkable(x, y, r):
    for ox in (-r, r):
        for oy in (-r, r):
            cx, cy = int(x + ox), int(y + oy)
            if not (0 <= cx < MW and 0 <= cy < MH) or MAP[cy][cx]:
                return False
    return True

def solid(x, y):
    cx, cy = int(x), int(y)
    return not (0 <= cx < MW and 0 <= cy < MH) or MAP[cy][cx] != 0

# ---------------------------------------------------------------- weapons
WEAPONS = [
    dict(n="Pistol",        d=22,  r=4.0,  mag=12,  res=120, sp=.010, pel=1, auto=False, rl=1.0, col=(120,120,130), L=.38, bw=34, kind="pistol", f=520),
    dict(n="Revolver",      d=70,  r=1.7,  mag=6,   res=60,  sp=.005, pel=1, auto=False, rl=1.6, col=(160,160,170), L=.42, bw=36, kind="pistol", f=300),
    dict(n="SMG",           d=12,  r=15.0, mag=32,  res=256, sp=.035, pel=1, auto=True,  rl=1.3, col=(70,70,80),    L=.42, bw=40, kind="smg",    f=700),
    dict(n="Assault Rifle", d=21,  r=9.5,  mag=30,  res=240, sp=.018, pel=1, auto=True,  rl=1.7, col=(70,90,70),    L=.55, bw=40, kind="rifle",  f=420),
    dict(n="Shotgun",       d=13,  r=1.2,  mag=6,   res=48,  sp=.075, pel=9, auto=False, rl=2.0, col=(110,70,40),   L=.55, bw=44, kind="shotgun",f=200),
    dict(n="Auto Shotgun",  d=9,   r=3.6,  mag=12,  res=72,  sp=.070, pel=7, auto=True,  rl=2.4, col=(60,60,60),    L=.55, bw=48, kind="shotgun",f=250),
    dict(n="Sniper",        d=150, r=0.8,  mag=5,   res=30,  sp=.000, pel=1, auto=False, rl=2.4, col=(50,70,50),    L=.70, bw=34, kind="sniper", f=160, pierce=2),
    dict(n="Minigun",       d=10,  r=28.0, mag=120, res=480, sp=.045, pel=1, auto=True,  rl=3.5, col=(90,90,100),   L=.60, bw=56, kind="mini",   f=900),
    dict(n="Rocket Launcher", d=110, r=0.9, mag=4,  res=20,  sp=.000, pel=1, auto=False, rl=2.5, col=(80,100,60),   L=.60, bw=60, kind="launch", f=110, splash=3.2),
    dict(n="Plasma Gun",    d=28,  r=8.0,  mag=40,  res=200, sp=.012, pel=1, auto=True,  rl=2.0, col=(40,90,120),   L=.52, bw=48, kind="plasma", f=900, splash=1.3, glow=(80,220,255)),
    dict(n="Flamethrower",  d=6,   r=30.0, mag=200, res=600, sp=.12,  pel=2, auto=True,  rl=2.5, col=(150,60,30),   L=.50, bw=46, kind="flame",  f=120, rng=5.5, glow=(255,150,40)),
    dict(n="Railgun",       d=220, r=0.6,  mag=3,   res=18,  sp=.000, pel=1, auto=False, rl=2.8, col=(60,60,90),    L=.62, bw=44, kind="rail",   f=1200, pierce=99, glow=(255,60,200)),
]
TWO_HAND = {"smg", "rifle", "shotgun", "sniper", "mini", "launch", "plasma", "rail", "flame"}
HAS_MAG = {"pistol", "smg", "rifle", "sniper", "plasma", "rail", "mini"}

# ---------------------------------------------------------------- enemies
ETYPES = {
    "grunt":   dict(hp=50,  sp=2.0, dmg=8,  r=.30, sc=.85, col=(190,60,50),  ranged=False, score=10,  adur=.60),
    "runner":  dict(hp=30,  sp=3.6, dmg=6,  r=.28, sc=.75, col=(230,140,40), ranged=False, score=15,  adur=.42),
    "shooter": dict(hp=45,  sp=1.4, dmg=7,  r=.30, sc=.85, col=(60,110,210), ranged=True,  score=20,  adur=.70),
    "tank":    dict(hp=220, sp=1.2, dmg=18, r=.45, sc=1.15, col=(130,60,170), ranged=False, score=40, adur=.85),
    "boss":    dict(hp=900, sp=1.8, dmg=25, r=.60, sc=1.6, col=(40,160,70),   ranged=True,  score=300, adur=.80),
}
STYLE = {
    "grunt":   dict(w=1.00, head=1.00, skin=(205,170,140), pants=(52,52,72),  lean=0, stride=12, helmet=None,          horns=False, pads=False, gun=False, eye=(255,230,60)),
    "runner":  dict(w=.82,  head=.92,  skin=(215,180,150), pants=(70,52,38),  lean=5, stride=18, helmet=None,          horns=False, pads=False, gun=False, eye=(255,240,90)),
    "shooter": dict(w=.95,  head=1.00, skin=(205,170,140), pants=(38,48,78),  lean=0, stride=11, helmet=(50,60,90),    horns=False, pads=False, gun=True,  eye=(120,230,255)),
    "tank":    dict(w=1.30, head=.95,  skin=(190,150,130), pants=(60,40,70),  lean=0, stride=7,  helmet=(90,50,110),   horns=False, pads=True,  gun=False, eye=(255,120,60)),
    "boss":    dict(w=1.35, head=1.10, skin=(105,185,105), pants=(30,60,35),  lean=0, stride=8,  helmet=None,          horns=True,  pads=True,  gun=True,  eye=(255,50,40)),
}
FW, FH, SS = 128, 160, 2          # frame size, supersample
NWALK, NATK, NDEATH = 12, 8, 9

def render_enemy(kind, mode, p):
    """Draw one humanoid frame. mode: walk (p=phase rad) | atk (p=0..1) | hurt"""
    t = ETYPES[kind]; st = STYLE[kind]; col = t["col"]
    big = pygame.Surface((FW * SS, FH * SS), pygame.SRCALPHA)
    P = lambda x, y: (int(x * SS), int(y * SS))
    def line(c, a, b, wd):
        pygame.draw.line(big, c, P(*a), P(*b), max(1, int(wd * SS)))
        r = max(1, int(wd * SS / 2)); pygame.draw.circle(big, c, P(*a), r); pygame.draw.circle(big, c, P(*b), r)
    def circ(c, pos, r): pygame.draw.circle(big, c, P(*pos), max(1, int(r * SS)))
    def rrect(c, x, y, w, h, r=3): pygame.draw.rect(big, c, (int(x * SS), int(y * SS), int(w * SS), int(h * SS)), border_radius=int(r * SS))
    def poly(c, pts): pygame.draw.polygon(big, c, [P(*q) for q in pts])

    dark, lite = shade(col, .55), shade(col, 1.3)
    pants = st["pants"]; pants_d = shade(pants, .7); boot = (25, 25, 28)
    skin = st["skin"]; skin_d = shade(skin, .78)
    sw = st["w"]; cx = 64.0
    walk = mode == "walk"; hurt = mode == "hurt"; atk = p if mode == "atk" else 0.0
    ph = p if walk else 0.0
    bob = abs(math.sin(ph)) * 3.2 if walk else 0.0
    sway = math.sin(ph) * 2.2 if walk else 0.0
    stride = st["stride"]

    # melee wind-up curve (0 = arms down, 1 = overhead) / aim curve for gunners
    if mode == "atk":
        if atk < .5: a = smooth(atk / .5)
        elif atk < .66: a = 1 - 1.25 * smooth((atk - .5) / .16)
        else: a = -.25 * (1 - smooth((atk - .66) / .34))
    else: a = 0.0
    lunge = (smooth((atk - .3) / .25) * (1 - smooth((atk - .55) / .3))) if mode == "atk" else 0.0

    # ---- legs
    hipy = 106 - bob + (lunge * 3)
    hw = 11 * sw
    for s in (-1, 1):
        lp = math.sin(ph + (math.pi if s > 0 else 0)) if walk else 0.0
        lift = max(0.0, lp) * stride
        spread = 4 if hurt else (2 + lunge * 3 if mode == "atk" else 0)
        hip = (cx + sway + s * hw, hipy)
        foot = (cx + s * (hw * 1.15 + spread) + s * lift * .15, 150 - lift)
        knee = (cx + s * (hw * 1.4 + 3 + lift * .25), (hip[1] + foot[1]) / 2 - lift * .35)
        pc = pants if s < 0 else pants_d
        line(pc, hip, knee, 14 * sw ** .6); line(pc, knee, foot, 12 * sw ** .6)
        rrect(boot, foot[0] - 9 * sw ** .5, foot[1] - 6, 18 * sw ** .5, 9, 3)

    # ---- torso
    tx = cx + sway - 26 * sw; ty = 60 - bob + lunge * 4; tw = 52 * sw; th = 50
    if hurt: ty += 2
    rrect(dark, tx - 1, ty - 1, tw + 2, th + 2, 13)
    rrect(col, tx, ty, tw, th, 12)
    rrect(lite, tx + 4, ty + 4, tw * .26, th * .5, 6)
    rrect(shade(col, .75), tx + tw * .68, ty + 8, tw * .28, th - 18, 6)
    line(dark, (cx + sway, ty + 6), (cx + sway, ty + th - 14), 2)
    rrect((35, 30, 28), tx, ty + th - 13, tw, 9, 2)
    rrect((220, 190, 60), cx + sway - 4, ty + th - 13, 8, 9, 1)

    # ---- arms
    sh_y = ty + 8
    hands = []
    for s in (-1, 1):
        sh = (cx + sway + s * (26 * sw + 1), sh_y)
        ap = math.sin(ph + (math.pi if s < 0 else 0)) if walk else 0.0
        if st["gun"] and not hurt:
            aim = 0.0
            if mode == "atk": aim = smooth(atk / .35) * (1 - smooth((atk - .75) / .25))
            hand = (cx + 4 + s * (-6 if s < 0 else 6) + sway * .5, 90 - aim * 11 - (0 if mode == "atk" else ap * 1.5))
            elbow = (sh[0] + s * 5, sh_y + 24 - aim * 6)
        elif hurt:
            hand = (sh[0] + s * 24, sh_y - 4); elbow = (sh[0] + s * 17, sh_y + 10)
        elif mode == "atk":
            hand = (sh[0] + s * (8 - a * 6), sh_y + 40 - a * 78)
            elbow = (sh[0] + s * (11 + a * 6), sh_y + 20 - a * 36)
        else:
            hand = (sh[0] + s * (8 + ap * 1.5), sh_y + 40 - ap * 9)
            elbow = (sh[0] + s * (11 + ap * 1), sh_y + 20 - ap * 4)
        line(dark, sh, elbow, 13 * sw ** .5); line(shade(col, .8), elbow, hand, 11 * sw ** .5)
        hands.append(hand)
        if st["pads"]: circ(shade(col, .95), (sh[0] + s * 1, sh_y - 1), 12 * sw ** .6); circ(lite, (sh[0] + s * 1 - 2, sh_y - 4), 6 * sw ** .5)
    for hnd in hands: circ(skin, hnd, 6.5 * sw ** .5)

    # ---- held gun (end-on, pointing at viewer)
    if st["gun"] and not hurt:
        gx, gy = (hands[0][0] + hands[1][0]) / 2, (hands[0][1] + hands[1][1]) / 2 - 2
        rrect((30, 30, 36), gx - 10, gy - 6, 22, 14, 3)
        circ((15, 15, 18), (gx + 1, gy), 7.5); circ((2, 2, 4), (gx + 1, gy), 4.5); circ((90, 90, 100), (gx - 3, gy - 4), 2)
        if mode == "atk" and .48 < atk < .66:
            k = 1 - abs(atk - .56) / .1
            pts = []
            for i in range(14):
                r_ = (20 if i % 2 == 0 else 7) * clamp(k, .3, 1) * (.8 if kind == "shooter" else 1.2)
                an = i / 14 * math.tau + .3; pts.append((gx + 1 + math.cos(an) * r_, gy + math.sin(an) * r_))
            poly((255, 225, 120), pts); circ((255, 255, 235), (gx + 1, gy), 6 * clamp(k, .3, 1))

    # ---- head
    hs = st["head"]
    hc = (cx + sway * .8, 38 - bob + st["lean"] + (-3 if hurt else 0) + lunge * 4)
    if hurt: hc = (hc[0] + 2, hc[1])
    rrect(skin_d, hc[0] - 6, hc[1] + 8, 12, 14, 3)                       # neck
    if st["horns"]:
        for s in (-1, 1):
            poly((225, 220, 190), [(hc[0] + s * 8 * hs, hc[1] - 10), (hc[0] + s * 26 * hs, hc[1] - 36), (hc[0] + s * 16 * hs, hc[1] - 4)])
    circ(shade(skin, .85), (hc[0] + 1, hc[1] + 1), 17.5 * hs)
    circ(skin, hc, 17 * hs)
    circ(shade(skin, 1.1), (hc[0] - 5, hc[1] - 6), 7 * hs)
    if st["helmet"]:
        hcol = st["helmet"]
        pygame.draw.circle(big, hcol, P(*hc), int(18.5 * hs * SS), draw_top_left=True, draw_top_right=True)
        rrect(shade(hcol, .7), hc[0] - 18 * hs, hc[1] - 2, 36 * hs, 4, 1)
        pygame.draw.circle(big, shade(hcol, 1.4), P(hc[0] - 6, hc[1] - 10), int(5 * SS), draw_top_left=True)
    else:
        pygame.draw.circle(big, shade(skin, .35), P(*hc), int(17.5 * hs * SS), draw_top_left=True, draw_top_right=True)
        rrect(skin, hc[0] - 17 * hs, hc[1] - 4, 34 * hs, 12, 2)
    ey = hc[1] + 1
    if hurt:
        for s in (-1, 1):
            line((40, 10, 10), (hc[0] + s * 8 * hs - 3, ey - 3), (hc[0] + s * 8 * hs + 3, ey + 3), 2)
            line((40, 10, 10), (hc[0] + s * 8 * hs + 3, ey - 3), (hc[0] + s * 8 * hs - 3, ey + 3), 2)
        circ((60, 8, 8), (hc[0], hc[1] + 11), 5 * hs)
    else:
        er = 3.6 * hs + (1.2 if kind == "boss" else 0)
        for s in (-1, 1):
            circ(shade(st["eye"], .5), (hc[0] + s * 8 * hs, ey), er + 1.4)
            circ(st["eye"], (hc[0] + s * 8 * hs, ey), er)
            line((30, 10, 10), (hc[0] + s * 13 * hs, ey - 7 + (0 if s < 0 else 0)), (hc[0] + s * 4 * hs, ey - 4), 2)
        open_m = (atk > .3 and atk < .7) if mode == "atk" else False
        if open_m: rrect((50, 6, 6), hc[0] - 6 * hs, hc[1] + 8, 12 * hs, 8, 3); rrect((235, 235, 225), hc[0] - 5 * hs, hc[1] + 8, 10 * hs, 2, 0)
        else: rrect((60, 10, 10), hc[0] - 6 * hs, hc[1] + 10, 12 * hs, 4, 2)
        if kind == "boss":
            for s in (-1, 1): poly((240, 240, 225), [(hc[0] + s * 5, hc[1] + 12), (hc[0] + s * 8, hc[1] + 12), (hc[0] + s * 6.5, hc[1] + 18)])
    return pygame.transform.smoothscale(big, (FW, FH))

def rot_about(img, pivot, ang):
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    rot_blit(out, img, pivot, pivot, ang)
    return out

def make_frames(kind):
    walk = [render_enemy(kind, "walk", i / NWALK * math.tau) for i in range(NWALK)]
    atk = [render_enemy(kind, "atk", i / (NATK - 1)) for i in range(NATK)]
    hurt = render_enemy(kind, "hurt", 0)
    death = []
    for i in range(NDEATH):
        pp = (i + 1) / NDEATH; e = 1 - (1 - pp) ** 2.2
        ang = 30 * e * (1 - .5 * e)
        fig = rot_about(hurt, (64, 150), ang)
        nh = max(14, int(FH * (1 - .8 * e)))
        sc = pygame.transform.smoothscale(fig, (FW, nh))
        can = pygame.Surface((FW, FH), pygame.SRCALPHA)
        can.blit(sc, (0, int(150 - 150 * nh / FH)))
        death.append(can)
    return dict(walk=walk, atk=atk, hurt=hurt, death=death)

def tint_white(img):
    c = img.copy(); c.fill((130, 130, 130, 0), special_flags=pygame.BLEND_RGB_ADD); return c

class Enemy:
    def __init__(self, kind, x, y):
        t = ETYPES[kind]; self.kind = kind; self.x, self.y = x, y
        self.hp = self.maxhp = t["hp"]; self.t = t; self.cd = random.uniform(.4, 1.2); self.flash = 0; self.alive = True
        self.phase = random.uniform(0, math.tau); self.moving = False
        self.atk = -1.0; self.atk_dur = t["adur"]; self.stun = 0.0; self.stun_cd = 0.0
        self.kbx = self.kby = 0.0; self.spawn = .8; self.fidx = 0
    def hurt(self, d, game, dx=0.0, dy=0.0):
        self.hp -= d; self.flash = .09; game.hitm = .18
        heavy = self.kind in ("tank", "boss")
        # knockback + stagger (rate limited so flamethrower/minigun can't stun-lock)
        k = min(4.0, d / 22) * (.25 if heavy else 1)
        self.kbx += dx * k; self.kby += dy * k
        if d >= 12 and self.stun_cd <= 0 and self.hp > 0:
            self.stun = .14 if not heavy else .07; self.stun_cd = .45; self.atk = -1.0
            if self.cd < .35: self.cd = .35
        if self.hp <= 0 and self.alive:
            self.alive = False; game.score += self.t["score"]; game.kills += 1; game.hitm = .35
            game.on_enemy_death(self, dx, dy)
            if random.random() < .4: game.pickups.append([self.x, self.y, random.choice(["ammo", "ammo", "health"])])
    def strike(self, g, d):
        t = self.t
        if not t["ranged"]:
            if d < t["r"] + 1.2: g.hurt_player(t["dmg"])
        else:
            ang0 = math.atan2(g.py - self.y, g.px - self.x)
            wall_d = cast(self.x, self.y, ang0)[0]
            if wall_d < d - .15:
                return
            n = 3 if self.kind == "boss" else 1
            for i in range(n):
                ang = ang0 + random.uniform(-.05, .05) + (i - (n - 1) / 2) * .13
                g.projectiles.append(dict(x=self.x + math.cos(ang) * .4, y=self.y + math.sin(ang) * .4, vx=math.cos(ang) * 15, vy=math.sin(ang) * 15,
                                          dmg=t["dmg"], ttl=2.5, col=(110, 255, 130) if self.kind == "boss" else (120, 200, 255)))
            g.burst(self.x + math.cos(ang0) * .35, self.y + math.sin(ang0) * .35, self.t["sc"] * .55, 5, "spark", (255, 220, 120), 1.5, .5)
    def update(self, g, dt):
        t = self.t; self.flash = max(0, self.flash - dt); self.stun_cd = max(0, self.stun_cd - dt)
        if self.spawn > 0: self.spawn -= dt; return
        self.cd -= dt
        dx, dy = g.px - self.x, g.py - self.y; d = math.hypot(dx, dy) or .001
        if abs(self.kbx) + abs(self.kby) > .05:
            mx_, my_ = self.kbx * dt, self.kby * dt
            if walkable(self.x + mx_, self.y, t["r"]): self.x += mx_
            if walkable(self.x, self.y + my_, t["r"]): self.y += my_
            k = max(0.0, 1 - dt * 9); self.kbx *= k; self.kby *= k
        if self.stun > 0:
            self.stun -= dt; self.moving = False; return
        if self.atk >= 0:
            prev = self.atk; self.atk += dt; hit_at = self.atk_dur * .55
            if prev < hit_at <= self.atk: self.strike(g, d)
            if self.atk >= self.atk_dur: self.atk = -1.0; self.cd = .5 if not t["ranged"] else 1.2
            self.moving = False; return
        self.moving = False
        if d > t["r"] + .5:
            vx, vy = dx / d * t["sp"] * dt, dy / d * t["sp"] * dt
            if t["ranged"] and d < 6: vx = vy = 0
            else: self.moving = True
            if walkable(self.x + vx, self.y, t["r"]): self.x += vx
            elif walkable(self.x, self.y + math.copysign(abs(vx) + abs(vy), vy or 1), t["r"]): self.y += math.copysign(abs(vx) + abs(vy), vy or 1)
            if walkable(self.x, self.y + vy, t["r"]): self.y += vy
            elif walkable(self.x + math.copysign(abs(vx) + abs(vy), vx or 1), self.y, t["r"]): self.x += math.copysign(abs(vx) + abs(vy), vx or 1)
        if self.moving: self.phase = (self.phase + dt * t["sp"] * 2.6) % math.tau
        if self.cd <= 0:
            wall_d = cast(self.x, self.y, math.atan2(dy, dx))[0]
            if not t["ranged"] and d < t["r"] + .9: self.atk = 0.0
            elif t["ranged"] and d < 14 and wall_d < d - .05: self.atk = 0.0

# ---------------------------------------------------------------- sound
def mk_sound(freq, dur=.12, noise=.7, vol=.35):
    try:
        n = int(22050 * dur); buf = array('h')
        for i in range(n):
            env = (1 - i / n) ** 2
            v = (random.uniform(-1, 1) * noise + math.sin(i * freq * 6.2832 / 22050) * (1 - noise)) * env * vol
            buf.append(int(v * 32767))
        return pygame.mixer.Sound(buffer=buf.tobytes())
    except Exception:
        return None

# ---------------------------------------------------------------- game
GW, GH = 640, 600                 # gun layer size
GCX, GBY = 320, 590               # gun pivot (bottom-centre) in gun layer

class Game:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("arial", 18, bold=True)
        self.big = pygame.font.SysFont("arial", 56, bold=True)
        self.ammo_font = pygame.font.SysFont("arial", 36, bold=True)
        self.tiny = pygame.font.Font(None, 20)
        # sky/floor gradient, taller than the screen so the horizon can move (bob / recoil)
        self.BGH = H + 2 * (PMAX + 110); half = self.BGH // 2
        self.bg = pygame.Surface((W, self.BGH))
        for y in range(half):
            k = y / half
            top = (15 + int(65 * k), 22 + int(64 * k), 36 + int(70 * k))
            bottom = (int(42 + 50 * (1 - k)), int(28 + 35 * (1 - k)), int(52 + 34 * (1 - k)))
            pygame.draw.line(self.bg, top, (0, y), (W, y))
            pygame.draw.line(self.bg, bottom, (0, self.BGH - 1 - y), (W, self.BGH - 1 - y))
        self.frames = {k: make_frames(k) for k in ETYPES}
        self._wf = {}
        self.spark = self.glow_img((255, 220, 120)); self.boom = self.glow_img((255, 120, 30))
        self.plasma = self.glow_img((90, 230, 255)); self.flame = self.glow_img((255, 160, 40))
        self.bolt_img = {c: self.glow_img(c) for c in ((120, 200, 255), (110, 255, 130))}
        self.rocket_glow = self.glow_img((255, 200, 120))
        self.smoke_img = self.glow_img((170, 170, 175), soft=True)
        self.ring_img = self.make_ring()
        self.pool_img = self.make_pool(); self.shadow_img = self.make_shadow()
        self.hole_img = self.make_hole(); self.scorch_img = self.glow_img((10, 8, 6), soft=True)
        self.big_glow = self.glow_img((255, 235, 170))
        self.gunsurf = pygame.Surface((GW, GH), pygame.SRCALPHA)
        self.snd = [mk_sound(w["f"], .14, .75 if w["kind"] not in ("plasma", "rail") else .15) for w in WEAPONS]
        self.snd_hit = mk_sound(170, .07, .9, .22); self.snd_die = mk_sound(80, .32, .8, .3)
        self.snd_boom = mk_sound(55, .55, .9, .5); self.snd_click = mk_sound(1100, .03, .9, .18)
        self.snd_step = mk_sound(75, .07, .9, .10); self.snd_hurt = mk_sound(120, .18, .85, .35)
        self.snd_reload = mk_sound(650, .05, .85, .2)
        self.reset()
    @staticmethod
    def glow_img(c, soft=False):
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        for r in range(32, 0, -2 if soft else -4):
            a = int((120 if soft else 255) * (1 - r / 32) ** (1.4 if soft else .6))
            pygame.draw.circle(s, (*c, a), (32, 32), r)
        return s
    @staticmethod
    def make_ring():
        s = pygame.Surface((128, 128), pygame.SRCALPHA)
        for i in range(6): pygame.draw.circle(s, (255, 220, 170, 190 - i * 30), (64, 64), 60 - i, 2)
        return s
    @staticmethod
    def make_pool():
        s = pygame.Surface((128, 32), pygame.SRCALPHA)
        for i in range(10):
            k = i / 10
            pygame.draw.ellipse(s, (95, 5, 8, int(40 + 150 * k)), (int(4 + k * 40), int(1 + k * 8), int(120 - k * 80), int(30 - k * 16)))
        return s
    @staticmethod
    def make_shadow():
        s = pygame.Surface((64, 16), pygame.SRCALPHA)
        for i in range(6): pygame.draw.ellipse(s, (0, 0, 0, 22), (i * 3, i * 1, 64 - i * 6, 16 - i * 2))
        return s
    @staticmethod
    def make_hole():
        s = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(s, (0, 0, 0, 90), (12, 12), 11); pygame.draw.circle(s, (8, 6, 5, 230), (12, 12), 6)
        pygame.draw.circle(s, (70, 65, 60, 160), (10, 10), 6, 1)
        return s
    def white(self, img):
        k = id(img)
        if k not in self._wf: self._wf[k] = tint_white(img)
        return self._wf[k]
    def play(self, s):
        if s: s.play()
    def reset(self):
        self.px, self.py, self.pa = 14.0, 14.0, 0.0
        self.hp = 100; self.score = 0; self.kills = 0; self.wave = 0; self.wave_t = 1.5
        self.enemies, self.pickups, self.fx = [], [], []
        self.parts, self.corpses, self.decals, self.projectiles = [], [], [], []
        self.tracers, self.casings, self.pending, self.eject_q = [], [], [], []
        self.ammo = [dict(mag=w["mag"], res=w["res"]) for w in WEAPONS]
        self.cur = self.want = 3; self.swv = 0.0
        self.cool = 0; self.reload_t = 0; self.flash = 0; self.flash_k = 1.0; self.fl_rot = 0.0; self.fl_sz = 1.0
        self.hurt_f = 0; self.bob = 0; self.t = 0; self.dead = False; self.dead_t = 0; self.shake = 0
        self.rc = 0.0; self.rv = 0.0               # recoil spring
        self.swx = 0.0; self.lean = 0.0            # weapon sway / strafe lean
        self.bobamp = 0.0; self.spr = 0.0          # walk-bob amplitude, sprint blend
        self.spin = 0.0; self.spin_ang = 0.0       # minigun
        self.pump = 0.0; self.spread = 0.0; self.hitm = 0.0; self.boomflash = 0.0
        self.muz = (W * .5, H * .6); self.port = (W * .7, H * .8)
        self.hor = H / 2; self.pitch = 0.0; self._step = 0; self.rl_ejected = False
    @property
    def wp(self): return WEAPONS[self.cur]
    # -- actions
    def hurt_player(self, d):
        if self.dead: return
        self.hp -= d; self.hurt_f = .35; self.shake = max(self.shake, .2); self.rv += 6
        self.play(self.snd_hurt)
        if self.hp <= 0: self.hp = 0; self.dead = True; self.dead_t = 0
    def switch(self, i):
        i %= len(WEAPONS)
        if i != self.want: self.want = i; self.reload_t = 0
    def start_reload(self):
        a = self.ammo[self.cur]
        if self.reload_t <= 0 and a["mag"] < self.wp["mag"] and a["res"] > 0 and self.want == self.cur:
            self.reload_t = self.wp["rl"]; self.rl_ejected = False; self.play(self.snd_reload)
            if self.wp["n"] == "Revolver":
                for i in range(6): self.eject_q.append([.28 + i * .035, "rev"])
    def add_fx(self, x, y, kind, ttl, size, z=.5, vx=0, vy=0, vz=0):
        self.fx.append(dict(x=x, y=y, k=kind, ttl=ttl, max=ttl, sz=size, z=z, vx=vx, vy=vy, vz=vz))
    def burst(self, x, y, z, n, kind, col, speed, up=2.0, dx=0, dy=0, spread=1.0, ttl=(.4, .9), size=(.012, .026)):
        for _ in range(n):
            a = random.uniform(0, math.tau); sp = random.uniform(.25, 1) * speed
            tl = random.uniform(*ttl)
            self.parts.append(dict(x=x, y=y, z=z, vx=dx * speed * .7 + math.cos(a) * sp * spread, vy=dy * speed * .7 + math.sin(a) * sp * spread,
                                   vz=random.uniform(-.2, 1) * up, ttl=tl, max=tl, col=col, sz=random.uniform(*size), k=kind))
        if len(self.parts) > 450: del self.parts[:len(self.parts) - 450]
    def eject(self, kind="brass", down=False):
        x, y = self.port
        if down: x, y = W * .62, H * .78
        self.casings.append(dict(x=x, y=y, vx=random.uniform(-80, -20) if down else random.uniform(110, 230), vy=random.uniform(-60, 0) if down else -random.uniform(240, 380),
                                 rot=random.uniform(0, 6), vr=random.uniform(-14, 14), ttl=1.4,
                                 col=(205, 55, 45) if kind == "shell" else (225, 185, 70), big=kind == "shell", rest=0))
    def fire(self):
        w, a = self.wp, self.ammo[self.cur]
        if self.reload_t > 0 or self.cool > 0 or self.dead or self.swv > 0 or self.want != self.cur: return
        k = w["kind"]
        if k == "mini" and self.spin < .9: return
        if a["mag"] <= 0:
            self.play(self.snd_click); self.cool = .25; self.start_reload(); return
        a["mag"] -= 1; self.cool = 1 / w["r"]; self.flash = .06; self.shake = max(self.shake, .02 + w["d"] / 3500)
        self.flash_k = clamp(.35 + w["d"] / 120, .35, 1.0); self.fl_rot = random.uniform(0, math.tau); self.fl_sz = random.uniform(.8, 1.2)
        self.rv += clamp(6 + w["d"] ** .5 * 1.9, 9, 34) * (1.0 if self.rc < 1.3 else .3)
        self.pa += random.uniform(-1, 1) * .0009 * (1 + w["d"] ** .5 * .15)
        self.play(self.snd[self.cur])
        if k in ("pistol", "smg", "rifle", "sniper", "mini") and w["n"] != "Revolver": self.eject()
        if k == "shotgun":
            self.pump = .5 if not w["auto"] else .0
            self.eject_q.append([.30 if not w["auto"] else .06, "shell"])
        for _ in range(w["pel"]):
            self.shoot_ray(self.pa + random.uniform(-w["sp"], w["sp"]), w)
        if k in ("smg", "rifle", "mini", "pistol", "shotgun") and random.random() < .5:
            c, s = math.cos(self.pa), math.sin(self.pa)
            self.parts.append(dict(x=self.px + c * .7, y=self.py + s * .7, z=.43, vx=c * .5 + random.uniform(-.1, .1), vy=s * .5 + random.uniform(-.1, .1), vz=.25,
                                   ttl=1.0, max=1.0, col=(0, 0, 0), sz=.05, k="smoke"))
        if a["mag"] <= 0: self.start_reload()
    def add_tracer(self, ang, wd, w, kind):
        da = ang - self.pa
        ex = W / 2 + math.tan(da) * PROJ; perp = max(.3, wd * math.cos(da))
        ey = H / 2 + random.uniform(-2, 2)
        if kind == "rocket": ttl = clamp(wd / 24, .12, 1.2)
        elif kind == "rail": ttl = .35
        elif kind == "plasma": ttl = .10
        else: ttl = .07
        self.tracers.append(dict(x0=self.muz[0], y0=self.muz[1], x1=ex, y1=ey, ttl=ttl, max=ttl, k=kind, col=w.get("glow", (255, 235, 160)), perp=perp))
    def shoot_ray(self, ang, w):
        c, s = math.cos(ang), math.sin(ang)
        wd = min(cast(self.px, self.py, ang)[0], w.get("rng", MAXD))
        k = w["kind"]
        hits = []
        for e in self.enemies:
            if not e.alive or e.spawn > .3: continue
            dx, dy = e.x - self.px, e.y - self.py
            al = dx * c + dy * s
            if 0 < al < wd + e.t["r"] and abs(dx * s - dy * c) < e.t["r"]: hits.append((al, e))
        hits.sort(key=lambda h: h[0])
        pierce = w.get("pierce", 1); hd = wd
        if hits and pierce == 1: hd = hits[0][0]
        elif hits and pierce > 1: hd = min(wd, hits[min(pierce, len(hits)) - 1][0]) if pierce < 50 else wd
        hx, hy = self.px + c * (hd - .05), self.py + s * (hd - .05)
        hit_wall = not hits or pierce > 1
        # visual: tracer
        if k in ("rifle", "smg", "mini", "pistol", "sniper"):
            if k not in ("smg", "mini") or random.random() < .5: self.add_tracer(ang, hd, w, "bullet")
        elif k == "shotgun":
            if random.random() < .25: self.add_tracer(ang, hd, w, "bullet")
        elif k == "rail": self.add_tracer(ang, wd, w, "rail")
        elif k == "plasma": self.add_tracer(ang, hd, w, "plasma")
        elif k == "launch": self.add_tracer(ang, hd, w, "rocket")
        if k == "launch":
            self.pending.append([clamp(hd / 24, .12, 1.2), "boom", hx, hy, w]); return
        if "splash" not in w:
            for al, e in hits[:pierce]:
                e.hurt(w["d"], self, c, s)
                self.hit_fx(e, w, c, s)
        if "splash" in w:
            self.explode(hx, hy, w, small=True)
        elif k == "flame":
            self.add_fx(self.px + c * hd * random.random(), self.py + s * hd * random.random(), "flame", .45, .5, .35, vx=c * .6, vy=s * .6, vz=.5)
            if random.random() < .5: self.burst(self.px + c * hd, self.py + s * hd, .4, 1, "ember", (255, 160, 50), .8, 1.2, ttl=(.5, 1.0), size=(.01, .018))
        elif hit_wall and hd < wd + .01 or (hit_wall and not hits):
            self.wall_hit(hx, hy, c, s, k)
        if k == "rail":
            for i in range(1, int(wd), 2): self.add_fx(self.px + c * i, self.py + s * i, "plasma", .3, .25, .5)
    def hit_fx(self, e, w, c, s):
        z = e.t["sc"] * random.uniform(.4, .75); k = w["kind"]
        if k in ("plasma", "rail"): self.burst(e.x - c * .15, e.y - s * .15, z, 7, "spark", (110, 230, 255), 2.4, 1.6, -c, -s, .6)
        elif k == "flame": self.burst(e.x, e.y, z, 2, "ember", (255, 150, 50), .8, 1.4)
        else:
            n = int(clamp(w["d"] / 5 + 3, 3, 22))
            self.burst(e.x, e.y, z, n, "blood", (170, 10, 10), 2.2 + w["d"] / 80, 1.6, c, s, .7)
        self.play(self.snd_hit)
    def wall_hit(self, hx, hy, c, s, k):
        z = random.uniform(.38, .62)
        self.burst(hx, hy, z, 5, "spark", (255, 215, 120), 2.0, 1.4, -c, -s, .6, ttl=(.15, .4))
        self.burst(hx, hy, z, 3, "debris", (150, 145, 140), 1.2, 1.0, -c, -s, .6, ttl=(.4, .8), size=(.012, .02))
        self.parts.append(dict(x=hx - c * .04, y=hy - s * .04, z=z, vx=-c * .15, vy=-s * .15, vz=.18, ttl=.9, max=.9, col=(0, 0, 0), sz=.04, k="smoke"))
        if k != "flame":
            self.decals.append(dict(x=hx, y=hy, z=z, t=0.0, life=9.0, big=False))
            if len(self.decals) > 60: del self.decals[0]
    def explode(self, hx, hy, w, small=False):
        R = w["splash"]
        for e in self.enemies:
            if e.alive:
                dd = math.hypot(e.x - hx, e.y - hy)
                if dd < R + e.t["r"]:
                    dxn, dyn = (e.x - hx) / (dd or 1), (e.y - hy) / (dd or 1)
                    e.hurt(w["d"] * max(.3, 1 - dd / (R + e.t["r"])), self, dxn, dyn)
        dd = math.hypot(self.px - hx, self.py - hy)
        if dd < R * .6: self.hurt_player(int(18 * (1 - dd / (R * .6))) + 2)
        if small:   # plasma impact
            self.add_fx(hx, hy, "plasma", .28, R * .7, .5)
            self.burst(hx, hy, .5, 8, "spark", (110, 230, 255), 2.6, 1.6)
            return
        self.play(self.snd_boom)
        for i in range(7):
            o = R * .35
            self.add_fx(hx + random.uniform(-o, o), hy + random.uniform(-o, o), "boom", random.uniform(.3, .6), R * random.uniform(.55, .9), random.uniform(.35, .65),
                        vz=random.uniform(.1, .5))
        self.add_fx(hx, hy, "ring", .38, R * 1.5, .5)
        self.burst(hx, hy, .5, 30, "spark", (255, 200, 90), 5.5, 3.5, ttl=(.4, 1.0))
        self.burst(hx, hy, .5, 14, "debris", (120, 110, 100), 4.0, 3.0, ttl=(.7, 1.4), size=(.02, .045))
        self.burst(hx, hy, .45, 14, "smoke", (0, 0, 0), .9, .6, ttl=(1.2, 2.2), size=(.12, .22), spread=.7)
        self.decals.append(dict(x=hx, y=hy, z=.5, t=0.0, life=12.0, big=True))
        dist = math.hypot(self.px - hx, self.py - hy)
        self.shake = max(self.shake, clamp(.5 / (1 + dist * .5), .04, .45)); self.boomflash = max(self.boomflash, clamp(.25 - dist * .02, 0, .25))
    def on_enemy_death(self, e, dx, dy):
        side = random.choice((-1, 1))
        self.corpses.append(dict(x=e.x, y=e.y, kind=e.kind, t=0.0, side=side, vx=dx * 2.2, vy=dy * 2.2, tint=random.uniform(.9, 1.0)))
        if len(self.corpses) > 28: del self.corpses[0]
        sc = e.t["sc"]
        self.burst(e.x, e.y, sc * .55, 18 + int(sc * 8), "blood", (160, 8, 8), 3.0, 2.2, dx, dy, .8, ttl=(.5, 1.1), size=(.014, .03))
        self.burst(e.x, e.y, sc * .4, 4, "debris", (140, 20, 20), 2.0, 2.2, dx, dy, .8, ttl=(.5, .9), size=(.03, .05))
        self.play(self.snd_die)
    def spawn_wave(self):
        self.wave += 1; n = 4 + self.wave * 2
        pool = ["grunt"] + (["runner"] if self.wave >= 2 else []) + (["shooter"] if self.wave >= 3 else []) + (["tank"] if self.wave >= 4 else [])
        kinds = [random.choice(pool) for _ in range(n)]
        if self.wave % 5 == 0: kinds.append("boss")
        for kd in kinds:
            for _ in range(200):
                x, y = random.uniform(2, MW - 2), random.uniform(2, MH - 2)
                if walkable(x, y, .6) and math.hypot(x - self.px, y - self.py) > 9:
                    e = Enemy(kd, x, y); e.spawn = random.uniform(.6, 1.1); self.enemies.append(e)
                    self.burst(x, y, .02, 9, "debris", (110, 100, 90), 1.4, 1.5, ttl=(.5, 1.0), size=(.015, .03))
                    self.burst(x, y, .05, 3, "smoke", (0, 0, 0), .25, .35, ttl=(.9, 1.5), size=(.08, .14))
                    break
        if self.wave > 1:
            self.hp = min(100, self.hp + 30)
            for a, w in zip(self.ammo, WEAPONS): a["res"] += w["mag"]
    # -- update
    def update_world(self, dt):
        for f in self.fx:
            f["ttl"] -= dt; f["x"] += f["vx"] * dt; f["y"] += f["vy"] * dt; f["z"] += f["vz"] * dt
        self.fx = [f for f in self.fx if f["ttl"] > 0]
        for p in self.parts:
            p["ttl"] -= dt; k = p["k"]
            if k == "smoke":
                p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt; p["z"] += p["vz"] * dt; p["sz"] += dt * .08
                dr = max(0, 1 - dt * 1.2); p["vx"] *= dr; p["vy"] *= dr; continue
            if k == "ember": p["vz"] += dt * .6
            else: p["vz"] -= (9.0 if k in ("blood", "debris") else 6.0) * dt
            nx, ny = p["x"] + p["vx"] * dt, p["y"] + p["vy"] * dt
            if solid(nx, ny): p["vx"] *= -.25; p["vy"] *= -.25
            else: p["x"], p["y"] = nx, ny
            p["z"] += p["vz"] * dt
            if p["z"] <= 0:
                p["z"] = 0
                if k == "blood": p["vx"] = p["vy"] = p["vz"] = 0; p["ttl"] = min(p["ttl"], 1.4)
                elif k in ("spark", "debris"): p["vz"] = abs(p["vz"]) * .35; p["vx"] *= .6; p["vy"] *= .6
                else: p["vz"] = 0
        self.parts = [p for p in self.parts if p["ttl"] > 0]
        for c in self.corpses:
            c["t"] += dt
            if abs(c["vx"]) + abs(c["vy"]) > .05:
                nx, ny = c["x"] + c["vx"] * dt, c["y"] + c["vy"] * dt
                if not solid(nx, ny): c["x"], c["y"] = nx, ny
                k = max(0.0, 1 - dt * 5); c["vx"] *= k; c["vy"] *= k
        self.corpses = [c for c in self.corpses if c["t"] < 14]
        for d in self.decals: d["t"] += dt
        self.decals = [d for d in self.decals if d["t"] < d["life"]]
        for tr in self.tracers: tr["ttl"] -= dt
        self.tracers = [t for t in self.tracers if t["ttl"] > 0]
        for c in self.casings:
            c["ttl"] -= dt
            if c["rest"]: continue
            c["vy"] += 1250 * dt; c["x"] += c["vx"] * dt; c["y"] += c["vy"] * dt; c["rot"] += c["vr"] * dt
            if c["y"] > H - 10:
                c["y"] = H - 10; c["vy"] *= -.35; c["vx"] *= .5; c["vr"] *= .4
                if abs(c["vy"]) < 60: c["rest"] = 1
        self.casings = [c for c in self.casings if c["ttl"] > 0]
        # delayed events (shell ejects, rocket impact)
        for ev in self.pending[:]:
            ev[0] -= dt
            if ev[0] <= 0:
                self.pending.remove(ev)
                if ev[1] == "boom": self.explode(ev[2], ev[3], ev[4])
        for ev in self.eject_q[:]:
            ev[0] -= dt
            if ev[0] <= 0:
                self.eject_q.remove(ev); self.eject("shell" if ev[1] == "shell" else "brass", down=ev[1] == "rev")
        # enemy bolts
        for b in self.projectiles[:]:
            b["x"] += b["vx"] * dt; b["y"] += b["vy"] * dt; b["ttl"] -= dt
            if random.random() < .6:
                self.parts.append(dict(x=b["x"], y=b["y"], z=.45, vx=0, vy=0, vz=0, ttl=.18, max=.18, col=b["col"], sz=.02, k="ember"))
            if solid(b["x"], b["y"]) or b["ttl"] <= 0:
                self.burst(b["x"] - b["vx"] * .02, b["y"] - b["vy"] * .02, .45, 6, "spark", b["col"], 1.6, 1.0, ttl=(.15, .35)); self.projectiles.remove(b)
            elif math.hypot(b["x"] - self.px, b["y"] - self.py) < .38:
                self.hurt_player(b["dmg"]); self.projectiles.remove(b)
    def update(self, dt, inp):
        dt = min(dt, .05); self.t += dt
        self.hurt_f = max(0, self.hurt_f - dt); self.flash = max(0, self.flash - dt)
        self.shake = max(0, self.shake - dt); self.hitm = max(0, self.hitm - dt); self.boomflash = max(0, self.boomflash - dt)
        self.pump = max(0, self.pump - dt)
        # recoil spring
        self.rv += (-170 * self.rc - 17 * self.rv) * dt; self.rc += self.rv * dt
        self.update_world(dt)
        if self.dead:
            self.dead_t += dt; return
        self.pa += inp.get("turn", 0)
        # look up / down (pitch is the horizon shift in screen px; + = looking up)
        if inp.get("recenter"): self.pitch = lerp(self.pitch, 0.0, min(1, dt * 10))
        self.pitch = clamp(self.pitch + inp.get("look", 0), -PMAX, PMAX)
        sprint = bool(inp.get("sprint"))
        sp = 3.4 * (1.6 if sprint else 1.0)
        fw, st = inp.get("fwd", 0), inp.get("strafe", 0)
        c, s = math.cos(self.pa), math.sin(self.pa)
        vx = (c * fw - s * st); vy = (s * fw + c * st)
        l = math.hypot(vx, vy); moving = l > 0
        if moving:
            vx, vy = vx / l * sp * dt, vy / l * sp * dt; self.bob += dt * (10 if sprint else 7)
            if walkable(self.px + vx, self.py, .25): self.px += vx
            if walkable(self.px, self.py + vy, .25): self.py += vy
        # smooth animation drivers
        self.bobamp = lerp(self.bobamp, 1.0 if moving else 0.0, min(1, dt * 8))
        self.spr = lerp(self.spr, 1.0 if (sprint and moving and fw > 0 and self.reload_t <= 0) else 0.0, min(1, dt * 7))
        self.lean = lerp(self.lean, st, min(1, dt * 6))
        tgt = clamp(-inp.get("turn", 0) / max(dt, 1e-3) * 6.0, -70, 70)
        self.swx = lerp(self.swx, tgt, min(1, dt * 9))
        stepph = math.floor(self.bob / math.pi)
        if moving and stepph != self._step: self.play(self.snd_step)
        self._step = stepph
        self.spread = lerp(self.spread, (.35 if moving else 0) + (.2 if sprint else 0) + clamp(self.rc, 0, 1.5) * .35, min(1, dt * 10))
        # weapon switching
        if self.want != self.cur:
            self.swv = min(1, self.swv + dt / .15)
            if self.swv >= 1: self.cur = self.want; self.reload_t = 0; self.cool = .08; self.spin = 0
        elif self.swv > 0: self.swv = max(0, self.swv - dt / .22)
        # minigun spin-up / spin-down
        if self.wp["kind"] == "mini":
            if inp.get("fire") and self.ammo[self.cur]["mag"] > 0 and self.reload_t <= 0 and self.swv <= 0: self.spin = min(1, self.spin + dt * 1.6)
            else: self.spin = max(0, self.spin - dt * .7)
            self.spin_ang += self.spin * dt * 34
        else: self.spin = 0
        self.cool = max(0, self.cool - dt)
        if self.reload_t > 0:
            self.reload_t -= dt
            if self.reload_t <= 0:
                a = self.ammo[self.cur]; take = min(self.wp["mag"] - a["mag"], a["res"]); a["mag"] += take; a["res"] -= take
                self.play(self.snd_reload)
            elif not self.rl_ejected and 1 - self.reload_t / self.wp["rl"] > .74: self.rl_ejected = True; self.play(self.snd_click)
        if inp.get("reload"): self.start_reload()
        if inp.get("fire") and self.wp["auto"] or inp.get("fire_press"): self.fire()
        elif self.wp["kind"] == "mini" and inp.get("fire"): self.fire()
        for e in self.enemies:
            if e.alive: e.update(self, dt)
        self.enemies = [e for e in self.enemies if e.alive]
        for p in self.pickups[:]:
            if math.hypot(p[0] - self.px, p[1] - self.py) < .7:
                if p[2] == "health": self.hp = min(100, self.hp + 25)
                else:
                    for a, w in zip(self.ammo, WEAPONS): a["res"] += max(2, w["mag"] // 2)
                self.burst(p[0], p[1], .2, 8, "spark", (120, 255, 140) if p[2] == "health" else (255, 220, 90), 1.2, 1.4, ttl=(.3, .6))
                self.pickups.remove(p)
        if not self.enemies:
            self.wave_t -= dt
            if self.wave_t <= 0: self.spawn_wave(); self.wave_t = 3.0
    # -- render
    def render(self):
        scr = self.screen
        # camera: recoil kick + footstep dip + hurt/death
        kick = self.rc * (3 + self.wp["d"] ** .5 * .55)
        dip = abs(math.sin(self.bob)) * 4.5 * self.bobamp * (1.4 if self.spr > .5 else 1)
        fall = smooth(self.dead_t / .9) * 90 if self.dead else 0
        sx = (math.sin(self.t * 71) * self.shake * 34); sy = (math.cos(self.t * 83) * self.shake * 34)
        self.hor = H / 2 + self.pitch + clamp(kick + dip - fall + sy, -110, 110)
        hor = self.hor
        scr.blit(self.bg, (0, int(-(self.BGH - H) / 2 + (hor - H / 2))))
        zb = [MAXD] * NR
        for i in range(NR):
            off = ((i + .5) * CW - W / 2)
            ra = self.pa + math.atan(off / PROJ)
            d, side, t, wx = cast(self.px, self.py, ra)
            perp = d * math.cos(ra - self.pa); zb[i] = perp
            if not t: continue
            lh = PROJ / max(perp, .05); top = hor - lh / 2
            y0, y1 = max(0, int(top)), min(H, int(top + lh))
            sh = max(.1, 1 / (1 + perp * perp * .012)) * (.72 if side else 1) * (.93 if int(wx * 4) % 2 else 1)
            b = WALL_COL[t]; col = (int(b[0] * sh), int(b[1] * sh), int(b[2] * sh))
            pygame.draw.rect(scr, col, (i * CW, y0, CW, y1 - y0))
            dk = (int(col[0] * .6), int(col[1] * .6), int(col[2] * .6))
            if lh > 20:
                for k in (.25, .5, .75):
                    y = int(top + lh * k)
                    if 0 <= y < H: pygame.draw.line(scr, dk, (i * CW, y), (i * CW + CW - 1, y))
        # sprites
        items = []
        px_, py_ = self.px, self.py
        for e in self.enemies: items.append((math.hypot(e.x - px_, e.y - py_), "e", e))
        for c in self.corpses: items.append((math.hypot(c["x"] - px_, c["y"] - py_) + .01, "c", c))
        for p in self.pickups: items.append((math.hypot(p[0] - px_, p[1] - py_), "p", p))
        for f in self.fx: items.append((math.hypot(f["x"] - px_, f["y"] - py_), "f", f))
        for q in self.parts: items.append((math.hypot(q["x"] - px_, q["y"] - py_), "q", q))
        for dcl in self.decals: items.append((math.hypot(dcl["x"] - px_, dcl["y"] - py_) + .02, "d", dcl))
        for b in self.projectiles: items.append((math.hypot(b["x"] - px_, b["y"] - py_), "b", b))
        items.sort(key=lambda a: -a[0])
        for dist, kind, o in items:
            if kind == "e": self.draw_enemy(o, zb)
            elif kind == "c": self.draw_corpse(o, zb)
            elif kind == "p":
                self.sprite(self.pk_img(o[2]), o[0], o[1], .28, .05 + .03 * math.sin(self.t * 4 + o[0]), zb)
            elif kind == "f":
                k = 1 - o["ttl"] / o["max"]
                if o["k"] == "ring":
                    self.sprite(self.ring_img, o["x"], o["y"], o["sz"] * (.2 + k * .8), o["z"] - o["sz"] * (.2 + k * .8) / 2, zb, int(255 * (1 - k)))
                    continue
                img = {"spark": self.spark, "boom": self.boom, "plasma": self.plasma, "flame": self.flame}[o["k"]]
                sz = o["sz"] * (1 + k * (1.2 if o["k"] in ("boom", "flame") else .2))
                self.sprite(img, o["x"], o["y"], sz, o["z"] - sz / 2, zb, int(255 * (1 - k * k * (.9 if o["k"] == "boom" else .6))))
            elif kind == "q": self.draw_part(o, zb)
            elif kind == "d":
                fade = clamp((o["life"] - o["t"]) / 2.0, 0, 1)
                if o["big"]: self.sprite(self.scorch_img, o["x"], o["y"], .8, o["z"] - .4, zb, int(200 * fade))
                else: self.sprite(self.hole_img, o["x"], o["y"], .05, o["z"] - .025, zb, int(255 * fade))
            elif kind == "b":
                img = self.bolt_img[o["col"]]
                self.sprite(img, o["x"], o["y"], .2 + .03 * math.sin(self.t * 40), .45 - .1, zb)
        self.draw_tracers()
        self.draw_gun()
        if self.boomflash > 0 or (self.flash > 0 and not self.dead):
            f = max(self.boomflash * 3, self.flash / .06 * .3 * self.flash_k)
            scr.fill((int(60 * f), int(42 * f), int(16 * f)), special_flags=pygame.BLEND_RGB_ADD)
        self.hud()
    _pk = {}
    def pk_img(self, kind):
        if kind not in self._pk:
            s = pygame.Surface((64, 64), pygame.SRCALPHA)
            if kind == "health":
                pygame.draw.rect(s, (240, 240, 240), (8, 8, 48, 48), border_radius=6)
                pygame.draw.rect(s, (220, 30, 30), (26, 14, 12, 36)); pygame.draw.rect(s, (220, 30, 30), (14, 26, 36, 12))
            else:
                pygame.draw.rect(s, (60, 100, 50), (6, 14, 52, 38), border_radius=4)
                pygame.draw.rect(s, (230, 200, 60), (14, 22, 36, 8)); pygame.draw.rect(s, (230, 200, 60), (14, 36, 36, 8))
            self._pk[kind] = s
        return self._pk[kind]
    def project(self, x, y):
        dx, dy = x - self.px, y - self.py
        ang = math.atan2(dy, dx) - self.pa
        ang = (ang + math.pi) % (2 * math.pi) - math.pi
        if abs(ang) > FOV: return None
        perp = math.hypot(dx, dy) * math.cos(ang)
        if perp < .25: return None
        return W / 2 + math.tan(ang) * PROJ, perp
    def sprite(self, img, x, y, scale, z, zb, alpha=255):
        pr = self.project(x, y)
        if not pr: return
        sxp, perp = pr
        hpx = int(PROJ * scale / perp)
        if hpx < 2 or hpx > 1600: return
        wpx = max(1, int(hpx * img.get_width() / img.get_height()))
        bottom = self.hor + PROJ * (.5 - z) / perp
        sc = pygame.transform.scale(img, (wpx, hpx))
        if alpha < 255: sc.set_alpha(max(0, alpha))
        x0 = int(sxp - wpx / 2); y0 = int(bottom - hpx)
        for c in range(max(0, x0 // CW), min(NR - 1, (x0 + wpx) // CW) + 1):
            if zb[c] < perp: continue
            l, r = max(c * CW, x0), min(c * CW + CW, x0 + wpx)
            if r > l: self.screen.blit(sc, (l, y0), pygame.Rect(l - x0, 0, r - l, hpx))
    def draw_enemy(self, e, zb):
        fr = self.frames[e.kind]; t = e.t
        if e.stun > 0: img = fr["hurt"]
        elif e.atk >= 0: img = fr["atk"][min(NATK - 1, int(e.atk / e.atk_dur * NATK))]
        else: img = fr["walk"][int(e.phase / math.tau * NWALK) % NWALK] if e.moving else fr["walk"][0]
        if e.flash > 0: img = self.white(img)
        sc = t["sc"]
        if e.atk >= 0 and not t["ranged"]:
            f = e.atk / e.atk_dur; sc *= 1 + .12 * math.sin(clamp((f - .35) / .4, 0, 1) * math.pi)
        z = 0.0
        if not e.moving and e.atk < 0 and e.stun <= 0: sc *= 1 + .012 * math.sin(self.t * 2.2 + e.x * 3)       # idle breathing
        if e.spawn > 0:        # rise out of the floor
            f = clamp(1 - e.spawn / .8, .05, 1); f = smooth(f)
            h = max(1, int(FH * f)); img = img.subsurface((0, FH - h, FW, h)); sc *= f
            self.sprite(self.shadow_img, e.x, e.y, .24 * STYLE[e.kind]["w"] * f, 0, zb, int(255 * f))
            self.sprite(img, e.x, e.y, sc, z, zb)
            return
        self.sprite(self.shadow_img, e.x, e.y, .24 * STYLE[e.kind]["w"], 0, zb)
        self.sprite(img, e.x, e.y, sc, z, zb)
        self.healthbar(e, zb)
    def draw_corpse(self, c, zb):
        fr = self.frames[c["kind"]]["death"]; i = min(NDEATH - 1, int(c["t"] / .075))
        img = fr[i]
        if c["side"] < 0: img = pygame.transform.flip(img, True, False)
        sc = ETYPES[c["kind"]]["sc"]; st = STYLE[c["kind"]]["w"]
        fade = clamp((14 - c["t"]) / 3.0, 0, 1)
        grow = smooth((c["t"] - .15) / 1.6)
        if grow > 0: self.sprite(self.pool_img, c["x"], c["y"], .30 * st * grow, 0, zb, int(235 * fade))
        self.sprite(img, c["x"], c["y"], sc, 0, zb, int(255 * fade))
    def draw_part(self, p, zb):
        pr = self.project(p["x"], p["y"])
        if not pr: return
        sxp, perp = pr; c = int(sxp // CW)
        if not 0 <= c < NR or zb[c] < perp: return
        f = p["ttl"] / p["max"]; k = p["k"]
        if k == "smoke":
            sz = p["sz"] * 3.2
            self.sprite(self.smoke_img, p["x"], p["y"], sz, p["z"] - sz / 2, zb, int(120 * f * min(1, (1 - f) * 8 + .2)))
            return
        ys = self.hor + PROJ * (.5 - p["z"]) / perp
        r = max(1, int(PROJ * p["sz"] / perp)); pos = (int(sxp), int(ys))
        if k == "blood": pygame.draw.circle(self.screen, (int(90 + 80 * f), 8, 8), pos, r)
        elif k == "spark":
            pygame.draw.circle(self.screen, (255, int(120 + 110 * f), int(40 * f)), pos, r)
            if r > 1: pygame.draw.circle(self.screen, (255, 250, 210), pos, max(1, r // 2))
        elif k == "debris": pygame.draw.rect(self.screen, tuple(int(v * (.6 + .4 * f)) for v in p["col"]), (pos[0], pos[1], r + 1, r + 1))
        elif k == "ember":
            col = p["col"]; pygame.draw.circle(self.screen, (int(col[0] * (.5 + .5 * f)), int(col[1] * f), int(col[2] * f)), pos, r + 1)
    def healthbar(self, e, zb):
        pr = self.project(e.x, e.y)
        if not pr or e.hp >= e.maxhp: return
        sxp, perp = pr; c = int(sxp // CW)
        if not 0 <= c < NR or zb[c] < perp: return
        wpx = int(PROJ * .6 / perp); top = self.hor + PROJ * .5 / perp - PROJ * e.t["sc"] / perp - 8
        pygame.draw.rect(self.screen, (40, 0, 0), (sxp - wpx / 2, top, wpx, 5))
        pygame.draw.rect(self.screen, (230, 40, 40), (sxp - wpx / 2, top, wpx * e.hp / e.maxhp, 5))
    def draw_tracers(self):
        scr = self.screen
        for tr in self.tracers:
            f = 1 - tr["ttl"] / tr["max"]; k = tr["k"]
            x0, y0, x1, y1 = tr["x0"], tr["y0"], tr["x1"], tr["y1"]
            if k == "bullet":
                a = clamp(f * 1.3, 0, 1); b = clamp(f * 1.3 - .35, 0, 1)
                p0 = (lerp(x0, x1, b), lerp(y0, y1, b)); p1 = (lerp(x0, x1, a), lerp(y0, y1, a))
                pygame.draw.line(scr, (255, 235, 150), p0, p1, 2)
            elif k == "plasma":
                p = (lerp(x0, x1, f), lerp(y0, y1, f)); r = int(10 * (1 - f * .7))
                g = pygame.transform.smoothscale(self.plasma, (r * 4, r * 4)); scr.blit(g, (p[0] - r * 2, p[1] - r * 2), special_flags=pygame.BLEND_ADD)
            elif k == "rocket":
                e = f * f * .6 + f * .4
                for i in range(10):
                    q = max(0, e - i * .02); pp = (lerp(x0, x1, q), lerp(y0, y1, q))
                    rr = int(4 + i * 1.5); sm = pygame.transform.smoothscale(self.smoke_img, (rr * 3, rr * 3)); sm.set_alpha(int(150 * (1 - i / 10)))
                    scr.blit(sm, (pp[0] - rr * 1.5, pp[1] - rr * 1.5))
                p = (lerp(x0, x1, e), lerp(y0, y1, e)); rr = int(14 * (1 - e * .75))
                g = pygame.transform.smoothscale(self.rocket_glow, (rr * 4, rr * 4)); scr.blit(g, (p[0] - rr * 2, p[1] - rr * 2), special_flags=pygame.BLEND_ADD)
            elif k == "rail":
                fade = clamp(1 - f * 1.1, 0, 1); col = tr["col"]
                bx0, by0 = min(x0, x1) - 30, min(y0, y1) - 30; bw, bh = int(abs(x1 - x0) + 60), int(abs(y1 - y0) + 60)
                if bw < 4000 and bh < 4000:
                    tmp = pygame.Surface((bw, bh), pygame.SRCALPHA)
                    for wd, mul in ((14, .25), (7, .55), (3, 1.0)):
                        c_ = tuple(int(v * fade * mul) for v in col) if wd > 3 else (int(255 * fade), int(255 * fade), int(255 * fade))
                        pygame.draw.line(tmp, c_, (x0 - bx0, y0 - by0), (x1 - bx0, y1 - by0), wd)
                    scr.blit(tmp, (bx0, by0), special_flags=pygame.BLEND_ADD)
    # ---- first-person weapon
    def draw_gun(self):
        w, scr = self.wp, self.screen; k = w["kind"]
        if self.dead and self.dead_t > 1.2: return
        t = self.t
        # ---------- animation state
        bo = self.bobamp * (1.35 if self.spr > .5 else 1.0)
        bx = math.cos(self.bob * .5) * 15 * bo; byb = abs(math.sin(self.bob)) * 12 * bo
        idle_x = math.sin(t * .9) * 2.0; idle_y = math.sin(t * 1.7) * 2.6
        a = self.ammo[self.cur]
        rp = 1 - self.reload_t / w["rl"] if self.reload_t > 0 else -1.0
        D = (sstep(rp, 0, .2) - sstep(rp, .8, 1.0)) if rp >= 0 else 0.0              # lowered amount while reloading
        offx = W * .66 + bx + idle_x + self.swx * .8 + self.lean * 14 + D * 40 + self.spr * 34
        offy = H + 30 + byb + idle_y + self.rc * 30 + self.swv * 300 + D * 105 + self.spr * 38 + (smooth(self.dead_t / .9) * 420 if self.dead else 0)
        ang = self.swx * .10 + self.rc * 3.8 + D * 20 - self.lean * 3 + self.spr * 12
        # ---------- draw gun in its own layer
        gs = self.gunsurf; gs.fill((0, 0, 0, 0))
        cx, by = GCX, GBY; bw = w["bw"]; col = w["col"]
        dark = shade(col, .55); lite = tuple(min(255, int(c * 1.4) + 20) for c in col); mid = shade(col, .8)
        mzx, mzy = cx - 70, by - H * w["L"] - 60
        body_top = by - (by - mzy) * .55
        sleeve = (62, 74, 66); sleeve_d = (40, 50, 44); skin = (206, 166, 136); skin_d = (170, 130, 104)
        # sleeve + right hand base
        pygame.draw.polygon(gs, sleeve_d, [(cx - bw - 26, by), (cx + bw + 70, by), (cx + bw + 20, body_top + 118), (cx + bw * .1, body_top + 110)])
        pygame.draw.polygon(gs, sleeve, [(cx - bw - 26, by), (cx + bw + 30, by), (cx + bw + 6, body_top + 118), (cx + bw * .1, body_top + 110)])
        pygame.draw.line(gs, (95, 110, 98), (cx + bw * .3, body_top + 114), (cx - bw * .3, by), 3)
        pygame.draw.rect(gs, (30, 36, 32), (cx + bw * .1 - 2, body_top + 104, bw * .9 + 26, 12), border_radius=4)   # cuff
        # magazine (animated during reload)
        mag_dy = 0.0; mag_vis = k in HAS_MAG; mag_dim = False
        if rp >= 0 and mag_vis:
            if .26 < rp < .5: mag_dy = smooth((rp - .26) / .24) * 190
            elif .5 <= rp < .74: mag_dy = (1 - smooth((rp - .5) / .24)) * 190
            if .5 <= rp < .74: mag_dim = True
            if .74 <= rp < .82: mag_dy = -math.sin((rp - .74) / .08 * math.pi) * 5      # seat-jolt
        if mag_vis:
            mw = 16 if k == "pistol" else 20
            mx = cx + 8 if k != "mini" else cx - 20
            mh = 60 if k != "mini" else 70
            mc = shade(col, .5) if not mag_dim else shade(col, .7)
            if k == "mini": mw = 44
            pygame.draw.rect(gs, mc, (mx, body_top + 36 + mag_dy, mw, mh), border_radius=3)
            pygame.draw.rect(gs, lite, (mx + 2, body_top + 38 + mag_dy, 3, mh - 6))
            if k in ("plasma", "rail"): pygame.draw.rect(gs, w["glow"], (mx + mw - 6, body_top + 42 + mag_dy, 3, mh - 16))
        # body
        pygame.draw.polygon(gs, dark, [(cx - bw - 3, by + 2), (cx + bw + 3, by + 2), (cx + bw * .6 + 2, body_top - 2), (cx - bw * .6 - 2, body_top - 2)])
        pygame.draw.polygon(gs, col, [(cx - bw, by), (cx + bw, by), (cx + bw * .6, body_top), (cx - bw * .6, body_top)])
        pygame.draw.polygon(gs, shade(col, .72), [(cx + bw * .3, by), (cx + bw, by), (cx + bw * .6, body_top), (cx + bw * .2, body_top)])
        pygame.draw.line(gs, lite, (cx - bw * .6, body_top), (cx - bw, by), 3)
        # barrel(s)
        def barrel(ox, hw, base_w, c1, topy=None):
            ty = body_top if topy is None else topy
            pygame.draw.polygon(gs, c1, [(cx + ox - base_w, ty), (cx + ox + base_w, ty), (mzx + ox * .3 + hw, mzy), (mzx + ox * .3 - hw, mzy)])
            pygame.draw.line(gs, shade(c1, 1.7), (cx + ox - base_w + 2, ty), (mzx + ox * .3 - hw + 1, mzy), 2)
        slide = 0.0
        if k in ("pistol", "smg", "rifle"):
            slide = self.rc * 7
            if a["mag"] <= 0 and rp < 0: slide = 13
            if rp >= .86: slide = math.sin((rp - .86) / .14 * math.pi) * 14
        if k == "mini":
            rad = 22
            order = sorted(range(3), key=lambda i: math.sin(self.spin_ang + i * math.tau / 3))
            for i in order:
                an = self.spin_ang + i * math.tau / 3; ox = math.cos(an) * rad; dep = (math.sin(an) + 1) / 2
                c1 = shade(dark, .8 + .6 * dep); barrel(ox, 7, 11, c1)
                pygame.draw.circle(gs, (10, 10, 10), (int(mzx + ox * .3), int(mzy)), 5)
            pygame.draw.ellipse(gs, lite, (mzx - 34, mzy - 8, 68, 20), 3)
            pygame.draw.ellipse(gs, dark, (cx - 46, body_top - 20, 92, 34), 0); pygame.draw.ellipse(gs, mid, (cx - 40, body_top - 17, 80, 26), 0)
        elif k == "launch":
            barrel(0, 28, 34, dark); pygame.draw.ellipse(gs, (20, 20, 20), (mzx - 28, mzy - 10, 56, 22))
            if a["mag"] > 0 or rp >= 0:
                pygame.draw.ellipse(gs, (210, 80, 40), (mzx - 11, mzy - 6, 22, 12))
            pygame.draw.rect(gs, (40, 40, 40), (cx - 10, body_top - 24, 20, 18), border_radius=3)
        elif k == "shotgun":
            barrel(-12, 9, 14, dark); barrel(12, 9, 14, dark)
            po = 0.0
            if self.pump > 0: po = math.sin((1 - self.pump / .5) * math.pi) * 22
            if rp >= 0 and rp > .72: po = max(po, math.sin(clamp((rp - .72) / .22, 0, 1) * math.pi) * 22)
            self._pump_off = po
            pygame.draw.rect(gs, shade(col, 1.15), (cx - 40, body_top - 56 + po, 54, 22), border_radius=6)
            pygame.draw.line(gs, lite, (cx - 36, body_top - 54 + po), (cx + 8, body_top - 54 + po), 2)
        elif k == "sniper":
            barrel(0, 6, 12, dark)
            pygame.draw.rect(gs, (24, 24, 28), (cx - 30, body_top - 34, 60, 24), border_radius=9)
            pygame.draw.rect(gs, (50, 50, 56), (cx - 34, body_top - 30, 10, 16), border_radius=3)
            pygame.draw.circle(gs, (80, 200, 255), (cx - 33, body_top - 22), 6); pygame.draw.circle(gs, (200, 240, 255), (cx - 35, body_top - 24), 2)
        elif k == "flame":
            barrel(0, 12, 20, dark)
            fl = 5 + random.random() * 4
            pygame.draw.circle(gs, (255, 90, 20), (int(mzx), int(mzy)), int(fl)); pygame.draw.circle(gs, (255, 220, 120), (int(mzx), int(mzy - 2)), int(fl * .5))
            pygame.draw.circle(gs, (90, 90, 95), (cx + 30, int(body_top + 20)), 22); pygame.draw.circle(gs, (140, 140, 150), (cx + 26, int(body_top + 14)), 7)
        elif k in ("plasma", "rail"):
            barrel(0, 10, 22, dark)
            g = w["glow"]; pulse = 4 + 3 * math.sin(t * 10)
            if k == "rail":
                charge = 1 - clamp(self.cool * w["r"], 0, 1) if self.cool > 0 else 1.0
                pulse = 2 + 9 * charge + 2 * math.sin(t * 14) * charge
                g = tuple(int(v * (.25 + .75 * charge)) for v in g)
                for off in (-14, 14): pygame.draw.line(gs, g, (cx + off * .6, body_top), (mzx + off * .3, mzy), 5); pygame.draw.line(gs, (255, 255, 255), (cx + off * .6, body_top), (mzx + off * .3, mzy), 1)
            pygame.draw.circle(gs, g, (int(cx - 25), int(body_top + 12)), int(14 + pulse))
            pygame.draw.circle(gs, (255, 255, 255), (int(cx - 25), int(body_top + 12)), 6)
        else:
            barrel(0, 9 if k != "pistol" else 12, 18, dark)
        if k in ("pistol", "smg", "rifle"):
            sl = (cx - bw * .55 + slide, body_top - 12, bw * 1.1, 26)
            pygame.draw.rect(gs, dark, (sl[0] - 1, sl[1] - 1, sl[2] + 2, sl[3] + 2), border_radius=5)
            pygame.draw.rect(gs, shade(col, 1.05), sl, border_radius=4)
            pygame.draw.line(gs, lite, (sl[0] + 4, sl[1] + 2), (sl[0] + sl[2] - 4, sl[1] + 2), 2)
            for i in range(4): pygame.draw.line(gs, dark, (sl[0] + sl[2] * .55 + i * 5, sl[1] + 5), (sl[0] + sl[2] * .55 + i * 5, sl[1] + 20), 2)
        pygame.draw.rect(gs, (15, 15, 15), (mzx - 2, mzy - 16, 4, 10))        # front sight
        # right hand over grip (fingers wrap)
        hx, hy = cx + bw * .45 + 12, body_top + 100
        pygame.draw.ellipse(gs, skin_d, (hx - 24, hy - 32, 52, 64)); pygame.draw.ellipse(gs, skin, (hx - 26, hy - 34, 50, 62))
        for i in range(4): pygame.draw.line(gs, skin_d, (hx - 24, hy - 22 + i * 13), (hx + 4, hy - 20 + i * 13), 3)
        pygame.draw.ellipse(gs, skin, (hx + 10, hy - 52, 22, 42))      # thumb
        # left (support) hand
        lh = None
        if k in TWO_HAND:
            base = (cx - 34, body_top - 44 + (getattr(self, "_pump_off", 0) if k == "shotgun" else 0))
            way = [(0, base), (.1, base), (.26, (cx + 26, body_top + 96)), (.34, (cx + 70, body_top + 330)), (.5, (cx + 70, body_top + 330)),
                   (.52, (cx + 26, body_top + 100 + mag_dy)), (.74, (cx + 26, body_top + 96)), (.88, base), (1.01, base)]
            if k in HAS_MAG and rp >= 0:
                for i in range(len(way) - 1):
                    if way[i][0] <= rp < way[i + 1][0]:
                        f = smooth((rp - way[i][0]) / (way[i + 1][0] - way[i][0])); lh = (lerp(way[i][1][0], way[i + 1][1][0], f), lerp(way[i][1][1], way[i + 1][1][1], f)); break
            elif rp >= 0:     # shell / rocket loading: hand dips toward the receiver, small insertion taps
                tap = math.sin(rp * math.pi * (6 if k == "shotgun" else 3)) * 14
                lh = (base[0] + 30 * D, base[1] + 70 * D + tap)
            if lh is None: lh = base
            pygame.draw.line(gs, sleeve_d, (lh[0] - 46, by + 20), lh, 42); pygame.draw.line(gs, sleeve, (lh[0] - 44, by + 20), (lh[0] - 2, lh[1]), 34)
            pygame.draw.ellipse(gs, skin_d, (lh[0] - 22, lh[1] - 20, 44, 40)); pygame.draw.ellipse(gs, skin, (lh[0] - 23, lh[1] - 22, 42, 38))
            for i in range(3): pygame.draw.line(gs, skin_d, (lh[0] - 22, lh[1] - 10 + i * 9), (lh[0] - 4, lh[1] - 8 + i * 9), 2)
        # muzzle flash
        if self.flash > 0:
            fk = self.flash / .06; sz = self.fl_sz * (.6 + .6 * fk)
            gcol = w.get("glow", (255, 225, 120)); n = 12 if k not in ("plasma", "rail", "flame") else 16
            pts = []
            for i in range(n):
                r = (58 if i % 2 == 0 else 20) * sz * (1.4 if k in ("shotgun", "launch", "mini") else 1.0); an = i / n * math.tau + self.fl_rot
                pts.append((mzx + math.cos(an) * r, mzy + math.sin(an) * r))
            pygame.draw.polygon(gs, gcol, pts); pygame.draw.circle(gs, (255, 255, 235), (int(mzx), int(mzy)), int(15 * sz))
        # ---------- compose with rotation
        tf = rot_blit(scr, gs, (GCX, GBY), (offx, offy), ang)
        self.muz = tf((mzx, mzy)); self.port = tf((cx + bw * .35, body_top + 4))
        if self.flash > 0 and not self.dead:
            sz = int(260 * clamp(self.flash / .06, .3, 1) * self.fl_sz * (.6 + self.flash_k * .5))
            gimg = pygame.transform.smoothscale(self.big_glow if "glow" not in w else self.glow_img(w["glow"]), (sz, sz))
            scr.blit(gimg, (self.muz[0] - sz / 2, self.muz[1] - sz / 2), special_flags=pygame.BLEND_ADD)
        # shell casings (screen space, in front of the gun)
        for c in self.casings:
            L, T = (9, 5) if c["big"] else (7, 3.5)
            ca, sa = math.cos(c["rot"]), math.sin(c["rot"])
            pts = [(c["x"] + (x * ca - y * sa), c["y"] + (x * sa + y * ca)) for x, y in ((-L, -T), (L, -T), (L, T), (-L, T))]
            pygame.draw.polygon(scr, c["col"], pts); pygame.draw.line(scr, (255, 240, 190), pts[0], pts[1], 1)
    def hud(self):
        scr, f = self.screen, self.font
        if self.hurt_f > 0:
            v = pygame.Surface((W, H), pygame.SRCALPHA); v.fill((200, 0, 0, int(140 * self.hurt_f / .35))); scr.blit(v, (0, 0))

        panel = pygame.Surface((W, H), pygame.SRCALPHA)
        # top status strip
        pygame.draw.rect(panel, (12, 16, 24, 180), (12, 12, 360, 52), border_radius=16)
        pygame.draw.rect(panel, (72, 220, 255, 120), (12, 12, 360, 52), 2, border_radius=16)
        pygame.draw.rect(panel, (10, 12, 18, 170), (W - 330, 12, 320, 52), border_radius=16)
        pygame.draw.rect(panel, (72, 220, 255, 120), (W - 330, 12, 320, 52), 2, border_radius=16)
        # bottom left / right info panels
        pygame.draw.rect(panel, (12, 16, 24, 180), (18, H - 58, 220, 40), border_radius=12)
        pygame.draw.rect(panel, (100, 255, 140, 140), (18, H - 58, 220, 40), 2, border_radius=12)
        pygame.draw.rect(panel, (12, 16, 24, 180), (W - 240, H - 78, 210, 58), border_radius=14)
        pygame.draw.rect(panel, (255, 208, 80, 120), (W - 240, H - 78, 210, 58), 2, border_radius=14)
        scr.blit(panel, (0, 0))

        # dynamic crosshair + hit marker
        cx, cy = W // 2, H // 2; g = 7 + self.spread * 16
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            a0 = (cx + dx * g, cy + dy * g); a1 = (cx + dx * (g + 7), cy + dy * (g + 7))
            pygame.draw.line(scr, (255, 255, 255), a0, a1, 2)
            pygame.draw.line(scr, (80, 240, 255), (cx + dx * (g - 2), cy + dy * (g - 2)), (cx + dx * (g + 5), cy + dy * (g + 5)), 1)
        if self.hitm > 0:
            kc = (255, 70, 60) if self.hitm > .2 else (255, 255, 255); o = 7 + (1 - self.hitm / .35) * 5
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                pygame.draw.line(scr, kc, (cx + dx * o, cy + dy * o), (cx + dx * (o + 7), cy + dy * (o + 7)), 2)
        # stats
        pygame.draw.rect(scr, (18, 24, 38), (20, H - 40, 220, 20), border_radius=10)
        pygame.draw.rect(scr, (92, 255, 135), (20, H - 40, 220 * self.hp / 100, 20), border_radius=10)
        scr.blit(f.render(f"HP {int(self.hp)}", True, (235, 245, 255)), (28, H - 41))
        wi = self.want; a, w = self.ammo[wi], WEAPONS[wi]
        reloading = self.reload_t > 0 and wi == self.cur
        if not reloading: scr.blit(self.ammo_font.render(f"{a['mag']} / {a['res']}", True, (255, 216, 102)), (W - 210, H - 60))
        else: scr.blit(f.render("RELOADING...", True, (255, 216, 102)), (W - 190, H - 48))
        scr.blit(f.render(f"[{wi + 1}] {w['n']}", True, (245, 245, 245)), (W - 215, H - 100))
        scr.blit(f.render(f"WAVE {self.wave}   KILLS {self.kills}   SCORE {self.score}", True, (230, 240, 255)), (26, 22))
        if not self.enemies and not self.dead: scr.blit(f.render(f"Next wave in {max(0, self.wave_t):.1f}s", True, (120, 255, 155)), (W // 2 - 90, 64))
        for i, wp in enumerate(WEAPONS):
            c = (255, 220, 80) if i == wi else (150, 170, 185)
            scr.blit(self.tiny.render(str(i + 1), True, c), (28 + i * 22, H - 62))
        # minimap
        S = 4; ox = W - MW * S - 12
        m = pygame.Surface((MW * S, MH * S), pygame.SRCALPHA); m.fill((0, 0, 0, 150))
        for y in range(MH):
            for x in range(MW):
                if MAP[y][x]: pygame.draw.rect(m, (*WALL_COL[MAP[y][x]], 200), (x * S, y * S, S, S))
        for e in self.enemies: pygame.draw.circle(m, (255, 70, 70), (int(e.x * S), int(e.y * S)), 2)
        pygame.draw.circle(m, (80, 255, 140), (int(self.px * S), int(self.py * S)), 3)
        pygame.draw.line(m, (80, 255, 140), (self.px * S, self.py * S), (self.px * S + math.cos(self.pa) * 10, self.py * S + math.sin(self.pa) * 10))
        scr.blit(m, (ox, 12))
        if self.dead:
            v = pygame.Surface((W, H), pygame.SRCALPHA); v.fill((90, 0, 0, int(170 * smooth(self.dead_t / 1.0)))); scr.blit(v, (0, 0))
            if self.dead_t > .6:
                t = self.big.render("YOU DIED", True, (255, 255, 255)); scr.blit(t, (W // 2 - t.get_width() // 2, H // 2 - 70))
                t = f.render(f"Score {self.score}  Wave {self.wave}   -   press R to restart", True, (255, 255, 255)); scr.blit(t, (W // 2 - t.get_width() // 2, H // 2 + 10))

def center_text(scr, font, lines, y, col=(255, 255, 255), gap=30):
    for i, l in enumerate(lines):
        shadow = font.render(l, True, (8, 12, 18))
        scr.blit(shadow, (W // 2 - shadow.get_width() // 2 + 3, y + i * gap + 3))
        t = font.render(l, True, col); scr.blit(t, (W // 2 - t.get_width() // 2, y + i * gap))

def main():
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption("IRON STORM // CYBER FRONTIER")
    canvas = pygame.Surface((W, H))            # the game always renders here at W x H
    fs = False

    def set_display(full):
        if full: return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)     # native desktop resolution
        return pygame.display.set_mode((W, H), pygame.RESIZABLE)
    set_display(False)

    def present():
        """Scale the canvas to the window / screen (keeps aspect ratio, black bars)."""
        win = pygame.display.get_surface(); ww, wh = win.get_size()
        if (ww, wh) == (W, H): win.blit(canvas, (0, 0))
        else:
            k = min(ww / W, wh / H); nw, nh = max(1, int(W * k)), max(1, int(H * k))
            win.fill((0, 0, 0)); win.blit(pygame.transform.scale(canvas, (nw, nh)), ((ww - nw) // 2, (wh - nh) // 2))
        pygame.display.flip()

    clock = pygame.time.Clock(); g = Game(canvas)
    state = "menu"
    def grab(on): pygame.event.set_grab(on); pygame.mouse.set_visible(not on)
    while True:
        dt = clock.tick(60) / 1000
        press = False
        for e in pygame.event.get():
            if e.type == pygame.QUIT: pygame.quit(); return
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if state == "play": state = "pause"; grab(False)
                    else: pygame.quit(); return
                elif e.key in (pygame.K_F11, pygame.K_f) or (e.key == pygame.K_RETURN and e.mod & pygame.KMOD_ALT):
                    fs = not fs; set_display(fs)
                    if state == "play": grab(True); pygame.mouse.get_rel()
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE) and state in ("menu", "pause"): state = "play"; grab(True); pygame.mouse.get_rel()
                elif e.key == pygame.K_r:
                    if g.dead: g.reset()
                elif e.key == pygame.K_e: g.switch(g.want + 1)
                elif e.key == pygame.K_q: g.switch(g.want - 1)
                else:
                    keys = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9, pygame.K_0, pygame.K_MINUS, pygame.K_EQUALS]
                    if e.key in keys: g.switch(keys.index(e.key))
            if e.type == pygame.MOUSEBUTTONDOWN:
                if state != "play": state = "play"; grab(True); pygame.mouse.get_rel()
                elif e.button == 1: press = True
                elif e.button == 4: g.switch(g.want - 1)
                elif e.button == 5: g.switch(g.want + 1)
        if state == "play":
            k = pygame.key.get_pressed(); mx, my = pygame.mouse.get_rel()
            inp = dict(fwd=(k[pygame.K_w] or k[pygame.K_UP]) - (k[pygame.K_s] or k[pygame.K_DOWN]),
                       strafe=k[pygame.K_d] - k[pygame.K_a], sprint=k[pygame.K_LSHIFT], turn=mx * .0025 + (k[pygame.K_RIGHT] - k[pygame.K_LEFT]) * 2.2 * dt,
                       look=-my * 1.8 + (k[pygame.K_PAGEUP] - k[pygame.K_PAGEDOWN]) * 420 * dt, recenter=k[pygame.K_HOME],
                       fire=pygame.mouse.get_pressed()[0], fire_press=press, reload=k[pygame.K_r] and not g.dead)
            g.update(dt, inp)
        g.render()
        if state == "menu":
            v = pygame.Surface((W, H), pygame.SRCALPHA); v.fill((7, 12, 18, 190)); canvas.blit(v, (0, 0))
            panel = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.rect(panel, (18, 26, 38, 180), (140, 92, W - 280, 330), border_radius=28)
            pygame.draw.rect(panel, (76, 206, 255, 120), (140, 92, W - 280, 330), 2, border_radius=28)
            canvas.blit(panel, (0, 0))
            title_glow = g.big.render("IRON STORM", True, (90, 210, 255)); title_glow.set_alpha(80)
            canvas.blit(title_glow, (W // 2 - title_glow.get_width() // 2 + 4, 120 + 4))
            center_text(canvas, g.big, ["IRON STORM"], 116, (245, 250, 255))
            center_text(canvas, g.font, ["WASD move   Mouse aim (up/down = look up/down)   Click fire   Shift sprint",
                                         "PgUp / PgDn look up / down   Home re-center view   F or F11 fullscreen",
                                         "R reload   1-9,0,-,= / Q,E / wheel : switch weapon (12 guns)",
                                         "Survive endless waves. Boss every 5th wave.", "", "Click or press ENTER to start   (ESC quit)"], 255)
        elif state == "pause":
            v = pygame.Surface((W, H), pygame.SRCALPHA); v.fill((7, 12, 18, 170)); canvas.blit(v, (0, 0))
            panel = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.rect(panel, (18, 26, 38, 180), (200, 180, W - 400, 170), border_radius=24)
            pygame.draw.rect(panel, (120, 255, 180, 120), (200, 180, W - 400, 170), 2, border_radius=24)
            canvas.blit(panel, (0, 0))
            center_text(canvas, g.big, ["PAUSED"], 220, (240, 250, 255)); center_text(canvas, g.font, ["Click / ENTER to resume   F fullscreen   ESC to quit"], 310, (210, 230, 255))
        present()

if __name__ == "__main__":
    main()