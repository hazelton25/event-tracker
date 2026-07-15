# Event Tracker — Spec (current state)

Personal event-tracking app for concerts, sports, festivals, and theatre.
Evolution of the earlier single-file "Setlist" project. Runs on Ben's Mac Mini
(`mini-ai`); reached over Tailscale; no auth layer by design; not exposed to
the public internet. This document describes the app **as built** — the
original build spec is superseded.

## Architecture

Single process, single port (8093). Flask serves the JSON API under `/api/*`,
cached images under `/uploads/*`, and the built React bundle for everything
else (SPA fallback to `index.html`). Waitress is the WSGI server. Deployment
is `./setup.sh` once, then `./run.sh` — or the launchd agent for autostart.
Docker was considered and rejected; launchd is the deployment mechanism.

- **Backend:** Flask + SQLite (WAL mode, foreign keys on)
- **Frontend:** React + Vite + Tailwind + Framer Motion
- **Design:** "The Stub" — vintage paper ticket cards that flip (front:
  event/venue/date; back: setlist or notes, attendees, rating), plus
  "The Numbers" stats view in the same aesthetic

## Data model (schema v4)

Schema changes are versioned migrations in `MIGRATIONS` (`backend/app.py`),
tracked per-database in `schema_version`. Append-only; entries are SQL scripts
or Python callables. Migrations also run on databases restored from backups.

- `events` — id, name, event_type (concert/sports/festival/theatre/other),
  date, venue, city, notes, rating (1–5), image_url, image_zoom (1.0–3.0,
  default 1.0), image_pos_x/image_pos_y (0–100 focal-point percent, default
  50/50), created_at, updated_at
- `people` — id, name (unique, case-insensitive)
- `event_people` — event_id, person_id, position (cascade on event delete)
- `setlist_songs` — id, event_id, position, title, cover_artist
  (cascade on event delete)

Setlists and attendees are **edited as text** (newline setlist; "A & B"
attendees) but **stored relationally**. The API parses on write — including
`(Artist cover)` suffixes — and synthesizes the text form on read, so clients
can treat them as text while stats stay exact.

## API

All JSON. CORS enabled (trusted-network deployment).

- `GET /api/events` — `type` filter; `sort` date|name|rating|created_at|event_type;
  `order` asc|desc. NULLs sort last. Events include `setlist`/`attendees`
  (text) and `setlist_songs`/`attendee_list` (structured).
- `GET|PUT|DELETE /api/events/<id>`; `POST /api/events` (name required,
  event_type defaults to concert)
- `POST /api/events/<id>/image` — multipart `file` upload or JSON `{url}`;
  remote images are downloaded to `backend/uploads/` so cards never hot-link;
  resets `image_zoom`/`image_pos_x`/`image_pos_y` to defaults
- `PATCH /api/events/<id>/image/adjust` — `{zoom, pos_x, pos_y}`, clamped to
  1.0–3.0 / 0–100; non-destructive crop of the existing image (400 if no
  image is set yet)
- `GET /api/image-search?q=` — Wikipedia REST proxy (no key), returns
  candidate images
- `GET /api/setlist-search?artist=&date=` — setlist.fm proxy; requires
  `SETLISTFM_API_KEY` env (free key from setlist.fm/settings/api); degrades
  to a helpful error without one
- `GET /api/stats` — totals, per-year, by-type, rating histogram, top venues /
  artists / attendees, songs heard 2+ times
- `GET /api/backup` — zip of DB (SQLite online-backup snapshot) + uploads +
  manifest
- `POST /api/import` — restore from backup zip; validates zip integrity,
  presence and validity of `events.db`, guards zip-slip; snapshots the current
  DB to `events.db.pre-import-<ts>` first; migrates restored DBs to current
  schema

## Network & environment

- `HOST=tailscale` (default in the service definition): binds the detected
  100.x Tailscale IP **and** 127.0.0.1; falls back to localhost-only with a
  warning if Tailscale is down (OS-agnostic — plain socket trick, no macOS
  API). `HOST=0.0.0.0` for LAN-wide. `PORT` (default 8093),
  `SETLISTFM_API_KEY`, `EVENTTRACKER_DB`, `EVENTTRACKER_UPLOADS`.

## Operations (`deploy/`)

`run.sh`/`setup.sh` are plain bash + python3/npm, no OS-specific calls, so
the app itself runs the same on macOS or Linux — only the autostart/
crash-recovery/backup-timer mechanism differs, since that's OS-level:

- **macOS** (launchd): `com.ben.eventtracker.plist` — run at load, restart on
  crash, logs to `eventtracker.log`; `com.ben.eventtracker.backup.plist` +
  `backup.sh` — nightly 03:30 backup
- **Linux** (systemd --user, e.g. Ubuntu on mini-ai): `event-tracker.service`
  — restart on crash, `loginctl enable-linger` for boot-time start without a
  login session, logs via `journalctl --user -u event-tracker`;
  `event-tracker-backup.service` + `.timer` — same nightly 03:30 backup via
  `backup.sh`, `Persistent=true` catches up a missed run after sleep/off

Both flavors call the same `backup.sh` (nightly 03:30 backup to
`~/backups/event-tracker`, newest 14 kept, zip validated before counting,
failures logged loudly).

## Testing

`backend/tests/` — pytest, 30 tests: CRUD, sort/filter safety, migrations
(fresh / legacy adoption / idempotency / backfill of v2 text columns),
backup–import round trip, import rejection (garbage, zip-slip), image upload
validation, image pan/zoom adjustment (persist, clamp, reset-on-reupload),
setlist.fm parsing, structured-field round trips, cascade deletes, stats.
Run: `python -m pytest tests/` with `requirements-dev.txt` installed.

## Non-goals

- Authentication / multi-user — Tailscale is the access boundary
- Public internet exposure, Cloudflare Tunnel
- Docker

## Future ideas (not committed)

- Upcoming-events state (countdown on the ticket front, flips to ATTENDED)
- Venue map (Leaflet + OpenStreetMap)
- "On this day" anniversaries
- Ticket-stub photo scans attached to card backs
- Export a card as a shareable image
