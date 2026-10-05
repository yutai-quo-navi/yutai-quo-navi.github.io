#!/usr/bin/env python3
import html, json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
KML = ROOT / "stations.kml"
JSON = ROOT / "stations.json"
INDEX = ROOT / "index.html"
AREA_DIR = ROOT / "area"
BRAND_DIR = ROOT / "brand"
SITEMAP = ROOT / "sitemap.xml"
ROBOTS = ROOT / "robots.txt"
JST = timezone(timedelta(hours=9))
BASE = "https://yutai-quo-navi.github.io"

PREF_SLUG = {
    "北海道":"hokkaido","青森県":"aomori","岩手県":"iwate","宮城県":"miyagi","秋田県":"akita","山形県":"yamagata","福島県":"fukushima",
    "茨城県":"ibaraki","栃木県":"tochigi","群馬県":"gunma","埼玉県":"saitama","千葉県":"chiba","東京都":"tokyo","神奈川県":"kanagawa",
    "新潟県":"niigata","富山県":"toyama","石川県":"ishikawa","福井県":"fukui","山梨県":"yamanashi","長野県":"nagano",
    "岐阜県":"gifu","静岡県":"shizuoka","愛知県":"aichi","三重県":"mie",
    "滋賀県":"shiga","京都府":"kyoto","大阪府":"osaka","兵庫県":"hyogo","奈良県":"nara","和歌山県":"wakayama",
    "鳥取県":"tottori","島根県":"shimane","岡山県":"okayama","広島県":"hiroshima","山口県":"yamaguchi",
    "徳島県":"tokushima","香川県":"kagawa","愛媛県":"ehime","高知県":"kochi",
    "福岡県":"fukuoka","佐賀県":"saga","長崎県":"nagasaki","熊本県":"kumamoto","大分県":"oita","宮崎県":"miyazaki","鹿児島県":"kagoshima","沖縄県":"okinawa",
}

def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "yutai-quo-navi/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8")

def municipality_table():
    txt = get_text("https://maps.gsi.go.jp/js/muni.js")
    out = {}
    for code, value in re.findall(r'MUNI_ARRAY\["(\d+)"\]\s*=\s*[\'"]([^\'"]+)[\'"]', txt):
        p = value.split(",")
        if len(p) >= 4:
            norm_code = str(int(code)) if code.isdigit() else code
            out[norm_code] = {"prefecture": p[1], "city": p[3].replace("\u3000", "")}
    return out

def parse_kml(path):
    root = ET.parse(path).getroot()
    ns = {"k":"http://www.opengis.net/kml/2.2"}
    rows = []
    for pm in root.findall(".//k:Placemark", ns):
        n = pm.find("k:name", ns)
        c = pm.find(".//k:Point/k:coordinates", ns)
        if c is None or not (c.text or "").strip():
            continue
        parts = c.text.strip().split(",")
        if len(parts) < 2:
            continue
        rows.append({
            "name": ((n.text if n is not None else "") or "名称不明").strip(),
            "lat": round(float(parts[1]), 7),
            "lng": round(float(parts[0]), 7),
        })
    return rows

def key(s):
    return f'{float(s["lat"]):.6f},{float(s["lng"]):.6f}'

def reverse_geocode(lat, lng, muni):
    url = ("https://mreversegeocoder.gsi.go.jp/reverse-geocoder/"
           f"LonLatToAddress?lat={urllib.parse.quote(str(lat))}&lon={urllib.parse.quote(str(lng))}")
    data = json.loads(get_text(url)).get("results") or {}
    raw_code = data.get("muniCd")
    code = str(raw_code or "").strip()
    if code.isdigit():
        code = str(int(code))
    town = str(data.get("lv01Nm") or "").strip()
    m = muni.get(code, {})
    pref = m.get("prefecture","")
    city = m.get("city","")
    if code and (not pref or not city):
        raise ValueError(f"municipality code {raw_code!r} (normalized {code!r}) not found in muni.js")
    return {"prefecture": pref, "city": city, "town": town, "address": f"{pref}{city}{town}"}

def brand_of(name):
    n = str(name or "")
    if re.search(r"ENEOS|エネオス", n, re.I):
        return "eneos"
    if re.search(r"JA[-‐‑–—－ ]?SS|JA－SS", n, re.I):
        return "ja-ss"
    return "other"

def maps_url(s):
    q = urllib.parse.quote(f'{s.get("name","")} {s.get("lat","")},{s.get("lng","")}')
    return f"https://www.google.com/maps/search/?api=1&query={q}"

def page_template(title, description, canonical, h1, intro, body, breadcrumb=""):
    today = datetime.now(JST).strftime("%Y.%m.%d")
    # Reuse the homepage identity so automated DB updates preserve common CI.
    homepage = INDEX.read_text(encoding="utf-8")
    header = re.search(r'<header class="site-header">.*?</header>', homepage, re.S).group(0)
    header = header.replace('aria-current="page"', 'aria-current="true"')
    creator = re.search(r'<a class="creator-link".*?</a>', homepage, re.S).group(0)
    creator = creator.replace('./assets/', '/assets/')
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f4f7f6">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="index,follow">
<style>
body{{margin:0;background:radial-gradient(circle at 90% 0%,#e7f3ee 0,transparent 32rem),#f4f7f6;color:#18222d;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif}}
.wrap{{max-width:720px;margin:auto;padding:24px 18px 40px}}a{{color:#0c7658}}.crumb{{font-size:12px;color:#71808e;margin-bottom:18px}}
h1{{font-size:clamp(26px,5vw,40px);line-height:1.25;margin:0 0 12px}}.lead{{color:#5f6c75;line-height:1.9}}
.grid{{display:grid;gap:10px;margin-top:22px}}.card{{background:#fff;border:1px solid #e6eaee;border-radius:22px;padding:16px 18px}}
.name{{font-weight:800;font-size:16px}}.addr{{margin-top:5px;color:#66727b;font-size:13px}}.meta{{margin-top:7px;font-size:12px;color:#87929a}}
.nav{{margin:22px 0;padding:14px;background:#fff;border:1px solid #e6eaee;border-radius:14px;line-height:2}}
@media(max-width:520px){{.wrap{{padding:20px 14px 32px}}}}
</style>
<link rel="stylesheet" href="/assets/brand.css?v=20261005-brand2">
</head>
<body class="gs-tool static-tool">{header}<main class="wrap">
<div class="crumb">{breadcrumb}</div>
<h1>{html.escape(h1)}</h1>
<p class="lead">{intro}</p>
{body}
</main><footer class="site-footer"><div class="site-footer-brand">株主優待券店舗とQUOガソリン給油検索</div>
<div class="footer-links"><a href="/">QUOガソリン給油検索</a><a href="/area/">都道府県一覧</a></div>
<p>この一覧ページでは現在地を取得しません。店舗の閉店・取扱変更等が反映されていない場合があります。ご利用前に店舗へご確認ください。</p>
<div class="data-update">DATA UPDATE {today}</div>{creator}</footer></body></html>"""

def generate_static_pages(stations):
    AREA_DIR.mkdir(exist_ok=True)
    BRAND_DIR.mkdir(exist_ok=True)

    by_pref = {}
    for s in stations:
        pref = s.get("prefecture") or "地域不明"
        by_pref.setdefault(pref, []).append(s)

    area_links = []
    sitemap_urls = [f"{BASE}/", f"{BASE}/area/", f"{BASE}/brand/eneos/", f"{BASE}/brand/ja-ss/"]

    for pref in sorted(by_pref, key=lambda p: (PREF_SLUG.get(p, "zz-"+p))):
        if pref == "地域不明":
            continue
        slug = PREF_SLUG.get(pref)
        if not slug:
            continue
        items = sorted(by_pref[pref], key=lambda s: (s.get("city",""), s.get("name","")))
        cards = []
        for s in items:
            cards.append(
                f'<div class="card"><div class="name">{html.escape(s.get("name",""))}</div>'
                f'<div class="addr">{html.escape(s.get("address",""))}</div>'
                f'<div class="meta"><a href="{maps_url(s)}" rel="nofollow">Googleマップで確認</a></div></div>'
            )
        city_count = len({s.get("city","") for s in items if s.get("city")})
        body = f'<div class="nav">掲載 {len(items)}店舗 ／ {city_count}市区町村</div><div class="grid">{"".join(cards)}</div>'
        title = f"{pref}のQUOカード対応ガソリンスタンド・GS一覧｜ENEOS・JA-SS｜優待QUOナビ"
        desc = f"{pref}でQUOカード・クオカードの支払いに対応するガソリンスタンド・GSを一覧掲載。ENEOS（エネオス）やJA-SSなど、株主優待でもらったQUOカードの利用先探しに。"
        path = AREA_DIR / slug
        path.mkdir(parents=True, exist_ok=True)
        canonical = f"{BASE}/area/{slug}/"
        (path / "index.html").write_text(page_template(
            title, desc, canonical,
            f"{pref}のQUOカード対応ガソリンスタンド・GS",
            f"{html.escape(pref)}でQUOカード・クオカードの支払いに対応するガソリンスタンドを掲載しています。ENEOS（エネオス）やJA-SSなど、給油時の支払い先や株主優待QUOカードの利用先探しにご利用ください。",
            body,
            '<a href="/">トップ</a> › <a href="/area/">都道府県一覧</a>'
        ), encoding="utf-8")
        area_links.append(f'<li><a href="./{slug}/">{html.escape(pref)}</a>（{len(items)}店舗）</li>')
        sitemap_urls.append(canonical)

    area_body = f'<div class="nav"><ul>{"".join(area_links)}</ul></div>'
    (AREA_DIR / "index.html").write_text(page_template(
        "都道府県別 QUOカード対応ガソリンスタンド・GS一覧｜優待QUOナビ",
        "全国のQUOカード・クオカード対応ガソリンスタンドを都道府県別に掲載。ENEOS（エネオス）やJA-SSなどの対応店舗を探せます。",
        f"{BASE}/area/",
        "都道府県別 QUOカード対応ガソリンスタンド・GS一覧",
        "QUOカード・クオカードで支払いできるガソリンスタンドを都道府県別に確認できます。",
        area_body,
        '<a href="/">トップ</a>'
    ), encoding="utf-8")

    for brand, label in [("eneos","ENEOS（エネオス）"),("ja-ss","JA-SS")]:
        items = [s for s in stations if brand_of(s.get("name")) == brand]
        groups = {}
        for s in items:
            groups.setdefault(s.get("prefecture") or "地域不明", []).append(s)
        sections = []
        for pref in sorted(groups, key=lambda p: (PREF_SLUG.get(p, "zz-"+p))):
            cards = []
            for s in sorted(groups[pref], key=lambda x:(x.get("city",""),x.get("name",""))):
                cards.append(
                    f'<div class="card"><div class="name">{html.escape(s.get("name",""))}</div>'
                    f'<div class="addr">{html.escape(s.get("address",""))}</div>'
                    f'<div class="meta"><a href="{maps_url(s)}" rel="nofollow">Googleマップで確認</a></div></div>'
                )
            sections.append(f'<h2>{html.escape(pref)}</h2><div class="grid">{"".join(cards)}</div>')
        path = BRAND_DIR / brand
        path.mkdir(parents=True, exist_ok=True)
        canonical = f"{BASE}/brand/{brand}/"
        title = f"{label}でQUOカードが使えるガソリンスタンド一覧｜優待QUOナビ"
        desc = f"{label}でQUOカード・クオカードの支払いに対応するガソリンスタンドを一覧掲載。株主優待QUOカードの利用先探しにも。"
        (path / "index.html").write_text(page_template(
            title, desc, canonical,
            f"{label}でQUOカードが使えるガソリンスタンド",
            f"{html.escape(label)}のうち、QUOカード・クオカードの支払いに対応する掲載店舗を一覧で確認できます。",
            f'<div class="nav">掲載 {len(items)}店舗</div>{"".join(sections)}',
            '<a href="/">トップ</a> › ブランド別'
        ), encoding="utf-8")

    today = datetime.now(JST).date().isoformat()
    xml = ['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in sitemap_urls:
        xml.append(f"<url><loc>{html.escape(url)}</loc><lastmod>{today}</lastmod></url>")
    xml.append("</urlset>")
    SITEMAP.write_text("\n".join(xml) + "\n", encoding="utf-8")
    ROBOTS.write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/yutai-map/sitemap.xml\n", encoding="utf-8")

if not KML.exists():
    raise SystemExit("stations.kml がありません。My Mapsから書き出したKMLを stations.kml の名前で置いてください。")

old = []
if JSON.exists():
    try:
        old = json.loads(JSON.read_text(encoding="utf-8"))
    except Exception:
        old = []
cache = {key(x): x for x in old if "lat" in x and "lng" in x}

fresh = parse_kml(KML)
muni = municipality_table()
new_count = reused = failed = 0

for i, s in enumerate(fresh, 1):
    prev = cache.get(key(s))
    if prev and prev.get("prefecture") and prev.get("city"):
        for f in ("prefecture","city","town","address"):
            s[f] = prev.get(f,"")
        reused += 1
        continue
    try:
        s.update(reverse_geocode(s["lat"], s["lng"], muni))
        new_count += 1
    except Exception as e:
        print(f"WARN {i}/{len(fresh)} {s['name']}: {e}")
        s.update({"prefecture":"","city":"","town":"","address":""})
        failed += 1
    time.sleep(0.35)

JSON.write_text(json.dumps(fresh, ensure_ascii=False, separators=(",",":")), encoding="utf-8")

if INDEX.exists():
    today = datetime.now(JST).strftime("%Y.%m.%d")
    text = INDEX.read_text(encoding="utf-8")
    text = re.sub(r"DATA UPDATE \d{4}\.\d{2}\.\d{2}", f"DATA UPDATE {today}", text)
    INDEX.write_text(text, encoding="utf-8")

generate_static_pages(fresh)

print(f"KML points: {len(fresh)}")
print(f"Address reused: {reused}")
print(f"Address newly fetched: {new_count}")
print(f"Address failed: {failed}")
print(f"Removed since previous JSON: {max(0, len(old)-len(fresh))}")
print("SEO pages: area index + prefectures + ENEOS + JA-SS + sitemap + robots")
