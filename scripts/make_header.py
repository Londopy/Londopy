#!/usr/bin/env python3
"""Draws the README's header: a topographic survey sheet of the profile.

Contour lines over a seeded terrain (the same idea as londo.me's background),
a trail that draws itself up to a summit, and the featured projects as
waypoints along it, each with a live number. Writes:

    assets/header-day.svg     for GitHub's light theme
    assets/header-night.svg   for the dark theme (the README picks with <picture>)

    python3 scripts/make_header.py

Standard library only. GitHub shows README images through <img>, which rules
out scripts, web fonts and anything fetched from inside the SVG, so the
motion is plain CSS animation, the text uses system fonts, and every number
is baked in here. The nightly profile-data workflow reruns this after it
refreshes badges/, so the numbers stay current.
"""
import json
import math
import os
import random
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1000, 460

# the README's badge colours: amber, moss, brown
AMBER, MOSS, BROWN = "#D97706", "#4A7B3E", "#7A5C3A"
PALETTES = {
    "day": dict(bg="#F4EEE2", line="#B08A5E", line_op=0.45, index_op=0.8, ink="#3B2A1A", soft=BROWN,
                route="#C2410C", chip="#F4EEE2", moss=MOSS),
    "night": dict(bg="#12100D", line=AMBER, line_op=0.22, index_op=0.5, ink="#EDE3D2", soft="#B9A88F",
                  route="#F59E0B", chip="#12100D", moss="#7FB06D"),
}
SERIF = "Georgia, 'Times New Roman', serif"
MONO = "Consolas, 'DejaVu Sans Mono', Menlo, monospace"

# the trail from the bottom left; every second point from the third is a
# waypoint, and the trail ends on the terrain's highest point (see summit())
TRAIL = [(60, 412), (150, 392), (230, 398), (310, 360), (385, 335), (455, 322), (520, 285),
         (565, 248), (625, 222), (700, 228)]
# (repo, where its number comes from, label offset from the point: a negative
# dx sets the label to the left). Each label sits clear of the trail.
WAYPOINTS = [("ropesim", "downloads", (-12, -26)), ("deadpoint", "downloads", (12, 14)),
             ("patchnotes", "downloads", (12, 14)), ("capture-bypass", "stars", (-12, -26))]
CHAR = 6.6  # a monospace character at 11px; labels are stretched to exactly this
SUMMIT = "nexium"
# the lines the old typing SVG cycled through, typed out in turn
TAGLINES = ["hey — i'm london", "python + rust / ship a lot",
            "climber · skier · surfer · wfr · sprat", "build because the problem is interesting"]


# ---- live numbers -----------------------------------------------------------------

def get_json(url):
    headers = {"User-Agent": "Londopy-profile-header", "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def numbers():
    """Every number the sheet shows. Raises if any source is unreachable."""
    stats = get_json("https://londo.me/api/v1/stats.json")["data"]
    labels = {}
    for repo, kind, _ in WAYPOINTS + [(SUMMIT, "stars", None)]:
        if kind == "stars":
            n = get_json(f"https://api.github.com/repos/Londopy/{repo}")["stargazers_count"]
            labels[repo] = f"★{n}"
        else:
            # badges/ is refreshed from pypistats earlier in the same workflow run
            with open(os.path.join(ROOT, "badges", f"{repo}.json"), encoding="utf-8") as f:
                labels[repo] = "↓" + json.load(f)["message"].replace("/month", "/mo")
    data = {"labels": labels, "projects": stats["projects"], "domains": stats["domains"],
            "stars": stats["stars"]["total"]}
    # a changed API shape should keep the old header, not print "★None" on it
    for key in ("projects", "domains", "stars"):
        if not isinstance(data[key], int):
            raise ValueError(f"stats.json {key} is {data[key]!r}, not a number")
    return data


# ---- terrain ------------------------------------------------------------------------

def lattice(rng, gw, gh):
    return [[rng.random() for _ in range(gw + 1)] for _ in range(gh + 1)]


def smoothstep(t):
    return t * t * (3 - 2 * t)


def sample(lat, gw, gh, u, v):
    x, y = u * gw, v * gh
    x0, y0 = min(int(x), gw - 1), min(int(y), gh - 1)
    tx, ty = smoothstep(x - x0), smoothstep(y - y0)
    a = lat[y0][x0] + (lat[y0][x0 + 1] - lat[y0][x0]) * tx
    b = lat[y0 + 1][x0] + (lat[y0 + 1][x0 + 1] - lat[y0 + 1][x0]) * tx
    return a + (b - a) * ty


def terrain(cols, rows):
    """Three octaves of seeded value noise plus three hills; the seed keeps the
    map identical on every run, so only the numbers ever change the file."""
    rng = random.Random(20261028)
    octaves = [(lattice(rng, 5, 3), 5, 3, 0.55), (lattice(rng, 11, 6), 11, 6, 0.3), (lattice(rng, 23, 11), 23, 11, 0.15)]
    hills = [(720, 175, 170, 0.95), (300, 360, 120, 0.35), (930, 380, 110, 0.3)]
    f = []
    for j in range(rows + 1):
        row = []
        for i in range(cols + 1):
            u, v = i / cols, j / rows
            n = sum(w * sample(lat, gw, gh, u, v) for lat, gw, gh, w in octaves)
            for px, py, pr, ph in hills:
                n += ph * math.exp(-((u * W - px) ** 2 + (v * H - py) ** 2) / (pr * pr))
            row.append(n)
        f.append(row)
    return f


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


COLS, ROWS = 125, 58
FIELD = terrain(COLS, ROWS)


def summit():
    """The terrain's highest grid point, where the trail ends."""
    _, j, i = max((v, j, i) for j, row in enumerate(FIELD) for i, v in enumerate(row))
    return (round(i * W / COLS), round(j * H / ROWS))


def contours(P):
    cols, rows, f = COLS, ROWS, FIELD
    lo, hi = min(map(min, f)), max(map(max, f))
    out = []
    for k in range(1, 24):
        level = lo + (hi - lo) * k / 24
        d = "".join("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in simplify(l))
                    for l in chain(segments(f, cols, rows, level)) if len(l) > 2)
        index = k % 4 == 0  # every fourth line is an index contour, drawn heavier
        out.append(f'<path d="{d}" stroke-opacity="{P["index_op"] if index else P["line_op"]}" stroke-width="{1.5 if index else 0.8}"/>')
    return f'<g class="drift" fill="none" stroke="{P["line"]}" stroke-linejoin="round">{"".join(out)}</g>'


# ---- the sheet ------------------------------------------------------------------------

def smooth_d(pts):
    """A Catmull-Rom curve through the points, as cubic Beziers."""
    d = f"M{pts[0][0]} {pts[0][1]}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]} {p2[1]}"
    return d


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def style(trail_css, type_css):
    # Every animation ends where the static picture is: the trail drawn, the
    # waypoints shown, the first tagline typed. So reduced motion, or a
    # viewer that doesn't animate, still gets the whole sheet. The dash lives
    # only in the keyframes for the same reason: without animation the trail
    # is a plain solid line. It draws at a steady speed (linear), so the
    # waypoints, timed by distance along it, appear as it reaches them.
    dash = "stroke-dasharray: 1 1"
    return f"""<style>
@keyframes drift {{ 0%,100% {{ transform: translate(0,0) }} 50% {{ transform: translate(-16px,7px) }} }}
@keyframes draw {{ 0% {{ {dash}; stroke-dashoffset: 1; animation-timing-function: linear }} 45%,90% {{ {dash}; stroke-dashoffset: 0; opacity: 1 }} 100% {{ {dash}; stroke-dashoffset: 0; opacity: 0 }} }}
@keyframes pulse {{ 0% {{ transform: scale(.6); opacity: .9 }} 100% {{ transform: scale(2.4); opacity: 0 }} }}
.drift {{ animation: drift 40s ease-in-out infinite }}
.route {{ animation: draw 12s ease-in-out infinite }}
.pulse {{ transform-box: fill-box; transform-origin: center; animation: pulse 2.4s ease-out infinite }}
{trail_css}
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
<text x="58" y="62" font-family="{MONO}" font-size="10" letter-spacing="2.5" fill="{P['route']}">QUADRANGLE · CALIFORNIA · 7.5′ SERIES</text>
<text x="56" y="108" font-family="{SERIF}" font-weight="bold" font-size="60" textLength="336" lengthAdjust="spacingAndGlyphs" fill="{P['ink']}">LONDOPY</text>
{lines}
<text x="58" y="152" font-family="{MONO}" font-size="10" letter-spacing="1" fill="{P['soft']}">→ londo.me</text>
</g>"""
    return svg, css


def trail(P, labels):
    pts = TRAIL + [summit()]
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    d = smooth_d(pts)
    out = [f'<path d="{d}" fill="none" stroke="{P["soft"]}" stroke-opacity=".55" stroke-width="1.6" stroke-dasharray="5 5"/>',
           # pathLength="1" lets the dash animation run 1 -> 0 whatever the real length
           f'<path class="route" pathLength="1" d="{d}" fill="none" stroke="{P["route"]}" stroke-width="3" stroke-linecap="round"/>']
    css = []
    for n, (repo, _, (dx, dy)) in enumerate(WAYPOINTS):
        i = 2 + 2 * n
        x, y = TRAIL[i]
        # each waypoint appears as the drawn trail reaches it
        t = round(acc[i] / acc[-1] * 45, 1)
        css.append(f"@keyframes wp{n} {{ 0%,{t}% {{ opacity: 0 }} {t + 3:.1f}%,90% {{ opacity: 1 }} 100% {{ opacity: 0 }} }}"
                   f" .wp{n} {{ animation: wp{n} 12s ease-in-out infinite }}")
        label = f"WP{n + 1} {repo} {labels[repo]}"
        # textLength pins the label to the chip whatever monospace font the
        # viewer has, so the chip never ends short of or long after its text
        tl = len(label) * CHAR
        w = tl + 12
        near, ly = x + dx, y + dy
        lx = near if dx >= 0 else near - w
        out.append(f'<g class="wp{n}">'
                   f'<circle cx="{x}" cy="{y}" r="5" fill="{P["chip"]}" stroke="{P["route"]}" stroke-width="2"/>'
                   f'<line x1="{x}" y1="{y}" x2="{near}" y2="{ly + 4.5}" stroke="{P["route"]}" stroke-width="1"/>'
                   f'<rect x="{lx:.1f}" y="{ly - 4}" width="{w:.1f}" height="17" fill="{P["chip"]}" fill-opacity=".9" stroke="{P["route"]}" stroke-opacity=".7"/>'
                   f'<text x="{lx + 6:.1f}" y="{ly + 8}" textLength="{tl:.1f}" lengthAdjust="spacingAndGlyphs" font-family="{MONO}" '
                   f'font-size="11" fill="{P["ink"]}">{esc(label)}</text></g>')
    x, y = pts[-1]
    out.append(f'<circle class="pulse" cx="{x}" cy="{y}" r="9" fill="none" stroke="{P["route"]}" stroke-width="2"/>'
               f'<path d="M{x} {y - 9}L{x + 8} {y + 5}L{x - 8} {y + 5}Z" fill="{P["route"]}"/>'
               # below the peak: the trail comes in from the left and the legend sits above
               f'<text x="{x}" y="{y + 26}" text-anchor="middle" font-family="{MONO}" font-size="11" font-weight="bold" fill="{P["ink"]}">'
               f'SUMMIT · {SUMMIT} {esc(labels[SUMMIT])}</text>')
    return "\n".join(out), "\n".join(css)


def legend(P):
    rows = [("security", P["route"], "M0 0H26", ""), ("radio", P["moss"], "M0 0H26", ' stroke-dasharray="4 3"'),
            ("climbing", P["ink"], "M0 4L5 -4L10 4L15 -4L20 4L26 -4", ""), ("medicine", P["route"], "M8 -4V4M4 0H12", ""),
            ("systems", P["soft"], "M0 0H26", ' stroke-dasharray="1 3"')]
    out = [f'<rect x="812" y="38" width="152" height="150" fill="{P["chip"]}" fill-opacity=".88" stroke="{P["soft"]}" stroke-opacity=".6"/>',
           f'<text x="826" y="60" font-family="{MONO}" font-size="10" letter-spacing="3" fill="{P["soft"]}">LEGEND</text>']
    for n, (name, col, d, dash) in enumerate(rows):
        y = 84 + n * 22
        out.append(f'<path transform="translate(826 {y - 4})" d="{d}" fill="none" stroke="{col}" stroke-width="2"{dash}/>'
                   f'<text x="864" y="{y}" font-family="{MONO}" font-size="11" fill="{P["ink"]}">{name}</text>')
    return "\n".join(out)


def frame(P):
    # coordinate ticks around San Luis Obispo, in the neatline like a USGS quad
    out = [f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="none" stroke="{P["ink"]}" stroke-width="1.4"/>',
           f'<rect x="7" y="7" width="{W - 14}" height="{H - 14}" fill="none" stroke="{P["ink"]}" stroke-opacity=".4"/>']
    for k, lab in enumerate(["120°44′W", "120°42′W", "120°40′W", "120°38′W", "120°36′W"]):
        x = 100 + k * 200
        out.append(f'<line x1="{x}" y1="12" x2="{x}" y2="20" stroke="{P["ink"]}"/>'
                   f'<text x="{x + 3}" y="27" font-family="{MONO}" font-size="8" fill="{P["soft"]}">{lab}</text>')
    # below the title block, which would hide a higher one
    for k, lab in enumerate(["35°19′N", "35°18′N"]):
        y = 220 + k * 110
        out.append(f'<line x1="12" y1="{y}" x2="20" y2="{y}" stroke="{P["ink"]}"/>'
                   f'<text x="22" y="{y + 3}" font-family="{MONO}" font-size="8" fill="{P["soft"]}">{lab}</text>')
    return "\n".join(out)


def band(P, data, surveyed):
    y = H - 30
    left = (f"{data['projects']} PROJECTS · {data['domains']} DOMAINS · ★{data['stars']} · "
            f"CONTOUR INTERVAL 1 COMMIT · SURVEYED {surveyed}")
    # the scale bar and its ends on one line, so nothing crosses the neatline
    bar = "".join(f'<rect x="{800 + k * 25}" y="{y + 3}" width="25" height="5" fill="{P["ink"] if k % 2 == 0 else P["chip"]}" '
                  f'stroke="{P["ink"]}" stroke-width=".6"/>' for k in range(4))
    return (f'<line x1="14" y1="{y - 8}" x2="{W - 14}" y2="{y - 8}" stroke="{P["soft"]}" stroke-opacity=".5"/>'
            f'<text x="30" y="{y + 10}" font-family="{MONO}" font-size="10" letter-spacing="1.5" fill="{P["soft"]}">{esc(left)}</text>'
            f'{bar}<text x="794" y="{y + 10}" text-anchor="end" font-family="{MONO}" font-size="8" fill="{P["soft"]}">0</text>'
            f'<text x="906" y="{y + 10}" font-family="{MONO}" font-size="8" fill="{P["soft"]}">1k COMMITS</text>')


def sheet(mode, data, surveyed):
    P = PALETTES[mode]
    title, type_css = title_block(P)
    route, trail_css = trail(P, data["labels"])
    body = "\n".join([f'<rect width="{W}" height="{H}" fill="{P["bg"]}"/>', contours(P), frame(P), title,
                      legend(P), route, band(P, data, surveyed)])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="Londopy: a topographic survey sheet of featured projects">\n'
            f'{style(trail_css, type_css)}\n{body}\n</svg>\n')


def check(text):
    """Fails on a sheet that parses wrong or has a path that draws nothing (a
    subpath whose points are all the same, which is how a lost contour ring
    looked)."""
    root = ET.fromstring(text)
    for el in root.iter("{http://www.w3.org/2000/svg}path"):
        d = el.get("d")
        if not re.fullmatch(r"[ML0-9. -]+", d):
            continue  # only the contours are plain M/L point lists
        for sub in d.split("M")[1:]:
            nums = re.findall(r"-?\d+(?:\.\d+)?", sub)
            if len(set(zip(nums[::2], nums[1::2]))) < 2:
                raise ValueError(f"a subpath draws nothing: M{sub[:40]}")


def main():
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
    sheets = {mode: sheet(mode, data, surveyed) for mode in outputs}
    for text in sheets.values():
        check(text)
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    for mode, path in outputs.items():
        with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            f.write(sheets[mode])
        os.replace(path + ".tmp", path)
        print(f"  {os.path.relpath(path, ROOT)}  {os.path.getsize(path):,} bytes")
    print(f"  {json.dumps(data)}")  # escapes ★ and ↓, which a Windows console can't print


if __name__ == "__main__":
    main()
