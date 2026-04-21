import json
import uuid
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, abort, flash

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
app.secret_key = "frog-in-space-secret"
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


def default_data():
    return {
        "logo": "uploads/logo.png",
        "feature": "uploads/feature.jpg",
        "instagram": "https://www.instagram.com/froginspaceband/",
        "youtube": "",
        "contact_email": "colton.gernon@gmail.com",
        "bio": DEFAULT_BIO,
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

    event_dates = request.form.getlist("event_date")
    event_names = request.form.getlist("event_name")
    event_locations = request.form.getlist("event_location")
    events = []
    for d, n, l in zip(event_dates, event_names, event_locations):
        if d.strip() or n.strip() or l.strip():
            events.append({"date": d.strip(), "name": n.strip(), "location": l.strip()})
    data["events"] = events

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
