from flask import Flask, render_template, request, redirect, url_for, send_file, abort
import os
import subprocess
import signal
import sqlite3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Paths
BOT_SCRIPT = os.path.join(os.getcwd(), "main.py")
BOT_DIR = os.getcwd()
ENV_FILE = os.path.join(BOT_DIR, ".env")
DB_FILE = os.path.join(BOT_DIR, "database.db")
TEMPLATES_DIR = os.path.join(BOT_DIR, "linode", "templates")

app.template_folder = TEMPLATES_DIR

BOT_PROCESS = None  # Store the bot process here


# Middleware to restrict access based on IP
@app.before_request
def limit_remote_addr():
    allowed_ips = os.getenv("ALLOWED_IPS", "").split(",")
    if request.remote_addr not in allowed_ips:
        abort(403)  # Forbidden


@app.route("/")
def index():
    return render_template("index.html", bot_running=(BOT_PROCESS is not None))


@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_PROCESS
    if BOT_PROCESS is None:
        BOT_PROCESS = subprocess.Popen(["python3", BOT_SCRIPT])
        return redirect(url_for("index"))
    return "Bot is already running. <a href='/'>Go back</a>"


@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_PROCESS
    if BOT_PROCESS is not None:
        os.kill(BOT_PROCESS.pid, signal.SIGTERM)
        BOT_PROCESS = None
    return redirect(url_for("index"))


@app.route("/update", methods=["POST"])
def update_files():
    try:
        subprocess.run(["git", "-C", BOT_DIR, "pull"], check=True)
        return "Bot updated successfully! <a href='/'>Go back</a>"
    except subprocess.CalledProcessError:
        return "Failed to update the bot. <a href='/'>Go back</a>"


@app.route("/files")
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