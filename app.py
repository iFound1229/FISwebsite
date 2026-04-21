import json
import mimetypes
import os
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
from flask import (
    Flask, render_template, request, redirect, url_for, abort, flash, Response
)

BASE_DIR = Path(__file__).parent

ADMIN_KEY = "lilyrose"
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

DEFAULT_BIO = """Introduction

Hello! We are Frog in Space, a rock-and-roll cover band from Mandeville, Louisiana. We play many events around school in the Northshore area, and are looking to expand our sound and reach.

Where in the world did that name come from?

The name, "Frog in Space," came from an improv game played in Colton and Grayson's Freshman theatre class. The game "Frog in the Pond" is about listening to what a leader is saying and not the action they are doing. Every action is "Frog in (blank)." Naturally, the one that has you waving your arms in the air crazy-style is the one where you yell, "FROG IN SPAAAAACE!" Grayson and Colton both thought this would be a hilarious but also super cool band name, so the rest is history. Here is a link to an example of the game for those that are interested:

https://www.youtube.com/watch?v=N34UNb6q9uA

Our Story

Frog in Space was founded on March 24th, 2024 by members Isaac Perdigao, Colton Gernon, James "Grayson" Honsberger, and Blaize Hastings. We started off very small having simple practices, and playing open mics. As we improved, we booked more gigs like the Fall Fest in the Sanctuary Subdivison. This year we've been growing rapidly in skill and bookings. Specifically, new musicians have been added or featured such as Cade Bourgeois (Bass), Liliana Maffei (Vocals), and Scott "Jay" Krieger (Keys). The band is now playing consistent gigs and is looking to branch out into original songwriting.

FIS is beyond excited for its future. We recently played at our Junior Prom which has certainly served as a turning point for the band. We have so many goals that we look forward to accomplish. As summer and our senior year approach, we have so much ahead of us. Expect to see original songs, performances, merch, and lots of Instagram Reels soon.

"Tell your friends. Word of mouth is very important!" - Gomez Addams

Thanks for your interest in Frog in Space!"""

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "frog-in-space-secret")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


# ---------- DB helpers ----------

def get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url)


def init_db():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_data (
              id INTEGER PRIMARY KEY DEFAULT 1,
              data JSONB NOT NULL,
              CONSTRAINT singleton CHECK (id = 1)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS media (
              id TEXT PRIMARY KEY,
              mime TEXT NOT NULL,
              bytes BYTEA NOT NULL,
              created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("SELECT 1 FROM site_data WHERE id = 1")
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO site_data (id, data) VALUES (1, %s)",
                (json.dumps(default_data()),),
            )
        conn.commit()


def default_data():
    return {
        "logo": None,
        "feature": None,
        "instagram": "https://www.instagram.com/froginspaceband/",
        "youtube": "",
        "contact_email": "colton.gernon@gmail.com",
        "bio": DEFAULT_BIO,
        "events": [],
        "past_events": [],
        "songs": [],
        "gallery": [],
    }


def load_data():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM site_data WHERE id = 1")
        row = cur.fetchone()
    base = default_data()
    if row:
        base.update(row[0] or {})
    return base


def save_data(data):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE site_data SET data = %s WHERE id = 1",
            (json.dumps(data),),
        )
        conn.commit()


# ---------- Media (images) stored in Postgres ----------

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    media_id = f"{uuid.uuid4().hex}.{ext}"
    mime = file_storage.mimetype or mimetypes.guess_type(file_storage.filename)[0] or "application/octet-stream"
    blob = file_storage.read()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO media (id, mime, bytes) VALUES (%s, %s, %s)",
            (media_id, mime, psycopg2.Binary(blob)),
        )
        conn.commit()
    return f"media/{media_id}"


def import_seed_files():
    """One-time: copy any local seed images into the DB if data has no logo/feature."""
    data = load_data()
    seed_dir = BASE_DIR / "static" / "uploads"
    changed = False

    def import_local(path: Path):
        ext = path.suffix.lstrip(".").lower()
        media_id = f"{uuid.uuid4().hex}.{ext}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            blob = f.read()
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO media (id, mime, bytes) VALUES (%s, %s, %s)",
                (media_id, mime, psycopg2.Binary(blob)),
            )
            conn.commit()
        return f"media/{media_id}"

    if not data.get("logo"):
        p = seed_dir / "logo.png"
        if p.exists():
            data["logo"] = import_local(p)
            changed = True
    if not data.get("feature"):
        p = seed_dir / "feature.jpg"
        if p.exists():
            data["feature"] = import_local(p)
            changed = True
    if changed:
        save_data(data)


@app.route("/media/<media_id>")
def serve_media(media_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT mime, bytes FROM media WHERE id = %s", (media_id,))
        row = cur.fetchone()
    if not row:
        abort(404)
    mime, blob = row
    return Response(bytes(blob), mimetype=mime, headers={"Cache-Control": "public, max-age=3600"})


# ---------- Template helper: build URLs for stored assets ----------

@app.context_processor
def inject_helpers():
    def asset_url(path):
        if not path:
            return ""
        if path.startswith("media/"):
            return url_for("serve_media", media_id=path.split("/", 1)[1])
        # legacy fallback for any leftover static path
        return url_for("static", filename=path)
    return {"asset_url": asset_url}


# ---------- Pages ----------

@app.route("/")
def home():
    return render_template("index.html", data=load_data(), active="home")


@app.route("/bio")
def bio():
    return render_template("bio.html", data=load_data(), active="bio")


@app.route("/shows")
def shows():
    return render_template("shows.html", data=load_data(), active="shows")


@app.route("/store")
def store():
    return render_template("store.html", data=load_data(), active="store")


@app.route("/songlist")
def songlist():
    return render_template("songlist.html", data=load_data(), active="songlist")


@app.route("/contact")
def contact():
    return render_template("contact.html", data=load_data(), active="contact")


# ---------- Admin ----------

@app.route("/<key>", methods=["GET"])
def admin(key):
    if key != ADMIN_KEY:
        abort(404)
    return render_template("admin.html", data=load_data(), key=key)


@app.route("/<key>/save", methods=["POST"])
def admin_save(key):
    if key != ADMIN_KEY:
        abort(404)
    data = load_data()

    data["instagram"] = request.form.get("instagram", "").strip()
    data["youtube"] = request.form.get("youtube", "").strip()
    data["contact_email"] = request.form.get("contact_email", "").strip() or "colton.gernon@gmail.com"
    data["bio"] = request.form.get("bio", "").strip() or DEFAULT_BIO

    logo = save_upload(request.files.get("logo"))
    if logo:
        data["logo"] = logo
    feature = save_upload(request.files.get("feature"))
    if feature:
        data["feature"] = feature

    def collect_events(prefix):
        dates = request.form.getlist(f"{prefix}_date")
        names = request.form.getlist(f"{prefix}_name")
        locations = request.form.getlist(f"{prefix}_location")
        existing_images = request.form.getlist(f"{prefix}_image_existing")
        new_files = request.files.getlist(f"{prefix}_image_new")
        out = []
        for i, (d, n, l) in enumerate(zip(dates, names, locations)):
            if not (d.strip() or n.strip() or l.strip()):
                continue
            img = existing_images[i] if i < len(existing_images) else ""
            if i < len(new_files):
                uploaded = save_upload(new_files[i])
                if uploaded:
                    img = uploaded
            out.append({
                "date": d.strip(),
                "name": n.strip(),
                "location": l.strip(),
                "image": img,
            })
        return out

    data["events"] = collect_events("event")
    data["past_events"] = collect_events("past_event")

    song_titles = request.form.getlist("song_title")
    song_artists = request.form.getlist("song_artist")
    songs = []
    for t, a in zip(song_titles, song_artists):
        if t.strip() or a.strip():
            songs.append({"title": t.strip(), "artist": a.strip()})
    data["songs"] = songs

    keep = request.form.getlist("gallery_keep")
    data["gallery"] = [g for g in data["gallery"] if g in keep]
    for f in request.files.getlist("gallery_new"):
        path = save_upload(f)
        if path:
            data["gallery"].append(path)

    save_data(data)
    flash("Saved!", "success")
    return redirect(url_for("admin", key=key))


# ---------- Startup ----------

init_db()
import_seed_files()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
