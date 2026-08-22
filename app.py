import json
import hashlib
import hmac
import mimetypes
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import psycopg2
import psycopg2.extras
from flask import (
    Flask, render_template, request, redirect, url_for, abort, flash, Response,
    jsonify, session, make_response
)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).parent

MEMBER_SLOT_COUNT = 8
NEW_MEMBER_NAME = "New Member"
ADMIN_PANEL_PATH = "/lilyrose"
ADMIN_INACTIVITY_SECONDS = 15 * 60
ADMIN_MAX_LIFETIME_SECONDS = 15 * 60
LOGIN_WINDOW = timedelta(minutes=20)
LOGIN_MAX_FAILURES = 5
CART_ADD_LIMIT = 5
CART_ADD_WINDOW_SECONDS = 60
CART_ADD_ATTEMPTS = {}
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
app.secret_key = (
    os.environ.get("SESSION_SECRET")
    or os.environ.get("FLASK_SECRET")
    or secrets.token_hex(32)
)
PRODUCTION_MODE = os.environ.get("APP_ENV", "").lower() == "production"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=PRODUCTION_MODE,
    SESSION_COOKIE_SAMESITE="Strict",
)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
PASSWORD_HASHER = PasswordHasher()
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
              session_hash TEXT PRIMARY KEY,
              csrf_hash TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL,
              invalidated_at TIMESTAMPTZ,
              ip_address INET,
              user_agent TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_login_limits (
              rate_key TEXT PRIMARY KEY,
              window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              failures INTEGER NOT NULL DEFAULT 0,
              blocked_until TIMESTAMPTZ
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
    members = [{"name": "", "bio": "", "image": None} for _ in range(MEMBER_SLOT_COUNT)]
    members[-1]["name"] = NEW_MEMBER_NAME
    return {
        "logo": None,
        "nav_logo": None,
        "feature": None,
        "login_image": None,
        "instagram": "https://www.instagram.com/froginspaceband/",
        "youtube": "",
        "contact_email": "colton.gernon@gmail.com",
        "bio": DEFAULT_BIO,
        "events": [],
        "past_events": [],
        "songs": [],
        "products": [],
        "gallery": [],
        "members": members,
    }


def load_data():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM site_data WHERE id = 1")
        row = cur.fetchone()
    base = default_data()
    if row:
        base.update(row[0] or {})
    members = list(base.get("members") or [])
    while len(members) < MEMBER_SLOT_COUNT:
        members.append({
            "name": NEW_MEMBER_NAME if len(members) == MEMBER_SLOT_COUNT - 1 else "",
            "bio": "",
            "image": None,
        })
    base["members"] = members[:MEMBER_SLOT_COUNT]
    return base


def save_data(data):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE site_data SET data = %s WHERE id = 1",
            (json.dumps(data),),
        )
        conn.commit()


# ---------- Admin authentication ----------

def _token_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_ip():
    return request.remote_addr or "unknown"


def _rate_keys(email):
    normalized_email = email.casefold()[:254]
    return [f"ip:{_client_ip()}", f"email:{normalized_email}"]


def _login_is_limited(rate_keys):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT blocked_until
            FROM admin_login_limits
            WHERE rate_key = ANY(%s)
              AND window_started_at >= NOW() - INTERVAL '20 minutes'
              AND blocked_until > NOW()
            """,
            (rate_keys,),
        )
        return cur.fetchone() is not None


def _record_failed_login(rate_keys):
    now = datetime.now(timezone.utc)
    with get_conn() as conn, conn.cursor() as cur:
        for rate_key in rate_keys:
            cur.execute(
                """
                SELECT window_started_at, failures
                FROM admin_login_limits
                WHERE rate_key = %s
                FOR UPDATE
                """,
                (rate_key,),
            )
            row = cur.fetchone()
            if not row or row[0] < now - LOGIN_WINDOW:
                window_started = now
                failures = 1
            else:
                window_started = row[0]
                failures = row[1] + 1

            backoff_seconds = 0
            if failures >= LOGIN_MAX_FAILURES:
                backoff_seconds = min(15 * 60, 5 * (2 ** min(failures - LOGIN_MAX_FAILURES, 8)))
            blocked_until = now + timedelta(seconds=backoff_seconds) if backoff_seconds else None
            cur.execute(
                """
                INSERT INTO admin_login_limits
                  (rate_key, window_started_at, failures, blocked_until)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (rate_key) DO UPDATE SET
                  window_started_at = EXCLUDED.window_started_at,
                  failures = EXCLUDED.failures,
                  blocked_until = EXCLUDED.blocked_until
                """,
                (rate_key, window_started, failures, blocked_until),
            )
        conn.commit()


def _clear_login_limits(rate_keys):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM admin_login_limits WHERE rate_key = ANY(%s)", (rate_keys,))
        conn.commit()


def _admin_credentials():
    email = os.environ.get("ADMIN_EMAIL", "").strip().casefold()
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    if not EMAIL_PATTERN.fullmatch(email) or not password_hash:
        return None, None
    return email, password_hash


def _get_admin_session():
    raw_token = request.cookies.get("admin_session", "")
    if not raw_token:
        return None

    session_hash = _token_hash(raw_token)
    now = datetime.now(timezone.utc)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_hash, csrf_hash, created_at, last_seen_at, expires_at
            FROM admin_sessions
            WHERE session_hash = %s AND invalidated_at IS NULL
            """,
            (session_hash,),
        )
        row = cur.fetchone()
        if not row:
            return None

        def utc(value):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        if (
            utc(row[2]) + timedelta(seconds=ADMIN_MAX_LIFETIME_SECONDS) <= now
            or utc(row[3]) + timedelta(seconds=ADMIN_INACTIVITY_SECONDS) <= now
            or utc(row[4]) <= now
        ):
            cur.execute(
                "UPDATE admin_sessions SET invalidated_at = NOW() WHERE session_hash = %s",
                (session_hash,),
            )
            conn.commit()
            app.logger.info("admin_session_expired ip=%s", _client_ip())
            return None

        cur.execute(
            "UPDATE admin_sessions SET last_seen_at = NOW() WHERE session_hash = %s",
            (session_hash,),
        )
        conn.commit()

    return {"session_hash": row[0], "csrf_hash": row[1]}


def _create_admin_session():
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ADMIN_MAX_LIFETIME_SECONDS)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_sessions
              (session_hash, csrf_hash, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                _token_hash(raw_token),
                _token_hash(csrf_token),
                expires_at,
                _client_ip() if _client_ip() != "unknown" else None,
                request.user_agent.string[:512],
            ),
        )
        conn.commit()
    return raw_token, csrf_token


def _invalidate_admin_session(auth):
    if not auth:
        return
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE admin_sessions SET invalidated_at = NOW() WHERE session_hash = %s",
            (auth["session_hash"],),
        )
        conn.commit()


def _csrf_is_valid(auth):
    submitted = request.form.get("csrf_token", "")
    return bool(submitted) and hmac.compare_digest(_token_hash(submitted), auth["csrf_hash"])


def _rotate_csrf_token(auth):
    csrf_token = secrets.token_urlsafe(32)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE admin_sessions SET csrf_hash = %s WHERE session_hash = %s",
            (_token_hash(csrf_token), auth["session_hash"]),
        )
        conn.commit()
    return csrf_token


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = _get_admin_session()
        if not auth:
            app.logger.warning("admin_authorization_failed path=%s ip=%s", request.path, _client_ip())
            return redirect(url_for("admin_login", next=ADMIN_PANEL_PATH))
        request.admin_auth = auth
        return view(*args, **kwargs)

    return wrapped


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'",
    )
    return response


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


@app.route("/store/item/<int:item_index>")
def store_item(item_index):
    products = load_data().get("products") or []
    if item_index < 0 or item_index >= len(products):
        abort(404)
    return render_template(
        "store_item.html",
        data=load_data(),
        product=products[item_index],
        item_index=item_index,
        active="store",
    )


@app.route("/store/cart")
def store_cart():
    return render_template("store_cart.html", data=load_data(), active="store")


@app.route("/store/cart/add", methods=["POST"])
def add_to_cart():
    now = time.monotonic()
    ip = _client_ip()
    attempts = [stamp for stamp in CART_ADD_ATTEMPTS.get(ip, []) if now - stamp < CART_ADD_WINDOW_SECONDS]
    if len(attempts) >= CART_ADD_LIMIT:
        retry_after = max(1, int(CART_ADD_WINDOW_SECONDS - (now - attempts[0])))
        response = jsonify({"ok": False, "message": "Please wait a moment before adding more items."})
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        CART_ADD_ATTEMPTS[ip] = attempts
        return response
    attempts.append(now)
    CART_ADD_ATTEMPTS[ip] = attempts
    return jsonify({"ok": True})


@app.route("/songlist")
def songlist():
    return render_template("songlist.html", data=load_data(), active="songlist")


@app.route("/contact")
def contact():
    return render_template("contact.html", data=load_data(), active="contact")


@app.route("/members")
def members():
    unlock_nonce = uuid.uuid4().hex
    session["admin_unlock_nonce"] = unlock_nonce
    return render_template(
        "members.html",
        data=load_data(),
        active="members",
        unlock_nonce=unlock_nonce,
    )


@app.route("/members/unlock", methods=["POST"])
def unlock_admin():
    nonce = request.form.get("nonce", "")
    expected_nonce = session.get("admin_unlock_nonce")
    if not nonce or nonce != expected_nonce:
        return jsonify({"ok": False}), 403
    session.pop("admin_unlock_nonce", None)
    return jsonify({"ok": True})


# ---------- Admin ----------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if _get_admin_session():
        return redirect(ADMIN_PANEL_PATH)

    next_path = request.args.get("next", request.form.get("next", ADMIN_PANEL_PATH))
    if next_path != ADMIN_PANEL_PATH:
        next_path = ADMIN_PANEL_PATH

    if request.method == "GET":
        login_csrf = secrets.token_urlsafe(32)
        response = make_login_response(login_csrf)
        response.set_cookie(
            "login_csrf",
            login_csrf,
            httponly=True,
            secure=PRODUCTION_MODE,
            samesite="Strict",
            max_age=600,
            path="/admin",
        )
        return response

    email = request.form.get("email", "").strip().casefold()
    password = request.form.get("password", "")
    login_csrf = request.form.get("login_csrf", "")
    cookie_csrf = request.cookies.get("login_csrf", "")
    generic_error = "Invalid email or password."

    if (
        not login_csrf
        or not cookie_csrf
        or not hmac.compare_digest(login_csrf, cookie_csrf)
        or len(email) > 254
        or not EMAIL_PATTERN.fullmatch(email)
        or not password
        or len(password) > 256
    ):
        flash(generic_error, "error")
        return redirect(url_for("admin_login", next=next_path))

    rate_keys = _rate_keys(email)
    if _login_is_limited(rate_keys):
        flash(generic_error, "error")
        return redirect(url_for("admin_login", next=next_path))

    configured_email, configured_hash = _admin_credentials()
    valid = configured_email == email and configured_hash is not None
    if valid:
        try:
            PASSWORD_HASHER.verify(configured_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False

    if not valid:
        _record_failed_login(rate_keys)
        app.logger.warning("admin_login_failed ip=%s", _client_ip())
        flash(generic_error, "error")
        return redirect(url_for("admin_login", next=next_path))

    _clear_login_limits(rate_keys)
    raw_token, csrf_token = _create_admin_session()
    app.logger.info("admin_login_success ip=%s", _client_ip())
    response = redirect(next_path)
    response.set_cookie(
        "admin_session",
        raw_token,
        httponly=True,
        secure=PRODUCTION_MODE,
        samesite="Strict",
        path="/",
    )
    response.delete_cookie("login_csrf", path="/admin")
    return response


def make_login_response(login_csrf):
    return make_response(
        render_template(
            "admin_login.html",
            data=load_data(),
            login_csrf=login_csrf,
        )
    )


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    auth = request.admin_auth
    if not _csrf_is_valid(auth):
        abort(400)
    _invalidate_admin_session(auth)
    app.logger.info("admin_logout ip=%s", _client_ip())
    response = redirect(url_for("admin_login"))
    response.delete_cookie("admin_session", path="/")
    session.clear()
    return response


@app.route("/lilyrose", methods=["GET"])
@admin_required
def admin_panel():
    return render_template(
        "admin.html",
        data=load_data(),
        csrf_token=_rotate_csrf_token(request.admin_auth),
    )


@app.route("/lilyrose/save", methods=["POST"])
@admin_required
def admin_save():
    if not _csrf_is_valid(request.admin_auth):
        abort(400)
    data = load_data()

    data["instagram"] = request.form.get("instagram", "").strip()
    data["youtube"] = request.form.get("youtube", "").strip()
    data["contact_email"] = request.form.get("contact_email", "").strip() or "colton.gernon@gmail.com"
    data["bio"] = request.form.get("bio", "").strip() or DEFAULT_BIO

    logo = save_upload(request.files.get("logo"))
    if logo:
        data["logo"] = logo
    nav_logo = save_upload(request.files.get("nav_logo"))
    if nav_logo:
        data["nav_logo"] = nav_logo
    feature = save_upload(request.files.get("feature"))
    if feature:
        data["feature"] = feature
    login_image = save_upload(request.files.get("login_image"))
    if login_image:
        data["login_image"] = login_image

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

    products = []
    product_names = request.form.getlist("product_name")
    product_prices = request.form.getlist("product_price")
    product_descriptions = request.form.getlist("product_description")
    product_keys = request.form.getlist("product_key")
    for i, (name, price) in enumerate(zip(product_names, product_prices)):
        name = name.strip()
        price = price.strip()
        description = product_descriptions[i].strip() if i < len(product_descriptions) else ""
        key = product_keys[i] if i < len(product_keys) else str(i)
        if not (name or price or description):
            continue
        colors = request.form.getlist(f"product_{key}_color")
        existing_images = request.form.getlist(f"product_{key}_existing")
        uploaded_images = request.files.getlist(f"product_{key}_image")
        clean_variants = []
        for variant_index, color_value in enumerate(colors):
            color = color_value.strip()
            images = []
            if variant_index < len(existing_images) and existing_images[variant_index].strip():
                images.append(existing_images[variant_index].strip())
            if variant_index < len(uploaded_images):
                saved = save_upload(uploaded_images[variant_index])
                if saved:
                    images.append(saved)
            if color or images:
                clean_variants.append({"color": color, "images": images})
        products.append({"name": name, "description": description, "price": price, "variants": clean_variants})
    data["products"] = products

    keep = request.form.getlist("gallery_keep")
    data["gallery"] = [g for g in data["gallery"] if g in keep]
    for f in request.files.getlist("gallery_new"):
        path = save_upload(f)
        if path:
            data["gallery"].append(path)

    member_names = request.form.getlist("member_name")
    member_bios = request.form.getlist("member_bio")
    member_existing = request.form.getlist("member_image_existing")
    member_files = request.files.getlist("member_image_new")
    members_out = []
    for i in range(MEMBER_SLOT_COUNT):
        name = member_names[i].strip() if i < len(member_names) else ""
        bio = member_bios[i].strip() if i < len(member_bios) else ""
        img = member_existing[i] if i < len(member_existing) else ""
        if i < len(member_files):
            uploaded = save_upload(member_files[i])
            if uploaded:
                img = uploaded
        if i == MEMBER_SLOT_COUNT - 1 and not name:
            name = NEW_MEMBER_NAME
        members_out.append({"name": name, "bio": bio, "image": img or None})
    data["members"] = members_out

    save_data(data)
    app.logger.info("admin_content_saved ip=%s", _client_ip())
    flash("Saved!", "success")
    return redirect(url_for("admin_panel"))


# ---------- Startup ----------

init_db()
import_seed_files()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
