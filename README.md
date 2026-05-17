# Trello to Dust

Syncs cards from a Trello board into a [Dust](https://dust.tt) data source so a Dust agent can search and reason over them. Runs automatically every hour via GitHub Actions.

## What it does

For each card on the configured Trello board, the script:

1. Fetches the card's basic fields (name, description, URL, labels, due date, completed flag, location, checklists, last activity).
2. Fetches the card's recent action history (comments, member assignments) and includes each comment's date, author, and text in the document body.
3. Computes a set of **temporal signals** from that history:
   - `days_since_last_activity` — derived from Trello's `dateLastActivity`.
   - `days_since_last_comment` — date of the most recent comment.
   - `days_until_due` — negative means overdue.
   - `has_had_no_activity_since_assigned` — flags cards that were assigned and then ignored.
4. Renders all of the above as Markdown and upserts it to Dust, using the Trello card ID as the Dust document ID (so re-runs update rather than duplicate).

## How the GitHub Action runs

The workflow lives at `.github/workflows/sync.yml`

- **Triggers:**
  - `schedule: cron: '0 * * * *'` — runs at the top of every hour (with the usual GitHub-Actions scheduling drift; expect a few minutes of delay during busy periods).
  - `workflow_dispatch` — adds a "Run workflow" button to the Actions tab for manual triggers.
- **Steps:** checkout the repo, install dependencies from `requirements.txt`, run `python trello_to_dust.py` with three secrets injected as environment variables.

### Secrets

Configure under repo **Settings → Secrets and variables → Actions → Repository secrets**:

- `TRELLO_API_KEY`
- `TRELLO_TOKEN`
- `DUST_API_KEY`
