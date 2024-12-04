from flask import Flask, render_template, request
import os
import subprocess
import signal

app = Flask(__name__)

# Path to your bot
BOT_SCRIPT = "/root/Clash-Royale-Bot/main.py"
BOT_PROCESS = None  # Store the bot process here


@app.route("/")
def index():
    return """
        <h1>Discord Bot Control Panel</h1>
        <form action="/start" method="post">
            <button type="submit">Start Bot</button>
        </form>
        <form action="/stop" method="post">
            <button type="submit">Stop Bot</button>
        </form>
        <form action="/update" method="post">
            <button type="submit">Update Bot (Pull from GitHub)</button>
        </form>
    """


@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_PROCESS
    if BOT_PROCESS is None:
        BOT_PROCESS = subprocess.Popen(["python3", BOT_SCRIPT])
        return "Bot started successfully! <a href='/'>Go back</a>"
    return "Bot is already running. <a href='/'>Go back</a>"


@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_PROCESS
    if BOT_PROCESS is not None:
        os.kill(BOT_PROCESS.pid, signal.SIGTERM)
        BOT_PROCESS = None
        return "Bot stopped successfully! <a href='/'>Go back</a>"
    return "Bot is not running. <a href='/'>Go back</a>"


@app.route("/update", methods=["POST"])
def update_files():
    try:
        # Change directory to your bot's GitHub repository
        repo_path = "/root/Clash-Royale-Bot"
        subprocess.run(["git", "-C", repo_path, "pull"], check=True)
        return "Bot updated successfully! <a href='/'>Go back</a>"
    except subprocess.CalledProcessError:
        return "Failed to update the bot. <a href='/'>Go back</a>"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)