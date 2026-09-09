#!/usr/bin/env python3
"""CS 418 Rasterizer MP — software WebGL-style triangle rasterizer."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image


# Attribute vector layout: [x, y, z, w, r, g, b, a, s, t]
X, Y, Z, W, R, G, B, A, S, T = range(10)
NATTR = 10


def vec_add(a, b):
    return [a[i] + b[i] for i in range(len(a))]


def vec_sub(a, b):
    return [a[i] - b[i] for i in range(len(a))]


def vec_scale(a, s):
    return [a[i] * s for i in range(len(a))]


def vec_div_scalar(a, s):
    return [a[i] / s for i in range(len(a))]


def lerp_vec(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]


def clamp01(v):
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def linear_to_srgb(c):
    c = clamp01(c)
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def srgb_to_linear(c):
    c = clamp01(c)
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def to_byte(c):
    # Truncate toward zero after scaling; matches course reference PNGs.
    return int(clamp01(c) * 255.0)


# ---------------------------------------------------------------------------
# DDA / scanline
# ---------------------------------------------------------------------------

def dda_setup(a, b, d):
    """DDA steps 1–7. Returns (p, s) or None if no points."""
    a = list(a)
    b = list(b)
    if a[d] == b[d]:
        return None
    if a[d] > b[d]:
        a, b = b, a
    delta = vec_sub(b, a)
    s = vec_div_scalar(delta, delta[d])
    e = math.ceil(a[d]) - a[d]
    o = vec_scale(s, e)
    p = vec_add(a, o)
    return p, s, b


def dda_points(a, b, d):
    setup = dda_setup(a, b, d)
    if setup is None:
        return
    p, s, bend = setup
    while p[d] < bend[d]:
        yield list(p)
        p = vec_add(p, s)


def scanline_triangle(p0, p1, p2, plot):
    pts = [list(p0), list(p1), list(p2)]
    pts.sort(key=lambda v: v[Y])
    top, mid, bot = pts[0], pts[1], pts[2]

    long_setup = dda_setup(top, bot, Y)
    if long_setup is None:
        return
    p_long, s_long, _ = long_setup

    # Top half: top -> mid vs long edge
    short_setup = dda_setup(top, mid, Y)
    if short_setup is not None:
        p, s, _ = short_setup
        while p[Y] < mid[Y]:
            for pix in dda_points(p, p_long, X):
                plot(pix)
            p = vec_add(p, s)
            p_long = vec_add(p_long, s_long)

    # Bottom half: mid -> bot vs long edge
    short_setup = dda_setup(mid, bot, Y)
    if short_setup is not None:
        p, s, _ = short_setup
        while p[Y] < bot[Y]:
            for pix in dda_points(p, p_long, X):
                plot(pix)
            p = vec_add(p, s)
            p_long = vec_add(p_long, s_long)


# ---------------------------------------------------------------------------
# Frustum clipping (Sutherland–Hodgman in homogeneous clip space)
# ---------------------------------------------------------------------------

# Plane coefficients (A, B, C, D) for A*x + B*y + C*z + D*w >= 0
CLIP_PLANES = [
    (1.0, 0.0, 0.0, 1.0),   #  x + w >= 0
    (-1.0, 0.0, 0.0, 1.0),  # -x + w >= 0
    (0.0, 1.0, 0.0, 1.0),   #  y + w >= 0
    (0.0, -1.0, 0.0, 1.0),  # -y + w >= 0
    (0.0, 0.0, 1.0, 1.0),   #  z + w >= 0
    (0.0, 0.0, -1.0, 1.0),  # -z + w >= 0
]


def plane_dist(plane, v):
    A, B, C, D = plane
    return A * v[X] + B * v[Y] + C * v[Z] + D * v[W]


def clip_triangle_one_plane(v0, v1, v2, plane):
    """Clip one triangle against one plane → 0, 1, or 2 triangles."""
    verts = [list(v0), list(v1), list(v2)]
    dists = [plane_dist(plane, v) for v in verts]
    inside = [d >= 0.0 for d in dists]
    n_out = 3 - sum(inside)
    if n_out == 3:
        return []
    if n_out == 0:
        return [(verts[0], verts[1], verts[2])]

    def intersect(i, j):
        di, dj = dists[i], dists[j]
        t = di / (di - dj)
        return lerp_vec(verts[i], verts[j], t)

    if n_out == 2:
        # one inside → one triangle
        i_in = inside.index(True)
        i_out = [i for i in range(3) if not inside[i]]
        a = verts[i_in]
        b = intersect(i_in, i_out[0])
        c = intersect(i_in, i_out[1])
        return [(a, b, c)]

    # n_out == 1: two inside → two triangles
    i_out = inside.index(False)
    i_in = [i for i in range(3) if inside[i]]
    p = intersect(i_in[0], i_out)
    q = intersect(i_in[1], i_out)
    a, b = verts[i_in[0]], verts[i_in[1]]
    # Shared edge between an inside vertex and a clip vertex; keep winding
    return [(a, b, p), (b, q, p)]


def clip_triangle(v0, v1, v2):
    tris = [(list(v0), list(v1), list(v2))]
    for plane in CLIP_PLANES:
        new_tris = []
        for a, b, c in tris:
            new_tris.extend(clip_triangle_one_plane(a, b, c, plane))
        tris = new_tris
        if not tris:
            return []
    return tris


# ---------------------------------------------------------------------------
# Rasterizer state / pipeline
# ---------------------------------------------------------------------------

class Rasterizer:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.filename = "out.png"
        self.fb_w = 0
        self.fb_h = 0

        self.depth_on = False
        self.srgb_on = False
        self.hyp_on = False
        self.cull_on = False
        self.frustum_on = False
        self.decals_on = False
        self.fsaa = 1

        self.positions = []
        self.colors = []
        self.texcoords = []
        self.pointsizes = []
        self.elements = []

        self.matrix = None
        self.texture = None  # (w, h, pixels RGBA linear floats)

        self.framebuffer = None  # list of [r,g,b,a] floats
        self.depthbuffer = None

    def init_buffers(self):
        n = self.fb_w * self.fb_h
        self.framebuffer = [[0.0, 0.0, 0.0, 0.0] for _ in range(n)]
        self.depthbuffer = [float("inf")] * n

    def idx(self, x, y):
        return y * self.fb_w + x

    def load_texture(self, path):
        img = Image.open(path).convert("RGBA")
        tw, th = img.size
        pixels = []
        for ty in range(th):
            row = []
            for tx in range(tw):
                r, g, b, a = img.getpixel((tx, ty))
                row.append(
                    [
                        srgb_to_linear(r / 255.0),
                        srgb_to_linear(g / 255.0),
                        srgb_to_linear(b / 255.0),
                        a / 255.0,
                    ]
                )
            pixels.append(row)
        self.texture = (tw, th, pixels)

    def sample_texture(self, s, t):
        tw, th, pixels = self.texture
        s = s - math.floor(s)
        t = t - math.floor(t)
        # Round-to-nearest texel; matches course references better than floor.
        tx = int(math.floor(s * tw + 0.5)) % tw
        ty = int(math.floor(t * th + 0.5)) % th
        return pixels[ty][tx]

    def get_vertex(self, i):
        if i < len(self.positions):
            x, y, z, w = self.positions[i]
        else:
            x, y, z, w = 0.0, 0.0, 0.0, 1.0
        if i < len(self.colors):
            r, g, b, a = self.colors[i]
        else:
            r, g, b, a = 0.0, 0.0, 0.0, 1.0
        if i < len(self.texcoords):
            s, t = self.texcoords[i]
        else:
            s, t = 0.0, 0.0
        v = [x, y, z, w, r, g, b, a, s, t]
        if self.matrix is not None:
            m = self.matrix
            x0, y0, z0, w0 = v[X], v[Y], v[Z], v[W]
            v[X] = m[0] * x0 + m[4] * y0 + m[8] * z0 + m[12] * w0
            v[Y] = m[1] * x0 + m[5] * y0 + m[9] * z0 + m[13] * w0
            v[Z] = m[2] * x0 + m[6] * y0 + m[10] * z0 + m[14] * w0
            v[W] = m[3] * x0 + m[7] * y0 + m[11] * z0 + m[15] * w0
        return v

    def project_vertex(self, v):
        """Perspective divide + viewport. Mutates a copy."""
        out = list(v)
        w = out[W]
        if self.hyp_on:
            inv_w = 1.0 / w
            out[X] = out[X] * inv_w
            out[Y] = out[Y] * inv_w
            out[Z] = out[Z] * inv_w
            out[W] = inv_w
            out[R] = out[R] * inv_w
            out[G] = out[G] * inv_w
            out[B] = out[B] * inv_w
            out[A] = out[A] * inv_w
            out[S] = out[S] * inv_w
            out[T] = out[T] * inv_w
        else:
            inv_w = 1.0 / w
            out[X] = out[X] * inv_w
            out[Y] = out[Y] * inv_w
            out[Z] = out[Z] * inv_w
            # leave W and attributes alone
        out[X] = (out[X] + 1.0) * 0.5 * self.fb_w
        out[Y] = (out[Y] + 1.0) * 0.5 * self.fb_h
        return out

    def is_front_facing(self, a, b, c):
        # Screen-space cross; keep visual CCW (negative with y-down).
        cross = (b[X] - a[X]) * (c[Y] - a[Y]) - (c[X] - a[X]) * (b[Y] - a[Y])
        return cross < 0.0

    def write_pixel(self, x, y, r, g, b, a, z):
        if x < 0 or y < 0 or x >= self.fb_w or y >= self.fb_h:
            return
        i = self.idx(x, y)
        if self.depth_on:
            if z >= self.depthbuffer[i]:
                return
            self.depthbuffer[i] = z

        dst = self.framebuffer[i]
        if a >= 1.0 - 1e-12:
            self.framebuffer[i] = [r, g, b, a]
            return
        if a <= 1e-12:
            return

        # Non-premultiplied "over" (not premultiplied SRC_ALPHA blend)
        rd, gd, bd, ad = dst
        out_a = a + ad * (1.0 - a)
        if out_a <= 1e-12:
            self.framebuffer[i] = [0.0, 0.0, 0.0, 0.0]
            return
        out_r = (a * r + ad * (1.0 - a) * rd) / out_a
        out_g = (a * g + ad * (1.0 - a) * gd) / out_a
        out_b = (a * b + ad * (1.0 - a) * bd) / out_a
        self.framebuffer[i] = [out_r, out_g, out_b, out_a]

    def shade_fragment(self, pix):
        z = pix[Z]
        if self.hyp_on:
            inv_w = pix[W]
            if abs(inv_w) < 1e-30:
                return
            r = pix[R] / inv_w
            g = pix[G] / inv_w
            b = pix[B] / inv_w
            a = pix[A] / inv_w
            s = pix[S] / inv_w
            t = pix[T] / inv_w
        else:
            r, g, b, a = pix[R], pix[G], pix[B], pix[A]
            s, t = pix[S], pix[T]

        if self.texture is not None:
            tr, tg, tb, ta = self.sample_texture(s, t)
            if self.decals_on:
                # tex over vertex color (from fragment shader in assignment)
                out_r = tr * ta + r * (1.0 - ta)
                out_g = tg * ta + g * (1.0 - ta)
                out_b = tb * ta + b * (1.0 - ta)
                out_a = ta + a - ta * a
                r, g, b, a = out_r, out_g, out_b, out_a
            else:
                r, g, b, a = tr, tg, tb, ta

        x = int(math.floor(pix[X] + 1e-9))
        y = int(math.floor(pix[Y] + 1e-9))
        self.write_pixel(x, y, r, g, b, a, z)

    def draw_triangle_raw(self, v0, v1, v2):
        """v* are clip-space attribute vectors (pre-divide)."""
        tris = [(v0, v1, v2)]
        if self.frustum_on:
            tris = []
            for tri in clip_triangle(v0, v1, v2):
                tris.append(tri)

        for a, b, c in tris:
            pa = self.project_vertex(a)
            pb = self.project_vertex(b)
            pc = self.project_vertex(c)
            if self.cull_on and not self.is_front_facing(pa, pb, pc):
                continue
            scanline_triangle(pa, pb, pc, self.shade_fragment)

    def draw_arrays_triangles(self, first, count):
        for i in range(first, first + count, 3):
            v0 = self.get_vertex(i)
            v1 = self.get_vertex(i + 1)
            v2 = self.get_vertex(i + 2)
            self.draw_triangle_raw(v0, v1, v2)

    def draw_elements_triangles(self, count, offset):
        for i in range(offset, offset + count, 3):
            v0 = self.get_vertex(self.elements[i])
            v1 = self.get_vertex(self.elements[i + 1])
            v2 = self.get_vertex(self.elements[i + 2])
            self.draw_triangle_raw(v0, v1, v2)

    def draw_arrays_points(self, first, count):
        for i in range(first, first + count):
            v = self.get_vertex(i)
            # Project center
            w = v[W]
            inv_w = 1.0 / w
            cx = (v[X] * inv_w + 1.0) * 0.5 * self.fb_w
            cy = (v[Y] * inv_w + 1.0) * 0.5 * self.fb_h
            cz = v[Z] * inv_w
            if i < len(self.pointsizes):
                diameter = self.pointsizes[i][0]
            else:
                diameter = 1.0
            # Point size is in output pixels; scale by fsaa
            diameter_fb = diameter * self.fsaa
            half = diameter_fb * 0.5
            # Inclusive pixel range for a square centered at (cx, cy)
            x0 = int(math.ceil(cx - half))
            x1 = int(math.floor(cx + half - 1e-12))
            y0 = int(math.ceil(cy - half))
            y1 = int(math.floor(cy + half - 1e-12))
            for py in range(y0, y1 + 1):
                for px in range(x0, x1 + 1):
                    # PointCoord: (0,0) top-left to (1,1) bottom-right
                    if diameter_fb <= 0:
                        continue
                    s = (px + 0.5 - (cx - half)) / diameter_fb
                    t = (py + 0.5 - (cy - half)) / diameter_fb
                    pix = [float(px), float(py), cz, 1.0, v[R], v[G], v[B], v[A], s, t]
                    if self.hyp_on:
                        # already in post-divide attribute space for a point
                        pass
                    # shade_fragment expects hyp-divided attrs if hyp_on; for points
                    # colors are not divided — temporarily disable hyp path
                    saved = self.hyp_on
                    self.hyp_on = False
                    if self.texture is not None:
                        # use point texcoords
                        tr, tg, tb, ta = self.sample_texture(s, t)
                        if self.decals_on:
                            r, g, b, a = v[R], v[G], v[B], v[A]
                            out_r = tr * ta + r * (1.0 - ta)
                            out_g = tg * ta + g * (1.0 - ta)
                            out_b = tb * ta + b * (1.0 - ta)
                            out_a = ta + a - ta * a
                            self.write_pixel(px, py, out_r, out_g, out_b, out_a, cz)
                        else:
                            self.write_pixel(px, py, tr, tg, tb, ta, cz)
                    else:
                        self.write_pixel(px, py, v[R], v[G], v[B], v[A], cz)
                    self.hyp_on = saved

    def save_png(self):
        level = self.fsaa
        out_w, out_h = self.width, self.height
        img = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        px = img.load()
        for y in range(out_h):
            for x in range(out_w):
                if level == 1:
                    r, g, b, a = self.framebuffer[self.idx(x, y)]
                else:
                    # Resolve in premultiplied space so partial coverage
                    # keeps full chroma (matches reference FSAA borders).
                    acc_r = acc_g = acc_b = acc_a = 0.0
                    n = float(level * level)
                    for sy in range(level):
                        for sx in range(level):
                            fr, fg, fb, fa = self.framebuffer[
                                self.idx(x * level + sx, y * level + sy)
                            ]
                            acc_r += fr * fa
                            acc_g += fg * fa
                            acc_b += fb * fa
                            acc_a += fa
                    a = acc_a / n
                    if acc_a > 1e-12:
                        r = acc_r / acc_a
                        g = acc_g / acc_a
                        b = acc_b / acc_a
                    else:
                        r = g = b = 0.0

                if self.srgb_on:
                    br = to_byte(linear_to_srgb(r))
                    bg = to_byte(linear_to_srgb(g))
                    bb = to_byte(linear_to_srgb(b))
                else:
                    br = to_byte(r)
                    bg = to_byte(g)
                    bb = to_byte(b)
                ba = to_byte(a)
                px[x, y] = (br, bg, bb, ba)
        img.save(self.filename)

    def parse_attr_buffer(self, size, nums, kind):
        verts = []
        for i in range(0, len(nums), size):
            chunk = nums[i : i + size]
            if kind == "position":
                if size == 2:
                    verts.append([chunk[0], chunk[1], 0.0, 1.0])
                elif size == 3:
                    verts.append([chunk[0], chunk[1], chunk[2], 1.0])
                else:
                    verts.append([chunk[0], chunk[1], chunk[2], chunk[3]])
            elif kind == "color":
                if size == 3:
                    verts.append([chunk[0], chunk[1], chunk[2], 1.0])
                else:
                    verts.append([chunk[0], chunk[1], chunk[2], chunk[3]])
            elif kind == "texcoord":
                verts.append([chunk[0], chunk[1]])
            elif kind == "pointsize":
                verts.append([chunk[0]])
        return verts

    def run(self, path):
        text = Path(path).read_text()
        base_dir = Path(path).resolve().parent
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            kw = parts[0]
            if kw == "png":
                self.width = int(parts[1])
                self.height = int(parts[2])
                self.filename = parts[3]
            elif kw == "depth":
                self.depth_on = True
            elif kw == "sRGB":
                self.srgb_on = True
            elif kw == "hyp":
                self.hyp_on = True
            elif kw == "cull":
                self.cull_on = True
            elif kw == "frustum":
                self.frustum_on = True
            elif kw == "decals":
                self.decals_on = True
            elif kw == "fsaa":
                self.fsaa = int(parts[1])
            elif kw == "texture":
                tex_path = base_dir / parts[1]
                if not tex_path.exists():
                    tex_path = Path(parts[1])
                self.load_texture(tex_path)
            elif kw == "uniformMatrix":
                self.matrix = [float(x) for x in parts[1:17]]
            elif kw == "position":
                size = int(parts[1])
                nums = [float(x) for x in parts[2:]]
                self.positions = self.parse_attr_buffer(size, nums, "position")
            elif kw == "color":
                size = int(parts[1])
                nums = [float(x) for x in parts[2:]]
                self.colors = self.parse_attr_buffer(size, nums, "color")
            elif kw == "texcoord":
                size = int(parts[1])
                nums = [float(x) for x in parts[2:]]
                self.texcoords = self.parse_attr_buffer(size, nums, "texcoord")
            elif kw == "pointsize":
                size = int(parts[1])
                nums = [float(x) for x in parts[2:]]
                self.pointsizes = self.parse_attr_buffer(size, nums, "pointsize")
            elif kw == "elements":
                self.elements = [int(x) for x in parts[1:]]
            elif kw in ("drawArraysTriangles", "drawElementsTriangles", "drawArraysPoints"):
                if self.framebuffer is None:
                    self.fb_w = self.width * self.fsaa
                    self.fb_h = self.height * self.fsaa
                    self.init_buffers()
                if kw == "drawArraysTriangles":
                    self.draw_arrays_triangles(int(parts[1]), int(parts[2]))
                elif kw == "drawElementsTriangles":
                    self.draw_elements_triangles(int(parts[1]), int(parts[2]))
                else:
                    self.draw_arrays_points(int(parts[1]), int(parts[2]))
            else:
                # unknown keyword — ignore
                continue

        if self.framebuffer is None:
            self.fb_w = self.width * self.fsaa
            self.fb_h = self.height * self.fsaa
            self.init_buffers()
        self.save_png()


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} input.txt", file=sys.stderr)
        sys.exit(1)
    Rasterizer().run(sys.argv[1])


if __name__ == "__main__":
    main()
