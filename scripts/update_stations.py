#!/usr/bin/env python3
import json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
KML = ROOT / "stations.kml"
JSON = ROOT / "stations.json"
INDEX = ROOT / "index.html"
JST = timezone(timedelta(hours=9))

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
    # Coordinates are the stable identity across monthly KML exports.
    return f'{float(s["lat"]):.6f},{float(s["lng"]):.6f}'

def reverse_geocode(lat, lng, muni):
    url = ("https://mreversegeocoder.gsi.go.jp/reverse-geocoder/"
           f"LonLatToAddress?lat={urllib.parse.quote(str(lat))}&lon={urllib.parse.quote(str(lng))}")
    data = json.loads(get_text(url)).get("results") or {}
    # API can return "01107", while muni.js uses "1107".
    # Normalize both sides by removing leading zeroes.
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
    return {
        "prefecture": pref,
        "city": city,
        "town": town,
        "address": f"{pref}{city}{town}",
    }

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
        # Reuse address, but always take current KML name.
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

# Automatically update the visible data date in index.html.
if INDEX.exists():
    today = datetime.now(JST).strftime("%Y.%m.%d")
    text = INDEX.read_text(encoding="utf-8")
    text = re.sub(r"DATA UPDATE \d{4}\.\d{2}\.\d{2}", f"DATA UPDATE {today}", text)
    INDEX.write_text(text, encoding="utf-8")

print(f"KML points: {len(fresh)}")
print(f"Address reused: {reused}")
print(f"Address newly fetched: {new_count}")
print(f"Address failed: {failed}")
print(f"Removed since previous JSON: {max(0, len(old)-len(fresh))}")
