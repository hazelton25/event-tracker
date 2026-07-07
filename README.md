# Event Tracker

A personal event-tracking app for concerts, sporting events, festivals, and theatre.
Each event renders as a flip-able **ticket stub** — front shows the event details,
flip it to see the setlist, notes, attendees, and rating on the back.

Self-hosted, single-process, no auth (designed for a home lab behind Tailscale).

![ticket stub UI](docs/preview.png)

## Stack

- **Backend** — Flask + SQLite, served by waitress
- **Frontend** — React + Vite + Tailwind + Framer Motion
- **Images** — Wikipedia REST API (no key), cached locally in `backend/uploads/`
- **Deploy** — one process serves both the API and the built React bundle on port 8093

## Quick start

```bash
git clone <your-repo-url> event-tracker
cd event-tracker
./setup.sh     # builds venv, installs deps, initializes DB, builds frontend
./run.sh       # serves on http://0.0.0.0:8093
```

Then open `http://localhost:8093` locally, or `http://<host>:8093` over your LAN / Tailscale.

> If `./setup.sh` reports *Permission denied*, the executable bit was stripped in
> transfer: `chmod +x setup.sh run.sh`. If you see *bad interpreter*, the scripts
> have CRLF endings: `sed -i '' 's/\r$//' setup.sh run.sh` (macOS).

## Development

Run the backend and the Vite dev server separately for hot-reload:

```bash
# terminal 1 — API
cd backend && . .venv/bin/activate && python app.py

# terminal 2 — frontend (proxies /api and /uploads to :8093)
cd frontend && npm run dev      # http://localhost:5173
```

## API

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/events` | List events. Params: `type`, `sort` (date/name/rating/created_at), `order` (asc/desc) |
| GET | `/api/events/<id>` | Single event |
| POST | `/api/events` | Create event |
| PUT | `/api/events/<id>` | Update event |
| DELETE | `/api/events/<id>` | Delete event |
| GET | `/api/image-search?q=` | Wikipedia image candidates |
| POST | `/api/events/<id>/image` | Set image — JSON `{url}` or multipart `file` |
| GET | `/api/backup` | Download a zip of the DB + uploads |
| POST | `/api/import` | Restore from a backup zip (multipart `file`) |

## Setlist.fm auto-fill

For concerts, "fetch from setlist.fm" in the event form pulls the real setlist
(venue and city too). Get a free API key at https://www.setlist.fm/settings/api
and set `SETLISTFM_API_KEY` in the launchd plist (or env). Without a key the
button explains what's missing — nothing else breaks.

## Network binding

`HOST=tailscale` (the default in the plist) binds the server to the machine's
Tailscale IP **and** `127.0.0.1` — reachable from your tailnet and from
localhost (the backup script), but not from the rest of the LAN. If Tailscale
is down at start, it falls back to localhost-only and logs a warning.
`HOST=0.0.0.0` restores LAN-wide binding if you ever want it.

## Backup & restore

`↓ Backup` (top-right of the app) downloads a single zip containing the SQLite
database **and** all cached images. `↑ Import` restores both atomically.

Before an import, the current database is snapshotted to
`backend/events.db.pre-import-<timestamp>` on the server, so a bad import is
recoverable. Prune those snapshots whenever you like.

## Autostart on boot (macOS)

`deploy/com.ben.eventtracker.plist` is a launchd agent that starts the app at
login and restarts it if it crashes. Edit the paths inside, then:

```bash
cp deploy/com.ben.eventtracker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ben.eventtracker.plist
launchctl start com.ben.eventtracker
```

Logs go to `eventtracker.log` in the repo root.

## Data model

`events` table: `id`, `name`, `event_type` (concert/sports/festival/theatre/other),
`date`, `venue`, `city`, `setlist`, `notes`, `attendees`, `rating` (1–5),
`image_url`, `created_at`, `updated_at`.

Personal data (`events.db`, `uploads/`) is git-ignored — your collection stays
on your machine.

## Roadmap

- Stats dashboard (events/year, most-visited venues, top artists)
- Ticket-stub photo scans
- Import from the earlier "Setlist" app
