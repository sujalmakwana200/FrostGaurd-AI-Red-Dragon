# 🐉 FrostGuard AI — Red Dragons Command Center

> **Real-time cold chain monitoring and AI-powered emergency rerouting for refrigerated cargo trucks**

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red?style=flat-square&logo=streamlit)
![Gemini](https://img.shields.io/badge/Gemini-Flash-orange?style=flat-square&logo=google)
![Flask](https://img.shields.io/badge/Flask-Bridge-lightgrey?style=flat-square&logo=flask)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## What is FrostGuard AI?

FrostGuard AI is a real-time cold chain intelligence system built for refrigerated cargo trucks on the **NH48 Vadodara to Ahmedabad highway**. It monitors cargo temperature 24/7, automatically boosts refrigeration when temperatures rise, and if the compressor fails it **instantly reroutes the truck to the nearest real cold storage facility** with a voice alert to the driver.

Built to solve a real problem: billions of dollars of pharmaceuticals, vaccines, and perishables are lost every year due to cold chain failures in transit. FrostGuard AI is the proactive layer that acts before the damage is done.

---

## Features

- 🗺 **Live truck tracking** on real NH48 road route via OSRM (no API key needed)
- 🌡 **Real-time temperature monitoring** with WARNING and CRITICAL threshold logic
- 🧊 **Auto rerouting** to nearest real cold storage facility when CRITICAL
- 🔊 **Voice alerts** to driver using browser Web Speech API
- 🧠 **Gemini AI analysis** — temperature prediction, route risk, cargo damage assessment, driver message
- 📋 **Event log** with AI analysis cards inside the dashboard
- 📊 **Live metrics** — speed, distance covered, ETA, temperature trend chart
- 💾 **Fleet log CSV** — historical record for fleet managers
- 🔔 **Discord alerts** on CRITICAL status via webhook
- 🖤 **OLED dark theme** — pure black UI built for command centers

---

## Architecture

```
Streamlit Cloud starts main_dashboard.py
        |
        |--- auto-launches ---> bridge.py (Flask, port 5000)
        |--- auto-launches ---> sensor_simulator.py
        
sensor_simulator.py
        |
        | POST /telemetry every 3s
        v
bridge.py
        |--- writes ---> fleet_logs.csv  (manager history)
        |--- sends  ---> Discord webhook (CRITICAL alerts)

main_dashboard.py
        |--- live truck view with Gemini AI
        |--- reads fleet_logs.csv for manager history panel
```

### Real Cold Storage Facilities on Route

| Facility | City | Type |
|---|---|---|
| GAIMFP PPC Cold Store | Vadodara | Pharma |
| Amar Cold Storage | Anand | Food / Dairy |
| Vrundavan Cold Storage | Gandhinagar | General |
| Gujarat Cold Storage Association | Ahmedabad | Pharma / Vaccines |

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/frostguard-ai.git
cd frostguard-ai
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate       # Mac / Linux
venv\Scripts\activate          # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API keys

Create a `.env` file in the root folder:

```env
GEMINI_API_KEY=your_gemini_api_key_here
DISCORD_WEBHOOK=your_discord_webhook_here
```

Get your free Gemini key at [aistudio.google.com](https://aistudio.google.com) — no credit card needed.

### 5. Run

```bash
streamlit run main_dashboard.py
```

`bridge.py` and `sensor_simulator.py` launch automatically as background processes when the dashboard starts.

---

## Deploying to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and create a new app
3. Set entry point to `main_dashboard.py`
4. Go to **Settings → Secrets** and add:

```toml
GEMINI_API_KEY = "your_key_here"
DISCORD_WEBHOOK = "your_webhook_here"
```

5. Deploy — all three files start automatically

---

## Project Structure

```
frostguard-ai/
│
├── main_dashboard.py      # Streamlit dashboard — live view + Gemini AI
├── bridge.py              # Flask server — receives telemetry, logs to CSV
├── sensor_simulator.py    # Truck movement simulation on real NH48 route
│
├── fleet_logs.csv         # Auto-generated historical telemetry log
├── requirements.txt       # Minimal dependencies only
├── .gitignore
└── README.md
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Dashboard | Streamlit + PyDeck |
| Map | CARTO Dark Matter (free, no API key) |
| Road Routing | OSRM Open Source Routing Machine |
| AI Analysis | Google Gemini Flash |
| Bridge Server | Flask |
| Voice Alerts | Web Speech API (browser native) |
| Data Logging | CSV via fleet_logs.csv |
| Notifications | Discord Webhooks |

---

## Team — Red Dragons 🐉

| Name | Role |
|---|---|
| **Sujal** | UI/UX — Dashboard design, OLED dark theme, metric cards, map layers, Gemini integration |
| **Ritik** | Backend — Bridge listener, telemetry pipeline, Flask server, CSV logging |
| **Rohit** | Intern — Sensor simulator, OSRM route integration, Discord webhook alerts |
| **Dheeraj** | Intern — Development support and contributions |
| **Sharang** | QA — Testing, bug reporting, edge case validation, quality assurance |
| **Alanjohn** | Business SPOC - Communication hub, requirement gathering, issue resolution, progress tracking |

---

## License

MIT License — free to use, modify, and distribute.

---

## Contributors

[![Sujal](https://img.shields.io/badge/Sujal-UI%2FUX-blue)](https://github.com/sujalmakwana200)
[![Ritik](https://img.shields.io/badge/Ritik-Backend-green)](https://github.com/ritikraushan812-rgb)
[![Rohit](https://img.shields.io/badge/Rohit-Intern-orange)](https://github.com/rohit)
[![Sharang](https://img.shields.io/badge/Sharang-QA-purple)](https://github.com/sharang)
[![Dheeraj](https://img.shields.io/badge/Dheeraj-Intern-orange)](https://github.com/dheeraj)
[![Alanjohn](https://img.shields.io/badge/Alanjohn-Business_SPOC-red)](https://github.com/dev-alanjohn)

<div align="center">
  Built with love by Team Red Dragons 🐉
</div>
