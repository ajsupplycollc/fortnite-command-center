"""Generic IGN wiki checklist scraper -> trackers/<slug>.json
Usage: python ign_checklist.py <ign_wiki_url> <slug> "<Title>"
IGN pages embed data as Next.js __NEXT_DATA__ -> htmlEntities[].values.html with
<checkbox data-checklist-task-id="ID">label</checkbox> tags. Images become data URIs so the
tracker works offline and never depends on IGN's image host.
"""
import sys, re, json, html, base64, os, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128"}

def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()

def main(url, slug, title):
    page = get(url).decode("utf-8", "ignore")
    nd = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S).group(1))
    ents = nd["props"]["pageProps"]["page"]["page"]["htmlEntities"]
    body = "\n".join((e.get("values") or {}).get("html") or "" for e in ents)
    CB = r'<checkbox[^>]*data-checklist-task-id="(\d+)"[^>]*>(.*?)</checkbox>'
    strip = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", s))).strip()
    groups, cur, last = [], None, None
    # Two IGN table shapes: (a) <th> row = group header, <td> cells = items (Sprites);
    # (b) one table per item: checkbox row, then <th>label</th><td>value</td> field rows (Admin codes).
    heading = title
    for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>|<tr>(.*?)</tr>", body, re.S):
        if m.group(1) is not None:
            heading = strip(m.group(1)) or heading; continue
        tr = m.group(2)
        ths = re.findall(r"<th[^>]*>(.*?)</th>", tr, re.S)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if ths and tds and last is not None and not re.search(CB, tr):   # shape (b) field row
            last["lines"].append(f"{strip(ths[0])}: {strip(tds[0])}")
            continue
        if ths and not tds:                                                # shape (a) group header
            # one th = a named group; several th = column headers, so the section heading names the group
            cur = {"group": strip(ths[0]) if len(ths) == 1 else heading, "items": []}
            groups.append(cur); continue
        for td in tds:
            tasks = re.findall(CB, td, re.S)
            if not tasks:
                continue
            if cur is None:
                cur = {"group": title, "items": []}; groups.append(cur)
            img = re.search(r'<img[^>]*src="([^"?]+)', td)
            txt = html.unescape(re.sub("<[^>]+>", "\n", re.sub(r"<checkbox.*?</checkbox>", "", td, flags=re.S)))
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            last = {"ids": [t[0] for t in tasks], "tasks": [strip(t[1]) for t in tasks],
                    "name": strip(tasks[0][1]), "lines": lines, "img": img.group(1) if img else None}
            cur["items"].append(last)
    # loose checkboxes outside tables (lists)
    if not groups:
        cur = {"group": title, "items": []}
        for tid, label in re.findall(CB, body, re.S):
            cur["items"].append({"ids": [tid], "tasks": [strip(label)], "name": strip(label), "lines": [], "img": None})
        groups.append(cur)
    groups = [g for g in groups if g["items"]]
    for g in groups:
        for it in g["items"]:
            if it["img"]:
                try:
                    it["img"] = "data:image/png;base64," + base64.b64encode(get(it["img"] + "?width=200")).decode()
                except Exception:
                    it["img"] = None
    out = {"slug": slug, "title": title, "source": url, "groups": groups,
           "count": sum(len(g["items"]) for g in groups)}
    os.makedirs("trackers", exist_ok=True)
    json.dump(out, open(f"trackers/{slug}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(slug, out["count"], "items in", len(groups), "groups")

if __name__ == "__main__":
    main(*sys.argv[1:4])
