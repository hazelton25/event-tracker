"""
Event Tracker — Flask backend.

Single-process app: serves the JSON API under /api/* and the built React
bundle (frontend/dist) as static files, so the whole thing runs on one port.
"""
import os
import io
import json
import shutil
import sqlite3
import zipfile
import tempfile
import datetime
import urllib.parse
import urllib.request

from flask import (
    Flask, request, jsonify, send_file, send_from_directory, abort
)
from flask_cors import CORS

# --------------------------------------------------------------------------- #
# Paths / config
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "events.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
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
# Database
# --------------------------------------------------------------------------- #
SCHEMA = """
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
"""

EVENT_FIELDS = (
    "name", "event_type", "date", "venue", "city",
    "setlist", "notes", "attendees", "rating", "image_url",
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


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
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/events/<int:event_id>", methods=["GET"])
def get_event(event_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json(silent=True) or {}
    if not (data.get("name") or "").strip():
        return jsonify({"error": "Name is required"}), 400

    vals = [data.get(f) for f in EVENT_FIELDS]
    placeholders = ", ".join("?" for _ in EVENT_FIELDS)
    cols = ", ".join(EVENT_FIELDS)

    with get_db() as conn:
        cur = conn.execute(
            f"INSERT INTO events ({cols}) VALUES ({placeholders})", vals
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM events WHERE id = ?", (new_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


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
        if not updates:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            return jsonify(row_to_dict(row))

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [event_id]
        conn.execute(
            f"UPDATE events SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            params,
        )
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return jsonify(row_to_dict(row))


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
            "UPDATE events SET image_url = ?, updated_at = datetime('now') WHERE id = ?",
            (local_path, event_id),
        )
        updated = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return jsonify(row_to_dict(updated))


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
            src = get_db()
            dst = sqlite3.connect(tmp_db)
            with dst:
                src.backup(dst)
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

    return jsonify({"status": "imported"}), 200


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
