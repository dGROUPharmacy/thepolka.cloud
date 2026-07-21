# ThePolka.Cloud — Render deployment

This repository runs the existing Flask/Jinja website as a continuously available paid Render web service. It is not a GitHub Pages site: GitHub stores the source, and Render executes `app.py` with Gunicorn.

## Local verification

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`.

Open `http://127.0.0.1:8000/` and verify `http://127.0.0.1:8000/health` returns JSON with `"status": "ok"`.

## Upload to GitHub

Create an empty public or private repository. From this directory:

```bash
git init
git add app.py requirements.txt render.yaml templates static instance/.gitkeep .gitignore .env.example README.md
git commit -m "Prepare ThePolka.Cloud for Render"
git branch -M main
git remote add origin https://github.com/dGROUPharmacy/thepolka.cloud.git
git push -u origin main
```

Do not commit `.env`, SQLite databases, private keys, tunnel credentials, or user data.

## Create the Render service

1. Sign in to Render with GitHub.
2. Select **New → Blueprint**.
3. Connect `dGROUPharmacy/thepolka.cloud`.
4. Render reads `render.yaml` and proposes one paid Starter web service with a 1 GB persistent disk.
5. Confirm the service creation.
6. Wait for the deployment to finish.
7. Visit the generated `onrender.com` URL.
8. Test `/`, `/health`, static assets, navigation, and the 404 page.

The service uses `/var/data` for durable files. Place production SQLite databases on that disk; do not store them in Git.

## Connect the custom domain

1. In Render, open the service and select **Settings → Custom Domains**.
2. Add `thepolka.cloud` and optionally `www.thepolka.cloud`.
3. Copy the DNS record Render displays.
4. In Cloudflare DNS, replace the old root tunnel record with Render's target.
5. Complete domain verification in Render.
6. Confirm HTTPS works before deleting the old deployment.

## Production checks

- `/health` returns HTTP 200.
- The root page renders Jinja templates.
- CSS, JavaScript, and the brand image load.
- Render reports the service as Live.
- The service uses a paid instance and does not spin down.
- `/var/data` is attached before importing any database.
- No secrets or database files appear in GitHub.
