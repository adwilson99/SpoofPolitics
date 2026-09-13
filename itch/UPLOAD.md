# Publishing the itch.io landing page

Everything in this folder is a ready-to-upload itch.io project page: a branded
landing screen with a big **Play in your browser** button that opens the live
game (hosted on Render).

## Files

| File | Used for |
|---|---|
| `spoof-politics-itch.zip` | The uploaded "game" — contains `index.html` (the landing page) |
| `cover.png` | The project cover image (630×500, itch's required size) |
| `index.html` | Source for the zip — edit this to change the page, then re-zip |

## Upload steps (once)

1. Log in to itch.io → **Dashboard → Create new project**
2. **Kind of project**: HTML
3. **Uploads**: drop in `spoof-politics-itch.zip`
4. Tick **"This file will be played in the browser"**
5. **Embed options**: viewport `800×600`, tick **Mobile friendly**
6. **Cover image**: upload `cover.png`
7. Fill in the description (steal the blurb from `index.html`), add tags like
   `satire`, `politics`, `turn-based`, `comedy`, `mobile-friendly`
8. **Save & view page** → when happy, **Publish**

> itch requires external links to open in a new tab — the button already does
> (`target="_blank"`), so the page works inside itch's iframe as-is.

## Editing the page later

Change `index.html`, re-zip it (`zip -j spoof-politics-itch.zip index.html`
from this folder), and re-upload the zip on your itch project page.
