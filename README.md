# Fortnite Command Center

Personal before-you-play dashboard. GitHub Actions runs `fetch.py` every 15 minutes and commits `data/*.json`; `index.html` is a static page that reads them. Trackers come from IGN wiki checklists via `ign_checklist.py <url> <slug> "<Title>"`.

Sources: fortnite-api.com (shop, news), status.epicgames.com, Reddit RSS (r/FortNiteBR, r/FortniteLeaks), YouTube channel RSS (HYPEX, ShiinaBR, iFireMonkey), IGN RSS. All keyless and free.

## Working on it locally
Never commit `data/` from this machine: the Actions bot owns those files and a local data commit conflicts on push. Edit code, `git pull --rebase`, push, then `gh workflow run fetch` if you want fresh data now.
