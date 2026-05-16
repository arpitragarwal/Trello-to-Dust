# Trello to Dust

Syncs cards from a Trello board into a [Dust](https://dust.tt) data source so a Dust agent can search and reason over them. Runs automatically every hour via GitHub Actions.

## What it does

For each card on the configured Trello board, the script:

1. Fetches the card's basic fields (name, description, URL, labels, due date, location, checklists, last activity).
2. Fetches the card's recent action history (list moves, comments, member assignments).
3. Computes a set of **temporal signals** from that history:
   - `days_in_current_list` — how long since the card was last moved into this column.
   - `days_since_last_activity` — derived from Trello's `dateLastActivity`.
   - `days_since_last_comment` — date of the most recent comment.
   - `days_until_due` — negative means overdue.
   - `times_moved_between_lists` — a churn signal.
   - `has_had_no_activity_since_assigned` — flags cards that were assigned and then ignored.
4. Renders all of the above as Markdown and upserts it to Dust, using the Trello card ID as the Dust document ID (so re-runs update rather than duplicate).

## How the GitHub Action runs

The workflow lives at `.github/workflows/sync.yml` and does three things:

- **Triggers:**
  - `schedule: cron: '0 * * * *'` — runs at the top of every hour (with the usual GitHub-Actions scheduling drift; expect a few minutes of delay during busy periods).
  - `workflow_dispatch` — adds a "Run workflow" button to the Actions tab for manual triggers.
- **Steps:** checkout the repo, install dependencies from `requirements.txt`, run `python trello_to_dust.py` with three secrets injected as environment variables.

### Secrets

The script reads three secrets from environment variables and exits with a clear error if any are missing. Configure them under repo **Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | What it is |
| --- | --- |
| `TRELLO_API_KEY` | Trello app key (short hex string). |
| `TRELLO_TOKEN` | Trello user token (long string starting with `ATTA...`) authorizing the app to read the board. |
| `DUST_API_KEY` | Dust API key (starts with `sk-`) with write access to the target data source. |

Paste values **without** surrounding quotes.

### Non-secret configuration

The Trello board ID, Dust workspace ID, space ID, and data source ID are hardcoded near the top of `trello_to_dust.py`. They are identifiers, not credentials, so they don't need to be secrets. Edit the file if you want to point at a different board or data source.

## Running locally

```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

TRELLO_API_KEY='...' \
TRELLO_TOKEN='...' \
DUST_API_KEY='...' \
python trello_to_dust.py
```

Output looks like:

```
Fetching Trello data...
Found 7 cards across 4 lists.
[1/7] ✅ Synced: Card title here
...
Sync complete!
```

## Viewing run logs

In the GitHub repo, open the **Actions** tab, click the **Trello to Dust Sync** workflow in the sidebar, then click any run to drill into per-step logs. Logs are retained for 90 days.

## Files

- `trello_to_dust.py` — the sync script.
- `requirements.txt` — Python dependencies (just `requests`).
- `.github/workflows/sync.yml` — GitHub Actions workflow.
- `.gitignore` — keeps `venv/` and logs out of git.
