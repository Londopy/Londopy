#!/usr/bin/env python3
"""Draws the README's header: a topographic survey sheet of Mount Shasta.

Real contours from real elevation, and five real climbing routes to the
summit, one per domain, each drawn in its own line style with two of that
domain's projects as waypoints, each with a live number. Writes:

    assets/header-day.svg     for GitHub's light theme
    assets/header-night.svg   for the dark theme (the README picks with <picture>)

    python3 scripts/make_header.py           # draw, from scripts/shasta.json
    python3 scripts/make_header.py --fetch   # refetch the mountain into scripts/shasta.json

Standard library only. The mountain is fetched once and baked into
scripts/shasta.json, so the nightly run is offline apart from the live
numbers, and draws the same sheet every time unless a number changes.
GitHub shows README images through <img>, which rules out scripts, web fonts
and anything fetched from inside the SVG, so the motion is plain CSS
animation and the text uses system fonts.
"""
import bisect
import json
import math
import os
import re
import struct
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "scripts", "shasta.json")
W, H = 1000, 460
UA = "Londopy-profile-header/1.0 (github.com/Londopy/Londopy)"

# the README's badge colours: amber, moss, brown
AMBER, MOSS, BROWN = "#D97706", "#4A7B3E", "#7A5C3A"
# one colour per route, keyed by domain; the line style tells them apart too
PALETTES = {
    "day": dict(bg="#F4EEE2", line="#B08A5E", line_op=0.45, index_op=0.8, ink="#3B2A1A", soft=BROWN,
                route="#C2410C", chip="#F4EEE2",
                climbing="#C2410C", medicine=MOSS, systems="#3B2A1A", security="#7A5C3A", devtools=AMBER),
    "night": dict(bg="#12100D", line=AMBER, line_op=0.22, index_op=0.5, ink="#EDE3D2", soft="#B9A88F",
                  route="#F59E0B", chip="#12100D",
                  climbing="#F59E0B", medicine="#7FB06D", systems="#EDE3D2", security="#C9A27A", devtools="#FB923C"),
}
SERIF = "Georgia, 'Times New Roman', serif"
MONO = "Consolas, 'DejaVu Sans Mono', Menlo, monospace"

# ---- the mountain and the sheet's layout --------------------------------------------
# The summit sits at ANCHOR on the sheet, MPP metres to the pixel. The
# elevation grid in shasta.json is sampled for exactly this layout, so a
# change here needs a --fetch.
ANCHOR = (600, 150)
MPP = 30.0
COLS, ROWS = 160, 74
MAP = (12, 12, W - 12, H - 70)  # the area the routes draw in, above the band
SUMMIT_QUERY = 'node["natural"="volcano"]["name"="Mount Shasta"](41.3,-122.3,41.5,-122.1);'
# Each route's OpenStreetMap ways, trailhead first. Where OSM has a gap, the
# line runs straight across it, as the real route does: Casaval Ridge from
# Horse Camp to the ridge's foot and from its top to the summit; Green Butte
# from the top of its trail to Red Banks (about 13,200 ft), where it joins
# Avalanche Gulch. Joins run after every route is built, so order doesn't matter.
OSM_ROUTES = {
    "avalanche-gulch": dict(ways=[1413370501, 129818705, 613529174]),
    "casaval-ridge": dict(ways=[1413370500, 1242086443, 613539274]),
    "clear-creek": dict(ways=[613529280, 613529273]),
    "green-butte": dict(ways=[613529241], join=("avalanche-gulch", 1.2)),
    "hotlum-bolam": dict(ways=[36870563, 36870564]),
}
TERRAIN_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TILE_ZOOM = 13  # about 14 m a pixel here, finer than the 30 m sheet

# The routes, in the order they draw: a domain, the real route it climbs, a
# line style, and two waypoints. A waypoint is (project, its number: a
# badges/ file for monthly downloads or None for stars, how far down the
# route's visible length from the summit, 0 to 1, and which label column it
# goes in: -1 left of the mountain, 1 right).
ROUTES = [
    dict(id="climbing", route="casaval-ridge", name="Casaval Ridge", style="solid",
         wps=[("whumpf", None, 0.35, -1), ("ropesim", "ropesim", 0.75, -1)]),
    dict(id="medicine", route="clear-creek", name="Clear Creek", style="dashed",
         wps=[("DiresQ", None, 0.4, 1), ("drugdose", "drugdose", 0.75, 1)]),
    dict(id="systems", route="green-butte", name="Green Butte", style="cased",
         wps=[("HideDesktopApps", "hide-desktop-apps", 0.4, 1), ("capture-bypass", None, 0.8, 1)]),
    dict(id="security", route="hotlum-bolam", name="Hotlum-Bolam", style="dotted",
         wps=[("nxtls", None, 0.45, 1), ("deadpoint", "deadpoint", 0.75, 1)]),
    dict(id="devtools", route="avalanche-gulch", name="Avalanche Gulch", style="dashdot",
         wps=[("nexium", None, 0.4, -1), ("patchnotes", "patchnotes", 0.8, -1)]),
]
# The label columns: the left one's right edge and the right one's left edge,
# clear of every route, and how high each may start (the left one below the
# title block). Labels stack down each column in order, 21 px apart.
COLUMNS = {-1: dict(x=470, top=178), 1: dict(x=810, top=24)}
# The fan: four of the five routes climb Shasta's south side and would run
# side by side, so the terrain is turned about the summit to set each route
# on its own bearing (degrees clockwise from east, as on screen). Only
# bearings change: every point keeps its distance from the summit, so each
# contour ring keeps its true elevation and stays round, and every route
# still runs up its own real gully or ridge. The turn is full inside the
# first radius and fades out by the second, so the sheet's edges are true.
FAN = {"clear-creek": 36, "green-butte": 76, "avalanche-gulch": 101, "casaval-ridge": 126, "hotlum-bolam": 272}
FAN_R = (230, 330)
# boxes the labels must stay clear of: the summit chip (x, y, w, h), the title block
SUMMIT_CHIP = (ANCHOR[0] + 24, ANCHOR[1] - 50, 176, 38)
TITLE = (34, 34, 406, 166)
CHAR = 6.6  # a monospace character at 11px; labels are stretched to exactly this
CYCLE = 18  # seconds: the routes draw one after another, hold, then fade and redraw
CONTOUR_FT = 500  # the contour interval; every fourth is an index contour
# the lines the old typing SVG cycled through, typed out in turn
TAGLINES = ["hey — i'm london", "python + rust / ship a lot",
            "climber · skier · surfer · wfr · sprat", "build because the problem is interesting"]


# ---- live numbers -------------------------------------------------------------------

def get(url, data=None, accept="application/json"):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def get_json(url, data=None):
    return json.loads(get(url, data))


def numbers():
    """Every number the sheet shows. Raises if any source is unreachable."""
    # the site's API has every project's stars, DiresQ's under Skythe7
    # included, in one request; it rebuilds nightly with live counts
    stats = get_json("https://londo.me/api/v1/stats.json")["data"]
    projects = {p.get("name"): p for p in get_json("https://londo.me/api/v1/projects.json")["data"]}
    stars = {name: p.get("stars") for name, p in projects.items()}
    labels = {}
    for route in ROUTES:
        for name, badge, _, _ in route["wps"]:
            # each route is one of the site's domains; say so if a project moves
            cluster = (projects.get(name) or {}).get("cluster") or {}
            if cluster.get("id") != route["id"]:
                print(f"::warning::{name} is in {cluster.get('id')!r} on the site, but on the {route['id']} route here")
            if badge:
                # badges/ is refreshed from pypistats earlier in the same workflow run
                with open(os.path.join(ROOT, "badges", f"{badge}.json"), encoding="utf-8") as f:
                    labels[name] = "↓" + json.load(f)["message"].replace("/month", "/mo")
            else:
                if type(stars.get(name)) is not int:  # not bool, which is an int too
                    raise ValueError(f"no star count for {name} in projects.json")
                labels[name] = f"★{stars[name]}"
    data = {"labels": labels, "projects": stats["projects"], "domains": stats["domains"],
            "stars": stats["stars"]["total"]}
    # a changed API shape should keep the old header, not print "★None" on it
    for key in ("projects", "domains", "stars"):
        if type(data[key]) is not int:
            raise ValueError(f"stats.json {key} is {data[key]!r}, not a number")
    return data


# ---- projection ----------------------------------------------------------------------

def per_degree(lat):
    """Metres in a degree of latitude and of longitude at this latitude, on
    the WGS 84 ellipsoid (the usual series)."""
    r = math.radians(lat)
    return (111132.954 - 559.822 * math.cos(2 * r) + 1.175 * math.cos(4 * r),
            111412.84 * math.cos(r) - 93.5 * math.cos(3 * r))


def to_px(lat, lon, top):
    """Lat/lon to sheet pixels, flat around the summit (fine across 40 km)."""
    my, mx = per_degree(top[0])
    return (ANCHOR[0] + (lon - top[1]) * mx / MPP, ANCHOR[1] - (lat - top[0]) * my / MPP)


def to_ll(x, y, top):
    my, mx = per_degree(top[0])
    return (top[0] - (y - ANCHOR[1]) * MPP / my, top[1] + (x - ANCHOR[0]) * MPP / mx)


# ---- the fan ----------------------------------------------------------------------------

def pchip(xs, ys):
    """A smooth curve through rising points that never turns back
    (Fritsch-Carlson), so the fan never folds the terrain over itself."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    dl = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [dl[0]] + [0.0] * (n - 2) + [dl[-1]]
    for i in range(1, n - 1):
        w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
        m[i] = (w1 + w2) / (w1 / dl[i - 1] + w2 / dl[i])

    def f(x):
        i = min(max(bisect.bisect_right(xs, x) - 1, 0), n - 2)
        t = (x - xs[i]) / h[i]
        return ((2 * t ** 3 - 3 * t ** 2 + 1) * ys[i] + (t ** 3 - 2 * t ** 2 + t) * h[i] * m[i]
                + (3 * t ** 2 - 2 * t ** 3) * ys[i + 1] + (t ** 3 - t ** 2) * h[i] * m[i + 1])
    return f


def bearing(p):
    return math.degrees(math.atan2(p[1] - ANCHOR[1], p[0] - ANCHOR[0]))


def make_fan(mtn):
    """The turn as a function of bearing: each route's real bearing from the
    summit (taken halfway up its visible length) goes to its FAN bearing."""
    if not FAN:
        return lambda a: 0.0  # no fan: the true map
    top = (mtn["summit"]["lat"], mtn["summit"]["lon"])
    pairs = sorted((bearing(along(visible([to_px(a, b, top) for a, b in mtn["routes"][name]]), 0.5)) % 360, dst % 360)
                   for name, dst in FAN.items())
    xs, ys = [a for a, _ in pairs], [d for _, d in pairs]
    for i in range(1, len(ys)):
        while ys[i] <= ys[i - 1]:
            ys[i] += 360
    if ys[-1] - ys[0] >= 360:
        raise ValueError("FAN's bearings aren't in the routes' own order around the summit")
    # repeat a turn either side, so any bearing finds its interval
    g = pchip([x + o for o in (-360, 0, 360) for x in xs], [y + o for o in (-360, 0, 360) for y in ys])
    return lambda a: g(a % 360) - a % 360  # how far to turn a point at bearing a


def fade(r):
    """How much of the turn applies at distance r: all of it near the summit,
    none at the edges."""
    t = min(max((r - FAN_R[0]) / (FAN_R[1] - FAN_R[0]), 0), 1)
    return 1 - t * t * (3 - 2 * t)


def warp(p, turn):
    r = math.dist(p, ANCHOR)
    a = math.radians(bearing(p) + fade(r) * turn(bearing(p)))
    return (ANCHOR[0] + r * math.cos(a), ANCHOR[1] + r * math.sin(a))


def unwarp(p, turn):
    """The point the fan moves onto p. The turn only ever grows with bearing,
    so bisection finds it."""
    r, want = math.dist(p, ANCHOR), bearing(p)
    k = fade(r)
    lo, hi = want - 180, want + 180
    for _ in range(40):
        mid = (lo + hi) / 2
        if mid + k * turn(mid) < want:
            lo = mid
        else:
            hi = mid
    a = math.radians((lo + hi) / 2)
    return (ANCHOR[0] + r * math.cos(a), ANCHOR[1] + r * math.sin(a))


def fanned_grid(mtn, turn):
    """The elevation grid, in feet, as it lies after the fan: each grid point
    takes the real elevation of the point the fan moves onto it."""
    src = mtn["elevation_m"]

    def at(x, y):
        gx = min(max(x * COLS / W, 0), COLS - 1e-9)
        gy = min(max(y * ROWS / H, 0), ROWS - 1e-9)
        i, j = int(gx), int(gy)
        fx, fy = gx - i, gy - j
        a = src[j][i] + (src[j][i + 1] - src[j][i]) * fx
        b = src[j + 1][i] + (src[j + 1][i + 1] - src[j + 1][i]) * fx
        return (a + (b - a) * fy) * 3.28084

    return [[at(*unwarp((i * W / COLS, j * H / ROWS), turn)) for i in range(COLS + 1)] for j in range(ROWS + 1)]


# ---- fetching the mountain (once, with --fetch) ---------------------------------------

def png_pixels(blob):
    """Decodes an 8-bit RGB or RGBA PNG, enough for the terrain tiles."""
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, head = 8, b"", None
    while pos < len(blob):
        n, kind = struct.unpack(">I4s", blob[pos:pos + 8])
        body = blob[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body[:13])
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    if head is None:
        raise ValueError("PNG without a header")
    w, h, depth, ctype, _, _, interlace = head
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError(f"unexpected PNG format: depth {depth}, colour type {ctype}, interlace {interlace}")
    bpp = 3 if ctype == 2 else 4
    raw, stride = zlib.decompress(idat), w * bpp
    out, prev, i = bytearray(), bytearray(stride), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if f > 4:
            raise ValueError(f"unknown PNG filter {f}")
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line
        prev = line
    return w, h, bpp, out


def tile_xy(lat, lon, z):
    """Lat/lon to global pixel coordinates at zoom z (Web Mercator, 256 px tiles)."""
    n = 256 * 2 ** z
    r = math.radians(lat)
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


def fetch_elevation(top):
    """The elevation grid under the sheet, in metres, from the Terrarium
    terrain tiles (USGS 3DEP in the US): elevation = R*256 + G + B/256 - 32768."""
    corners = [tile_xy(*to_ll(x, y, top), TILE_ZOOM) for x in (0, W) for y in (0, H)]
    tx0, tx1 = int(min(c[0] for c in corners) // 256), int(max(c[0] for c in corners) // 256)
    ty0, ty1 = int(min(c[1] for c in corners) // 256), int(max(c[1] for c in corners) // 256)
    tiles = {}
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            w, h, bpp, px = png_pixels(get(TERRAIN_TILES.format(z=TILE_ZOOM, x=tx, y=ty), accept="image/png"))
            tiles[tx, ty] = [px[k] * 256 + px[k + 1] + px[k + 2] / 256 - 32768 for k in range(0, len(px), bpp)]
            print(f"  tile {tx},{ty}")

    def at(gx, gy):
        t = tiles[int(gx // 256), int(gy // 256)]
        return t[int(gy % 256) * 256 + int(gx % 256)]

    grid = []
    for j in range(ROWS + 1):
        row = []
        for i in range(COLS + 1):
            gx, gy = tile_xy(*to_ll(i * W / COLS, j * H / ROWS, top), TILE_ZOOM)
            gx, gy = gx - 0.5, gy - 0.5  # pixel centres
            x0, y0 = math.floor(gx), math.floor(gy)
            fx, fy = gx - x0, gy - y0
            a = at(x0, y0) + (at(x0 + 1, y0) - at(x0, y0)) * fx
            b = at(x0, y0 + 1) + (at(x0 + 1, y0 + 1) - at(x0, y0 + 1)) * fx
            row.append(round(a + (b - a) * fy, 1))
        grid.append(row)
    return grid


def km_between(a, b):
    my, mx = per_degree(a[0])
    return math.hypot((a[0] - b[0]) * my, (a[1] - b[1]) * mx) / 1000


def fetch_routes():
    """The summit and each route as a lat/lon line from OpenStreetMap."""
    ids = ",".join(str(w) for r in OSM_ROUTES.values() for w in r["ways"])
    query = f"[out:json][timeout:120];({SUMMIT_QUERY}way(id:{ids}););out geom;"
    elements = get_json("https://overpass-api.de/api/interpreter",
                        urllib.parse.urlencode({"data": query}).encode())["elements"]
    node = next(e for e in elements if e["type"] == "node")
    top = (node["lat"], node["lon"])
    ways = {e["id"]: [(p["lat"], p["lon"]) for p in e["geometry"]] for e in elements if e["type"] == "way"}
    lines = {}
    for name, spec in OSM_ROUTES.items():
        line = []
        for wid in spec["ways"]:
            g = list(ways[wid])
            # orient each way to carry on from the line so far (the first
            # from its end farther from the summit); a gap becomes a straight
            # step from one way's end to the next one's start
            if line and km_between(line[-1], g[-1]) < km_between(line[-1], g[0]):
                g.reverse()
            if not line and km_between(g[0], top) < km_between(g[-1], top):
                g.reverse()
            line += g
        lines[name] = line
    for name, spec in OSM_ROUTES.items():
        if "join" in spec:
            # carry on up the other route from where it's `km` from the summit
            other, km = spec["join"]
            rest, acc = lines[other], 0.0
            for i in range(len(rest) - 1, 0, -1):
                acc += km_between(rest[i], rest[i - 1])
                if acc >= km:
                    lines[name] += rest[i:]
                    break
        if km_between(lines[name][-1], top) > 0.01:
            lines[name].append(top)
    return node, {k: [[round(a, 5), round(b, 5)] for a, b in v] for k, v in lines.items()}


def fetch():
    node, lines = fetch_routes()
    top = (node["lat"], node["lon"])
    print(f"  summit {top}, routes: " + ", ".join(f"{k} {len(v)} pts" for k, v in lines.items()))
    grid = fetch_elevation(top)
    data = {
        "about": "Mount Shasta for scripts/make_header.py; regenerate with --fetch.",
        "sources": {
            "routes": "© OpenStreetMap contributors, available under the Open Database License (ODbL): "
                      "https://www.openstreetmap.org/copyright",
            "elevation": "Terrarium terrain tiles (AWS Open Data, elevation-tiles-prod); in the US from "
                         "USGS 3DEP, public domain",
        },
        "layout": {"size": [W, H], "anchor": list(ANCHOR), "mpp": MPP, "cols": COLS, "rows": ROWS},
        "summit": {"name": node["tags"]["name"], "lat": top[0], "lon": top[1], "ele_m": float(node["tags"]["ele"])},
        "routes": lines,
        "elevation_m": grid,
    }
    with open(DATA + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        # one grid row per line keeps the file diffable
        body = json.dumps({k: v for k, v in data.items() if k != "elevation_m"}, ensure_ascii=False, indent=1)
        rows = ",\n".join(json.dumps(r) for r in grid)
        f.write(body[:-2] + ',\n "elevation_m": [\n' + rows + "\n ]\n}\n")
    os.replace(DATA + ".tmp", DATA)
    print(f"  {os.path.relpath(DATA, ROOT)}  {os.path.getsize(DATA):,} bytes")


def load():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    if data["layout"] != {"size": [W, H], "anchor": list(ANCHOR), "mpp": MPP, "cols": COLS, "rows": ROWS}:
        sys.exit("the sheet's layout changed since shasta.json was fetched; run with --fetch")
    data["turn"] = make_fan(data)
    data["grid_ft"] = fanned_grid(data, data["turn"])
    return data


# ---- contours -------------------------------------------------------------------------

def segments(f, cols, rows, level):
    """Marching squares: where the level crosses each cell, as segments."""
    cw, ch = W / cols, H / rows
    segs = []
    for j in range(rows):
        for i in range(cols):
            p = [(i * cw, j * ch), ((i + 1) * cw, j * ch), ((i + 1) * cw, (j + 1) * ch), (i * cw, (j + 1) * ch)]
            v = [f[j][i], f[j][i + 1], f[j + 1][i + 1], f[j + 1][i]]
            e = []
            for k in range(4):
                a, b = k, (k + 1) % 4
                if (v[a] >= level) != (v[b] >= level):
                    t = (level - v[a]) / (v[b] - v[a])
                    e.append((p[a][0] + (p[b][0] - p[a][0]) * t, p[a][1] + (p[b][1] - p[a][1]) * t))
                else:
                    e.append(None)
            hit = [x for x in e if x]
            if len(hit) == 2:
                segs.append((hit[0], hit[1]))
            elif len(hit) == 4:
                # a saddle: the cell's mean decides which corners join
                if (sum(v) / 4 >= level) == (v[0] >= level):
                    segs += [(e[0], e[1]), (e[2], e[3])]
                else:
                    segs += [(e[3], e[0]), (e[1], e[2])]
    return segs


def chain(segs):
    """Joins segments that share an end into polylines."""
    key = lambda q: (round(q[0], 1), round(q[1], 1))
    ends = {}
    for n, (a, b) in enumerate(segs):
        ends.setdefault(key(a), []).append(n)
        ends.setdefault(key(b), []).append(n)
    used = [False] * len(segs)
    lines = []
    for s in range(len(segs)):
        if used[s]:
            continue
        used[s] = True
        line = list(segs[s])
        for _ in range(2):
            while True:
                end = key(line[-1])
                nxt = next((n for n in ends.get(end, []) if not used[n]), None)
                if nxt is None:
                    break
                used[nxt] = True
                a, b = segs[nxt]
                line.append(b if key(a) == end else a)
            line.reverse()
        lines.append(line)
    return lines


def simplify(pts, eps=0.6):
    """Ramer-Douglas-Peucker: drops points that sit on the line anyway, which
    cuts the contour data roughly in half without a visible change."""
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)
    far, at = 0.0, 0
    for i in range(1, len(pts) - 1):
        # a closed ring starts and ends on the same point, so there's no chord
        # to measure against; use the distance from that point instead, or
        # every ring collapses to nothing
        if norm < 1e-6:
            d = math.hypot(pts[i][0] - ax, pts[i][1] - ay)
        else:
            d = abs(dy * (pts[i][0] - ax) - dx * (pts[i][1] - ay)) / norm
        if d > far:
            far, at = d, i
    if far <= eps:
        return [pts[0], pts[-1]]
    return simplify(pts[:at + 1], eps)[:-1] + simplify(pts[at:], eps)


def contours(P, mtn):
    f = mtn["grid_ft"]
    lo, hi = min(map(min, f)), max(map(max, f))
    out = []
    level = math.ceil(lo / CONTOUR_FT) * CONTOUR_FT
    while level < hi:
        d = ""
        for l in chain(segments(f, COLS, ROWS, level)):
            l = [(round(x, 1), round(y, 1)) for x, y in simplify(l)]
            # a knoll smaller than a pixel simplifies to one point; skip it
            if len(set(l)) > 1:
                d += "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in l)
        index = level % (4 * CONTOUR_FT) == 0
        if d:
            out.append(f'<path d="{d}" stroke-opacity="{P["index_op"] if index else P["line_op"]}" stroke-width="{1.5 if index else 0.8}"/>')
        level += CONTOUR_FT
    return f'<g fill="none" stroke="{P["line"]}" stroke-linejoin="round">{"".join(out)}</g>'


# ---- the sheet ------------------------------------------------------------------------

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def style(route_css, type_css):
    # Every animation ends where the static picture is: the routes drawn, the
    # waypoints shown, the first tagline typed. So reduced motion, or a
    # viewer that doesn't animate, still gets the whole sheet.
    return f"""<style>
@keyframes pulse {{ 0% {{ transform: scale(.6); opacity: .9 }} 100% {{ transform: scale(2.4); opacity: 0 }} }}
.pulse {{ transform-box: fill-box; transform-origin: center; animation: pulse 2.4s ease-out infinite }}
{route_css}
{type_css}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important }} }}
</style>"""


def taglines(P, x, y, size=13):
    """The old typing SVG's lines, each typed in its quarter of a 16 s cycle."""
    texts, css = [], []
    slot = 100 / len(TAGLINES)
    for n, line in enumerate(TAGLINES):
        s, e = n * slot, (n + 1) * slot
        hidden = "" if n == 0 else ' opacity="0"'
        texts.append(f'<text class="tl{n}" x="{x}" y="{y}" font-family="{MONO}" font-size="{size}" fill="{P["ink"]}"{hidden}>{esc(line)}</text>')
        # opacity hides a line before its turn too, not just the clip, so a
        # viewer without clip-path on SVG text still shows one line at a time
        before = f"0%,{s - 0.1:g}% {{ opacity: 0 }} " if n else ""
        css.append(f"@keyframes tl{n} {{ {before}{s:g}% {{ opacity: 1; clip-path: inset(0 100% 0 0); animation-timing-function: steps({len(line)}, end) }}"
                   f" {s + 9:g}%,{e - 1:g}% {{ opacity: 1; clip-path: inset(0 0 0 0) }} {e:g}%,100% {{ opacity: 0; clip-path: inset(0 0 0 0) }} }}"
                   f" .tl{n} {{ animation: tl{n} 16s infinite }}")
    return "".join(texts), "\n".join(css)


def title_block(P):
    lines, css = taglines(P, 58, 132)
    svg = f"""<g>
<rect x="34" y="34" width="372" height="132" fill="{P['chip']}" fill-opacity=".86" stroke="{P['soft']}" stroke-opacity=".6"/>
<rect x="39" y="39" width="362" height="122" fill="none" stroke="{P['soft']}" stroke-opacity=".35"/>
<text x="58" y="62" font-family="{MONO}" font-size="10" letter-spacing="2.5" fill="{P['route']}">MOUNT SHASTA QUADRANGLE · CALIFORNIA</text>
<text x="56" y="108" font-family="{SERIF}" font-weight="bold" font-size="60" textLength="336" lengthAdjust="spacingAndGlyphs" fill="{P['ink']}">LONDOPY</text>
{lines}
<text x="58" y="152" font-family="{MONO}" font-size="10" letter-spacing="1" fill="{P['soft']}">→ londo.me</text>
</g>"""
    return svg, css


def stroke(P, route, d):
    """A route's line in its style. The legend draws its samples with this
    too, so the key always matches the map."""
    c = P[route["id"]]
    base = f'd="{d}" fill="none" stroke-linejoin="round"'
    if route["style"] == "cased":
        # a double line, like a road on a quad sheet
        return (f'<path {base} stroke="{c}" stroke-width="5"/>'
                f'<path {base} stroke="{P["bg"]}" stroke-width="1.8"/>')
    dash = {"solid": "", "dashed": ' stroke-dasharray="8 5"', "dotted": ' stroke-dasharray="0.1 6"',
            "dashdot": ' stroke-dasharray="10 4 2 4"'}[route["style"]]
    width = 3.6 if route["style"] == "dotted" else 2.8
    return f'<path {base} stroke="{c}" stroke-width="{width}" stroke-linecap="round"{dash}/>'


def inside(p):
    return MAP[0] <= p[0] <= MAP[2] and MAP[1] <= p[1] <= MAP[3]


def visible(pts):
    """The part of a route from where it enters the map to the summit. Every
    route ends inside, so walk back from the summit to the first point
    outside, and start on the map's edge between the two."""
    for i in range(len(pts) - 1, 0, -1):
        if not inside(pts[i - 1]):
            (ax, ay), (bx, by) = pts[i - 1], pts[i]
            lo, hi = 0.0, 1.0  # bisect for the crossing; the segment is short
            for _ in range(30):
                mid = (lo + hi) / 2
                if inside((ax + (bx - ax) * mid, ay + (by - ay) * mid)):
                    hi = mid
                else:
                    lo = mid
            return [(ax + (bx - ax) * hi, ay + (by - ay) * hi)] + pts[i:]
    return pts


def along(pts, frac):
    """The point `frac` of the way down the route from the summit."""
    left = frac * sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    for i in range(len(pts) - 1, 0, -1):
        step = math.dist(pts[i], pts[i - 1])
        if step >= left:
            t = left / step if step else 0
            return (pts[i][0] + (pts[i - 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i - 1][1] - pts[i][1]) * t)
        left -= step
    return pts[0]


def dense(pts, step=3.0):
    """The line with a point at least every `step` px, so a long straight
    piece (a gap OSM doesn't map) bends with the fan instead of cutting
    across it."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, math.ceil(math.dist(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


def stack(items):
    """Places each waypoint's label in its column: in the order of the
    waypoints' heights, 21 px apart, as near level with its waypoint as the
    labels above allow, and pushed up if the column runs past the band."""
    for side, col in COLUMNS.items():
        group = sorted((it for it in items if it["side"] == side), key=lambda it: it["y"])
        prev = col["top"] - 21
        for it in group:
            it["ly"] = max(it["y"] - 8, prev + 21)
            prev = it["ly"]
        over = prev - (MAP[3] - 22)
        for it in group:
            it["ly"] -= max(over, 0)
            it["lx"] = col["x"] - it["w"] if side < 0 else col["x"]


def routes(P, mtn, labels):
    """The five routes, each drawn in its window of the cycle, with its
    waypoints appearing as it reaches them."""
    top = (mtn["summit"]["lat"], mtn["summit"]["lon"])
    slot = 45 / len(ROUTES)  # all five draw in the first 45% of the cycle
    defs, lines, marks, css, items = [], [], [], [], []
    for k, route in enumerate(ROUTES):
        pts = visible([warp(p, mtn["turn"]) for p in dense([to_px(a, b, top) for a, b in mtn["routes"][route["route"]]])])
        pts = simplify(pts, 0.8)
        c = P[route["id"]]
        d = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        s, e = k * slot, (k + 1) * slot
        # The styled line is revealed through a mask, because its own dashes
        # (dotted, dash-dot) can't also carry the draw-on dash. The mask
        # stroke runs 1 -> 0 on pathLength="1" at a steady speed; without
        # animation it's a plain solid stroke, so the whole route shows.
        defs.append(f'<mask id="m-{route["id"]}" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">'
                    f'<path class="rv{k}" pathLength="1" d="{d}" fill="none" stroke="#fff" stroke-width="12" '
                    f'stroke-linecap="round" stroke-linejoin="round"/></mask>')
        dash = "stroke-dasharray: 1 1"
        css.append(f"@keyframes rv{k} {{ 0%,{s:g}% {{ {dash}; stroke-dashoffset: 1; animation-timing-function: linear }}"
                   f" {e:g}%,92% {{ {dash}; stroke-dashoffset: 0; opacity: 1 }} 100% {{ {dash}; stroke-dashoffset: 0; opacity: 0 }} }}"
                   f" .rv{k} {{ animation: rv{k} {CYCLE}s infinite }}")
        # faint underneath, so every route reads before it's drawn
        lines.append(f'<g opacity=".22">{stroke(P, route, d)}</g><g mask="url(#m-{route["id"]})">{stroke(P, route, d)}</g>')
        for j, (name, _, frac, side) in enumerate(route["wps"]):
            x, y = along(pts, frac)
            # appear as the line reaches the point, frac of the way back from the top
            t = s + (1 - frac) * (e - s)
            cls = f"wp{k}{j}"
            css.append(f"@keyframes {cls} {{ 0%,{t:.1f}% {{ opacity: 0 }} {t + 2:.1f}%,92% {{ opacity: 1 }} 100% {{ opacity: 0 }} }}"
                       f" .{cls} {{ animation: {cls} {CYCLE}s infinite }}")
            label = f"{name} {labels[name]}"
            # textLength pins the label to the chip whatever monospace font the
            # viewer has, so the chip never ends short of or long after its text
            tl = len(label) * CHAR
            items.append(dict(cls=cls, c=c, x=round(x, 1), y=round(y, 1), side=side, label=label, tl=tl, w=tl + 12))
    stack(items)
    for it in items:
        near = it["lx"] + it["w"] if it["side"] < 0 else it["lx"]
        marks.append(f'<g class="{it["cls"]}">'
                     f'<line x1="{it["x"]}" y1="{it["y"]}" x2="{near:.1f}" y2="{it["ly"] + 4.5:.1f}" stroke="{it["c"]}" stroke-width="1" stroke-opacity=".8"/>'
                     f'<circle cx="{it["x"]}" cy="{it["y"]}" r="5" fill="{P["chip"]}" stroke="{it["c"]}" stroke-width="2"/>'
                     f'<rect x="{it["lx"]:.1f}" y="{it["ly"] - 4:.1f}" width="{it["w"]:.1f}" height="17" fill="{P["chip"]}" fill-opacity=".9" '
                     f'stroke="{it["c"]}" stroke-opacity=".8"/>'
                     f'<text x="{it["lx"] + 6:.1f}" y="{it["ly"] + 8:.1f}" textLength="{it["tl"]:.1f}" lengthAdjust="spacingAndGlyphs" '
                     f'font-family="{MONO}" font-size="11" fill="{P["ink"]}">{esc(it["label"])}</text></g>')
    boxes = [(it["label"], it["lx"], it["ly"] - 4, it["lx"] + it["w"], it["ly"] + 13,
              (it["x"], it["y"], it["lx"] + it["w"] if it["side"] < 0 else it["lx"], it["ly"] + 4.5)) for it in items]
    return "<defs>" + "".join(defs) + "</defs>\n" + "\n".join(lines) + "\n" + "\n".join(marks), "\n".join(css), boxes


def summit_chip(P, mtn, data):
    """The peak every route ends on, with the whole catalog, set off to the
    northeast: between the north route and the right label column, the one
    stretch of the mountain no route comes up."""
    x, y = ANCHOR
    feet = round(mtn["summit"]["ele_m"] * 3.28084)
    cx, cy, w, h = SUMMIT_CHIP
    return (f'<circle class="pulse" cx="{x}" cy="{y}" r="9" fill="none" stroke="{P["ink"]}" stroke-width="2"/>'
            f'<path d="M{x} {y - 10}L{x + 9} {y + 6}L{x - 9} {y + 6}Z" fill="{P["ink"]}"/>'
            f'<line x1="{x + 8}" y1="{y - 2}" x2="{cx}" y2="{cy + h}" stroke="{P["ink"]}" stroke-width="1"/>'
            f'<rect x="{cx}" y="{cy}" width="{w}" height="{h}" fill="{P["chip"]}" fill-opacity=".92" stroke="{P["ink"]}"/>'
            f'<text x="{cx + 8}" y="{cy + 15}" font-family="{MONO}" font-size="11" font-weight="bold" fill="{P["ink"]}">'
            f'{esc(mtn["summit"]["name"].upper())} · {feet:,} FT</text>'
            f'<text x="{cx + 8}" y="{cy + 30}" font-family="{MONO}" font-size="11" fill="{P["ink"]}">'
            f'{data["projects"]} projects · ★{data["stars"]}</text>')


def frame(P, mtn):
    """The neatline, with real graticule ticks: every 2′ of longitude, every
    1′ of latitude, labelled where the title block and band leave room."""
    top = (mtn["summit"]["lat"], mtn["summit"]["lon"])
    out = [f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="none" stroke="{P["ink"]}" stroke-width="1.4"/>',
           f'<rect x="7" y="7" width="{W - 14}" height="{H - 14}" fill="none" stroke="{P["ink"]}" stroke-opacity=".4"/>']
    west, east = to_ll(0, 0, top)[1], to_ll(W, 0, top)[1]
    m = math.ceil(-east * 30)  # whole 2′ steps, counted west from 0°
    while m / 30 <= -west:
        x = to_px(top[0], -m / 30, top)[0]
        # only where the fan has faded out, so every tick is true
        if 30 < x < W - 60 and (not FAN or math.dist((x, 12), ANCHOR) > FAN_R[1]):
            deg, mins = divmod(m * 2, 60)
            out.append(f'<line x1="{x:.1f}" y1="12" x2="{x:.1f}" y2="20" stroke="{P["ink"]}"/>'
                       f'<text x="{x + 3:.1f}" y="27" font-family="{MONO}" font-size="8" fill="{P["soft"]}">{deg}°{mins:02d}′W</text>')
        m += 1
    south, north = to_ll(0, MAP[3], top)[0], to_ll(0, 0, top)[0]
    m = math.ceil(south * 60)
    while m / 60 <= north:
        y = to_px(m / 60, top[1], top)[1]
        # clear of the title block above and the band below
        if 176 < y < MAP[3] - 8:
            deg, mins = divmod(m, 60)
            out.append(f'<line x1="12" y1="{y:.1f}" x2="20" y2="{y:.1f}" stroke="{P["ink"]}"/>'
                       f'<text x="22" y="{y + 3:.1f}" font-family="{MONO}" font-size="8" fill="{P["soft"]}">{deg}°{mins:02d}′N</text>')
        m += 1
    return "\n".join(out)


def band(P, data, surveyed):
    """The sheet's foot: the legend in a row (domain, then the real route),
    then the fine print, credits and a true scale bar."""
    top = MAP[3]
    # inset by half the neatline's width, so the band doesn't cover its inner half
    out = [f'<rect x="12.7" y="{top}" width="{W - 25.4}" height="{H - 12.7 - top}" fill="{P["bg"]}" fill-opacity=".92"/>',
           f'<line x1="12" y1="{top}" x2="{W - 12}" y2="{top}" stroke="{P["soft"]}" stroke-opacity=".6"/>',
           f'<text x="30" y="{top + 22}" font-family="{MONO}" font-size="9" letter-spacing="2.5" fill="{P["soft"]}">ROUTES</text>']
    for k, route in enumerate(ROUTES):
        x = 96 + k * 166
        out.append(stroke(P, route, f"M{x} {top + 18}H{x + 30}") +
                   f'<text x="{x + 38}" y="{top + 21}" font-family="{MONO}" font-size="11" fill="{P["ink"]}">{route["id"]}</text>'
                   f'<text x="{x + 38}" y="{top + 33}" font-family="{MONO}" font-size="9" fill="{P["soft"]}">{esc(route["name"])}</text>')
    # says plainly what isn't to scale: the bearings are fanned (see FAN)
    fine = (f"{len(ROUTES)} OF {data['domains']} DOMAINS · {CONTOUR_FT} FT CONTOURS · BEARINGS FANNED · "
            f"TERRAIN USGS 3DEP · © OPENSTREETMAP CONTRIBUTORS · {surveyed}")
    y = H - 20
    # a true 4 km scale bar in four 1 km blocks, ends labelled on its own line
    block = 1000 / MPP
    bar = "".join(f'<rect x="{800 + k * block:g}" y="{y - 7}" width="{block:g}" height="5" fill="{P["ink"] if k % 2 == 0 else P["chip"]}" '
                  f'stroke="{P["ink"]}" stroke-width=".6"/>' for k in range(4))
    out.append(f'<text x="30" y="{y}" font-family="{MONO}" font-size="9" letter-spacing="1" fill="{P["soft"]}">{esc(fine)}</text>'
               f'{bar}<text x="794" y="{y}" text-anchor="end" font-family="{MONO}" font-size="8" fill="{P["soft"]}">0</text>'
               f'<text x="{806 + 4 * block:g}" y="{y}" font-family="{MONO}" font-size="8" fill="{P["soft"]}">4 KM</text>')
    return "\n".join(out)


def sheet(mode, mtn, data, surveyed):
    P = PALETTES[mode]
    title, type_css = title_block(P)
    paths, route_css, boxes = routes(P, mtn, data["labels"])
    no_overlaps(boxes)
    body = "\n".join([f'<rect width="{W}" height="{H}" fill="{P["bg"]}"/>', contours(P, mtn), frame(P, mtn), title,
                      paths, summit_chip(P, mtn, data), band(P, data, surveyed)])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="Londopy: a topographic survey sheet of Mount Shasta, five real routes by domain up to the summit">\n'
            f'{style(route_css, type_css)}\n{body}\n</svg>\n')


def no_overlaps(labels):
    """Fails if a waypoint label would cover another label, the summit chip
    or the title block, or leave the map. A longer number can push labels
    together, and a failed check keeps the last good header."""
    sx, sy, sw, sh = SUMMIT_CHIP
    fixed = [("the summit chip", sx, sy, sx + sw, sy + sh), ("the title block", *TITLE)]
    boxes = [b[:5] for b in labels] + fixed
    for i, (name, x0, y0, x1, y1, leader) in enumerate(labels):
        if x0 < MAP[0] + 2 or x1 > MAP[2] - 2 or y0 < MAP[1] + 2 or y1 > MAP[3] - 2:
            raise ValueError(f"the {name!r} label runs off the map")
        for other, a0, b0, a1, b1 in boxes[i + 1:]:
            if x0 < a1 + 2 and a0 < x1 + 2 and y0 < b1 + 2 and b0 < y1 + 2:
                raise ValueError(f"the {name!r} label overlaps {other!r}")
        # the leader line too: one running behind another box would make that
        # box read as this waypoint's label
        for other, a0, b0, a1, b1 in boxes:
            if other != name and crosses(leader, (a0, b0, a1, b1)):
                raise ValueError(f"the leader line of {name!r} passes through {other!r}")


def crosses(seg, box):
    """Whether the segment (x0, y0, x1, y1) passes through the box (clipping
    the segment to the box's slabs, Liang-Barsky)."""
    x0, y0, x1, y1 = seg
    lo, hi = 0.0, 1.0
    for p, q in ((x0 - x1, x0 - box[0]), (x1 - x0, box[2] - x0), (y0 - y1, y0 - box[1]), (y1 - y0, box[3] - y0)):
        if p == 0:
            if q < 0:
                return False
        elif p < 0:
            lo = max(lo, q / p)
        else:
            hi = min(hi, q / p)
    return lo < hi


def check(text):
    """Fails on a sheet that parses wrong or has a path that draws nothing (a
    subpath whose points are all the same, which is how a lost contour ring
    looked)."""
    root = ET.fromstring(text)
    for el in root.iter("{http://www.w3.org/2000/svg}path"):
        d = el.get("d")
        if not re.fullmatch(r"[ML0-9. -]+", d):
            continue  # only plain M/L point lists: the contours and routes
        for sub in d.split("M")[1:]:
            nums = re.findall(r"-?\d+(?:\.\d+)?", sub)
            if len(set(zip(nums[::2], nums[1::2]))) < 2:
                raise ValueError(f"a subpath draws nothing: M{sub[:40]}")


def main():
    if sys.argv[1:] == ["--fetch"]:
        fetch()
        return
    mtn = load()
    outputs = {mode: os.path.join(ROOT, "assets", f"header-{mode}.svg") for mode in PALETTES}
    try:
        data = numbers()
    except Exception as e:
        # same rule as the badge step: a flaky source leaves the last good sheet
        # alone, with a warning in the Actions log so a lasting break is seen
        if all(os.path.exists(p) for p in outputs.values()):
            print(f"::warning::couldn't fetch the header's numbers ({e}); leaving the header as it is")
            return
        sys.exit(f"couldn't fetch the numbers and there's no header yet: {e}")
    # month, not day, so the file only changes when something real does
    surveyed = datetime.now(timezone.utc).strftime("%Y-%m")
    # draw and check both before touching either file, then swap each in
    # whole, so an error can't leave a half-written or empty header behind
    try:
        sheets = {mode: sheet(mode, mtn, data, surveyed) for mode in outputs}
        for text in sheets.values():
            check(text)
    except ValueError as e:
        # a label that no longer fits, say: keep the last good header, loudly
        print(f"::warning::the header didn't pass its checks ({e}); leaving it as it is")
        return
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    for mode, path in outputs.items():
        with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            f.write(sheets[mode])
        os.replace(path + ".tmp", path)
        print(f"  {os.path.relpath(path, ROOT)}  {os.path.getsize(path):,} bytes")
    print(f"  {json.dumps(data)}")  # escapes ★ and ↓, which a Windows console can't print


if __name__ == "__main__":
    main()
