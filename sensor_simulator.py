import time
import random
import requests
import datetime

START_LON, START_LAT = 73.1812, 22.3072
END_LON,   END_LAT   = 72.5714, 23.0225

SAFE_MAX    = 6.5
CRITICAL_AT = 8.0
TEMP_CEIL   = 12.0

BRIDGE_URL  = "http://127.0.0.1:5000"

# ─────────────────────────────────────────────────────────────
#  PLANNED FAILURE EVENTS
#  Each entry: (waypoint_index, event_type, description)
#
#  Event types:
#    "compressor_degrade" — temp starts rising faster
#    "compressor_fail"    — temp spikes rapidly
#    "compressor_recover" — temp stabilizes / drops back
# ─────────────────────────────────────────────────────────────
FAILURE_EVENTS = {
    60  : "compressor_degrade",   # ~30% into trip — compressor weakens
    100 : "compressor_fail",      # ~50% into trip — full compressor failure
    140 : "compressor_recover",   # ~70% into trip — partial recovery
    180 : "compressor_fail",      # ~90% into trip — second failure near destination
}


def fetch_route():
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{START_LON},{START_LAT};{END_LON},{END_LAT}"
        f"?overview=full&geometries=geojson"
    )
    try:
        resp    = requests.get(url, timeout=10)
        coords  = resp.json()["routes"][0]["geometry"]["coordinates"]
        print(f"✅ OSRM route: {len(coords)} waypoints")
        return [(c[1], c[0]) for c in coords]
    except Exception as e:
        print(f"⚠️  OSRM failed ({e}), straight-line fallback")
        steps = 200
        return [
            (START_LAT + i/steps*(END_LAT-START_LAT),
             START_LON + i/steps*(END_LON-START_LON))
            for i in range(steps)
        ]


def poll_command():
    """Check bridge for any command sent from the dashboard."""
    try:
        r = requests.get(f"{BRIDGE_URL}/command", timeout=1)
        if r.status_code == 200:
            return r.json().get("command", "normal")
    except Exception:
        pass
    return "normal"


def reset_command():
    """Reset command back to normal after processing."""
    try:
        requests.post(f"{BRIDGE_URL}/command",
                      json={"command": "normal"}, timeout=1)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
print("🐉 Red Dragons Simulator Online...")
print("📡 Fetching real road route...\n")

# Register PID with bridge so it can kill us on reset
import os as _os
try:
    requests.post(f"{BRIDGE_URL}/register_sim", json={"pid": _os.getpid()}, timeout=3)
    print(f"✅ Registered with bridge (PID {_os.getpid()})")
except Exception:
    print("⚠️  Could not register PID with bridge")

ROUTE        = fetch_route()
current_temp = 5.0
idx          = 0
compressor_state = "normal"   # normal | degrade | fail | recover

while idx < len(ROUTE):
    lat, lon = ROUTE[idx]
    idx += 1

    # ── Check for planned failure event at this waypoint ──
    if idx in FAILURE_EVENTS:
        compressor_state = FAILURE_EVENTS[idx]
        print(f"⚡ PLANNED EVENT at waypoint {idx}: {compressor_state.upper()}")

    # ── Check dashboard command (overrides planned events) ──
    cmd = poll_command()
    if cmd == "compressor_fail":
        compressor_state = "fail"
        reset_command()   # consume the command so it fires once
        print("🚨 DASHBOARD COMMAND: Compressor Failure Injected")

    # ── Temperature simulation based on compressor state ──
    if compressor_state == "fail":
        # Compressor failed — temp rises fast
        current_temp += random.uniform(0.8, 1.8)

    elif compressor_state == "degrade":
        # Compressor weakening — temp drifts up slowly
        current_temp += random.uniform(0.1, 0.5)

    elif compressor_state == "recover":
        # Partial recovery — temp stabilizes or drops slightly
        current_temp += random.uniform(-0.4, 0.1)
        if current_temp < 5.0:
            compressor_state = "normal"   # fully recovered

    else:
        # Normal operation — gentle drift
        if current_temp > CRITICAL_AT:
            current_temp += random.uniform(-0.2, 0.35)
        elif current_temp > SAFE_MAX:
            current_temp += random.uniform(-0.3, 0.2)
        else:
            current_temp += random.uniform(-0.1, 0.25)

    current_temp = round(min(max(current_temp, 2.0), TEMP_CEIL), 2)

    # ── Status ──
    if current_temp > CRITICAL_AT:
        status = "CRITICAL"
    elif current_temp > SAFE_MAX:
        status = "WARNING"
    else:
        status = "SAFE"

    payload = {
        "truck_id"   : "TRK-RD-001",
        "cargo"      : "Vaccines",
        "temperature": current_temp,
        "status"     : status,
        "lat"        : round(lat, 6),
        "lng"        : round(lon, 6),
        "timestamp"  : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    state_icon = {"normal": "✅", "degrade": "⚠️", "fail": "🚨", "recover": "🔄"}
    print(
        f"{state_icon.get(compressor_state, '?')} "
        f"Temp: {current_temp:.2f}°C | {status:<10} | "
        f"State: {compressor_state:<10} | WP {idx}/{len(ROUTE)}"
    )

    try:
        requests.post(f"{BRIDGE_URL}/telemetry", json=payload, timeout=3)
    except Exception:
     print("⚠️  Bridge not reachable on port 5000")

    time.sleep(3)

print("\n✅ Journey complete.")
