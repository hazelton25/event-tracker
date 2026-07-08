"""
Event Tracker test suite.

Run from backend/:  .venv/bin/python -m pytest tests/ -v
Uses a temp DB + uploads dir per test session (set via env before app import).
"""
import io
import os
import json
import sqlite3
import zipfile
import tempfile

import pytest

# Point the app at throwaway paths BEFORE importing it.
_TMP = tempfile.mkdtemp(prefix="et-test-")
os.environ["EVENTTRACKER_DB"] = os.path.join(_TMP, "test.db")
os.environ["EVENTTRACKER_UPLOADS"] = os.path.join(_TMP, "uploads")

import app as et  # noqa: E402


@pytest.fixture()
def client():
    # Fresh DB per test.
    for sfx in ("", "-wal", "-shm"):
        p = et.DB_PATH + sfx
        if os.path.exists(p):
            os.remove(p)
    et.init_db()
    et.app.config["TESTING"] = True
    with et.app.test_client() as c:
        yield c


def make_event(client, **over):
    payload = {
        "name": "The National",
        "event_type": "concert",
        "date": "2025-08-14",
        "venue": "Massey Hall",
        "city": "Toronto",
        "setlist": "Sea of Love\nBloodbuzz Ohio",
        "attendees": "Sarah & Mike",
        "rating": 5,
    }
    payload.update(over)
    return client.post("/api/events", json=payload)


# ---------------------------------------------------------------- migrations
def test_migrations_apply_and_are_idempotent(client):
    with et.get_db() as conn:
        assert et.schema_version(conn) == len(et.MIGRATIONS)
    et.init_db()  # second run must be a no-op
    with et.get_db() as conn:
        assert et.schema_version(conn) == len(et.MIGRATIONS)
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert count == len(et.MIGRATIONS)


def test_pre_migration_db_adopts_cleanly(client):
    """A DB created before the migration system (no schema_version) upgrades."""
    os.remove(et.DB_PATH)
    conn = sqlite3.connect(et.DB_PATH)
    conn.executescript(et.MIGRATIONS[0])  # baseline table only, no version table
    conn.execute("INSERT INTO events (name) VALUES ('Legacy Event')")
    conn.commit()
    conn.close()

    et.init_db()
    with et.get_db() as conn:
        assert et.schema_version(conn) == len(et.MIGRATIONS)
        name = conn.execute("SELECT name FROM events").fetchone()["name"]
        assert name == "Legacy Event"  # data survives adoption


# ---------------------------------------------------------------------- CRUD
def test_create_and_get(client):
    r = make_event(client)
    assert r.status_code == 201
    ev = r.get_json()
    assert ev["id"] == 1 and ev["rating"] == 5

    r2 = client.get(f"/api/events/{ev['id']}")
    assert r2.status_code == 200
    assert r2.get_json()["venue"] == "Massey Hall"


def test_create_requires_name(client):
    r = client.post("/api/events", json={"name": "  "})
    assert r.status_code == 400


def test_create_with_only_name(client):
    """Minimal payload must not 500 — event_type falls back to default."""
    r = client.post("/api/events", json={"name": "Bare Minimum"})
    assert r.status_code == 201
    assert r.get_json()["event_type"] == "concert"


def test_list_filter_and_sort(client):
    make_event(client, name="A Show", date="2025-01-01", rating=3)
    make_event(client, name="B Game", event_type="sports", date="2025-06-01", rating=4)
    make_event(client, name="C Fest", event_type="festival", date="2025-03-01", rating=5)

    r = client.get("/api/events?type=sports")
    assert [e["name"] for e in r.get_json()] == ["B Game"]

    r = client.get("/api/events?sort=date&order=asc")
    assert [e["name"] for e in r.get_json()] == ["A Show", "C Fest", "B Game"]

    r = client.get("/api/events?sort=rating&order=desc")
    assert [e["rating"] for e in r.get_json()] == [5, 4, 3]

    # unknown sort column must not 500 (and must not be injectable)
    r = client.get("/api/events?sort=;DROP TABLE events;--")
    assert r.status_code == 200


def test_update_and_delete(client):
    ev = make_event(client).get_json()
    r = client.put(f"/api/events/{ev['id']}", json={"rating": 2, "city": "Hamilton"})
    body = r.get_json()
    assert body["rating"] == 2 and body["city"] == "Hamilton"
    assert body["name"] == "The National"  # untouched fields survive

    assert client.delete(f"/api/events/{ev['id']}").status_code == 200
    assert client.get(f"/api/events/{ev['id']}").status_code == 404
    assert client.delete("/api/events/999").status_code == 404
    assert client.put("/api/events/999", json={"rating": 1}).status_code == 404


# ------------------------------------------------------------- backup/import
def test_backup_zip_contents(client):
    make_event(client)
    os.makedirs(et.UPLOADS_DIR, exist_ok=True)
    with open(os.path.join(et.UPLOADS_DIR, "event_1_x.jpg"), "wb") as f:
        f.write(b"fakeimg")

    r = client.get("/api/backup")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.data))
    names = z.namelist()
    assert "events.db" in names
    assert "manifest.json" in names
    assert "uploads/event_1_x.jpg" in names
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["app"] == "event-tracker"


def test_backup_import_round_trip(client):
    make_event(client)
    make_event(client, name="Second Show")
    backup_bytes = client.get("/api/backup").data

    # wipe: delete both events
    for e in client.get("/api/events").get_json():
        client.delete(f"/api/events/{e['id']}")
    assert client.get("/api/events").get_json() == []

    r = client.post("/api/import", data={
        "file": (io.BytesIO(backup_bytes), "backup.zip"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200

    names = sorted(e["name"] for e in client.get("/api/events").get_json())
    assert names == ["Second Show", "The National"]

    # pre-import safety snapshot must exist
    snaps = [f for f in os.listdir(os.path.dirname(et.DB_PATH))
             if f.startswith(os.path.basename(et.DB_PATH) + ".pre-import-")]
    assert snaps


def test_import_rejects_garbage(client):
    # not a zip
    r = client.post("/api/import", data={
        "file": (io.BytesIO(b"not a zip"), "x.zip"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400

    # zip without events.db
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hi")
    buf.seek(0)
    r = client.post("/api/import", data={"file": (buf, "x.zip")},
                    content_type="multipart/form-data")
    assert r.status_code == 400

    # zip where events.db is not a sqlite db
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("events.db", "definitely not sqlite")
    buf.seek(0)
    r = client.post("/api/import", data={"file": (buf, "x.zip")},
                    content_type="multipart/form-data")
    assert r.status_code == 400

    # zip-slip attempt
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("events.db", "x")
        z.writestr("../../evil.txt", "pwned")
    buf.seek(0)
    r = client.post("/api/import", data={"file": (buf, "x.zip")},
                    content_type="multipart/form-data")
    assert r.status_code == 400

    # no file at all
    assert client.post("/api/import").status_code == 400


def test_import_migrates_old_backup(client):
    """A backup taken at schema v1 must be migrated to current on import."""
    fd, old_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(old_db)
    conn.executescript(et.MIGRATIONS[0])
    conn.execute(
        "CREATE TABLE schema_version (version INTEGER NOT NULL, "
        "applied_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.execute("INSERT INTO events (name) VALUES ('Old Backup Event')")
    conn.commit()
    conn.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(old_db, "events.db")
    os.remove(old_db)
    buf.seek(0)

    r = client.post("/api/import", data={"file": (buf, "old.zip")},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    with et.get_db() as conn:
        assert et.schema_version(conn) == len(et.MIGRATIONS)
    names = [e["name"] for e in client.get("/api/events").get_json()]
    assert names == ["Old Backup Event"]


# --------------------------------------------------------------------- stats
def test_split_attendees():
    assert et.split_attendees("Sarah & Mike") == ["Sarah", "Mike"]
    assert et.split_attendees("Dad") == ["Dad"]
    assert et.split_attendees("A, B and C + D") == ["A", "B", "C", "D"]
    assert et.split_attendees(None) == []
    assert et.split_attendees("  ") == []


def test_stats(client):
    make_event(client, name="The National", date="2024-05-01", rating=5,
               attendees="Sarah & Mike", setlist="Fake Empire\nAbout Today")
    make_event(client, name="The National", date="2025-08-14", rating=4,
               attendees="Sarah", setlist="Fake Empire\nSea of Love")
    make_event(client, name="Leafs vs Bruins", event_type="sports",
               date="2025-11-02", rating=4, attendees="Dad", venue="Scotiabank Arena")

    s = client.get("/api/stats").get_json()
    assert s["totals"]["events"] == 3
    assert s["totals"]["avg_rating"] == 4.33
    assert {"year": "2025", "count": 2} in s["per_year"]
    assert s["by_type"][0] == {"type": "concert", "count": 2}
    assert s["top_artists"][0] == {"name": "The National", "count": 2}
    assert s["top_attendees"][0] == {"name": "Sarah", "count": 2}
    # only songs seen 2+ times chart
    assert s["top_songs"] == [{"song": "Fake Empire", "count": 2}]
    assert s["ratings"]["4"] == 2 and s["ratings"]["5"] == 1


def test_stats_empty_db(client):
    s = client.get("/api/stats").get_json()
    assert s["totals"]["events"] == 0
    assert s["totals"]["avg_rating"] is None
    assert s["per_year"] == [] and s["top_songs"] == []


# -------------------------------------------------------------------- images
def test_image_upload_rejects_bad_extension(client):
    ev = make_event(client).get_json()
    r = client.post(f"/api/events/{ev['id']}/image", data={
        "file": (io.BytesIO(b"#!/bin/sh"), "evil.sh"),
    }, content_type="multipart/form-data")
    assert r.status_code == 400


def test_image_upload_accepts_jpg(client):
    ev = make_event(client).get_json()
    r = client.post(f"/api/events/{ev['id']}/image", data={
        "file": (io.BytesIO(b"\xff\xd8\xff\xe0fakejpg"), "photo.jpg"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    url = r.get_json()["image_url"]
    assert url.startswith("/uploads/") and url.endswith(".jpg")
    assert os.path.exists(os.path.join(et.UPLOADS_DIR, os.path.basename(url)))


# ----------------------------------------------------------------- setlist.fm
def test_parse_setlistfm():
    sample = {"setlist": [{
        "artist": {"name": "The National"},
        "eventDate": "14-08-2025",
        "venue": {"name": "Massey Hall", "city": {"name": "Toronto"}},
        "sets": {"set": [
            {"song": [{"name": "Sea of Love"},
                      {"name": "Peggy-O", "cover": {"name": "Grateful Dead"}}]},
            {"encore": 1, "song": [{"name": "About Today"}, {"name": ""}]},
        ]},
    }]}
    r = et.parse_setlistfm(sample)
    assert len(r) == 1
    c = r[0]
    assert c["venue"] == "Massey Hall" and c["city"] == "Toronto"
    assert c["songs"] == ["Sea of Love", "Peggy-O (Grateful Dead cover)", "About Today"]
    assert c["song_count"] == 3
    assert et.parse_setlistfm({}) == []


def test_setlist_search_without_key(client):
    et.SETLISTFM_API_KEY = ""
    r = client.get("/api/setlist-search?artist=The+National")
    body = r.get_json()
    assert r.status_code == 200
    assert body["results"] == [] and "API key" in body["error"]
