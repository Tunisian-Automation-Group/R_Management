"""The nine category objects (VD-13): layered SVGs in one isometric camera.

One camera (30°), one key light from the top left (135°, the glass rim's),
the brand palette only and one crimson detail per object. Each face is a
diagonal gradient of its material, lit side to shaded side, with a lit rim on
the edges that face the light. Run: python3 scripts/make-objects.py
"""
import math
import os

OUT = os.path.join(os.path.dirname(__file__), '..', 'public', 'objects')

# (top, lit side, shaded side) per material.
MAT = {
    'paper': ('#fdfcf8', '#ebe9e1', '#c9c6ba'),
    'green': ('#56794f', '#34522f', '#1d2d1b'),
    'ink': ('#586058', '#2d332d', '#141814'),
    'metal': ('#f2f4f2', '#c5cbc6', '#858d88'),
    'ice': ('#f1f7f8', '#cfe0e3', '#9db8be'),
    'crimson': ('#e4506a', '#b0182e', '#760d1d'),
    'clay': ('#eddfc2', '#d6c29c', '#aa9572'),
}
C30, S30 = math.cos(math.pi / 6), 0.5


def P(x, y, z):
    return ((x - y) * C30, (x + y) * S30 - z)


class Obj:
    def __init__(self):
        self.parts, self.pts, self.grads = [], [], {}

    def grad(self, mat, face):
        key = f'{mat}{face}'
        if key not in self.grads:
            t, l, r = MAT[mat]
            a, b = {'t': (t, l), 'l': (t, l), 'r': (l, r), 'c': (t, r)}[face]
            self.grads[key] = f'<linearGradient id="{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>'
        return f'url(#{key})'

    def poly(self, pts3, mat, face):
        pts = [P(*p) for p in pts3]
        self.pts += pts
        d = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
        fill = self.grad(mat, face)
        self.parts.append(f'<polygon points="{d}" fill="{fill}" stroke="{fill}" stroke-width="1.2" stroke-linejoin="round"/>')

    def rim(self, pts3, op=0.7):
        d = ' '.join('%.1f,%.1f' % P(*p) for p in pts3)
        self.parts.append(f'<polyline points="{d}" fill="none" stroke="#fff" stroke-opacity="{op}" stroke-width=".8" stroke-linecap="round" stroke-linejoin="round"/>')

    def box(self, x, y, z, w, d, h, mat):
        x1, y1, z1 = x + w, y + d, z + h
        self.poly([(x, y1, z1), (x1, y1, z1), (x1, y1, z), (x, y1, z)], mat, 'l')
        self.poly([(x1, y, z1), (x1, y1, z1), (x1, y1, z), (x1, y, z)], mat, 'r')
        self.poly([(x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1)], mat, 't')
        self.rim([(x, y1, z), (x, y1, z1), (x, y, z1), (x1, y, z1)])

    def ring(self, c, axis, r, n=28):
        cx, cy, cz = c
        out = []
        for i in range(n):
            a, b = r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)
            out.append({'x': (cx, cy + a, cz + b), 'y': (cx + a, cy, cz + b), 'z': (cx + a, cy + b, cz)}[axis])
        return out

    def disc(self, c, axis, r, mat, face='t'):
        self.poly(self.ring(c, axis, r), mat, face)

    def cyl(self, c, axis, r, length, mat, cap=None):
        """A cylinder from c along +axis; the near cap (or the top) is drawn."""
        e = {'x': (length, 0, 0), 'y': (0, length, 0), 'z': (0, 0, length)}[axis]
        c2 = (c[0] + e[0], c[1] + e[1], c[2] + e[2])
        a, b = self.ring(c, axis, r), self.ring(c2, axis, r)
        hull = convex_hull([P(*p) for p in a + b])
        self.pts += hull
        fill = self.grad(mat, 'c')
        d = ' '.join(f'{x:.1f},{y:.1f}' for x, y in hull)
        self.parts.append(f'<polygon points="{d}" fill="{fill}"/>')
        self.disc(c2, axis, r, cap or mat, 't')

    def line(self, a, b, mat, w):
        (x1, y1), (x2, y2) = P(*a), P(*b)
        self.pts += [(x1, y1), (x2, y2)]
        t, l, r = MAT[mat]
        self.parts.append(f'<path d="M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}" stroke="{r}" stroke-width="{w}" stroke-linecap="round"/>')
        self.parts.append(f'<path d="M{x1 - .5:.1f} {y1:.1f}L{x2 - .5:.1f} {y2:.1f}" stroke="{t}" stroke-width="{w * .4:.1f}" stroke-linecap="round"/>')

    def svg(self, footprint):
        fx, fy = P(0, 0, 0)
        # The shadow belongs to the frame too, or it is cut off at the bottom.
        self.pts += [(fx + 3 - footprint * 1.25, fy + 2 + footprint * .5), (fx + 3 + footprint * 1.25, fy + 2 + footprint * .5)]
        xs, ys = [p[0] for p in self.pts], [p[1] for p in self.pts]
        side = max(max(xs) - min(xs), max(ys) - min(ys)) + 4
        cx, bottom = (max(xs) + min(xs)) / 2, max(ys)
        vx, vy = cx - side / 2, bottom + 2 - side
        # The contact shadow under the footprint, soft and a little to the right (light from the left).
        shadow = (f'<radialGradient id="sh"><stop offset="0" stop-color="#101810" stop-opacity=".32"/>'
                  f'<stop offset="1" stop-color="#101810" stop-opacity="0"/></radialGradient>')
        ell = f'<ellipse cx="{fx + 3:.1f}" cy="{fy + 2:.1f}" rx="{footprint * 1.25:.1f}" ry="{footprint * .5:.1f}" fill="url(#sh)"/>'
        defs = shadow + ''.join(self.grads.values())
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.1f} {vy:.1f} {side:.1f} {side:.1f}" width="96" height="96">'
                f'<defs>{defs}</defs>{ell}{"".join(self.parts)}</svg>')


def convex_hull(pts):
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def fabrication():
    o = Obj()
    o.box(-22, -16, 0, 44, 32, 6, 'metal')
    o.box(-7, -16, 6, 14, 12, 46, 'green')
    o.box(-6, -1, 6, 12, 10, 7, 'ice')
    o.cyl((0, 4, 13), 'z', 1.4, 7, 'ink')
    o.cyl((0, 4, 20), 'z', 4, 10, 'metal')
    o.cyl((0, 4, 28), 'z', 5.5, 3, 'crimson')
    o.box(-9, -8, 31, 18, 20, 14, 'green')
    return o, 26


def additive():
    o = Obj()
    o.box(-20, -20, 0, 40, 40, 7, 'paper')
    for x, y in ((-20, -20), (16, -20), (-20, 16)):
        o.box(x, y, 7, 4, 4, 36, 'ink')
    o.cyl((0, 0, 7), 'z', 8, 5, 'ice')
    o.cyl((0, 0, 12), 'z', 6, 5, 'ice')
    o.cyl((0, 0, 17), 'z', 7, 4, 'ice')
    o.box(-18, -2, 36, 36, 4, 3, 'metal')
    o.box(-3, -4, 27, 6, 6, 9, 'crimson')
    o.box(16, 16, 7, 4, 4, 36, 'ink')
    o.box(-20, -20, 43, 40, 40, 5, 'paper')
    return o, 28


def finishing():
    o = Obj()
    o.box(-14, -3, 2, 8, 7, 26, 'ink')
    o.box(-4, -2, 16, 3, 5, 9, 'metal')
    o.cyl((-16, 0, 30), 'x', 5, 32, 'metal')
    o.cyl((16, 0, 30), 'x', 3, 7, 'crimson')
    o.cyl((2, 0, 35), 'z', 9, 16, 'paper')
    o.cyl((2, 0, 51), 'z', 4, 3, 'metal')
    return o, 20


def print_():
    o = Obj()
    o.box(-20, 2, 0, 32, 30, 1, 'paper')
    o.box(-14, 16, 1, 20, 3, .5, 'crimson')
    o.box(-14, 22, 1, 12, 2, .5, 'ink')
    o.cyl((-20, 0, 13), 'x', 13, 32, 'ice', cap='paper')
    o.disc((12, 0, 13), 'x', 4, 'green', 'l')
    return o, 26


def freight():
    o = Obj()
    o.box(-26, -12, 6, 36, 24, 26, 'paper')
    o.box(10, -12, 6, 15, 24, 18, 'paper')
    o.poly([(25, -9, 22), (25, 9, 22), (25, 9, 15), (25, -9, 15)], 'ice', 'r')
    o.poly([(12, 12, 22), (22, 12, 22), (22, 12, 15), (12, 12, 15)], 'ice', 'l')
    o.poly([(-24, 12, 15), (8, 12, 15), (8, 12, 12), (-24, 12, 12)], 'crimson', 'l')
    for x in (-16, 16):
        o.cyl((x, 11, 6), 'y', 6, 3, 'ink', cap='metal')
    return o, 30


def warehousing():
    o = Obj()
    for x in (-24, -3, 18):
        o.box(x, 20, 0, 6, 4, 4, 'clay')
    for y in (-24, -3):
        o.box(20, y, 0, 4, 6, 4, 'clay')
    o.box(-24, -24, 4, 48, 48, 3, 'clay')
    o.box(-20, -20, 7, 22, 22, 18, 'clay')
    o.box(4, -18, 7, 17, 17, 13, 'paper')
    o.box(-8, 4, 7, 18, 16, 11, 'clay')
    o.box(-17, -16, 25, 16, 16, 12, 'clay')
    o.poly([(-10.5, -16, 37.1), (-7.5, -16, 37.1), (-7.5, 0, 37.1), (-10.5, 0, 37.1)], 'crimson', 't')
    return o, 32


def workshop():
    o = Obj()
    o.box(-26, -11, 0, 50, 22, 3, 'metal')
    o.cyl((-4, -6, 15), 'y', 13, 9, 'metal', cap='metal')
    o.disc((-4, 3, 15), 'y', 4, 'ink', 'l')
    o.cyl((4, -4, 20), 'x', 7, 13, 'green')
    o.box(-10, -3, 30, 20, 6, 5, 'ink')
    o.box(2, -2, 26, 4, 4, 4, 'crimson')
    return o, 30


def events():
    o = Obj()
    o.box(-15, -14, 0, 30, 28, 56, 'ink')
    o.disc((0, 14, 20), 'y', 11, 'metal', 'l')
    o.disc((0, 14.3, 20), 'y', 8.5, 'ink', 'r')
    o.disc((0, 14.6, 20), 'y', 3.5, 'ice', 'l')
    o.disc((0, 14, 42), 'y', 6, 'metal', 'l')
    o.disc((0, 14.3, 42), 'y', 4, 'ink', 'r')
    o.disc((0, 14.6, 42), 'y', 1.8, 'ice', 'l')
    o.disc((10, 14.3, 52), 'y', 1.3, 'crimson', 'l')
    return o, 22


def creator():
    o = Obj()
    o.line((0, 0, 34), (0, -16, 0), 'metal', 2.6)
    o.line((0, 0, 34), (-15, 10, 0), 'metal', 2.6)
    o.line((0, 0, 34), (15, 8, 0), 'metal', 2.6)
    o.box(-3, -3, 30, 6, 6, 5, 'ink')
    o.box(-14, -8, 35, 28, 14, 18, 'ink')
    o.box(-5, -6, 53, 11, 10, 5, 'ink')
    o.poly([(8, -3, 53.1), (11, -3, 53.1), (11, 0, 53.1), (8, 0, 53.1)], 'crimson', 't')
    o.cyl((0, 6, 44), 'y', 7.5, 9, 'ink', cap='metal')
    o.disc((0, 15.2, 44), 'y', 5.2, 'ice', 'l')
    return o, 20


OBJECTS = {
    'fabrication': fabrication, 'additive': additive, 'finishing': finishing, 'print': print_,
    'freight': freight, 'warehousing': warehousing, 'workshop': workshop, 'events': events, 'creator': creator,
}

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for name, make in OBJECTS.items():
        o, foot = make()
        svg = o.svg(foot)
        assert len(svg) <= 12_000, (name, len(svg))
        with open(os.path.join(OUT, f'{name}.svg'), 'w') as f:
            f.write(svg)
        print(f'{name}: {len(svg)} bytes')
