# Shoe stock tracker

Watches for one pair of shoes and pings your phone the moment they can be bought:

> **Brooks Ghost Max 4, men's size 12, Extra Wide (4E), Black/Black/Ebony**
> (Brooks style 110496, colour 020)

A GitHub Actions job checks once an hour. Physical stores only count when they're within **40 miles of ZIP 33027**. Online shops ship anywhere, so they're always checked.

## Stores near you (within 40 miles of 33027)

| Store | Distance | How it's checked |
|---|---|---|
| Fleet Feet North Miami | about 11 mi | Fleet Feet publishes each store's stock |
| Fleet Feet Coconut Grove | about 18 mi | same |
| Fleet Feet Miami | about 25 mi | same |
| Fleet Feet Delray Beach | about 36 mi | same |
| Fit2Run Aventura | about 12 mi | Fit2Run's "pick up in store" stock |
| Fit2Run Coconut Creek | about 23 mi | same |

Fleet Feet stores farther than 40 miles never trigger an alert.

## Online, shipped to you

| Shop | Notes |
|---|---|
| **brooksrunning.com** | Brooks' own site |
| **Zappos** | Lists Black/Black/Ebony in "4E - X-Wide", sold out in every size as of Oct 1 |
| **Fit2Run** online | Florida chain; also covers the two stores above |
| Holabird Sports, Luke's Locker, Runners Plus, Lebo's, Pacers, Potomac River Running, Gazelle Sports, Lamey Wellehan | Running shops that sell online. Each check searches their catalogue, so a newly added 4E page gets picked up |

## Places that can't be checked automatically

| Place | Near you? | Why |
|---|---|---|
| Dick's Sporting Goods | yes (Pembroke Pines, about 3 mi, and others) | A bot wall (Akamai) blocks every automated visit |
| Runner's Depot, Davie | about 8 mi | Its online shop stops at the Ghost Max 3. Call (954) 474-4074 |
| Runner's Edge, Boca Raton | about 30 mi | Lists the Ghost Max 4, but sizes and stock load from a private data service after the page opens. Call (561) 361-1950 |
| Running Wild, Fort Lauderdale | about 16 mi | No online store. Call (954) 565-9400 |
| Sole-Lutions Footwear, Pembroke Pines | about 2 mi | No online store. Call (954) 447-4400 |
| Footworks, South Miami | about 21 mi | Its online shop doesn't sell shoes |
| iRun, Miami | about 15 mi | No online store |
| Brooks' "Find a store" (Locally.com) | n/a | Store stock pages sit behind a Cloudflare bot wall |
| Famous Footwear, REI, Amazon, Nordstrom, JCPenney | n/a | Bot walls |

Checked and ruled out: **Academy Sports** sells the Ghost Max 4 only in regular and wide, no 4E. **Foot Locker, Champs and Lady Foot Locker** don't sell the Ghost Max 4. **Running Warehouse** sells it, but not in Black/Black/Ebony.

When the shoe shows up anywhere, you get one alert listing where. You won't get repeats on every check. A new alert comes only when another place gets it. When everything sells out again you get a quiet "sold out again" note.

## Phone alerts

Alerts go to the **ntfy** app on your phone ([iPhone and Android links](https://docs.ntfy.sh/subscribe/phone/)), subscribed to the topic `GhostBrooks`. The topic is set in `config.toml` under `[alerts]`.

Every alert also opens a GitHub issue that @mentions you, so GitHub notifies you as well.

**This repo is public, so anyone can read the topic name.** Someone who finds it could see the alerts or send junk notifications to your phone. To hide it, subscribe the app to a random name instead (e.g. `ghostmax-4e-k29xq7`), then open [this repo's "New secret" page](https://github.com/Quasar21400/Brooks-Shoe-Tracker/settings/secrets/actions/new) in a browser. Enter `NTFY_TOPIC` as the name and your new topic as the value. The secret overrides `config.toml`, and GitHub never shows it publicly.

To send a test alert: **Actions → Check shoe stock → Run workflow**, tick **Send a test alert**, then **Run workflow**. Your phone should buzz within a minute.

### Email instead (optional)

Add these repository secrets. For Gmail, `SMTP_PASSWORD` must be an [app password](https://myaccount.google.com/apppasswords), not your normal one.

| Secret | Example |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | `you@gmail.com` |
| `SMTP_PASSWORD` | the 16-character app password |
| `EMAIL_TO` | where alerts go |

To turn the GitHub-issue alerts off, add a repository **variable** (not a secret) `GITHUB_ISSUE_ALERTS` = `false`.

## Changing your location

Edit `[location]` in `config.toml`:

```toml
[location]
zip          = "33027"
radius_miles = 40
```

Every nearby store with stock gets its own alert with its distance. Leave `zip` empty to hear about Fleet Feet stock anywhere in the country instead.

## What it found on the first run (Sept 28, 2026)

- **Brooks.com:** Black/Black/Ebony in 4E is sold out in every size. The 1D and 2E versions are in stock.
- **Fleet Feet:** carries this colour only in D and 2E so far.
- **Shopify shops:** the ones that stock 4E or X-Wide (Fit2Run, Holabird, Luke's Locker, Lebo's, Runners Plus) don't have it in Black/Black/Ebony.

The tracker's own summary for each run is under **Actions → Check shoe stock → (latest run)**.

## Good to know

- **Brooks' own restock email.** On the Brooks product page, pick Black/Black/Ebony, Extra Wide (4E), size 12. If Brooks offers a "Notify me" button there, sign up for that too.
- **Something breaks?** Retailers redesign sites. If one can't be checked for 6 hours straight, you get a "tracker can't check X" alert, so silence always means "not in stock", never "broken".
- **Once an hour, without gaps.** GitHub skips scheduled runs when its servers are busy. A plain hourly schedule only ran every 3 to 8 hours. So GitHub is asked four times an hour, and only the first run that lands in each hour checks the stores. The others stop after a few seconds.
- **Keep this repo public.** Public repos get unlimited free GitHub Actions time. A private repo gets 2,000 free minutes a month, and the four-times-an-hour schedule could use them up.
- **The schedule stays switched on.** GitHub turns off schedules in public repos after 60 days with no activity. Each run re-enables the workflow to prevent that. If checks ever stop, open **Actions → Check shoe stock** and click **Enable workflow**.
- **Scheduled runs only happen on the default branch** (`main`). Keep the tracker's files there.

## Tracking a different shoe

Change the `[shoe]` section of `config.toml`. Brooks style and colour codes are in the product page URL (`.../110496.html?dwvar_110496_color=020`).

## Running it yourself

```bash
pip install -r requirements.txt
python -m shoe_tracker --dry-run      # check everything, print results, send nothing
python -m unittest discover -s tests -t .
```
