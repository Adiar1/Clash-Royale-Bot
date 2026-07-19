import hmac
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for


# ---- Resolve repo root regardless of where the app is launched ----
def find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists():
            return parent
    # Fallback: use the folder containing this file
    return p


HERE = Path(__file__).resolve().parent  # folder with this file
BOT_DIR = find_repo_root(HERE)  # repo root: /opt/Clash-Royale-Bot
BOT_SCRIPT = BOT_DIR / "main.py"
ENV_FILE = BOT_DIR / ".env"
TEMPLATES_DIR = BOT_DIR / "linode" / "templates"
STATIC_DIR = BOT_DIR / "linode" / "static"  # optional; use if you have one

load_dotenv(ENV_FILE if ENV_FILE.exists() else None)


def db_path() -> Path:
    """Where the bot keeps its SQLite file.

    Mirrors the bot's config (DATABASE_PATH, default "database.db"), resolved
    relative to the repo root so the panel reads the *same* file the bot writes.
    """
    raw = os.getenv("DATABASE_PATH", "database.db")
    p = Path(raw)
    return p if p.is_absolute() else (BOT_DIR / p)

# Stable secret key (don't regenerate on every restart or you'll get logged out)
SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("FLASK_SECRET_KEY must be set to run the control panel.")

# The panel exposes the .env editor, file browser, and restart controls, so a
# missing/empty password must be a startup error — with an empty ADMIN_PASSWORD
# an empty login form would authenticate.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_PASSWORD must be set (non-empty) to run the control panel.")

# Always register the static folder (even if it isn't present at startup).
# Passing None here leaves the 'static' endpoint unregistered, and base.html's
# `url_for('static', ...)` then raises BuildError on EVERY page — which is what
# broke the Files and Database views. With the folder always set, url_for works;
# a missing stylesheet simply 404s and the page renders unstyled but functional.
app = Flask(__name__, template_folder=str(TEMPLATES_DIR),
            static_folder=str(STATIC_DIR), static_url_path="/static")
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    # Lax stops other sites from riding the admin session on cross-site POSTs.
    SESSION_COOKIE_SAMESITE="Lax",
    # Only mark the cookie Secure when the panel is actually behind HTTPS,
    # otherwise the browser would drop it and logins over plain HTTP break.
    SESSION_COOKIE_SECURE=os.getenv("PANEL_HTTPS", "").lower() in ("1", "true", "yes"),
)


@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response

# When BOT_SERVICE is set (e.g. "crbot.service"), the panel manages the bot
# through systemd instead of spawning it as a child process. That gives the bot
# its own lifecycle (auto-restart, start-on-boot) and stops a panel restart from
# orphaning bot processes. When unset, the panel falls back to the original
# subprocess behavior (handy for local/dev runs without systemd).
BOT_SERVICE = os.getenv("BOT_SERVICE")
# The panel's own systemd unit, so "Update & restart" can reload panel code too.
PANEL_SERVICE = os.getenv("PANEL_SERVICE", "crpanel.service")
BOT_PROCESS = None  # only used in subprocess (non-systemd) mode


def _systemctl(*args):
    return subprocess.run(["systemctl", *args], capture_output=True, text=True)


def _schedule_panel_restart(delay_seconds: int = 5) -> bool:
    """Reload the panel itself shortly after the current response is sent.

    A process can't cleanly ``systemctl restart`` itself inline — systemd would
    kill it mid-request and the browser would just see a dropped connection.
    ``systemd-run`` schedules the restart on a *detached* transient timer, so
    this request returns first and the panel then comes back running the freshly
    pulled ``control_panel.py``. The login session survives it (the secret key
    is stable).

    Only applies under systemd (BOT_SERVICE set); returns True if scheduled.
    """
    if not BOT_SERVICE:
        return False  # dev/subprocess mode: the panel isn't a managed service
    try:
        subprocess.Popen(
            ["systemd-run", f"--on-active={delay_seconds}", "--collect",
             "systemctl", "restart", PANEL_SERVICE]
        )
        return True
    except (OSError, subprocess.SubprocessError):
        app.logger.exception("Could not schedule control panel self-restart")
        return False


def bot_is_running() -> bool:
    if BOT_SERVICE:
        return _systemctl("is-active", "--quiet", BOT_SERVICE).returncode == 0
    return BOT_PROCESS is not None


def _spawn_bot():
    """Start the bot as a child process (subprocess mode)."""
    global BOT_PROCESS
    python = sys.executable or "python3"
    BOT_PROCESS = subprocess.Popen([python, str(BOT_SCRIPT)], cwd=str(BOT_DIR))


def _terminate_bot():
    """Stop the child-process bot (subprocess mode)."""
    global BOT_PROCESS
    if BOT_PROCESS is not None:
        BOT_PROCESS.terminate()
        try:
            BOT_PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:
            BOT_PROCESS.kill()
            BOT_PROCESS.wait()
        BOT_PROCESS = None


# ---------- Auth ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.full_path))
        return f(*args, **kwargs)

    return decorated_function


# ---- CSRF: every POST must echo the per-session token ----
def csrf_token() -> str:
    token = session.get('_csrf')
    if not token:
        token = secrets.token_hex(16)
        session['_csrf'] = token
    return token


app.jinja_env.globals['csrf_token'] = csrf_token


@app.before_request
def _verify_csrf():
    if request.method == 'POST':
        expected = session.get('_csrf')
        sent = request.form.get('csrf_token', '')
        # compare_digest on str raises TypeError for non-ASCII; bytes never do
        if not expected or not hmac.compare_digest(sent.encode(), expected.encode()):
            abort(400, description="Missing or invalid CSRF token. Reload the page and try again.")


# ---- Login rate limiting: 5 failures per IP locks login for 15 minutes ----
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_login_failures: dict[str, list[float]] = {}


def _login_locked(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _login_failures.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    if recent:
        _login_failures[ip] = recent
    else:
        _login_failures.pop(ip, None)
    return len(recent) >= LOGIN_MAX_FAILURES


def _safe_next(target: str | None) -> str | None:
    """Only follow relative in-app paths after login, never external URLs."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return None


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr or "unknown"
        if _login_locked(ip):
            flash('Too many failed attempts. Try again in 15 minutes.', 'error')
            return redirect(url_for('login', next=request.args.get('next')))
        password = request.form.get('password', '')
        if hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
            _login_failures.pop(ip, None)
            session['logged_in'] = True
            return redirect(_safe_next(request.args.get('next')) or url_for('index'))
        _login_failures.setdefault(ip, []).append(time.time())
        flash('Invalid password.', 'error')
        return redirect(url_for('login', next=request.args.get('next')))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# ---------- Public command guide (no login required) ----------
# The canonical guide lives in docs/ and is hosted by GitHub Pages. When
# GUIDE_URL points there, /guide redirects so old ip:port/guide links keep
# working; without GUIDE_URL the panel serves the file itself as a fallback.
GUIDE_FILE = BOT_DIR / "docs" / "index.html"
GUIDE_URL = os.getenv("GUIDE_URL")


@app.route('/guide')
def command_guide():
    if GUIDE_URL:
        return redirect(GUIDE_URL)
    if not GUIDE_FILE.exists():
        return "Command guide is not available.", 404
    return send_file(GUIDE_FILE)


# ---------- UI ----------
@app.route('/')
@login_required
def index():
    return render_template('index.html', bot_running=bot_is_running())


# ---------- Bot control ----------
@app.route('/start', methods=['POST'])
@login_required
def start_bot():
    if BOT_SERVICE:
        result = _systemctl("start", BOT_SERVICE)
        if result.returncode == 0:
            flash('Bot started.', 'success')
        else:
            flash(f"Failed to start bot: {(result.stderr or result.stdout).strip()}", 'error')
        return redirect(url_for('index'))
    if BOT_PROCESS is None:
        _spawn_bot()
        flash('Bot started.', 'success')
    else:
        flash('Bot is already running.', 'info')
    return redirect(url_for('index'))


@app.route('/stop', methods=['POST'])
@login_required
def stop_bot():
    if BOT_SERVICE:
        result = _systemctl("stop", BOT_SERVICE)
        if result.returncode == 0:
            flash('Bot stopped.', 'success')
        else:
            flash(f"Failed to stop bot: {(result.stderr or result.stdout).strip()}", 'error')
        return redirect(url_for('index'))
    if BOT_PROCESS is not None:
        _terminate_bot()
        flash('Bot stopped.', 'success')
    else:
        flash('Bot is not running.', 'info')
    return redirect(url_for('index'))


@app.route('/update', methods=['POST'])
@login_required
def update_files():
    try:
        # Check if .git exists
        if not (BOT_DIR / ".git").exists():
            flash(f"Not a git repository: .git folder not found in {BOT_DIR}.", 'error')
            return redirect(url_for('index'))

        # Check current branch
        branch_result = subprocess.run(
            ["git", "-C", str(BOT_DIR), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = branch_result.stdout.strip()

        # Check for uncommitted changes
        status_result = subprocess.run(
            ["git", "-C", str(BOT_DIR), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )

        if status_result.stdout.strip():
            # There are uncommitted changes - stash them
            subprocess.run(["git", "-C", str(BOT_DIR), "stash"], check=True)
            stashed = True
        else:
            stashed = False

        # Fetch and pull
        subprocess.run(["git", "-C", str(BOT_DIR), "fetch"], check=True)
        pull_result = subprocess.run(
            ["git", "-C", str(BOT_DIR), "pull", "origin", current_branch],
            capture_output=True,
            text=True,
            check=True
        )

        # Pop stash if we stashed changes
        if stashed:
            subprocess.run(["git", "-C", str(BOT_DIR), "stash", "pop"], check=False)

        # Check if anything was actually updated
        if "Already up to date" in pull_result.stdout or "Already up-to-date" in pull_result.stdout:
            message = "Bot is already on the newest version."
        else:
            message = "Bot updated successfully."

        if stashed:
            message += " Your local changes were preserved."

        flash(message, 'success')
        return redirect(url_for('index'))

    except subprocess.CalledProcessError as e:
        error_output = (e.stderr or e.stdout or str(e)).strip()
        app.logger.error("git update failed: %s", error_output)
        flash(
            "Failed to update the bot.\n"
            f"{error_output}\n"
            "Check your internet connection, that git is installed, and that repo credentials are set up.",
            'error'
        )
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Unexpected error: {e}", 'error')
        return redirect(url_for('index'))


@app.route('/update_and_restart', methods=['POST'])
@login_required
def update_and_restart():
    global BOT_PROCESS
    try:
        # Check if .git exists
        if not (BOT_DIR / ".git").exists():
            flash(f"Not a git repository: .git folder not found in {BOT_DIR}.", 'error')
            return redirect(url_for('index'))

        # Check current branch
        branch_result = subprocess.run(
            ["git", "-C", str(BOT_DIR), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = branch_result.stdout.strip()

        # Check for uncommitted changes and stash if needed
        status_result = subprocess.run(
            ["git", "-C", str(BOT_DIR), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )

        if status_result.stdout.strip():
            subprocess.run(["git", "-C", str(BOT_DIR), "stash"], check=True)
            stashed = True
        else:
            stashed = False

        # Pull latest changes
        subprocess.run(["git", "-C", str(BOT_DIR), "fetch"], check=True)
        pull_result = subprocess.run(
            ["git", "-C", str(BOT_DIR), "pull", "origin", current_branch],
            capture_output=True,
            text=True,
            check=True
        )

        # Pop stash if we stashed changes
        if stashed:
            subprocess.run(["git", "-C", str(BOT_DIR), "stash", "pop"], check=False)

        # Restart the bot with the new code
        if BOT_SERVICE:
            _systemctl("restart", BOT_SERVICE)
        else:
            _terminate_bot()
            _spawn_bot()

        # Also reload the panel itself so pulled changes to control_panel.py,
        # templates, or static files (e.g. the command guide) take effect —
        # deferred so this request can return before the panel is replaced.
        panel_restarting = _schedule_panel_restart()

        # Check if anything was updated
        if "Already up to date" in pull_result.stdout or "Already up-to-date" in pull_result.stdout:
            message = "Already on the newest version. Everything restarted anyway."
        else:
            message = "Updated and restarted successfully."

        if panel_restarting:
            message += " The control panel is reloading too, give it a few seconds, then refresh this page."
        if stashed:
            message += " Local changes were preserved."

        flash(message, 'success')
        return redirect(url_for('index'))

    except subprocess.CalledProcessError as e:
        BOT_PROCESS = None
        error_output = (e.stderr or e.stdout or str(e)).strip()
        app.logger.error("git update (with restart) failed: %s", error_output)
        flash(f"Failed to update and restart the bot.\n{error_output}", 'error')
        return redirect(url_for('index'))
    except Exception as e:
        BOT_PROCESS = None
        flash(f"Unexpected error during update and restart: {e}", 'error')
        return redirect(url_for('index'))


# ---------- File viewer (safe within repo only) ----------
def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


@app.route('/files')
@login_required
def file_viewer():
    def list_items(directory: Path):
        items = []
        try:
            entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except OSError as e:
            # e.g. the panel process lacks permission to read this directory
            flash(f"Cannot list this directory: {e}", 'error')
            return items
        for item in entries:
            is_dir = item.is_dir()  # returns False for broken symlinks, never raises
            size = None
            if not is_dir:
                # A single unreadable entry (broken symlink, permission denied,
                # socket) must not take down the whole listing.
                try:
                    size = format_size(item.stat().st_size)
                except OSError:
                    size = "unknown"
            items.append({
                "name": item.name,
                "path": str(item.relative_to(BOT_DIR)),  # relative path
                "is_dir": is_dir,
                "size": size,
            })
        return items

    rel = request.args.get("dir", "")
    # Normalize & prevent path traversal. is_relative_to (not a string-prefix
    # check) so a sibling like /opt/Clash-Royale-Bot-evil can't slip through.
    full_path = (BOT_DIR / rel).resolve()
    if not full_path.is_relative_to(BOT_DIR.resolve()):
        flash('Invalid path.', 'error')
        return redirect(url_for('file_viewer'))

    if full_path.is_dir():
        files = list_items(full_path)
        return render_template("files.html", files=files, current_dir=str(Path(rel)))
    if full_path.is_file():
        return send_file(full_path)
    flash('Invalid path.', 'error')
    return redirect(url_for('file_viewer'))


# ---------- .env editor ----------
@app.route('/edit_env', methods=['GET', 'POST'])
@login_required
def edit_env():
    if request.method == 'POST':
        new_content = request.form.get('env_content', '')
        ENV_FILE.write_text(new_content, encoding='utf-8')
        flash('Environment saved. Restart the bot to apply changes.', 'success')
        return redirect(url_for('edit_env'))
    env_content = ENV_FILE.read_text(encoding='utf-8') if ENV_FILE.exists() else ""
    return render_template('edit_env.html', env_content=env_content)


# ---------- DB viewer ----------
@app.route('/database')
@login_required
def view_database():
    db_file = db_path()
    if not db_file.exists():
        flash(
            f"No database file at {db_file}. If the bot uses a custom DATABASE_PATH, "
            "set the same value in the panel's environment.",
            'error',
        )
        return render_template('database.html', database_data=[])
    try:
        # Read-only: a wrong/unreadable path fails loudly instead of silently
        # creating an empty database that looks like "no tables".
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        database_data = []
        for table_name in tables:
            cursor.execute(f"SELECT * FROM {table_name};")
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            database_data.append({"table_name": table_name, "columns": column_names, "rows": rows})
        conn.close()
        return render_template('database.html', database_data=database_data)
    except Exception as e:
        flash(f"Error reading database at {db_file}: {e}", 'error')
        return render_template('database.html', database_data=[])


if __name__ == '__main__':
    # Once the guide is hosted elsewhere the panel has no public-facing routes
    # left — set PANEL_HOST=127.0.0.1 and reach it over an SSH tunnel
    # (ssh -L 5000:localhost:5000 user@host) instead of the open internet.
    app.run(host=os.getenv("PANEL_HOST", "0.0.0.0"), port=int(os.getenv("PORT", "5000")))
