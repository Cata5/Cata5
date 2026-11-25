#!/usr/bin/env python3
"""Generates two animated SVGs for a GitHub profile README:
  assets/repo-galaxy.svg     - every repo is a star, language = spiral arm
  assets/contrib-galaxy.svg  - your contribution calendar as a living constellation
No dependencies (stdlib only). Run in GitHub Actions or locally:
  GITHUB_TOKEN=xxx python scripts/galaxy.py Cata5
  python scripts/galaxy.py Cata5 --mock      # offline preview
"""
import json, math, os, random, sys, urllib.request
from collections import defaultdict
from xml.sax.saxutils import escape

USER = next((a for a in sys.argv[1:] if not a.startswith("--")), "Cata5")
MOCK = "--mock" in sys.argv
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

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
    repos = api(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner&sort=updated")
    repos = [r for r in repos if not r["fork"]]
    for r in repos:
        try: r["_langs"] = api(r["languages_url"])
        except Exception: r["_langs"] = {r["language"]: 1} if r["language"] else {}
    return repos

def fetch_calendar():
    q = """query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{
      totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
    body = json.dumps({"query": q, "variables": {"u": USER}}).encode()
    d = api("https://api.github.com/graphql", body)
    cal = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return cal["totalContributions"], [[day["contributionCount"] for day in w["contributionDays"]] for w in cal["weeks"]]

def mock_repos():
    names = [("CataAI-Ultra","Python",3),("Proiect-Python","Python",1),("EzyAid","JavaScript",2),
             ("TranslateEdu","Python",0),("Portfolio","TypeScript",4),("Blender-Scenes","HTML",0),
             ("Arduino-Lab","C++",1),("NextShop","TypeScript",2),("Styles","CSS",0)]
    return [{"name":n,"language":l,"stargazers_count":s,"_langs":{l:random.randint(3000,40000)}} for n,l,s in names]

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

    totals = defaultdict(int)
    for r in repos:
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

    # repos = bright labelled stars
    placed = []
    for i, r in enumerate(sorted(repos, key=lambda r: -sum(r["_langs"].values()))):
        lang = max(r["_langs"], key=r["_langs"].get) if r["_langs"] else "Other"
        t = 0.25 + 0.7*(i+1)/(len(repos)+1)
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

    # shooting stars
    for o in (0, 3.5):
        s.append(f'<line class="shoot" style="--o:{o}s" x1="{80+o*60}" y1="{30+o*10}" x2="{50+o*60}" y2="{18+o*10}" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>')

    # HUD
    stars = sum(r["stargazers_count"] for r in repos)
    s.append('<text x="36" y="46" font-size="9" letter-spacing="3" fill="#7c86ff">REPO GALAXY</text>')
    s.append(f'<text x="36" y="76" font-size="22" font-weight="800" fill="#fff">@{escape(USER)}</text>')
    s.append(f'<text x="36" y="98" font-size="11" fill="#a5b4fc">{stars} stars · {len(repos)} repositories</text>')
    s.append('<text x="36" y="114" font-size="9" fill="#6b73b8">Each star is a repository, sized by its stars.</text>')
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

# ───────────────────────── main ─────────────────────────
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if MOCK:
        repos, (total, weeks) = mock_repos(), mock_calendar()
    else:
        repos = fetch_repos()
        try: total, weeks = fetch_calendar()
        except Exception as e:
            print("calendar fetch failed (token needed):", e); total, weeks = mock_calendar()
    open(os.path.join(OUT, "repo-galaxy.svg"), "w", encoding="utf-8").write(repo_galaxy(repos))
    open(os.path.join(OUT, "contrib-galaxy.svg"), "w", encoding="utf-8").write(contrib_galaxy(total, weeks))
    print("done:", len(repos), "repos,", total, "contributions")
