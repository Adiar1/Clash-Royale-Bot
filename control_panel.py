from flask import Flask, render_template, request, redirect, url_for, send_file, session
import os
import sys
import subprocess
import sqlite3
from dotenv import load_dotenv
from functools import wraps
from pathlib import Path


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
DB_FILE = BOT_DIR / "database.db"
TEMPLATES_DIR = BOT_DIR / "linode" / "templates"
STATIC_DIR = BOT_DIR / "linode" / "static"  # optional; use if you have one

load_dotenv(ENV_FILE if ENV_FILE.exists() else None)

# Stable secret key (don't regenerate on every restart or you'll get logged out)
SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "change-me"

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
        return 'Invalid password'
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
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
        return redirect(url_for('index'))
    return "Bot is already running. <a href='/'>Go back</a>"


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
    return redirect(url_for('index'))


@app.route('/update', methods=['POST'])
@login_required
def update_files():
    try:
        # Check if .git exists
        if not (BOT_DIR / ".git").exists():
            return f"Error: Not a git repository. .git folder not found in {BOT_DIR}. <a href='/'>Go back</a>"

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
            message = "Bot is already on the newest version!"
        else:
            message = "Bot updated successfully!"

        if stashed:
            message += " (Your local changes were preserved)"

        return f"{message} <a href='/'>Go back</a>"

    except subprocess.CalledProcessError as e:
        error_output = e.stderr if e.stderr else e.stdout
        return f"""
        <h3>Failed to update the bot</h3>
        <p><strong>Error:</strong> {e}</p>
        <p><strong>Output:</strong></p>
        <pre>{error_output}</pre>
        <p><strong>Possible solutions:</strong></p>
        <ul>
            <li>Check if you have internet connection</li>
            <li>Verify Git is installed: <code>git --version</code></li>
            <li>Check if the repository is properly configured</li>
            <li>If it's a private repo, ensure SSH keys or credentials are set up</li>
        </ul>
        <a href='/'>Go back</a>
        """
    except Exception as e:
        return f"Unexpected error: {e}. <a href='/'>Go back</a>"


@app.route('/update_and_restart', methods=['POST'])
@login_required
def update_and_restart():
    global BOT_PROCESS
    try:
        # Check if .git exists
        if not (BOT_DIR / ".git").exists():
            return f"Error: Not a git repository. .git folder not found in {BOT_DIR}. <a href='/'>Go back</a>"

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
            message = "Bot was already on newest version but has been restarted!"
        else:
            message = "Bot updated and restarted successfully!"

        if stashed:
            message += " (Local changes preserved)"

        return f"{message} <a href='/'>Go back</a>"

    except subprocess.CalledProcessError as e:
        BOT_PROCESS = None
        error_output = e.stderr if e.stderr else e.stdout
        return f"""
        <h3>Failed to update and restart</h3>
        <p><strong>Error:</strong> {e}</p>
        <p><strong>Output:</strong></p>
        <pre>{error_output}</pre>
        <a href='/'>Go back</a>
        """
    except Exception as e:
        BOT_PROCESS = None
        return f"Unexpected error during update and restart: {e}. <a href='/'>Go back</a>"


# ---------- File viewer (safe within repo only) ----------
@app.route('/files')
@login_required
def file_viewer():
    def list_items(directory: Path):
        items = []
        for item in sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            items.append({
                "name": item.name,
                "path": str(item.relative_to(BOT_DIR)),  # relative path
                "is_dir": item.is_dir()
            })
        return items

    rel = request.args.get("dir", "")
    # Normalize & prevent path traversal
    full_path = (BOT_DIR / rel).resolve()
    if not str(full_path).startswith(str(BOT_DIR.resolve())):
        return "Invalid path. <a href='/files'>Go back</a>"

    if full_path.is_dir():
        files = list_items(full_path)
        return render_template("files.html", files=files, current_dir=str(Path(rel)))
    if full_path.is_file():
        return send_file(full_path)
    return "Invalid path. <a href='/files'>Go back</a>"


# ---------- .env editor ----------
@app.route('/edit_env', methods=['GET', 'POST'])
@login_required
def edit_env():
    if request.method == 'POST':
        new_content = request.form.get('env_content', '')
        ENV_FILE.write_text(new_content, encoding='utf-8')
        return redirect(url_for('edit_env'))
    env_content = ENV_FILE.read_text(encoding='utf-8') if ENV_FILE.exists() else ""
    return render_template('edit_env.html', env_content=env_content)


# ---------- DB viewer ----------
@app.route('/database')
@login_required
def view_database():
    try:
        conn = sqlite3.connect(str(DB_FILE))
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
        return f"Error reading database: {e}"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", "5000")))