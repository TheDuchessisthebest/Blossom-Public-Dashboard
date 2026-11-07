"""Lightweight rose/cherry-blossom background for the public Streamlit viewer.

Uses the user's supplied blossom photo as a static page background and pure
CSS animated petals. No external assets, network requests, JS or controls.
"""
from __future__ import annotations
import base64
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def render_theme(asset_root: Path | None = None) -> str:
    root = Path(__file__).resolve().parent if asset_root is None else Path(asset_root)
    photo = root/'assets'/'cherry_blossom_bg.jpg'
    if photo.is_file():
        # Escapes nothing from the file: base64 alphabet is safe in a CSS URL.
        b64=base64.b64encode(photo.read_bytes()).decode('ascii')
        background = ('linear-gradient(110deg,rgba(12,7,17,.90) 0%,rgba(18,8,20,.79) '
                      '53%,rgba(15,8,20,.81) 100%),'
                      'url("data:image/jpeg;base64,'+b64+'")')
    else:
        background='radial-gradient(ellipse at 70% 20%,#3d1e3b,#100b16 76%)'
    petals=''.join(f'<span class="blossom-falling-petal p{i}"></span>' for i in range(1,17))
    return f'''<style>
/* Photo stays fixed during market-fragment reruns, petals never catch clicks. */
.stApp, [data-testid="stAppViewContainer"] {{
  background-image:{background} !important;
  background-position:center 27% !important;
  background-size:cover !important;
  background-attachment:fixed !important;
  color:#fff1f8 !important;
}}
[data-testid="stMain"], section.main {{background:transparent !important;position:relative;}}
header[data-testid="stHeader"]{{background:rgba(18,10,22,.2)!important;}}
/* Text remains on dark translucent panels, rather than directly on photo. */
.public-card,.public-ref,.blossom-board,.notice-public{{backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);}}
.public-card{{background:linear-gradient(150deg,rgba(38,19,37,.93),rgba(23,14,27,.94))!important;}}
.public-ref{{background:linear-gradient(150deg,rgba(39,23,42,.94),rgba(24,16,29,.92))!important;}}
.blossom-board{{background:linear-gradient(135deg,rgba(37,21,38,.95),rgba(22,16,28,.94))!important;}}
.hero-public{{text-shadow:0 2px 12px rgba(5,0,8,.65)}}
.public-call.up{{color:#91edb5 !important;}}
.public-call.down{{color:#ff92a8 !important;}}
.public-pick b.up{{color:#91edb5 !important;}}
.public-pick b.down{{color:#ff92a8 !important;}}
.public-call.locked.up{{text-shadow:0 0 12px rgba(110,238,166,.7),0 0 30px rgba(120,234,166,.35);}}
.public-call.locked.down{{text-shadow:0 0 12px rgba(255,120,148,.68),0 0 30px rgba(255,115,147,.33);}}
/* Decorative fall layer is fixed above the photo, never interactive. */
.blossom-floating-layer{{position:fixed;inset:0;z-index:999;overflow:hidden;pointer-events:none;
 contain:layout style;isolation:isolate;}}
.blossom-falling-petal{{position:absolute;top:-8vh;width:14px;height:11px;opacity:0;
 background:linear-gradient(135deg,#ffe5f1,#ff99c1);border-radius:80% 15% 70% 35%;
 box-shadow:0 0 5px rgba(244,162,200,.14);animation:blossom-fall linear infinite;
 transform:translate3d(0,-30px,0) rotate(0deg);will-change:transform,opacity;}}
@keyframes blossom-fall{{
  0%{{transform:translate3d(0,-10vh,0) rotate(0deg);opacity:0;}}
  9%{{opacity:.58;}}
  47%{{transform:translate3d(42px,47vh,0) rotate(210deg);opacity:.45;}}
  100%{{transform:translate3d(-33px,108vh,0) rotate(510deg);opacity:0;}}
}}
.blossom-falling-petal.p1{{left:3%;animation-duration:20s;animation-delay:-8s}}
.blossom-falling-petal.p2{{left:10%;animation-duration:24s;animation-delay:-16s}}
.blossom-falling-petal.p3{{left:17%;animation-duration:23s;animation-delay:-11s}}
.blossom-falling-petal.p4{{left:25%;animation-duration:27s;animation-delay:-19s}}
.blossom-falling-petal.p5{{left:32%;animation-duration:22s;animation-delay:-3s}}
.blossom-falling-petal.p6{{left:39%;animation-duration:26s;animation-delay:-14s}}
.blossom-falling-petal.p7{{left:46%;animation-duration:28s;animation-delay:-21s}}
.blossom-falling-petal.p8{{left:53%;animation-duration:23s;animation-delay:-9s}}
.blossom-falling-petal.p9{{left:60%;animation-duration:26s;animation-delay:-7s}}
.blossom-falling-petal.p10{{left:67%;animation-duration:21s;animation-delay:-17s}}
.blossom-falling-petal.p11{{left:74%;animation-duration:27s;animation-delay:-5s}}
.blossom-falling-petal.p12{{left:81%;animation-duration:24s;animation-delay:-18s}}
.blossom-falling-petal.p13{{left:88%;animation-duration:25s;animation-delay:-12s}}
.blossom-falling-petal.p14{{left:95%;animation-duration:29s;animation-delay:-22s}}
.blossom-falling-petal.p15{{left:42%;animation-duration:31s;animation-delay:-25s}}
.blossom-falling-petal.p16{{left:78%;animation-duration:19s;animation-delay:-15s}}
@media(max-width:650px){{
  .stApp,[data-testid="stAppViewContainer"]{{background-attachment:scroll!important;}}
  .blossom-falling-petal:nth-child(n+10){{display:none;}}
  .blossom-falling-petal{{width:10px;height:8px;}}
  .public-card,.public-ref,.blossom-board{{backdrop-filter:none;}}
}}
@media(prefers-reduced-motion:reduce){{.blossom-falling-petal{{display:none;}}}}
</style><div class="blossom-floating-layer" aria-hidden="true">{petals}</div>'''
