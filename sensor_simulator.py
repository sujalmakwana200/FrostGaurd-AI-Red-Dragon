import time
import random
import requests
import datetime

START_LON, START_LAT = 73.1812, 22.3072
END_LON,   END_LAT   = 72.5714, 23.0225

SAFE_MAX    = 6.5
CRITICAL_AT = 8.0
TEMP_CEIL   = 12.0


def fetch_route():
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{START_LON},{START_LAT};{END_LON},{END_LAT}"
        f"?overview=full&geometries=geojson"
    )
    try:
        resp = requests.get(url, timeout=10)
        coords = resp.json()["routes"][0]["geometry"]["coordinates"]
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


print("🐉 Red Dragons Simulator Online...")
print("📡 Fetching real road route...\n")

ROUTE        = fetch_route()
current_temp = 5.0
idx          = 0

while idx < len(ROUTE):
    lat, lon = ROUTE[idx]
    idx += 1

    if current_temp > CRITICAL_AT:
        current_temp += random.uniform(-0.2, 0.35)
    elif current_temp > SAFE_MAX:
        current_temp += random.uniform(-0.3, 0.2)
    else:
        current_temp += random.uniform(-0.1, 0.25)

    current_temp = round(min(max(current_temp, 2.0), TEMP_CEIL), 2)
    status = "CRITICAL" if current_temp > CRITICAL_AT else ("WARNING" if current_temp > SAFE_MAX else "SAFE")

    payload = {
        "truck_id"   : "TRK-RD-001",
        "cargo"      : "Vaccines",
        "temperature": current_temp,
        "status"     : status,
        "lat"        : round(lat, 6),
        "lng"        : round(lon, 6),
        "timestamp"  : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    print(f"Temp: {current_temp:.2f}°C | {status:<10} | WP {idx}/{len(ROUTE)}")

    try:
        requests.post("http://127.0.0.1:5000/telemetry", json=payload, timeout=3)
    except Exception:
        print("⚠️  Bridge not reachable on port 5000")

    time.sleep(3)

print("✅ Journey complete.")
