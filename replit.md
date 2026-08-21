# Frog in Space

## Run

The app is a Flask site served by Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 --reuse-port app:app
```

Set `DATABASE_URL`, `SESSION_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD_HASH` before starting. Railway uses the included Dockerfile and starts `app:app` on its assigned `PORT`.

The public store is managed from `/lilyrose` after signing in at `/admin`. Admin sessions expire after 15 minutes.