"""Pull every feed into data/*.json. Stdlib only. Run by GitHub Actions every 15 min.
ponytail: one file, one function per source; a failing source logs and keeps the old file.
"""
import json, os, re, time, hashlib, html
import urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UA = {"User-Agent": "Mozilla/5.0 (fortnite-command-center; personal dashboard)"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

def get(url, timeout=30, tries=3):
    req = urllib.request.Request(url, headers=UA)
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or n == tries - 1:
                raise
            time.sleep(8 * (n + 1))  # reddit rate-limits back-to-back hits

def save(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def load(name, default):
    try:
        return json.load(open(os.path.join(OUT, name), encoding="utf-8"))
    except Exception:
        return default

def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------- shop + self-built history ----------
def shop():
    d = json.loads(get("https://fortnite-api.com/v2/shop"))["data"]
    today = d["date"][:10]
    hist = load("history.json", {})          # itemId -> {"name","first","last","count"}
    entries = []
    for e in d["entries"]:
        items = e.get("brItems") or []
        if not items:
            continue
        lead = items[0]
        img = None
        nda = e.get("newDisplayAsset") or {}
        ri = nda.get("renderImages") or []
        if ri:
            img = ri[0].get("image")
        if not img:
            img = (lead.get("images") or {}).get("icon")
        ids = [i["id"] for i in items]
        for i in items:
            h = hist.get(i["id"])
            if h:
                if h["last"] != today:            # first sighting today: roll last -> prev
                    h["prev"], h["last"], h["count"] = h["last"], today, h["count"] + 1
            else:
                hist[i["id"]] = {"name": i["name"], "first": today, "last": today, "prev": None, "count": 1}
        h0 = hist[lead["id"]]
        prev = h0.get("prev")
        entries.append({
            "offerId": e["offerId"], "name": lead["name"], "type": lead["type"]["displayValue"],
            "rarity": lead["rarity"]["value"], "series": (lead.get("series") or {}).get("value"),
            "price": e["finalPrice"], "regular": e["regularPrice"], "img": img,
            "in": e["inDate"], "out": e["outDate"], "section": (e.get("layout") or {}).get("name"),
            "bundle": (e.get("bundle") or {}).get("name"), "items": ids,
            "isNew": h0["first"] == today and h0["count"] == 1,
            "lastSeen": prev if prev and prev != today else None,
            "appearances": h0["count"],
        })
    save("history.json", hist)
    save("shop.json", {"date": today, "fetched": iso(datetime.now(timezone.utc)), "count": len(entries), "entries": entries})

# ---------- Epic status ----------
def status():
    d = json.loads(get("https://status.epicgames.com/api/v2/summary.json"))
    comps = [{"name": c["name"], "status": c["status"]} for c in d["components"] if "ortnite" in c["name"] or c["name"] in ("Login", "Matchmaking", "Parties, Friends, and Messaging")]
    inc = [{"name": i["name"], "status": i["status"], "impact": i["impact"], "updated": i["updated_at"], "url": i["shortlink"]} for i in d.get("incidents", [])]
    save("status.json", {"overall": d["status"], "components": comps, "incidents": inc, "fetched": iso(datetime.now(timezone.utc))})

# ---------- Epic in-game news ----------
def news():
    d = json.loads(get("https://fortnite-api.com/v2/news/br"))["data"]
    save("news.json", {"date": d.get("date"), "items": [{"title": m.get("title"), "body": m.get("body"), "img": m.get("image") or m.get("tileImage"), "url": m.get("websiteUrl")} for m in d.get("motds") or []]})

# ---------- RSS / Atom merge ----------
FEEDS = [
    ("leaks",  "r/FortniteLeaks", "https://www.reddit.com/r/FortniteLeaks/new.rss?limit=25"),
    ("news",   "r/FortNiteBR",    "https://www.reddit.com/r/FortNiteBR/new.rss?limit=25"),
    ("video",  "HYPEX",           "https://www.youtube.com/feeds/videos.xml?channel_id=UCR91MC-1uTn10J7bh-V-OqQ"),
    ("video",  "ShiinaBR",        "https://www.youtube.com/feeds/videos.xml?channel_id=UCBenOYHG3jne-zqHJYn5sxQ"),
    ("video",  "iFireMonkey",     "https://www.youtube.com/feeds/videos.xml?channel_id=UCOt3tWBRi4HTFce3jGMukiQ"),
    ("news",   "IGN",             "https://www.ign.com/rss/articles/feed?tags=fortnite"),
    ("status", "Epic Status",     "https://status.epicgames.com/history.rss"),
]
NS = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/", "yt": "http://www.youtube.com/xml/schemas/2015"}

def _text(el, *paths):
    for p in paths:
        x = el.find(p, NS)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""

def _when(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(s)
        except Exception:
            return None

def parse_feed(kind, src, raw):
    root = ET.fromstring(raw)
    out = []
    if root.tag.endswith("feed"):                       # Atom (reddit, youtube)
        for e in root.findall("a:entry", NS):
            link = e.find("a:link", NS)
            url = link.get("href") if link is not None else ""
            thumb = e.find("m:group/m:thumbnail", NS)
            body = _text(e, "a:content", "a:summary", "m:group/m:description")
            cat = e.find("a:category", NS)
            sub = (cat.get("term") if cat is not None else "") or ""
            k, sname = (("leaks", "r/FortniteLeaks") if "leaks" in sub.lower() else ("news", "r/FortNiteBR")) if src == "reddit" else (kind, src)
            out.append({"kind": k, "src": sname, "title": _text(e, "a:title"), "url": url,
                        "when": _text(e, "a:published", "a:updated"),
                        "img": thumb.get("url") if thumb is not None else _img(body),
                        "body": _strip(body)[:280]})
    else:                                               # RSS 2.0 (IGN, statuspage)
        for it in root.iter("item"):
            body = (it.findtext("description") or "")
            out.append({"kind": kind, "src": src, "title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                        "when": it.findtext("pubDate") or "", "img": _img(body), "body": _strip(body)[:280]})
    for o in out:
        dt = _when(o["when"])
        o["when"] = iso(dt) if dt else None
        o["id"] = hashlib.md5(o["url"].encode()).hexdigest()[:10]
    return out

def _img(s):
    m = re.search(r'<img[^>]+src="([^"]+)"', s or "")
    return html.unescape(m.group(1)) if m else None

def _strip(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def feed():
    old = {i["id"]: i for i in load("feed.json", {}).get("items", [])}
    items = {}
    for kind, src, url in FEEDS:
        try:
            parsed = None
            if "reddit.com" in url and any(k for k in items if items[k]["src"].startswith("r/")):
                time.sleep(61)                       # reddit: one unauthenticated RSS hit per minute per client
            for u in url.split("|"):                 # alternates: first that answers AND parses wins
                try:
                    parsed = parse_feed(kind, src, get(u)); break
                except Exception as ex:
                    print(f"feed retry {src}: {ex}"); time.sleep(10)
            if parsed is None:
                raise RuntimeError("all alternates failed")
            for it in parsed:
                items[it["id"]] = it
        except Exception as ex:
            print(f"feed FAIL {src}: {ex}")
            for k, v in old.items():
                if v["src"] == src:
                    items[k] = v
        time.sleep(6)  # reddit 429s on back-to-back hits
    merged = sorted(items.values(), key=lambda x: x["when"] or "", reverse=True)[:400]
    save("feed.json", {"fetched": iso(datetime.now(timezone.utc)), "items": merged})

if __name__ == "__main__":
    for fn in (shop, status, news, feed):
        try:
            fn(); print("ok", fn.__name__)
        except Exception as ex:                          # keep the last good file
            print("FAIL", fn.__name__, ex)
    save("meta.json", {"fetched": iso(datetime.now(timezone.utc))})
