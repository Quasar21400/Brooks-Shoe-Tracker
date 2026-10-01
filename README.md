# Shoe stock tracker

Watches for one pair of shoes and pings your phone the moment they can be bought:

> **Brooks Ghost Max 4, men's size 12, Extra Wide (4E), Black/Black/Ebony**
> (Brooks style 110496, colour 020)

A GitHub Actions job runs every 15 minutes and checks:

| Where | How |
|---|---|
| **brooksrunning.com** | Reads the product page and the site's own variant data for 110496 / 020 / 4E / 12.0. |
| **Fleet Feet stores** (250+ US locations) | Fleet Feet publishes per-store stock on its product page. You get the store names, distances and phone numbers. |
| **Independent running shops** on Shopify | Fit2Run, Holabird, Luke's Locker, Runners Plus, Lebo's, Pacers, Potomac River Running, Gazelle Sports, Lamey Wellehan. Each run searches their catalogue, so a newly added 4E page gets picked up. |

When the shoe shows up anywhere, you get one alert listing where. You won't get repeats on every check. A new alert comes only when another place gets it. When everything sells out again you get a quiet "sold out again" note.

## Set up alerts on your phone (2 minutes)

The tracker already runs without setup. Out of the box it opens a GitHub issue that @mentions you when the shoe is in stock, so GitHub emails you. For an instant push notification, add ntfy:

1. Install the **ntfy** app ([iPhone and Android links](https://docs.ntfy.sh/subscribe/phone/)). It's free and needs no account.
2. In the app, tap **+** and subscribe to a topic name nobody could guess, e.g. `ghostmax-4e-k29xq7`. Anyone who knows the name can read it, so make it random.
3. In this repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**. Name `NTFY_TOPIC`, value is your topic name.
4. Test it: **Actions → Check shoe stock → Run workflow**, tick **Send a test alert**, then **Run workflow**. Your phone should buzz within a minute.

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

## Only care about nearby stores?

Edit `config.toml` and set your ZIP:

```toml
[location]
zip          = "27510"
radius_miles = 50
```

Every Fleet Feet store within the radius then gets its own alert with its phone number. Stock anywhere else still triggers one summary alert, since Fleet Feet stores can ship.

## What it found on the first run (Sept 28, 2026)

- **Brooks.com:** Black/Black/Ebony in 4E is sold out in every size. The 1D and 2E versions are in stock.
- **Fleet Feet:** carries this colour only in D and 2E so far.
- **Shopify shops:** the ones that stock 4E or X-Wide (Fit2Run, Holabird, Luke's Locker, Lebo's, Runners Plus) don't have it in Black/Black/Ebony.

The tracker's own summary for each run is under **Actions → Check shoe stock → (latest run)**.

## Good to know

- **Brooks' own restock email.** On the Brooks product page, pick Black/Black/Ebony, Extra Wide (4E), size 12. If Brooks offers a "Notify me" button there, sign up for that too.
- **Not covered:** Zappos, Running Warehouse, Dick's, Amazon and REI. They either block automated checks or render stock with scripts that change often.
- **Something breaks?** Retailers redesign sites. If one can't be checked for 6 hours straight, you get a "tracker can't check X" alert, so silence always means "not in stock", never "broken".
- **How often it really checks.** GitHub skips scheduled runs when its servers are busy. With an hourly schedule it ran only every 3 to 8 hours, so the schedule asks for every 15 minutes to land at least hourly. The schedule is the `cron` line in `.github/workflows/check-stock.yml`.
- **Keep this repo public.** Public repos get unlimited free GitHub Actions time. If it goes back to private, runs count against the free 2,000 minutes a month, and checking every 15 minutes could use them up. Switch the `cron` line to `"11 * * * *"` (hourly) in that case.
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
