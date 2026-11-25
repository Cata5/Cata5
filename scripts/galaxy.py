#!/usr/bin/env python3
"""Generates two animated SVGs for a GitHub profile README:
  assets/repo-galaxy.svg     - every repo is a star, language = spiral arm
  assets/contrib-galaxy.svg  - your contribution calendar as a living constellation
No dependencies (stdlib only). Run in GitHub Actions or locally:
  GITHUB_TOKEN=xxx python scripts/galaxy.py Cata5
  python scripts/galaxy.py Cata5 --mock      # offline preview
"""
import datetime, json, math, os, random, re, struct, sys, urllib.request, zlib
from collections import defaultdict
from xml.sax.saxutils import escape

USER = next((a for a in sys.argv[1:] if not a.startswith("--")), "Cata5")
MOCK = "--mock" in sys.argv
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
PAT = os.environ.get("GH_PAT", "")            # user token: unlocks private repos/contributions
TOKEN = PAT or os.environ.get("GITHUB_TOKEN", "")

LANG_COLORS = {
    "Python": "#4B8BBE", "TypeScript": "#3178C6", "JavaScript": "#F7DF1E",
    "CSS": "#9B59D0", "HTML": "#E34F26", "Shell": "#89E051", "C#": "#68B84A",
    "C++": "#F34B7D", "C": "#A8B9CC", "Java": "#E76F00", "Jupyter Notebook": "#F37626",
    "Go": "#00ADD8", "Rust": "#DEA584", "Other": "#8B949E",
}
def color(lang): return LANG_COLORS.get(lang, LANG_COLORS["Other"])

# ───────────────────────── data ─────────────────────────
def api(url, data=None):
    req = urllib.request.Request(url, data=data)
    req.add_header("User-Agent", "galaxy-profile")
    if TOKEN: req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def fetch_repos():
    """Public repos always; private repos only when a user PAT is present."""
    if PAT:
        url = "https://api.github.com/user/repos?per_page=100&affiliation=owner&visibility=all&sort=updated"
    else:
        url = f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner&sort=updated"
    repos = [r for r in api(url) if not r["fork"]]
    for r in repos:
        r["private"] = bool(r.get("private"))
        try: r["_langs"] = api(r["languages_url"])
        except Exception: r["_langs"] = {r["language"]: 1} if r["language"] else {}
    return repos

def fetch_calendar_graphql():
    q = """query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{
      totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
    body = json.dumps({"query": q, "variables": {"u": USER}}).encode()
    d = api("https://api.github.com/graphql", body)
    if "errors" in d: raise RuntimeError(d["errors"])
    cal = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return cal["totalContributions"], [[day["contributionCount"] for day in w["contributionDays"]] for w in cal["weeks"]]

def fetch_calendar_public():
    """Token-free fallback: parse the public contribution calendar page."""
    url = f"https://github.com/users/{USER}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "galaxy-profile", "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8")
    counts = {}
    for cid, text in re.findall(r'<tool-tip[^>]*for="(contribution-day-component-[\d-]+)"[^>]*>(.*?)</tool-tip>', html, re.S):
        m = re.match(r"\s*(\d[\d,]*)\s+contribution", text)
        counts[cid] = int(m.group(1).replace(",", "")) if m else 0
    days = {}
    for tag in re.findall(r"<td\b[^>]*>", html):
        cid = re.search(r'id="(contribution-day-component-[\d-]+)"', tag)
        date = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        if cid and date: days[datetime.date.fromisoformat(date.group(1))] = counts.get(cid.group(1), 0)
    if not days: raise RuntimeError(f"no contribution days found on {url}")
    first, last = min(days), max(days)
    weeks = [[0]*7 for _ in range((last-first).days//7 + 1)]
    for day, n in days.items():
        weeks[(day-first).days//7][(day.weekday()+1) % 7] = n
    return sum(days.values()), weeks

def fetch_calendar():
    """Real contribution data: GraphQL when a token is available, public page otherwise."""
    if TOKEN:
        try: return fetch_calendar_graphql()
        except Exception as e: print("graphql calendar failed, falling back to public page:", e, file=sys.stderr)
    return fetch_calendar_public()

def mock_repos():
    names = [("CataAI-Ultra","Python",3,False),("Proiect-Python","Python",1,False),("EzyAid","JavaScript",2,False),
             ("TranslateEdu","Python",0,False),("Portfolio","TypeScript",4,False),("Blender-Scenes","HTML",0,False),
             ("Arduino-Lab","C++",1,False),("NextShop","TypeScript",2,False),("Styles","CSS",0,False),
             ("secret-lab","Python",1,True)]
    return [{"name":n,"language":l,"stargazers_count":s,"private":p,
             "_langs":{l:random.randint(3000,40000)}} for n,l,s,p in names]

def mock_calendar():
    rnd = random.Random(7)
    weeks = [[0 if rnd.random()<.55 else rnd.choice([1,2,3,5,8,12]) for _ in range(7)] for _ in range(53)]
    return sum(map(sum, weeks)), weeks

# ───────────────────────── shared svg bits ─────────────────────────
def defs(w, h, uid):
    return f"""<defs>
  <radialGradient id="bg{uid}" cx="50%" cy="50%" r="75%">
    <stop offset="0" stop-color="#0d1233"/><stop offset="1" stop-color="#03040d"/></radialGradient>
  <radialGradient id="core{uid}"><stop offset="0" stop-color="#fff"/><stop offset=".25" stop-color="#a5b4fc"/>
    <stop offset="1" stop-color="#6366f1" stop-opacity="0"/></radialGradient>
  <filter id="glow{uid}" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3"/></filter>
  <clipPath id="clip{uid}"><rect width="{w}" height="{h}" rx="18"/></clipPath>
</defs>"""

STYLE = """<style>
  text{font-family:'JetBrains Mono','Fira Code',ui-monospace,Menlo,monospace}
  .tw{animation:tw var(--d) ease-in-out infinite;animation-delay:var(--o)}
  @keyframes tw{0%,100%{opacity:.25}50%{opacity:1}}
  .spin{transform-origin:var(--cx) var(--cy);animation:spin 240s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  .pulse{animation:pulse 4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
  @keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.35)}}
  .shoot{opacity:0;animation:shoot 7s linear infinite;animation-delay:var(--o)}
  @keyframes shoot{0%{opacity:0;transform:translate(0,0)}4%{opacity:1}
    14%{opacity:0;transform:translate(260px,110px)}100%{opacity:0;transform:translate(260px,110px)}}
</style>"""

# ───────────────────────── repo galaxy ─────────────────────────
def repo_galaxy(repos):
    W, H = 900, 340
    cx, cy = 600, 175
    rnd = random.Random(USER)

    public = [r for r in repos if not r.get("private")]
    private = [r for r in repos if r.get("private")]

    # language mix is computed from public repos only: private stacks never leak
    totals = defaultdict(int)
    for r in public:
        for l, b in r["_langs"].items(): totals[l] += b
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda x: -x[1])[:5]
    arm_angle = {l: i * (2*math.pi/max(len(ranked),1)) for i, (l, _) in enumerate(ranked)}

    def arm_point(lang, t, spread=0.35):
        a0 = arm_angle.get(lang, rnd.random()*6.28)
        ang = a0 + t*3.2 + rnd.uniform(-spread, spread)
        rad = 28 + t*165 + rnd.uniform(-10, 10)
        return cx + math.cos(ang)*rad*1.45, cy + math.sin(ang)*rad*0.72

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
         defs(W, H, "r"), STYLE,
         f'<g clip-path="url(#clipr)"><rect width="{W}" height="{H}" fill="url(#bgr)"/>']

    # dust: thousands of tiny stars along the arms, slowly rotating
    s.append(f'<g class="spin" style="--cx:{cx}px;--cy:{cy}px">')
    for l, b in ranked:
        n = int(80 + 320*b/grand)
        for _ in range(n):
            x, y = arm_point(l, rnd.random()**0.8, 0.5)
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(.4,1.3):.2f}" fill="{color(l)}" opacity="{rnd.uniform(.2,.8):.2f}"/>')
    s.append('</g>')
    for _ in range(70):  # background stars that twinkle
        s.append(f'<circle class="tw" style="--d:{rnd.uniform(2,6):.1f}s;--o:-{rnd.uniform(0,6):.1f}s" '
                 f'cx="{rnd.uniform(0,W):.0f}" cy="{rnd.uniform(0,H):.0f}" r="{rnd.uniform(.4,1):.1f}" fill="#fff"/>')

    # core
    s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="70" ry="38" fill="#6366f1" opacity=".12"/>')
    s.append(f'<circle class="pulse" cx="{cx}" cy="{cy}" r="16" fill="url(#corer)"/>')
    s.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="#fff"/>')

    # repos = bright labelled stars; private ones stay unnamed
    placed = []
    for i, r in enumerate(sorted(public, key=lambda r: -sum(r["_langs"].values()))):
        lang = max(r["_langs"], key=r["_langs"].get) if r["_langs"] else "Other"
        t = 0.25 + 0.7*(i+1)/(len(public)+1)
        x, y = arm_point(lang, t, 0.12)
        rad = 3.5 + math.sqrt(r["stargazers_count"])*2.2
        c = color(lang)
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad*3:.1f}" fill="{c}" opacity=".35" filter="url(#glowr)"/>')
        s.append(f'<circle class="tw" style="--d:{rnd.uniform(2.5,5):.1f}s;--o:-{rnd.uniform(0,5):.1f}s" cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="{c}"/>')
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad*.4:.1f}" fill="#fff"/>')
        if len(placed) < 7 and all(abs(x-px)>70 or abs(y-py)>14 for px,py in placed):
            placed.append((x, y))
            s.append(f'<text x="{x+rad+6:.0f}" y="{y+3:.0f}" font-size="10" font-weight="700" fill="#e0e7ff">{escape(r["name"])}'
                     f'<tspan fill="#8b93c9" font-weight="400"> ★ {r["stargazers_count"]}</tspan></text>')

    # private repos: anonymous grey stars, never named, never counted in the arms
    for i, r in enumerate(sorted(private, key=lambda r: -r["stargazers_count"])):
        t = 0.3 + 0.6*(i+1)/(len(private)+1)
        x, y = arm_point(None, t, 0.55)
        rad = 3.5 + math.sqrt(r["stargazers_count"])*2.2
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad*3:.1f}" fill="#8b949e" opacity=".28" filter="url(#glowr)"/>')
        s.append(f'<circle class="tw" style="--d:{rnd.uniform(2.5,5):.1f}s;--o:-{rnd.uniform(0,5):.1f}s" cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="#8b949e"/>')
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad*.4:.1f}" fill="#fff"/>')
        if len(placed) < 7 and all(abs(x-px)>70 or abs(y-py)>14 for px,py in placed):
            placed.append((x, y))
            s.append(f'<text x="{x+rad+6:.0f}" y="{y+3:.0f}" font-size="10" font-weight="700" fill="#8b93c9">private</text>')

    # shooting stars
    for o in (0, 3.5):
        s.append(f'<line class="shoot" style="--o:{o}s" x1="{80+o*60}" y1="{30+o*10}" x2="{50+o*60}" y2="{18+o*10}" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>')

    # HUD
    stars = sum(r["stargazers_count"] for r in repos)
    s.append('<text x="36" y="46" font-size="9" letter-spacing="3" fill="#7c86ff">REPO GALAXY</text>')
    s.append(f'<text x="36" y="76" font-size="22" font-weight="800" fill="#fff">@{escape(USER)}</text>')
    s.append(f'<text x="36" y="98" font-size="11" fill="#a5b4fc">{stars} stars · {len(repos)} repositories'
             + (f' · {len(private)} private' if private else '') + '</text>')
    s.append('<text x="36" y="114" font-size="9" fill="#6b73b8">'
             + ('Each star is a repository; private ones are left unnamed.' if private else 'Each star is a repository, sized by its stars.')
             + '</text>')
    s.append('<text x="36" y="196" font-size="9" letter-spacing="3" fill="#7c86ff">ARMS</text>')
    for i, (l, b) in enumerate(ranked):
        y = 220 + i*20
        s.append(f'<circle cx="40" cy="{y-3}" r="5" fill="{color(l)}"/>'
                 f'<text x="56" y="{y}" font-size="11" font-weight="700" fill="#e0e7ff">{escape(l)}</text>'
                 f'<text x="190" y="{y}" font-size="11" fill="#a5b4fc" text-anchor="end">{round(100*b/grand)}%</text>')
    s.append(f'<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="18" fill="none" stroke="#4f5bd5" stroke-opacity=".55"/></g></svg>')
    return "\n".join(s)

# ───────────────────────── contribution galaxy (snake replacement) ─────────────────────────
def contrib_galaxy(total, weeks):
    W, H = 900, 220
    rnd = random.Random(42)
    left, top, gx, gy = 40, 52, 16.2, 19
    mx = max((max(w) for w in weeks), default=1) or 1
    palette = ["#3b3f7a", "#6366f1", "#8b5cf6", "#c084fc", "#f0abfc"]

    pts = {}
    for wi, week in enumerate(weeks):
        for di, n in enumerate(week):
            pts[(wi, di)] = (left + wi*gx + rnd.uniform(-3, 3), top + di*gy + rnd.uniform(-3, 3), n)

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
         defs(W, H, "c"), STYLE,
         f'<g clip-path="url(#clipc)"><rect width="{W}" height="{H}" fill="url(#bgc)"/>']
    for _ in range(90):
        s.append(f'<circle class="tw" style="--d:{rnd.uniform(2,7):.1f}s;--o:-{rnd.uniform(0,7):.1f}s" '
                 f'cx="{rnd.uniform(0,W):.0f}" cy="{rnd.uniform(0,H):.0f}" r="{rnd.uniform(.3,.9):.1f}" fill="#fff"/>')

    # constellation lines: connect consecutive active days (same week, next day) and week to week
    lines = []
    for (wi, di), (x, y, n) in pts.items():
        if n == 0: continue
        for nb in ((wi, di+1), (wi+1, di), (wi+1, di+1)):
            if nb in pts and pts[nb][2] > 0:
                x2, y2, _ = pts[nb]
                lines.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
    s.append('<g stroke="#818cf8" stroke-opacity=".28" stroke-width=".7">' + "".join(lines) + '</g>')

    for (wi, di), (x, y, n) in pts.items():
        if n == 0:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r=".9" fill="#4b5090" opacity=".55"/>')
            continue
        lvl = min(4, 1 + int(3.99 * n / mx))
        c, r = palette[lvl], 1.8 + lvl*0.9
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*2.6:.1f}" fill="{c}" opacity=".30" filter="url(#glowc)"/>')
        s.append(f'<circle class="tw" style="--d:{rnd.uniform(2,5):.1f}s;--o:-{rnd.uniform(0,5):.1f}s" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{c}"/>')
        if lvl >= 3:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*.4:.1f}" fill="#fff"/>')

    for o in (0, 2.4, 4.8):
        s.append(f'<line class="shoot" style="--o:{o}s" x1="{60+o*90}" y1="{14+o*6}" x2="{26+o*90}" y2="{2+o*6}" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>')

    s.append('<text x="40" y="30" font-size="9" letter-spacing="3" fill="#7c86ff">CONTRIBUTION CONSTELLATION</text>')
    s.append(f'<text x="{W-40}" y="30" font-size="11" fill="#a5b4fc" text-anchor="end"><tspan font-weight="800" fill="#fff">{total}</tspan> contributions in the last year</text>')
    s.append(f'<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="18" fill="none" stroke="#4f5bd5" stroke-opacity=".55"/></g></svg>')
    return "\n".join(s)

# ───────────────────────── ascii portrait ─────────────────────────
RAMP = " .:-=+*#%@"

def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "galaxy-profile"})
    with urllib.request.urlopen(req, timeout=30) as r: return r.read()

def decode_png(data):
    """Minimal decoder for 8-bit, non-interlaced PNGs (grey, RGB, RGBA)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n": raise ValueError("not a png")
    pos, idat, w, h, ctype = 8, b"", None, None, None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos+8])
        chunk = data[pos+8:pos+8+ln]; pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or inter: raise ValueError("unsupported png variant")
        elif typ == b"IDAT": idat += chunk
        elif typ == b"IEND": break
    if w is None: raise ValueError("no IHDR")
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(bpp, stride): line[i] = (line[i] + line[i-bpp]) & 255
        elif f == 2:
            for i in range(stride): line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                b = prev[i]; c = prev[i-bpp] if i >= bpp else 0
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    return w, h, bpp, bytes(out)

def ascii_lines(w, h, bpp, px, cols=44):
    """Down-sample an image to a luminance ramp; polarity follows the border colour."""
    rows = max(1, round(cols * h / w * 0.55))  # char cells are ~2x taller than wide
    def lum(x, y):
        i = (y*w + x) * bpp
        v = 0.299*px[i] + 0.587*px[i+1] + 0.114*px[i+2] if bpp >= 3 else px[i]
        alpha = px[i+bpp-1] if bpp in (2, 4) else 255
        return v * (alpha/255)
    border = [lum(x, 0) for x in range(0, w, 5)] + [lum(x, h-1) for x in range(0, w, 5)] \
           + [lum(0, y) for y in range(0, h, 5)] + [lum(w-1, y) for y in range(0, h, 5)]
    invert = sum(border)/len(border) > 140
    grid, vals = [], []
    for ry in range(rows):
        row = []
        for rx in range(cols):
            tot = n = 0
            for y in range(ry*h//rows, max(ry*h//rows+1, (ry+1)*h//rows), max(1, h//rows//3)):
                for x in range(rx*w//cols, max(rx*w//cols+1, (rx+1)*w//cols), max(1, w//cols//3)):
                    tot += lum(x, y); n += 1
            v = tot/n
            v = 255 - v if invert else v
            row.append(v); vals.append(v)
        grid.append(row)
    vals.sort()
    lo, hi = vals[len(vals)//20], vals[-max(1, len(vals)//20)]
    span = max(hi - lo, 1e-6)
    out = []
    for row in grid:
        line = "".join(RAMP[max(0, min(len(RAMP)-1, int((v-lo)/span*(len(RAMP)-1) + .5)))] for v in row)
        out.append(line.rstrip())
    return out

def avatar_svg(lines):
    fs, cw, lh = 10.5, 6.4, 11.5
    cols = max(len(l) for l in lines) or 1
    padx, padtop, padbot = 22, 46, 30
    W = round(cols*cw + padx*2)
    H = round(len(lines)*lh + padtop + padbot)
    head = (f'<text x="{padx}" y="24" font-size="8" letter-spacing="3" fill="#7c86ff">ASCII PORTRAIT</text>'
            f'<text x="{W-padx}" y="24" font-size="8" letter-spacing="1" fill="#6b73b8" text-anchor="end">'
            f'github.com/{escape(USER)}</text>')
    art = "".join(f'<text x="{padx}" y="{round(padtop + i*lh)}" xml:space="preserve">{escape(l)}</text>'
                  for i, l in enumerate(lines))
    prompt = (f'<line x1="{padx}" y1="{H-20}" x2="{W-padx}" y2="{H-20}" stroke="#4f5bd5" stroke-opacity=".45"/>'
              f'<text x="{padx}" y="{H-6}" font-size="9" fill="#8b93c9">cata5@github:~$ '
              f'<tspan class="cur" fill="#a5b4fc">_</tspan></text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" xml:space="preserve">
<title>ASCII portrait of @{escape(USER)}</title>
<desc>Luminance-rendered ASCII art generated from the GitHub profile picture.</desc>
<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#e0e7ff"/><stop offset="1" stop-color="#818cf8"/></linearGradient>
  <filter id="ablur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.6"/></filter></defs>
<style>text{{font-family:'JetBrains Mono','Fira Code',ui-monospace,Menlo,monospace}}
.cur{{animation:blink 1.2s steps(1) infinite}}@keyframes blink{{50%{{opacity:0}}}}</style>
<rect width="{W}" height="{H}" rx="16" fill="#05070f"/>
<rect x=".75" y=".75" width="{W-1.5}" height="{H-1.5}" rx="16" fill="none" stroke="#4f5bd5" stroke-opacity=".55"/>
{head}
<g filter="url(#ablur)" opacity=".45" fill="#a5b4fc">{art}</g>
<g fill="url(#ag)">{art}</g>
{prompt}
</svg>'''

def write_avatar(cols=44):
    w, h, bpp, px = decode_png(fetch_bytes(f"https://github.com/{USER}.png?size=420"))
    lines = ascii_lines(w, h, bpp, px, cols)
    with open(os.path.join(OUT, "avatar-ascii.svg"), "w", encoding="utf-8") as f:
        f.write(avatar_svg(lines))
    return len(lines)

# ───────────────────────── main ─────────────────────────
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if MOCK:
        repos, (total, weeks) = mock_repos(), mock_calendar()
    else:
        repos = fetch_repos()
        total, weeks = fetch_calendar()
        try:
            rows = write_avatar()
            print("ascii portrait:", rows, "rows")
        except Exception as e: print("avatar render skipped:", e, file=sys.stderr)
    open(os.path.join(OUT, "repo-galaxy.svg"), "w", encoding="utf-8").write(repo_galaxy(repos))
    open(os.path.join(OUT, "contrib-galaxy.svg"), "w", encoding="utf-8").write(contrib_galaxy(total, weeks))
    print("done:", len(repos), "repos,", total, "contributions ->", os.path.abspath(OUT))