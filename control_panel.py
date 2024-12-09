from flask import Flask, render_template, request, redirect, url_for, send_file, abort, session
import os
import subprocess
import signal
import sqlite3
from dotenv import load_dotenv
from functools import wraps


load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Paths
BOT_SCRIPT = os.path.join(os.getcwd(), "main.py")
BOT_DIR = os.getcwd()
ENV_FILE = os.path.join(BOT_DIR, ".env")
DB_FILE = os.path.join(BOT_DIR, "database.db")
TEMPLATES_DIR = os.path.join(BOT_DIR, "linode", "templates")

app.template_folder = TEMPLATES_DIR

BOT_PROCESS = None

# Password protection
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
        password = request.form['password']
        if password == os.getenv('ADMIN_PASSWORD'):
            session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('index'))
        else:
            return 'Invalid password'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route("/")
@login_required
def index():
    return render_template("index.html", bot_running=(BOT_PROCESS is not None))

@app.route("/start", methods=["POST"])
@login_required
def start_bot():
    global BOT_PROCESS
    if BOT_PROCESS is None:
        BOT_PROCESS = subprocess.Popen(["python3", BOT_SCRIPT])
        return redirect(url_for("index"))
    return "Bot is already running. <a href='/'>Go back</a>"

@app.route("/stop", methods=["POST"])
@login_required
def stop_bot():
    global BOT_PROCESS
    if BOT_PROCESS is not None:
        # Send SIGTERM to terminate the process
        BOT_PROCESS.terminate()
        try:
            # Wait for the process to terminate
            BOT_PROCESS.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Force kill the process if it doesn't terminate in time
            BOT_PROCESS.kill()
            BOT_PROCESS.wait()  # Ensure it's fully stopped

        BOT_PROCESS = None  # Reset the global reference
    return redirect(url_for("index"))

@app.route("/update", methods=["POST"])
@login_required
def update_files():
    try:
        subprocess.run(["git", "-C", BOT_DIR, "pull"], check=True)
        return "Bot updated successfully! <a href='/'>Go back</a>"
    except subprocess.CalledProcessError:
        return "Failed to update the bot. <a href='/'>Go back</a>"

@app.route("/files")
@login_required
def file_viewer():
    def list_files(directory):
        items = []
        for item in os.listdir(directory):
            path = os.path.join(directory, item)
            items.append({
                "name": item,
                "path": path.replace(BOT_DIR, ""),  # Path relative to BOT_DIR
                "is_dir": os.path.isdir(path)
            })
        return items

    directory_path = request.args.get("dir", "")
    full_path = os.path.join(BOT_DIR, directory_path.lstrip("/"))
    if os.path.isdir(full_path):
        files = list_files(full_path)
        return render_template("files.html", files=files, current_dir=directory_path)
    elif os.path.isfile(full_path):
        return send_file(full_path)
    return "Invalid path. <a href='/files'>Go back</a>"

@app.route("/edit_env", methods=["GET", "POST"])
@login_required
def edit_env():
    if request.method == "POST":
        new_content = request.form["env_content"]
        with open(ENV_FILE, "w") as f:
            f.write(new_content)
        return redirect(url_for("edit_env"))
    with open(ENV_FILE, "r") as f:
        env_content = f.read()
    return render_template("edit_env.html", env_content=env_content)

@app.route("/database")
@login_required
def view_database():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        database_data = []
        for table_name, in tables:
            cursor.execute(f"SELECT * FROM {table_name};")
            rows = cursor.fetchall()
            column_names = [description[0] for description in cursor.description]
            database_data.append({"table_name": table_name, "columns": column_names, "rows": rows})

        conn.close()
        return render_template("database.html", database_data=database_data)
    except Exception as e:
        return f"Error reading database: {e}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)