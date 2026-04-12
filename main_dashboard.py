import streamlit as st
import pydeck as pdk
import requests
import time
import random
import math
import subprocess
import sys
import os
import threading
import queue
from google import genai
from google.genai import types

# ─────────────────────────────────────────────────────────────
#  AUTO-LAUNCH bridge.py + sensor_simulator.py as background
#  processes — runs all 3 files when Streamlit Cloud starts
# ─────────────────────────────────────────────────────────────
def _bridge_online():
    """Returns True if bridge is already up and healthy."""
    try:
        return requests.get("http://127.0.0.1:5000/health", timeout=2).status_code == 200
    except Exception:
        return False


def _wait_for_bridge(max_wait=10):
    """Polls /health until bridge responds or timeout. Returns True if online."""
    for _ in range(max_wait):
        if _bridge_online():
            return True
        time.sleep(1)
    return False


def launch_background_services():
    base_dir       = os.path.dirname(os.path.abspath(__file__))
    bridge_path    = os.path.join(base_dir, "bridge.py")
    simulator_path = os.path.join(base_dir, "sensor_simulator.py")

    # ── Step 1: Start bridge if not already running ──
    if not _bridge_online():
        if os.path.exists(bridge_path):
            try:
                log = open(os.path.join(base_dir, "bridge.log"), "ab")
                subprocess.Popen(
                    [sys.executable, bridge_path],
                    stdout=log, stderr=log,
                )
            except Exception:
                pass

        # Wait up to 10s for bridge to come online before starting simulator
        bridge_ready = _wait_for_bridge(max_wait=10)
        if not bridge_ready:
            return  # Bridge failed to start — don't launch simulator into void
    
    # ── Step 2: Start simulator only after bridge is confirmed online ──
    # Check simulator isn't already sending (bridge /latest returns data)
    try:
        r = requests.get("http://127.0.0.1:5000/latest", timeout=1)
        if r.status_code == 200:
            return  # Simulator already running and sending data
    except Exception:
        pass  # No data yet — start simulator

    if os.path.exists(simulator_path):
        try:
            log = open(os.path.join(base_dir, "simulator.log"), "ab")
            subprocess.Popen(
                [sys.executable, simulator_path],
                stdout=log, stderr=log,
            )
        except Exception:
            pass

if "services_launched" not in st.session_state:
    launch_background_services()
    st.session_state["services_launched"] = True

st.set_page_config(
    page_title="FrostGuard AI",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────
#  GEMINI API KEY  ← free at aistudio.google.com
# ─────────────────────────────────────────────────────────────
# Gemini key — loaded from env (Streamlit Cloud) or entered by user at runtime
GEMINI_API_KEY_ENV = os.environ.get("GEMINI_API_KEY", "")

# ─────────────────────────────────────────────────────────────
#  OLED DARK THEME  — injected via st.markdown
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Base OLED black ── */
  html, body, [data-testid="stAppViewContainer"],
  [data-testid="stMain"], .main, .block-container {
      background-color: #000000 !important;
      color: #E8E8E8 !important;
  }

  /* Hide sidebar toggle, deploy button & toolbar */
  [data-testid="collapsedControl"]   { display: none !important; }
  [data-testid="stToolbar"]          { display: none !important; }
  [data-testid="stDecoration"]       { display: none !important; }
  [data-testid="stStatusWidget"]     { display: none !important; }
  #MainMenu                          { display: none !important; }
  header                             { display: none !important; }
  .block-container { padding: 1.5rem 2rem 2rem 2rem !important; }

  /* ── Metric cards ── */
  [data-testid="metric-container"] {
      background: #0D0D0D;
      border: 1px solid #1A1A1A;
      border-radius: 12px;
      padding: 14px 18px !important;
  }
  [data-testid="stMetricLabel"]  { color: #666 !important; font-size: 0.72rem !important; letter-spacing: 0.08em; text-transform: uppercase; }
  [data-testid="stMetricValue"]  { color: #F0F0F0 !important; font-size: 1.45rem !important; font-weight: 700; }
  [data-testid="stMetricDelta"]  { font-size: 0.75rem !important; }

  /* ── Section cards (custom divs) ── */
  .fg-card {
      background: #0D0D0D;
      border: 1px solid #1A1A1A;
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 0px;
  }
  .fg-card-title {
      font-size: 0.68rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #555;
      margin-bottom: 10px;
  }

  /* ── Alert banners ── */
  [data-testid="stAlert"] {
      border-radius: 10px !important;
      border-width: 1px !important;
  }

  /* ── Line chart ── */
  [data-testid="stVegaLiteChart"] {
      background: transparent !important;
      border-radius: 8px;
  }

  /* ── Divider ── */
  hr { border-color: #1A1A1A !important; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: #000; }
  ::-webkit-scrollbar-thumb { background: #222; border-radius: 4px; }

  /* ── Button ── */
  [data-testid="stButton"] button {
      background: #111 !important;
      border: 1px solid #2A2A2A !important;
      color: #CCC !important;
      border-radius: 8px !important;
  }
  [data-testid="stButton"] button:hover {
      border-color: #FF4B4B !important;
      color: #FF4B4B !important;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────
START_LAT, START_LON = 22.3072, 73.1812
DEST_LAT,  DEST_LON  = 23.0225, 72.5714

SAFE_MAX    = 6.5
CRITICAL_AT = 8.0
TEMP_CEIL   = 12.0

# Simulated truck speed — realistic NH48 highway speed
BASE_SPEED  = 68.0   # km/h average
SPEED_NOISE = 6.0    # ± variation

COLD_STORAGES = [
    {"name": "GAIMFP PPC Cold Store",           "city": "Vadodara",    "lat": 22.3100, "lon": 73.1650, "type": "Pharma"},
    {"name": "Amar Cold Storage",               "city": "Anand",       "lat": 22.5907, "lon": 72.9316, "type": "Food / Dairy"},
    {"name": "Vrundavan Cold Storage",          "city": "Gandhinagar", "lat": 23.1500, "lon": 72.6800, "type": "General"},
    {"name": "Gujarat Cold Storage Association","city": "Ahmedabad",   "lat": 23.0613, "lon": 72.5857, "type": "Pharma / Vaccines"},
]


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def nearest_cold_storage(lat, lon):
    return min(COLD_STORAGES, key=lambda s: haversine(lat, lon, s["lat"], s["lon"]))

def fetch_osrm(slon, slat, elon, elat):
    try:
        url = (f"https://router.project-osrm.org/route/v1/driving/"
               f"{slon},{slat};{elon},{elat}?overview=full&geometries=geojson")
        d = requests.get(url, timeout=10).json()
        coords = d["routes"][0]["geometry"]["coordinates"]
        dist   = d["routes"][0]["distance"] / 1000
        return [(c[1], c[0]) for c in coords], round(dist, 1)
    except Exception:
        steps = 120
        return [(slat + i/steps*(elat-slat), slon + i/steps*(elon-slon)) for i in range(steps)], \
               haversine(slat, slon, elat, elon)


# ─────────────────────────────────────────────────────────────
#  VOICE ALERT
# ─────────────────────────────────────────────────────────────
def voice(msg: str):
    safe = msg.replace("'", "\\'")
    st.components.v1.html(f"""
        <script>
            const u = new SpeechSynthesisUtterance('{safe}');
            u.rate = 0.92; u.pitch = 1.0; u.volume = 1.0;
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(u);
        </script>""", height=0)




# ─────────────────────────────────────────────────────────────
#  GEMINI — official SDK, background thread, never blocks UI
# ─────────────────────────────────────────────────────────────
_gemini_queue   = queue.Queue()
_gemini_running = threading.Event()


def _get_active_key():
    """Returns API key — env var first, then user-entered key from session."""
    return (
        GEMINI_API_KEY_ENV
        or st.session_state.get("gemini_api_key", "")
    )


def _gemini_worker(prompt, api_key):
    """Runs in daemon thread using official google-generativeai SDK."""
    import json as _json, re as _re

    def _extract_json(text):
        try:
            return _json.loads(text.strip())
        except Exception:
            pass
        cleaned = _re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        try:
            return _json.loads(cleaned)
        except Exception:
            pass
        match = _re.search(r"\{[\s\S]*?\}", text)
        if match:
            try:
                return _json.loads(match.group())
            except Exception:
                pass
        return None

    result      = None
    last_error  = None

    resp_text = ""
    for attempt in range(3):
        try:
            client   = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=512,
                ),
            )
            # SDK responses may expose text differently across versions.
            # Try common attributes then fallback to str(response).
            resp_text = None
            try:
                resp_text = getattr(response, "text", None)
            except Exception:
                resp_text = None
            if not resp_text:
                try:
                    # Some SDKs return a candidates list with content
                    resp_text = response.candidates[0].content if hasattr(response, "candidates") and response.candidates else None
                except Exception:
                    resp_text = None
            if not resp_text:
                try:
                    # Fallback to string representation
                    resp_text = str(response)
                except Exception:
                    resp_text = ""

            result = _extract_json(resp_text)
            required = ("temp_prediction","route_risk","cargo_damage","driver_message","severity")
            if result and all(k in result for k in required):
                last_error = None
                break
            result     = None
            last_error = "JSON missing required keys"
        except Exception as e:
            last_error = str(e)
            result     = None
            if attempt < 2:
                time.sleep(2)

    if last_error and result is None:
        # Put error in queue so event log shows what went wrong and include raw response
        _gemini_queue.put({"_error": last_error, "_raw": resp_text})
    else:
        _gemini_queue.put(result)
    _gemini_running.clear()


def gemini_analyze_async(temp, temp_history, speed, dist_covered,
                         dist_remaining, is_crit, is_warn, rerouted,
                         reroute_target, minutes_above_safe):
    """Fire-and-forget — skips silently if no key or call already in flight."""
    api_key = _get_active_key()
    if not api_key or _gemini_running.is_set():
        return

    status_str  = "CRITICAL" if is_crit else ("WARNING" if is_warn else "SAFE")
    # Guard against missing reroute_target to avoid KeyError when rerouted flag is set
    if rerouted and reroute_target:
        reroute_str = f"Truck rerouted to {reroute_target.get('name')} in {reroute_target.get('city')}."
    else:
        reroute_str = "Truck on original route to Ahmedabad."
    trend_str = " -> ".join(str(t) for t in (temp_history[-5:] if len(temp_history) >= 5 else temp_history))

    prompt = f"""You are FrostGuard AI, a STRICT cold-chain monitoring system.

YOU MUST FOLLOW THESE RULES:

- Vaccines must stay between 2°C and 8°C
- If temperature > 8°C → CRITICAL
- If temperature > 6.5°C → WARNING
- NEVER say everything is fine if WARNING or CRITICAL
- Your output MUST match the telemetry exactly

TELEMETRY:
- Cargo: Vaccines
- Temperature: {temp} C
- Status: {status_str}
- Temp trend: {trend_str}
- Speed: {speed:.0f} km/h
- Covered: {dist_covered:.1f} km
- Remaining: {dist_remaining:.1f} km
- Minutes above safe: {minutes_above_safe:.1f}
- {reroute_str}

LOGIC RULES:
- If status is CRITICAL:
    severity MUST be "CRITICAL"
    cargo_damage MUST mention spoilage or damage
    route_risk MUST mention danger
- If status is WARNING:
    severity MUST be "MEDIUM" or "HIGH"
- If rerouted:
    route_risk MUST mention rerouting

Return ONLY JSON:
{{"temp_prediction":"...","route_risk":"...","cargo_damage":"...","driver_message":"...","severity":"..."}}"""

    _gemini_running.set()
    threading.Thread(target=_gemini_worker, args=(prompt, api_key), daemon=True).start()


def gemini_collect_result():
    """Non-blocking — returns result if thread finished, else None."""
    try:
        result = _gemini_queue.get_nowait()
        if result and "_error" in result:
            # API returned an error — log it but show last good result
            st.session_state["gemini_last_error"] = result["_error"]
            # store raw text for debugging
            st.session_state["gemini_last_raw"] = result.get("_raw")
            return st.session_state.get("gemini_last_good", None)
        if result:
            st.session_state["gemini_last_good"]  = result
            st.session_state["gemini_last_error"] = None
            return result
        return st.session_state.get("gemini_last_good", None)
    except queue.Empty:
        return None

# ─────────────────────────────────────────────────────────────
#  SESSION STATE INIT
# ─────────────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    route, dist = fetch_osrm(START_LON, START_LAT, DEST_LON, DEST_LAT)
    st.session_state.update({
        "initialized"   : True,
        "main_route"    : route,
        "active_route"  : route,
        "total_dist"    : dist,
        "waypoint_idx"  : 0,
        "temp"          : 4.5,
        "rerouted"      : False,
        "reroute_target": None,
        "dist_covered"  : 0.0,
        "prev_lat"      : START_LAT,
        "prev_lon"      : START_LON,
        "speed_kmh"     : BASE_SPEED,
        "speed_history" : [BASE_SPEED] * 20,
        "temp_history"  : [4.5] * 20,
        "warning_log"   : [],
        "warn_alerted"       : False,
        "gemini_result"      : None,
        "gemini_last_run"    : 0,
        "gemini_last_error"  : None,
        "gemini_last_good"   : None,
        "minutes_above_safe" : 0,
    })


# ─────────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:1.2rem;">
  <div>
    <div style="font-size:0.65rem; letter-spacing:0.18em; color:#444; text-transform:uppercase; margin-bottom:2px;">
      FrostGuard AI · Red Dragons Fleet
    </div>
    <div style="font-size:1.6rem; font-weight:800; color:#F0F0F0; letter-spacing:-0.02em;">
      🐉 Command Center
    </div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:0.65rem; color:#444; letter-spacing:0.1em;">TRUCK ID</div>
    <div style="font-size:1.1rem; font-weight:700; color:#FF4B4B; font-family:monospace;">TRK-RD-001</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
#  RESTORE KEY FROM QUERY PARAMS (runs before render)
# ─────────────────────────────────────────────────────────────
# Restore key from query params on every run (survives st.rerun)
if not GEMINI_API_KEY_ENV:
    saved = st.query_params.get("gk", "")
    if saved and not st.session_state.get("gemini_api_key"):
        st.session_state["gemini_api_key"] = saved

#  CONTROLS ROW  (no sidebar — everything inline)
# ─────────────────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1, 1, 1, 5])
_fail_clicked  = ctrl1.button("🚨 Compressor Fail", key="btn_fail")
inject_failure = _fail_clicked
# Send command to bridge so simulator picks it up
if _fail_clicked:
    try:
        requests.post(
            "http://127.0.0.1:5000/command",
            json={"command": "compressor_fail"},
            timeout=2,
        )
    except Exception:
        pass
reset_btn      = ctrl2.button("🔄 Reset", key="btn_reset")
ask_ai_btn     = ctrl3.button("🧠 Ask Gemini", key="btn_gemini")

if reset_btn:
    # 1. Tell bridge to kill old simulator and clear data
    try:
        requests.post("http://127.0.0.1:5000/reset", timeout=3)
    except Exception:
        pass

    # 2. Clear all session state
    for k in list(st.session_state.keys()):
        del st.session_state[k]

    # 3. Rerun — launch_background_services will start fresh simulator
    st.rerun()

if ask_ai_btn and "initialized" in st.session_state:
    # Fire async — button shows "🧠 Thinking..." in next rerender
    gemini_analyze_async(
        st.session_state.get("temp", 4.5),
        st.session_state.get("temp_history", [4.5]*20),
        st.session_state.get("speed_kmh", 68.0),
        st.session_state.get("dist_covered", 0.0),
        max(st.session_state.get("total_dist", 113.0) - st.session_state.get("dist_covered", 0.0), 0),
        st.session_state.get("temp", 4.5) > CRITICAL_AT,
        st.session_state.get("temp", 4.5) > SAFE_MAX,
        st.session_state.get("rerouted", False),
        st.session_state.get("reroute_target", None),
        st.session_state.get("minutes_above_safe", 0),
    )
    st.session_state.gemini_last_run = time.time()
    st.session_state.warning_log.insert(0, {
        "icon": "🧠", "time": time.strftime("%H:%M:%S"),
        "msg" : "[AI] Analyzing... result appears in event log shortly.",
        "ai"  : False,
    })

st.markdown("<div style='margin-bottom:0.8rem;'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
#  PLACEHOLDER
# ─────────────────────────────────────────────────────────────
placeholder = st.empty()

# ─────────────────────────────────────────────────────────────
#  LIVE STEP (single-run per page load; browser auto-refresh handles iteration)
# ─────────────────────────────────────────────────────────────
if True:
    # If journey already marked complete, just show arrival and stop auto-refresh
    if st.session_state.get("journey_complete", False):
        with placeholder.container():
            t = st.session_state.reroute_target
            msg = f"✅ Arrived at **{t['name']}**, {t['city']} — Cargo secured 🧊" if t else "✅ Arrived in **Ahmedabad** — Journey complete 🎉"
            st.success(msg)
    else:
        # ── Animation always follows main_route (NH48 original path) ──
        # Real GPS from bridge overrides position for WARNING/CRITICAL/rerouted
        anim_route = st.session_state.main_route
        idx        = st.session_state.waypoint_idx

        # ── Poll bridge for real telemetry FIRST ──
        real_lat       = st.session_state.get("last_real_lat", START_LAT)
        real_lon       = st.session_state.get("last_real_lon", START_LON)
        telemetry_used = False
        tele_status    = None
        try:
            resp = requests.get("http://127.0.0.1:5000/latest", timeout=0.6)
            if resp.status_code == 200:
                tele = resp.json()
                if "temperature" in tele:
                    st.session_state.temp = float(tele["temperature"])
                    telemetry_used = True
                if "lat" in tele and "lng" in tele:
                    real_lat = float(tele["lat"])
                    real_lon = float(tele["lng"])
                    st.session_state.last_real_lat = real_lat
                    st.session_state.last_real_lon = real_lon
                if "status" in tele:
                    tele_status = tele["status"]
        except Exception:
            telemetry_used = False

        # ── Journey complete check ──
        if st.session_state.rerouted and st.session_state.reroute_target:
            # Rerouted: complete when within 0.5km of cold storage
            t = st.session_state.reroute_target
            if haversine(real_lat, real_lon, t["lat"], t["lon"]) < 0.5:
                st.session_state["journey_complete"] = True
        elif idx >= len(anim_route):
            st.session_state["journey_complete"] = True

        if st.session_state.get("journey_complete", False):
            with placeholder.container():
                t   = st.session_state.reroute_target
                msg = (f"✅ Arrived at **{t['name']}**, {t['city']} — Cargo secured 🧊"
                       if t else "✅ Arrived in **Ahmedabad** — Journey complete 🎉")
                st.success(msg)
        else:
            # Advance animation on original NH48 route
            if idx < len(anim_route):
                anim_lat, anim_lon = anim_route[idx]
                st.session_state.waypoint_idx += 1
            else:
                anim_lat, anim_lon = real_lat, real_lon

            # ── Final truck dot position ──
            # Rerouted or WARNING/CRITICAL → real GPS (follows actual truck)
            # SAFE normal               → animation (smooth on NH48)
            if st.session_state.rerouted or tele_status in ("CRITICAL", "WARNING"):
                lat, lon = real_lat, real_lon
            else:
                lat, lon = anim_lat, anim_lon

            # ── Simulated speed (smooth, realistic) ──
            target_speed  = BASE_SPEED + random.uniform(-SPEED_NOISE, SPEED_NOISE)
            current_speed = st.session_state.speed_kmh
            # Smooth toward target — no sudden jumps
            new_speed = current_speed + (target_speed - current_speed) * 0.08
            st.session_state.speed_kmh = round(new_speed, 1)

            st.session_state.speed_history.append(st.session_state.speed_kmh)
            st.session_state.speed_history = st.session_state.speed_history[-20:]

            # ── Distance covered ──
            # Use last known real position → current position
            # Capped at 0.5km per tick to prevent GPS jumps causing spikes
            step = haversine(
                st.session_state.prev_lat, st.session_state.prev_lon,
                lat, lon
            )
            if step < 0.5:   # ignore teleport jumps > 500m in one tick
                st.session_state.dist_covered += step
            st.session_state.prev_lat = lat
            st.session_state.prev_lon = lon

            dist_remaining = max(st.session_state.total_dist - st.session_state.dist_covered, 0)
            eta_min = (dist_remaining / max(st.session_state.speed_kmh, 1)) * 60

            # ── Temperature ── (only simulate when external telemetry not available)
            if not telemetry_used:
                if inject_failure:
                    st.session_state.temp += random.uniform(0.9, 1.6)
                elif st.session_state.temp > CRITICAL_AT:
                    st.session_state.temp += random.uniform(-0.15, 0.35)
                elif st.session_state.temp > SAFE_MAX:
                    st.session_state.temp += random.uniform(-0.25, 0.18)
                else:
                    st.session_state.temp = max(min(st.session_state.temp + random.uniform(-0.08, 0.18), 4.5), 3.5)

            st.session_state.temp = round(min(max(st.session_state.temp, 2.0), TEMP_CEIL), 1)
            temp    = st.session_state.temp
            # Use simulator's own status when available — more accurate
            if tele_status:
                is_crit = tele_status == "CRITICAL"
                is_warn = tele_status in ("WARNING", "CRITICAL")
            else:
                is_crit = temp > CRITICAL_AT
                is_warn = temp > SAFE_MAX

            if is_warn or is_crit:
                st.session_state.minutes_above_safe += 1/60
            else:
                st.session_state.minutes_above_safe = 0

            st.session_state.temp_history.append(temp)
            st.session_state.temp_history = st.session_state.temp_history[-20:]

            # ── Rerouting ──
            if is_crit and not st.session_state.rerouted:
                # Use real GPS from telemetry if available for accurate reroute
                reroute_lat = st.session_state.get("last_real_lat", lat)
                reroute_lon = st.session_state.get("last_real_lon", lon)
                cs = nearest_cold_storage(reroute_lat, reroute_lon)
                new_route, new_dist = fetch_osrm(reroute_lon, reroute_lat, cs["lon"], cs["lat"])
                st.session_state.rerouted        = True
                st.session_state.reroute_target  = cs
                st.session_state.active_route    = new_route
                st.session_state.waypoint_idx    = 0
                st.session_state.total_dist      = new_dist
                st.session_state.dist_covered    = 0.0
                st.session_state.prev_lat        = reroute_lat
                st.session_state.prev_lon        = reroute_lon
                dist_to = haversine(lat, lon, cs["lat"], cs["lon"])
                st.session_state.warning_log.insert(0, {
                    "icon": "🚨", "time": time.strftime("%H:%M:%S"),
                    "msg": f"CRITICAL {temp}°C — Rerouted to {cs['name']}, {cs['city']}"
                })
                voice(
                    f"Warning! Cargo temperature critical at {temp} degrees. "
                    f"Rerouting to {cs['name']} in {cs['city']}. "
                    f"Distance: {dist_to:.0f} kilometres."
                )

            elif is_warn and not st.session_state.warn_alerted:
                st.session_state.warn_alerted = True
                st.session_state.warning_log.insert(0, {
                    "icon": "⚠️", "time": time.strftime("%H:%M:%S"),
                    "msg": f"WARNING {temp}°C — Compressor activated"
                })
                voice(f"Temperature warning. Cargo at {temp} degrees. Compressor activated.")

            if not is_warn:
                st.session_state.warn_alerted = False

            # ── Auto Gemini trigger — non-blocking, fires in background thread ──
            now_ts = time.time()
            if (is_warn or is_crit) and (now_ts - st.session_state.gemini_last_run > 120):
                gemini_analyze_async(
                    temp, st.session_state.temp_history,
                    st.session_state.speed_kmh,
                    st.session_state.dist_covered,
                    dist_remaining, is_crit, is_warn,
                    st.session_state.rerouted,
                    st.session_state.reroute_target,
                    st.session_state.minutes_above_safe,
                )
                st.session_state.gemini_last_run = now_ts

            # ── Collect result if thread finished (non-blocking check) ──
            ready = gemini_collect_result()
            if ready:

                # 🚨 FULL OVERRIDE IN CRITICAL (safety-first)
                if is_crit:
                    ready = {
                        "temp_prediction": "Temperature will continue rising if not controlled",
                        "route_risk": "Route unsafe due to critical temperature",
                        "cargo_damage": "High probability of vaccine spoilage",
                        "driver_message": "Immediate cooling or stop required",
                        "severity": "CRITICAL",
                    }

                elif is_warn and ready.get("severity") == "LOW":
                    # Promote overly-low severity to MEDIUM for warnings
                    ready["severity"] = "MEDIUM"

                st.session_state.warning_log.insert(0, {
                    "icon"  : "🧠",
                    "time"  : time.strftime("%H:%M:%S"),
                    "msg"   : f"[AI] {ready['driver_message']}",
                    "ai"    : True,
                    "result": ready,
                })
            elif st.session_state.get("gemini_last_error"):
                err = st.session_state.pop("gemini_last_error")
                # Only show error if we have never had a successful result
                # (avoids showing stale errors from before key was entered)
                if not st.session_state.get("gemini_last_good"):
                    st.session_state.warning_log.insert(0, {
                        "icon": "⚠️",
                        "time": time.strftime("%H:%M:%S"),
                        "msg" : f"[AI Error] {err[:80]}",
                        "ai"  : False,
                    })

            # ── Dot color ──
            dot_color = [255, 40, 40, 255] if is_crit else ([255, 165, 0, 255] if is_warn else [0, 220, 100, 255])

            # ── Map layers ──
            layers = []

            # Original planned route
            orig_line = [[lo, la] for la, lo in st.session_state.main_route]
            layers.append(pdk.Layer("PathLayer",
                data=[{"path": orig_line}], get_path="path",
                get_color=[40, 80, 200, 70] if st.session_state.rerouted else [0, 140, 255, 130],
                width_scale=14, width_min_pixels=3))

            # Reroute path
            if st.session_state.rerouted:
                rr_line = [[lo, la] for la, lo in st.session_state.active_route]
                layers.append(pdk.Layer("PathLayer",
                    data=[{"path": rr_line}], get_path="path",
                    get_color=[255, 110, 0, 220], width_scale=16, width_min_pixels=4))

            # Cold storage dots
            layers.append(pdk.Layer("ScatterplotLayer",
                data=[{"lat": c["lat"], "lon": c["lon"], "name": c["name"], "city": c["city"]} for c in COLD_STORAGES],
                get_position="[lon, lat]", get_color=[0, 200, 255, 180],
                get_radius=500, radiusMinPixels=9, pickable=True))

            # Reroute target glow
            if st.session_state.rerouted and st.session_state.reroute_target:
                t = st.session_state.reroute_target
                layers.append(pdk.Layer("ScatterplotLayer",
                    data=[{"lat": t["lat"], "lon": t["lon"]}],
                    get_position="[lon, lat]", get_color=[255, 50, 50, 60],
                    get_radius=1400, radiusMinPixels=22))

            # Truck
            layers.append(pdk.Layer("ScatterplotLayer",
                data=[{"lat": lat, "lon": lon}],
                get_position="[lon, lat]", get_color=dot_color,
                get_radius=320, radiusMinPixels=10, radiusMaxPixels=20))

            # ─────────────────────────────────────────
            #  RENDER
            # ─────────────────────────────────────────
            with placeholder.container():

                # ── Gemini key input (only if not set via env) ──
                if not GEMINI_API_KEY_ENV:
                    if not st.session_state.get("gemini_api_key"):
                        key_col, btn_col = st.columns([4, 1])
                        with key_col:
                            entered_key = st.text_input(
                                "🔑 Gemini API Key", type="password",
                                placeholder="Paste your key from aistudio.google.com",
                                label_visibility="collapsed",
                                key="gemini_key_input",
                            )
                        with btn_col:
                            if st.button("Save Key", key="btn_save_key") and entered_key:
                                st.session_state["gemini_api_key"] = entered_key
                                st.query_params["gk"] = entered_key
                        st.markdown(
                            '<div style="font-size:0.7rem;color:#555;margin-bottom:0.5rem;">'
                            'Get free key at <a href="https://aistudio.google.com" style="color:#4FC3F7;">aistudio.google.com</a>'
                            '</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(
                            """
                            <div style="display:inline-block;background:#0a1a0a;border:1px solid #1a3a1a;
                            border-radius:8px;padding:4px 12px;font-size:0.73rem;color:#4CAF50;margin-bottom:0.5rem;">
                            🟢 Gemini AI Online</div>
                            """,
                            unsafe_allow_html=True,
                        )

                # ── Service status badges (bridge + simulator) ──
                bridge_status = False
                sim_status = False
                try:
                    h = requests.get("http://127.0.0.1:5000/health", timeout=0.6)
                    bridge_status = (h.status_code == 200)
                except Exception:
                    bridge_status = False
                try:
                    l = requests.get("http://127.0.0.1:5000/latest", timeout=0.6)
                    sim_status = (l.status_code == 200)
                except Exception:
                    sim_status = False

                bridge_bg = "#4CAF50" if bridge_status else "#444"
                sim_bg = "#4CAF50" if sim_status else "#444"
                status_html = (
                    f'<div style="display:inline-block;margin-left:10px;">'
                    f'<span style="display:inline-block;background:{bridge_bg};color:#000;padding:4px 8px;border-radius:8px;font-size:0.72rem;margin-right:6px;">Bridge</span>'
                    f'<span style="display:inline-block;background:{sim_bg};color:#000;padding:4px 8px;border-radius:8px;font-size:0.72rem;">Simulator</span>'
                    '</div>'
                )
                st.markdown(status_html, unsafe_allow_html=True)

                # Alert banner
                if is_crit and st.session_state.rerouted:
                    t = st.session_state.reroute_target
                    st.error(f"🚨 CRITICAL BREACH — {temp}°C  ·  REROUTING TO **{t['name'].upper()}**, {t['city'].upper()} 🧊")
                elif is_warn:
                    st.warning(f"⚠️ WARNING — Temperature rising: **{temp}°C**  ·  Compressor activated")

        # ── ROW 1: 6 metric cards ──
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("📦 Cargo",       "Vaccines")
        m2.metric("🌡 Temperature", f"{temp}°C",
                  delta=f"{temp - 4.0:+.1f}°C baseline", delta_color="inverse")
        m3.metric("🔴 Status",      "CRITICAL" if is_crit else ("WARNING" if is_warn else "NOMINAL"))
        m4.metric("🏎 Speed",       f"{st.session_state.speed_kmh:.0f} km/h")
        m5.metric("📏 Covered",     f"{st.session_state.dist_covered:.1f} km")
        m6.metric("⏱ ETA",
                  "REROUTING 🧊" if st.session_state.rerouted else f"{eta_min:.0f} min")

        st.markdown("<div style='margin:0.6rem 0;'></div>", unsafe_allow_html=True)

        # ── ROW 2: Map (wide) ──
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=lat, longitude=lon,
                zoom=11, pitch=52, bearing=0),
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            tooltip={"text": "📍 {name}\n{city}"},
        ))

        st.markdown("<div style='margin:0.6rem 0;'></div>", unsafe_allow_html=True)

        # ── ROW 3: Speed chart | Temp chart | Event log ──
        ch1, ch2, ch3 = st.columns([1, 1, 1])

        with ch1:
            st.markdown('<div class="fg-card"><div class="fg-card-title">⚡ Live Speed (km/h)</div>', unsafe_allow_html=True)
            st.line_chart({"Speed": st.session_state.speed_history}, height=110)
            st.markdown('</div>', unsafe_allow_html=True)

        with ch2:
            st.markdown('<div class="fg-card"><div class="fg-card-title">🌡 Temperature History (°C)</div>', unsafe_allow_html=True)
            st.line_chart({"Temp": st.session_state.temp_history}, height=110)
            st.markdown('</div>', unsafe_allow_html=True)

        with ch3:
            st.markdown('<div class="fg-card"><div class="fg-card-title">📋 Event Log + AI Analysis</div>', unsafe_allow_html=True)
            if st.session_state.warning_log:
                for ev in st.session_state.warning_log[:5]:
                    is_ai = ev.get("ai", False)
                    color = "#4FC3F7" if is_ai else ("#FF4B4B" if "CRITICAL" in ev["msg"] else "#FFA500")
                    st.markdown(
                        f'<div style="background:#111; border-left:3px solid {color}; '
                        f'border-radius:6px; padding:7px 10px; margin-bottom:6px;>'
                        f'<span style="font-size:0.62rem; color:#555;">{ev["time"]}</span><br>'
                        f'<span style="font-size:0.76rem; color:#DDD;">{ev["icon"]} {ev["msg"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    if is_ai and ev.get("result"):
                        r = ev["result"]
                        sev_color = "#FF4B4B" if r["severity"] == "CRITICAL" else ("#FFA500" if r["severity"] in ("HIGH","MEDIUM") else "#4FC3F7")
                        st.markdown(
                            f'<div style="background:#0A0A0A; border:1px solid #1A1A1A; border-radius:6px; '
                            f'padding:8px 10px; margin:-2px 0 6px 0; font-size:0.72rem; line-height:1.6;>'
                            f'<span style="color:{sev_color}; font-weight:700; letter-spacing:0.06em;">■ {r["severity"]}</span><br>'
                            f'<span style="color:#888;">🌡 Prediction: </span><span style="color:#CCC;">{r["temp_prediction"]}</span><br>'
                            f'<span style="color:#888;">🛣 Route: </span><span style="color:#CCC;">{r["route_risk"]}</span><br>'
                            f'<span style="color:#888;">📦 Cargo: </span><span style="color:#CCC;">{r["cargo_damage"]}</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
            else:
                st.markdown(
                    '<div style="background:#111; border-left:3px solid #1A6E3C; border-radius:6px; '
                    'padding:7px 10px;"><span style="font-size:0.78rem; color:#666;">✅ All systems nominal</span></div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)

        # ── ROW 4: Footer info ──
        st.markdown("<div style='margin:0.4rem 0;'></div>", unsafe_allow_html=True)
        f1, f2, f3, f4 = st.columns(4)
        dest = st.session_state.reroute_target["city"] if st.session_state.rerouted else "Ahmedabad"
        f1.caption(f"📍 {lat:.5f}°N  {lon:.5f}°E")
        f2.caption(f"🏁 Destination: {dest}")
        f3.caption(f"🛣 {'NH48 → Emergency Reroute' if st.session_state.rerouted else 'NH48  Vadodara → Ahmedabad'}")
        f4.caption(f"📊 Waypoint {st.session_state.waypoint_idx} / {len(route)}")

# ─────────────────────────────────────────────────────────────
#  TICK — one frame per second using session_state pattern
#  script runs top-to-bottom once, advances state, reruns once
#  journey_complete = True → no rerun → page freezes cleanly
# ─────────────────────────────────────────────────────────────
if not st.session_state.get("journey_complete", False):
    time.sleep(1)
    st.rerun()
