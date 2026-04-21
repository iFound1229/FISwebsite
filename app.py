import json
import os
import uuid
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, flash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_KEY = "lilyrose"
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = "frog-in-space-secret"
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB


def default_data():
    return {
        "logo": "uploads/logo.png",
        "feature": "uploads/feature.jpg",
        "instagram": "",
        "youtube": "",
        "events": [],
        "songs": [],
        "gallery": [],
    }


def load_data():
    if not DATA_FILE.exists():
        save_data(default_data())
    with open(DATA_FILE) as f:
        data = json.load(f)
    base = default_data()
    base.update(data)
    return base


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex}.{ext}"
    path = UPLOAD_DIR / name
    file_storage.save(path)
    return f"uploads/{name}"


@app.route("/")
def home():
    return render_template("index.html", data=load_data())


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

    logo = save_upload(request.files.get("logo"))
    if logo:
        data["logo"] = logo
    feature = save_upload(request.files.get("feature"))
    if feature:
        data["feature"] = feature

    # Events
    event_dates = request.form.getlist("event_date")
    event_names = request.form.getlist("event_name")
    event_locations = request.form.getlist("event_location")
    events = []
    for d, n, l in zip(event_dates, event_names, event_locations):
        if d.strip() or n.strip() or l.strip():
            events.append({"date": d.strip(), "name": n.strip(), "location": l.strip()})
    data["events"] = events

    # Songs
    song_titles = request.form.getlist("song_title")
    song_artists = request.form.getlist("song_artist")
    songs = []
    for t, a in zip(song_titles, song_artists):
        if t.strip() or a.strip():
            songs.append({"title": t.strip(), "artist": a.strip()})
    data["songs"] = songs

    # Gallery: keep existing ones whose paths are submitted, plus new uploads
    keep = request.form.getlist("gallery_keep")
    data["gallery"] = [g for g in data["gallery"] if g in keep]
    for f in request.files.getlist("gallery_new"):
        path = save_upload(f)
        if path:
            data["gallery"].append(path)

    save_data(data)
    flash("Saved!", "success")
    return redirect(url_for("admin", key=key))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
