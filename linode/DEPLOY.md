# Deploying on a Linux host (systemd)

Two long-running processes: the **bot** (`main.py`) and the **web control panel**
(`control_panel.py`). Running each as a systemd service makes them start on boot,
restart on crash, and — importantly — lets the panel manage the bot cleanly
(without orphaning bot processes when the panel restarts).

This assumes the repo lives at `/opt/Clash-Royale-Bot` and runs as `root`. Adjust
`WorkingDirectory`, `ExecStart`, and `User` in the unit files if yours differ.

## 1. Install the unit files

```bash
cp /opt/Clash-Royale-Bot/linode/crbot.service   /etc/systemd/system/crbot.service
cp /opt/Clash-Royale-Bot/linode/crpanel.service /etc/systemd/system/crpanel.service
systemctl daemon-reload
```

## 2. Point the panel at the bot service

Add this to `/opt/Clash-Royale-Bot/.env` so the panel's start/stop toggle drives
the systemd service instead of spawning its own child process:

```
BOT_SERVICE=crbot.service
```

If `BOT_SERVICE` is unset, the panel falls back to running the bot as a child
process (fine for local/dev, but it can leak processes if the panel is killed).

## 3. Enable and start

```bash
systemctl enable --now crbot.service     # bot: start now + on boot
systemctl enable --now crpanel.service   # panel: start now + on boot
```

The panel needs to run as a user that can `systemctl start/stop/restart crbot`
(root can, as configured here).

## Everyday commands

```bash
systemctl status crbot crpanel      # health
journalctl -u crbot -f              # live bot logs
journalctl -u crpanel -f            # live panel logs
systemctl restart crpanel           # after pulling new panel code
```

The panel's **Start/Stop toggle** now runs `systemctl start/stop crbot`, and
**Update & restart** runs `git pull` then `systemctl restart crbot`. Note the
panel does not restart *itself* — after pulling changes to `control_panel.py`,
run `systemctl restart crpanel` to load them.
