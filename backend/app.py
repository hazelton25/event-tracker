"""
Event Tracker — Flask backend.

Single-process app: serves the JSON API under /api/* and the built React
bundle (frontend/dist) as static files, so the whole thing runs on one port.
"""
import os
import io
import re
import json
import shutil
import sqlite3
import zipfile
import tempfile
import datetime
import urllib.parse
import urllib.request
from contextlib import contextmanager

from flask import (
    Flask, request, jsonify, send_file, send_from_directory, abort
)
from flask_cors import CORS

# --------------------------------------------------------------------------- #
# Paths / config
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("EVENTTRACKER_DB", os.path.join(BASE_DIR, "events.db"))
UPLOADS_DIR = os.environ.get("EVENTTRACKER_UPLOADS", os.path.join(BASE_DIR, "uploads"))
DIST_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend", "dist"))

PORT = int(os.environ.get("PORT", "8093"))
HOST = os.environ.get("HOST", "0.0.0.0")
SETLISTFM_API_KEY = os.environ.get("SETLISTFM_API_KEY", "").strip()

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
USER_AGENT = "EventTracker/1.0 (personal home-lab app)"

os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)
CORS(app)  # LAN/Tailscale only; no auth layer by design


# --------------------------------------------------------------------------- #
# Database — versioned migrations
#
# To change the schema: append a new SQL script to MIGRATIONS. Never edit or
# reorder existing entries — each runs exactly once per database, tracked in
# the schema_version table. Existing pre-migration DBs adopt cleanly because
# migration 1 is the baseline schema with IF NOT EXISTS.
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Text parsing — the UI edits setlists/attendees as text; storage is relational
# --------------------------------------------------------------------------- #
_ATTENDEE_SPLIT = re.compile(r"\s*(?:,|&|\+|\band\b|\bw/\b)\s*", re.IGNORECASE)
_COVER_SUFFIX = re.compile(r"\s*\(([^)]*?)\s+cover\)\s*$", re.IGNORECASE)


def split_attendees(text):
    """Best-effort split of attendee text ('Sarah & Mike') into names."""
    if not text:
        return []
    return [p.strip() for p in _ATTENDEE_SPLIT.split(text) if p.strip()]


def parse_setlist_text(text):
    """'Peggy-O (Grateful Dead cover)' -> [('Peggy-O', 'Grateful Dead'), ...]"""
    out = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        cover = None
        m = _COVER_SUFFIX.search(line)
        if m:
            cover = m.group(1).strip() or None
            line = _COVER_SUFFIX.sub("", line).strip()
        if line:
            out.append((line, cover))
    return out


def song_to_text(title, cover_artist):
    return f"{title} ({cover_artist} cover)" if cover_artist else title


def save_setlist(conn, event_id, text):
    conn.execute("DELETE FROM setlist_songs WHERE event_id = ?", (event_id,))
    for pos, (title, cover) in enumerate(parse_setlist_text(text), start=1):
        conn.execute(
            "INSERT INTO setlist_songs (event_id, position, title, cover_artist)"
            " VALUES (?, ?, ?, ?)",
            (event_id, pos, title, cover),
        )


def save_attendees(conn, event_id, text):
    conn.execute("DELETE FROM event_people WHERE event_id = ?", (event_id,))
    for pos, name in enumerate(split_attendees(text), start=1):
        row = conn.execute(
            "SELECT id FROM people WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        pid = row["id"] if row else conn.execute(
            "INSERT INTO people (name) VALUES (?)", (name,)
        ).lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO event_people (event_id, person_id, position)"
            " VALUES (?, ?, ?)",
            (event_id, pid, pos),
        )


def _migration_3_structured_fields(conn):
    """Create people/setlist tables, backfill from legacy text columns, drop them."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS people (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE
    );
    CREATE TABLE IF NOT EXISTS event_people (
        event_id  INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        person_id INTEGER NOT NULL REFERENCES people(id),
        position  INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (event_id, person_id)
    );
    CREATE TABLE IF NOT EXISTS setlist_songs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id     INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        position     INTEGER NOT NULL,
        title        TEXT NOT NULL,
        cover_artist TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_setlist_event ON setlist_songs(event_id, position);
    CREATE INDEX IF NOT EXISTS idx_event_people ON event_people(event_id);
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    if "setlist" in cols:
        for r in conn.execute("SELECT id, setlist, attendees FROM events"):
            save_setlist(conn, r["id"], r["setlist"])
            save_attendees(conn, r["id"], r["attendees"])
        for col in ("setlist", "attendees"):
            try:
                conn.execute(f"ALTER TABLE events DROP COLUMN {col}")
            except sqlite3.OperationalError:
                # SQLite < 3.35 can't drop columns — null them out instead
                conn.execute(f"UPDATE events SET {col} = NULL")


MIGRATIONS = [
    # 1 — baseline schema
    """
    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        event_type  TEXT NOT NULL DEFAULT 'concert',
        date        TEXT,
        venue       TEXT,
        city        TEXT,
        setlist     TEXT,
        notes       TEXT,
        attendees   TEXT,
        rating      INTEGER,
        image_url   TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now'))
    );
    """,
    # 2 — index for the default sort
    """
    CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
    """,
    # 3 — structured setlist + attendees (tables defined in the callable)
    _migration_3_structured_fields,
    # 4 — non-destructive image pan/zoom (focal point + zoom level)
    """
    ALTER TABLE events ADD COLUMN image_zoom REAL NOT NULL DEFAULT 1.0;
    ALTER TABLE events ADD COLUMN image_pos_x REAL NOT NULL DEFAULT 50.0;
    ALTER TABLE events ADD COLUMN image_pos_y REAL NOT NULL DEFAULT 50.0;
    """,
]

EVENT_FIELDS = (  # direct columns; setlist/attendees live in their own tables
    "name", "event_type", "date", "venue", "city",
    "notes", "rating", "image_url",
)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_db():
    """Connection that commits on success, rolls back on error, always closes.

    (sqlite3's own `with conn:` manages transactions but never closes the
    handle — using it directly leaks a connection per request.)
    """
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def schema_version(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER NOT NULL, applied_at TEXT DEFAULT (datetime('now')))"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def init_db():
    """Apply any unapplied migrations, in order, each in its own transaction."""
    with get_db() as conn:
        current = schema_version(conn)
        for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
            if callable(script):
                script(conn)
            else:
                conn.executescript(script)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (number,))
        applied = len(MIGRATIONS) - current
        if applied:
            print(f"DB migrated: v{current} -> v{len(MIGRATIONS)} ({applied} applied)")


def serialize_events(conn, rows):
    """Rows -> dicts with synthesized text fields + structured lists.

    `setlist`/`attendees` remain text for the UI; `setlist_songs`/
    `attendee_list` expose the structured storage.
    """
    ids = [r["id"] for r in rows]
    songs, people = {}, {}
    if ids:
        ph = ",".join("?" * len(ids))
        for r in conn.execute(
            f"SELECT event_id, title, cover_artist FROM setlist_songs"
            f" WHERE event_id IN ({ph}) ORDER BY event_id, position", ids
        ):
            songs.setdefault(r["event_id"], []).append(
                {"title": r["title"], "cover_artist": r["cover_artist"]}
            )
        for r in conn.execute(
            f"SELECT ep.event_id, p.name FROM event_people ep"
            f" JOIN people p ON p.id = ep.person_id"
            f" WHERE ep.event_id IN ({ph}) ORDER BY ep.event_id, ep.position", ids
        ):
            people.setdefault(r["event_id"], []).append(r["name"])

    out = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        sl = songs.get(r["id"], [])
        pl = people.get(r["id"], [])
        d["setlist_songs"] = sl
        d["attendee_list"] = pl
        d["setlist"] = "\n".join(song_to_text(s["title"], s["cover_artist"]) for s in sl) or None
        d["attendees"] = " & ".join(pl) or None
        out.append(d)
    return out


def serialize_event(conn, row):
    return serialize_events(conn, [row])[0]


# --------------------------------------------------------------------------- #
# Event CRUD
# --------------------------------------------------------------------------- #
SORTABLE = {"date", "name", "rating", "created_at", "event_type"}


@app.route("/api/events", methods=["GET"])
def list_events():
    sort = request.args.get("sort", "date")
    order = request.args.get("order", "desc").lower()
    etype = request.args.get("type")

    if sort not in SORTABLE:
        sort = "date"
    order = "ASC" if order == "asc" else "DESC"

    sql = "SELECT * FROM events"
    params = []
    if etype and etype != "all":
        sql += " WHERE event_type = ?"
        params.append(etype)
    # NULLs (e.g. missing dates/ratings) sort last regardless of direction
    sql += f" ORDER BY ({sort} IS NULL), {sort} {order}"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return jsonify(serialize_events(conn, rows))


@app.route("/api/events/<int:event_id>", methods=["GET"])
def get_event(event_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return jsonify({"error": "Event not found"}), 404
        return jsonify(serialize_event(conn, row))


@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json(silent=True) or {}
    if not (data.get("name") or "").strip():
        return jsonify({"error": "Name is required"}), 400
    if not data.get("event_type"):
        data["event_type"] = "concert"  # None would override the column DEFAULT

    vals = [data.get(f) for f in EVENT_FIELDS]
    placeholders = ", ".join("?" for _ in EVENT_FIELDS)
    cols = ", ".join(EVENT_FIELDS)

    with get_db() as conn:
        cur = conn.execute(
            f"INSERT INTO events ({cols}) VALUES ({placeholders})", vals
        )
        new_id = cur.lastrowid
        save_setlist(conn, new_id, data.get("setlist"))
        save_attendees(conn, new_id, data.get("attendees"))
        row = conn.execute("SELECT * FROM events WHERE id = ?", (new_id,)).fetchone()
        return jsonify(serialize_event(conn, row)), 201


@app.route("/api/events/<int:event_id>", methods=["PUT"])
def update_event(event_id):
    data = request.get_json(silent=True) or {}
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if existing is None:
            return jsonify({"error": "Event not found"}), 404

        updates = {f: data[f] for f in EVENT_FIELDS if f in data}
        touched = bool(updates)
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            params = list(updates.values()) + [event_id]
            conn.execute(
                f"UPDATE events SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                params,
            )
        if "setlist" in data:
            save_setlist(conn, event_id, data["setlist"])
            touched = True
        if "attendees" in data:
            save_attendees(conn, event_id, data["attendees"])
            touched = True
        if touched and not updates:
            conn.execute(
                "UPDATE events SET updated_at = datetime('now') WHERE id = ?",
                (event_id,),
            )
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return jsonify(serialize_event(conn, row))


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    if cur.rowcount == 0:
        return jsonify({"error": "Event not found"}), 404
    return jsonify({"status": "deleted"})


# --------------------------------------------------------------------------- #
# Image sourcing (Wikipedia REST + Action API; no key required)
# --------------------------------------------------------------------------- #
def _http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


@app.route("/api/image-search", methods=["GET"])
def image_search():
    """Return a few candidate images from Wikipedia for a query string."""
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"results": []})

    results = []
    try:
        # 1) Find the best-matching articles.
        search_url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json"
            "&srlimit=5&srsearch=" + urllib.parse.quote(query)
        )
        hits = _http_get_json(search_url).get("query", {}).get("search", [])
        titles = [h["title"] for h in hits]

        # 2) Pull the lead thumbnail for each candidate article.
        for title in titles:
            summary_url = (
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + urllib.parse.quote(title.replace(" ", "_"))
            )
            try:
                data = _http_get_json(summary_url)
            except Exception:
                continue
            thumb = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
            if thumb:
                results.append({
                    "title": data.get("title", title),
                    "description": data.get("description", ""),
                    "url": thumb,
                })
    except Exception as exc:  # network down, rate limited, etc.
        return jsonify({"results": [], "error": str(exc)}), 200

    return jsonify({"results": results})


def _download_image(url, event_id):
    """Fetch a remote image into uploads/ and return the local /uploads path."""
    parsed = urllib.parse.urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        ext = ".jpg"
    fname = f"event_{event_id}_{datetime.datetime.now():%Y%m%d%H%M%S}{ext}"
    dest = os.path.join(UPLOADS_DIR, fname)

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    return f"/uploads/{fname}"


@app.route("/api/events/<int:event_id>/image", methods=["POST"])
def set_event_image(event_id):
    """
    Set an event image three ways:
      - multipart file upload (field 'file')
      - JSON {"url": "..."} to download & cache a remote image
    Stored locally so cards keep working if the source URL dies.
    """
    with get_db() as conn:
        row = conn.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Event not found"}), 404

    local_path = None

    if "file" in request.files:
        f = request.files["file"]
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_IMAGE_EXT:
            return jsonify({"error": "Unsupported image type"}), 400
        fname = f"event_{event_id}_{datetime.datetime.now():%Y%m%d%H%M%S}{ext}"
        f.save(os.path.join(UPLOADS_DIR, fname))
        local_path = f"/uploads/{fname}"
    else:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "Provide a file or a url"}), 400
        try:
            local_path = _download_image(url, event_id)
        except Exception as exc:
            return jsonify({"error": f"Could not fetch image: {exc}"}), 400

    with get_db() as conn:
        conn.execute(
            "UPDATE events SET image_url = ?, image_zoom = 1.0, image_pos_x = 50.0,"
            " image_pos_y = 50.0, updated_at = datetime('now') WHERE id = ?",
            (local_path, event_id),
        )
        updated = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return jsonify(serialize_event(conn, updated))


@app.route("/api/events/<int:event_id>/image/adjust", methods=["PATCH"])
def adjust_event_image(event_id):
    """Persist non-destructive pan/zoom for an already-set image."""
    data = request.get_json(silent=True) or {}
    with get_db() as conn:
        row = conn.execute(
            "SELECT image_url FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return jsonify({"error": "Event not found"}), 404
        if not row["image_url"]:
            return jsonify({"error": "No image set for this event"}), 400

        try:
            zoom = float(data["zoom"])
            pos_x = float(data["pos_x"])
            pos_y = float(data["pos_y"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "zoom, pos_x, pos_y are required numbers"}), 400

        zoom = max(1.0, min(3.0, zoom))
        pos_x = max(0.0, min(100.0, pos_x))
        pos_y = max(0.0, min(100.0, pos_y))

        conn.execute(
            "UPDATE events SET image_zoom = ?, image_pos_x = ?, image_pos_y = ?,"
            " updated_at = datetime('now') WHERE id = ?",
            (zoom, pos_x, pos_y, event_id),
        )
        updated = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return jsonify(serialize_event(conn, updated))


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOADS_DIR, filename)


# --------------------------------------------------------------------------- #
# Setlist.fm integration (free API key: https://www.setlist.fm/settings/api)
# --------------------------------------------------------------------------- #
def parse_setlistfm(data, limit=5):
    """Flatten setlist.fm search results into simple candidate dicts."""
    out = []
    for sl in (data.get("setlist") or [])[:limit]:
        songs = []
        for st in ((sl.get("sets") or {}).get("set") or []):
            for song in (st.get("song") or []):
                name = (song.get("name") or "").strip()
                if not name:
                    continue
                if song.get("cover"):
                    name += f" ({song['cover'].get('name', '?')} cover)"
                songs.append(name)
        venue = sl.get("venue") or {}
        out.append({
            "artist": (sl.get("artist") or {}).get("name"),
            "venue": venue.get("name"),
            "city": (venue.get("city") or {}).get("name"),
            "date": sl.get("eventDate"),  # DD-MM-YYYY (setlist.fm format)
            "songs": songs,
            "song_count": len(songs),
        })
    return out


@app.route("/api/setlist-search", methods=["GET"])
def setlist_search():
    if not SETLISTFM_API_KEY:
        return jsonify({
            "results": [],
            "error": "No setlist.fm API key configured. Get a free key at "
                     "setlist.fm/settings/api and set SETLISTFM_API_KEY.",
        })

    artist = (request.args.get("artist") or "").strip()
    date = (request.args.get("date") or "").strip()  # YYYY-MM-DD from the form
    if not artist:
        return jsonify({"results": []})

    params = {"artistName": artist, "p": "1"}
    if date:
        try:
            params["date"] = datetime.date.fromisoformat(date).strftime("%d-%m-%Y")
        except ValueError:
            pass

    url = "https://api.setlist.fm/rest/1.0/search/setlists?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "x-api-key": SETLISTFM_API_KEY,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:  # setlist.fm's "no results"
            return jsonify({"results": []})
        return jsonify({"results": [], "error": f"setlist.fm returned HTTP {e.code}"})
    except Exception as exc:
        return jsonify({"results": [], "error": str(exc)})

    return jsonify({"results": parse_setlistfm(data)})


# --------------------------------------------------------------------------- #
# Backup / import  (DB + uploads in one zip)
# --------------------------------------------------------------------------- #
@app.route("/api/backup", methods=["GET"])
def backup():
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        # Consistent snapshot via SQLite online-backup API (WAL-safe).
        fd, tmp_db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            src = _connect()
            dst = sqlite3.connect(tmp_db)
            try:
                with dst:
                    src.backup(dst)
            finally:
                src.close()
                dst.close()
            z.write(tmp_db, "events.db")
        finally:
            os.remove(tmp_db)

        if os.path.isdir(UPLOADS_DIR):
            for root, _, files in os.walk(UPLOADS_DIR):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, UPLOADS_DIR)
                    z.write(full, os.path.join("uploads", rel))

        z.writestr("manifest.json", json.dumps({
            "app": "event-tracker",
            "version": 1,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }))

    mem.seek(0)
    fname = f"event-tracker-backup-{datetime.date.today().isoformat()}.zip"
    return send_file(mem, mimetype="application/zip",
                     as_attachment=True, download_name=fname)


@app.route("/api/import", methods=["POST"])
def import_backup():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    with tempfile.TemporaryDirectory() as tmpd:
        zip_path = os.path.join(tmpd, "in.zip")
        request.files["file"].save(zip_path)
        extract_dir = os.path.join(tmpd, "extract")
        os.makedirs(extract_dir)

        try:
            with zipfile.ZipFile(zip_path) as z:
                if "events.db" not in z.namelist():
                    return jsonify({"error": "Invalid backup: events.db missing"}), 400
                # zip-slip guard
                root_real = os.path.realpath(extract_dir)
                for n in z.namelist():
                    dest = os.path.realpath(os.path.join(extract_dir, n))
                    if not dest.startswith(root_real + os.sep):
                        return jsonify({"error": "Unsafe path in archive"}), 400
                z.extractall(extract_dir)
        except zipfile.BadZipFile:
            return jsonify({"error": "Not a valid zip file"}), 400

        new_db = os.path.join(extract_dir, "events.db")
        try:
            c = sqlite3.connect(new_db)
            ok = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"
            ).fetchone()
            c.close()
            if not ok:
                return jsonify({"error": "Invalid backup: events table missing"}), 400
        except sqlite3.DatabaseError:
            return jsonify({"error": "Invalid backup: corrupt database"}), 400

        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, f"{DB_PATH}.pre-import-{ts}")

        shutil.copy2(new_db, DB_PATH)
        for sfx in ("-wal", "-shm"):
            p = DB_PATH + sfx
            if os.path.exists(p):
                os.remove(p)

        src_up = os.path.join(extract_dir, "uploads")
        if os.path.isdir(src_up):
            if os.path.isdir(UPLOADS_DIR):
                shutil.rmtree(UPLOADS_DIR)
            shutil.copytree(src_up, UPLOADS_DIR)
        os.makedirs(UPLOADS_DIR, exist_ok=True)

    init_db()  # backup may predate current schema — bring it up to date
    return jsonify({"status": "imported"}), 200


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
@app.route("/api/stats", methods=["GET"])
def stats():
    with get_db() as conn:
        totals_row = conn.execute(
            "SELECT COUNT(*) AS events,"
            " COUNT(DISTINCT venue) AS venues,"
            " COUNT(DISTINCT city) AS cities,"
            " AVG(rating) AS avg_rating"
            " FROM events"
        ).fetchone()

        per_year = [
            {"year": r["y"], "count": r["c"]}
            for r in conn.execute(
                "SELECT substr(date, 1, 4) AS y, COUNT(*) AS c FROM events"
                " WHERE date IS NOT NULL AND length(date) >= 4"
                " GROUP BY y ORDER BY y"
            )
        ]

        by_type = [
            {"type": r["event_type"], "count": r["c"]}
            for r in conn.execute(
                "SELECT event_type, COUNT(*) AS c FROM events"
                " GROUP BY event_type ORDER BY c DESC"
            )
        ]

        top_venues = [
            {"venue": r["venue"], "city": r["city"], "count": r["c"]}
            for r in conn.execute(
                "SELECT venue, city, COUNT(*) AS c FROM events"
                " WHERE venue IS NOT NULL AND venue != ''"
                " GROUP BY venue, city ORDER BY c DESC, venue LIMIT 8"
            )
        ]

        top_artists = [
            {"name": r["name"], "count": r["c"]}
            for r in conn.execute(
                "SELECT name, COUNT(*) AS c FROM events"
                " WHERE event_type = 'concert'"
                " GROUP BY name ORDER BY c DESC, name LIMIT 8"
            )
        ]

        ratings = {str(n): 0 for n in range(1, 6)}
        for r in conn.execute(
            "SELECT rating, COUNT(*) AS c FROM events"
            " WHERE rating BETWEEN 1 AND 5 GROUP BY rating"
        ):
            ratings[str(r["rating"])] = r["c"]

        # Structured tables make these exact (no free-text parsing)
        top_attendees = [
            {"name": r["name"], "count": r["c"]}
            for r in conn.execute(
                "SELECT p.name, COUNT(*) AS c FROM event_people ep"
                " JOIN people p ON p.id = ep.person_id"
                " GROUP BY p.id ORDER BY c DESC, p.name LIMIT 8"
            )
        ]

        top_songs = [
            {"song": r["title"], "count": r["c"]}
            for r in conn.execute(
                "SELECT s.title, COUNT(*) AS c FROM setlist_songs s"
                " JOIN events e ON e.id = s.event_id"
                " WHERE e.event_type = 'concert'"
                " GROUP BY s.title COLLATE NOCASE"
                " HAVING c >= 2 ORDER BY c DESC, s.title LIMIT 10"
            )
        ]

    return jsonify({
        "totals": {
            "events": totals_row["events"],
            "venues": totals_row["venues"],
            "cities": totals_row["cities"],
            "avg_rating": round(totals_row["avg_rating"], 2) if totals_row["avg_rating"] else None,
        },
        "per_year": per_year,
        "by_type": by_type,
        "top_venues": top_venues,
        "top_artists": top_artists,
        "ratings": ratings,
        "top_attendees": top_attendees,
        "top_songs": top_songs,
    })


# --------------------------------------------------------------------------- #
# Static frontend (built React bundle)
# --------------------------------------------------------------------------- #
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/") or path.startswith("uploads/"):
        abort(404)
    if not os.path.isdir(DIST_DIR):
        return (
            "<h1>Event Tracker</h1><p>Frontend not built yet. "
            "Run <code>./setup.sh</code> to build it.</p>",
            200,
        )
    target = os.path.join(DIST_DIR, path)
    if path and os.path.isfile(target):
        return send_from_directory(DIST_DIR, path)
    return send_from_directory(DIST_DIR, "index.html")


# --------------------------------------------------------------------------- #
init_db()


def _detect_tailscale_ip():
    """Return this machine's Tailscale (100.x) IP, or None if not connected."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("100.100.100.100", 53))  # Tailscale MagicDNS; no packets sent
        ip = s.getsockname()[0]
        s.close()
        if ip.startswith("100."):
            return ip
    except OSError:
        pass
    return None


if __name__ == "__main__":
    from waitress import serve

    if HOST == "tailscale":
        ts_ip = _detect_tailscale_ip()
        if ts_ip:
            listen = f"{ts_ip}:{PORT} 127.0.0.1:{PORT}"
            print(f"Event Tracker listening on http://{ts_ip}:{PORT} (tailnet) "
                  f"and http://127.0.0.1:{PORT} (local)")
        else:
            listen = f"127.0.0.1:{PORT}"
            print("WARNING: HOST=tailscale but no Tailscale interface found — "
                  f"binding localhost only (http://127.0.0.1:{PORT})")
        serve(app, listen=listen)
    else:
        print(f"Event Tracker listening on http://{HOST}:{PORT}")
        serve(app, host=HOST, port=PORT)
