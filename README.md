# 🎬 RenderQ - Simple Blender Render Farm

RenderQ is a lightweight render farm system built with **Python + Flask (server)** and **PySide6 (GUI)** to manage distributed Blender rendering.  
It supports **multiple workers**, **progress tracking**, and **manual/auto worker assignment**.



## ✨ Features
- ✅ Backend server with **Flask REST API**
- ✅ Register & update workers in real-time
- ✅ Submit render tasks from Artist GUI
- ✅ Manual or automatic worker assignment
- ✅ Progress monitoring: frame, percentage, ETA
- ✅ Task logs streaming directly from Blender
- ✅ Modern dark-mode GUI (PySide6)
- ✅ Multi-worker management & live worker status



## 📦 Requirements
Install dependencies with:
```bash
pip install Flask PySide6 requests
```
Make sure Blender is available in your PATH (so it can be executed via blender -b).

## ⚙️ Configuration
At the top of the code (main.py):
```bash
# --------- CONFIG ----------
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000
SERVER_URL = f"http://192.168.1.47:{SERVER_PORT}"  # replace with your server IP on LAN
POLL_INTERVAL = 1.0  # GUI polling interval (seconds)
FRAME_TIME_WINDOW = 8  # number of recent frames for ETA calculation
# ---------------------------
```
- SERVER_HOST → keep 0.0.0.0 so other machines on the network can access it.
- SERVER_URL → change to match your server IP.
- POLL_INTERVAL → refresh interval for GUI.
- FRAME_TIME_WINDOW → determines the frame average for ETA calculation.

## 🚀 How to Run
1. Start the app
   ```bash
   python main.py
   ```
### 🖥️ GUI Overview
- Artist Window → Submit & monitor tasks
- Worker Window → View worker status and render logs

## 🔗 API Endpoints
- The server also provides a simple REST API:
- POST /register_worker – register a new worker
- POST /update_worker – update worker status
- GET /list_workers – list all workers
- POST /submit_task – submit a render task
- GET /get_task – worker fetches task
- POST /update_task – update task status & progress
- GET /tasks – list all tasks

## 📌 Notes
- A worker is considered alive if its last update < 15 seconds.
- Tasks can be auto-assigned (first ON worker) or manually assigned to a worker.
- ETA is calculated based on the average duration of recent frames × remaining frames.
