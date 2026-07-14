import os
import sqlite3
import subprocess
import sys
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for


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

app = Flask(__name__, template_folder=str(TEMPLATES_DIR),
            static_folder=str(STATIC_DIR) if STATIC_DIR.exists() else None)
app.secret_key = SECRET_KEY

BOT_PROCESS = None


# ---------- Auth ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == os.getenv('ADMIN_PASSWORD'):
            session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('index'))
        flash('Invalid password.', 'error')
        return redirect(url_for('login', next=request.args.get('next')))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# ---------- UI ----------
@app.route('/')
@login_required
def index():
    return render_template('index.html', bot_running=(BOT_PROCESS is not None))


# ---------- Bot control ----------
@app.route('/start', methods=['POST'])
@login_required
def start_bot():
    global BOT_PROCESS
    if BOT_PROCESS is None:
        python = sys.executable or "python3"
        BOT_PROCESS = subprocess.Popen([python, str(BOT_SCRIPT)], cwd=str(BOT_DIR))
        flash('Bot started.', 'success')
    else:
        flash('Bot is already running.', 'info')
    return redirect(url_for('index'))


@app.route('/stop', methods=['POST'])
@login_required
def stop_bot():
    global BOT_PROCESS
    if BOT_PROCESS is not None:
        BOT_PROCESS.terminate()
        try:
            BOT_PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:
            BOT_PROCESS.kill()
            BOT_PROCESS.wait()
        BOT_PROCESS = None
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

        # Stop the bot if running
        if BOT_PROCESS is not None:
            BOT_PROCESS.terminate()
            try:
                BOT_PROCESS.wait(timeout=10)
            except subprocess.TimeoutExpired:
                BOT_PROCESS.kill()
                BOT_PROCESS.wait()

        # Start the bot with new code
        python = sys.executable or "python3"
        BOT_PROCESS = subprocess.Popen([python, str(BOT_SCRIPT)], cwd=str(BOT_DIR))

        # Check if anything was updated
        if "Already up to date" in pull_result.stdout or "Already up-to-date" in pull_result.stdout:
            message = "Bot was already on the newest version but has been restarted."
        else:
            message = "Bot updated and restarted successfully."

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
                    size = "—"
            items.append({
                "name": item.name,
                "path": str(item.relative_to(BOT_DIR)),  # relative path
                "is_dir": is_dir,
                "size": size,
            })
        return items

    rel = request.args.get("dir", "")
    # Normalize & prevent path traversal
    full_path = (BOT_DIR / rel).resolve()
    if not str(full_path).startswith(str(BOT_DIR.resolve())):
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
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", "5000")))
