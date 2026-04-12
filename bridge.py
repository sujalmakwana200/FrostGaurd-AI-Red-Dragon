from flask import Flask, request
import csv
import requests
import os

app = Flask(__name__)

# Store latest telemetry for dashboards to poll
LATEST = None

# Store pending command for simulator to poll
PENDING_COMMAND = {"command": "normal"}

# Track simulator process pid so we can kill it on reset
SIM_PID = None


@app.route("/register_sim", methods=["POST"])
def register_sim():
    """Simulator calls this on startup to register its PID."""
    global SIM_PID
    data = request.json or {}
    SIM_PID = data.get("pid")
    return {"status": "registered", "pid": SIM_PID}, 200

# ── Your Discord webhook (optional — alerts sent on CRITICAL) ──
WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK",
    "https://discord.com/api/webhooks/YOUR_WEBHOOK_HERE"
)

CSV_FILE = "fleet_logs.csv"


@app.route("/telemetry", methods=["POST"])
def handle_telemetry():
    data = request.json

    # update latest telemetry (shallow copy)
    global LATEST
    try:
        LATEST = dict(data)
    except Exception:
        LATEST = data

    # 1. Log to CSV — manager's historical record
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Truck_ID", "Cargo", "Current_Temp",
                             "Status", "Lat", "Lng", "Timestamp"])
        writer.writerow([
            data["truck_id"], data["cargo"], data["temperature"],
            data["status"], data["lat"], data["lng"], data["timestamp"],
        ])

    # 2. Discord alert on CRITICAL
    if data["status"] == "CRITICAL" and "discord.com" in WEBHOOK_URL:
        msg = {
            "content": (
                f"🐉 **RED DRAGONS ALERT**\n"
                f"Truck `{data['truck_id']}` | Cargo: {data['cargo']}\n"
                f"🌡 Temperature: **{data['temperature']}°C** — CRITICAL\n"
                f"📍 Location: {data['lat']}, {data['lng']}\n"
                f"🕐 {data['timestamp']}"
            )
        }
        try:
            requests.post(WEBHOOK_URL, json=msg, timeout=5)
        except Exception:
            pass

    return "OK", 200


@app.route("/latest", methods=["GET"])
def latest():
    """Return last-received telemetry for dashboards/test clients."""
    if LATEST is None:
        return {"error": "no telemetry"}, 404
    # return a copy to avoid accidental mutation
    try:
        return dict(LATEST), 200
    except Exception:
        return LATEST, 200


@app.route("/health", methods=["GET"])
def health():
    return {"status": "bridge_online", "csv": CSV_FILE}, 200


@app.route("/command", methods=["GET"])
def get_command():
    """Simulator polls this to get pending commands from dashboard."""
    return dict(PENDING_COMMAND), 200


@app.route("/command", methods=["POST"])
def set_command():
    """Dashboard posts here to send commands to simulator."""
    global PENDING_COMMAND
    data = request.json or {}
    cmd  = data.get("command", "normal")
    PENDING_COMMAND = {"command": cmd}
    return {"status": "ok", "command": cmd}, 200


@app.route("/reset", methods=["POST"])
def reset():
    """Kill simulator and clear latest data so dashboard can restart fresh."""
    global LATEST, PENDING_COMMAND, SIM_PID
    import signal

    # Kill simulator process if we know its PID
    if SIM_PID:
        try:
            os.kill(SIM_PID, signal.SIGTERM)
            print(f"🛑 Killed simulator PID {SIM_PID}")
        except Exception as e:
            print(f"⚠️  Could not kill simulator: {e}")
        SIM_PID = None

    # Clear latest telemetry so dashboard knows simulator is gone
    LATEST          = None
    PENDING_COMMAND = {"command": "normal"}

    return {"status": "reset_ok"}, 200


if __name__ == "__main__":
    print("🌉 Data Bridge listening on port 5000...")
    app.run(port=5000, debug=False)
