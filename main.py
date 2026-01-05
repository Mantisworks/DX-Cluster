import telnetlib
import threading
import time
import re
import os
import webview
import tkinter as tk
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

# CONFIGURAZIONE
CLUSTER_HOST = "dx.iz7auh.net"
CLUSTER_PORT = 8000
CONFIG_FILE = "config.txt"

spots = []
connected = False
current_call = ""

# --- LOGICA PROPAGAZIONE AVANZATA ---
def get_propagation_info():
    hour = datetime.utcnow().hour
    if 7 <= hour <= 16:  # GIORNO
        return {
            "status": "PROPAGAZIONE DIURNA",
            "short": "40m, 30m",
            "long": "10m, 12m, 15m, 20m",
            "advice": "Bande alte (10-20m) ottime per DX. 40m per traffico EU."
        }
    elif 17 <= hour <= 19 or 5 <= hour <= 6:  # GREYLINE
        return {
            "status": "GREYLINE (TRANSIZIONE)",
            "short": "80m, 40m",
            "long": "20m, 30m, 40m",
            "advice": "Aperture DX rare seguendo la linea d'ombra terrestre."
        }
    else:  # NOTTE
        return {
            "status": "PROPAGAZIONE NOTTURNA",
            "short": "160m, 80m",
            "long": "40m, 20m (chiusura)",
            "advice": "Bande basse dominanti. 40m ideali per DX notturni."
        }

def get_mode(freq_str):
    try:
        f = float(freq_str)
        if 14074 <= f <= 14076 or 7074 <= f <= 7076: return "FT8"
        if f % 1000 <= 50: return "CW"
        if f > 14150 or f > 7100: return "SSB"
        return "DIGI"
    except: return "DX"

def get_special_activity(comment):
    c = comment.upper()
    if "SOTA" in c: return "SOTA"
    if "POTA" in c: return "POTA"
    if "IOTA" in c: return "IOTA"
    return None

# --- WORKER TELNET ---
def telnet_worker(callsign):
    global spots, connected
    while connected:
        try:
            tn = telnetlib.Telnet(CLUSTER_HOST, CLUSTER_PORT, timeout=10)
            time.sleep(1)
            tn.write(callsign.encode('ascii') + b"\r\n")
            while connected:
                line_raw = tn.read_until(b"\n", timeout=2).decode('ascii', errors='ignore')
                line = re.sub(r'[^\x20-\x7E]', '', line_raw).strip()
                if "DX de" in line:
                    try:
                        f_val = line[16:26].strip()
                        comm = line[38:-5].strip()
                        new_spot = {
                            "de": line[6:16].replace(":", "").strip()[:5],
                            "freq": f_val,
                            "mode": get_mode(f_val),
                            "dx": line[26:38].strip(),
                            "time": re.sub(r'[^\d]', '', line[-5:])[:4],
                            "special": get_special_activity(comm)
                        }
                        spots.insert(0, new_spot)
                        spots = spots[:30]
                    except: continue
        except:
            if connected: time.sleep(5)

# --- INTERFACCIA HTML ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; border: 1px solid #30363d; overflow: hidden; height: 100vh; }
        .title-bar { background: #21262d; height: 35px; display: flex; justify-content: space-between; align-items: center; padding: 0 10px; -webkit-app-region: drag; cursor: move; border-bottom: 1px solid #30363d; }
        .close-btn { background: transparent; color: #8b949e; border: none; font-size: 20px; cursor: pointer; -webkit-app-region: no-drag; padding: 0 5px; }
        .close-btn:hover { color: #f85149; }
        .content { height: calc(100vh - 35px); overflow-y: auto; }
        
        .prop-box { background: #161b22; padding: 12px; font-size: 11px; border-bottom: 1px solid #30363d; border-left: 4px solid #58a6ff; }
        .tag-row { margin-top: 8px; display: flex; gap: 8px; }
        .tag { background: #21262d; padding: 3px 6px; border-radius: 4px; font-size: 10px; border: 1px solid #30363d; }
        .tag b { color: #58a6ff; }

        table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
        thead th { background: #0d1117; color: #8b949e; text-align: left; padding: 10px 5px; font-size: 9px; text-transform: uppercase; border-bottom: 2px solid #30363d; position: sticky; top: 0; z-index: 10; }
        td { padding: 10px 5px; border-bottom: 1px solid #21262d; font-family: 'Consolas', monospace; overflow: hidden; white-space: nowrap; }
        
        .m-badge { padding: 1px 4px; border-radius: 3px; font-size: 9px; font-weight: bold; color: #fff; }
        .m-FT8 { background: #7057ff; } .m-CW { background: #d29922; } .m-SSB { background: #238636; } .m-DX { background: #6e7681; }
        
        .SOTA { color: #ff9d00 !important; font-weight: bold; }
        .POTA { color: #2ecc71 !important; font-weight: bold; }
        .IOTA { color: #3498db !important; font-weight: bold; }
        .sp-label { font-size: 8px; padding: 1px 4px; border-radius: 3px; background: #30363d; color: #fff; margin-left: 5px; vertical-align: middle; }

        .c-time { width: 45px; color: #f85149; }
        .c-mode { width: 45px; text-align: center; }
        .c-freq { width: 75px; color: #d29922; font-weight: bold; }
        .c-dx { width: 110px; }

        .login { text-align: center; padding-top: 100px; }
        input { background: #161b22; border: 1px solid #30363d; color: #58a6ff; padding: 10px; border-radius: 5px; width: 160px; text-align: center; margin-bottom: 15px; text-transform: uppercase; font-size: 1.1em; }
        .btn { background: #238636; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="title-bar">
        <span style="font-size: 11px; font-weight: bold; color: #8b949e;">DX Cluster <span id="user-call"></span></span>
        <button class="close-btn" onclick="closeApp()">×</button>
    </div>
    <div class="content">
        <div id="login" class="login">
            <h2 style="color:#58a6ff; font-size:18px">CLUSTER GATEWAY</h2>
            <input type="text" id="callsign" placeholder="CALLSIGN" value="{{ last_call }}"><br>
            <button class="btn" onclick="connect()">CONNETTI ORA</button>
        </div>
        <div id="app" style="display:none;">
            <div class="prop-box">
                <b id="p-status" style="color:#58a6ff; text-transform: uppercase;"></b><br>
                <span id="p-advice" style="color:#8b949e; font-size:10px;"></span>
                <div class="tag-row">
                    <div class="tag">LOCALE: <b id="p-short"></b></div>
                    <div class="tag">DX: <b id="p-long"></b></div>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th class="c-time">UTC</th>
                        <th class="c-mode">MOD</th>
                        <th class="c-freq">FREQ</th>
                        <th class="c-dx">DX CALL</th>
                    </tr>
                </thead>
                <tbody id="list"></tbody>
            </table>
        </div>
    </div>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        function closeApp() { window.pywebview.api.close_window(); }
        function connect() {
            let call = $('#callsign').val().trim().toUpperCase();
            if(!call) return;
            $.post('/api/connect', {call: call}, function() {
                $('#user-call').text("| " + call);
                $('#login').hide(); $('#app').show();
                setInterval(update, 3000); update();
            });
        }
        function update() {
            $.getJSON('/api/data', function(res) {
                $('#p-status').text(res.prop.status);
                $('#p-advice').text(res.prop.advice);
                $('#p-short').text(res.prop.short);
                $('#p-long').text(res.prop.long);
                $('#list').empty();
                res.spots.forEach(s => {
                    let spCls = s.special ? s.special : "";
                    let spLbl = s.special ? `<span class="sp-label">${s.special}</span>` : "";
                    $('#list').append(`<tr>
                        <td class="c-time">${s.time}</td>
                        <td class="c-mode"><span class="m-badge m-${s.mode}">${s.mode}</span></td>
                        <td class="c-freq">${s.freq}</td>
                        <td class="c-dx ${spCls}">${s.dx}${spLbl}</td>
                    </tr>`);
                });
            });
        }
    </script>
</body>
</html>
"""

class API:
    def close_window(self): window.destroy()

@app.route('/')
def index():
    last_call = ""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f: last_call = f.read().strip()
    return render_template_string(HTML_TEMPLATE, last_call=last_call)

@app.route('/api/connect', methods=['POST'])
def connect_call():
    global connected, current_call, spots
    current_call = request.form.get('call').upper()
    with open(CONFIG_FILE, "w") as f: f.write(current_call)
    connected = True
    threading.Thread(target=telnet_worker, args=(current_call,), daemon=True).start()
    return jsonify({"status": "ok"})

@app.route('/api/data')
def get_data():
    return jsonify({"spots": spots, "prop": get_propagation_info()})

if __name__ == '__main__':
    api = API()
    threading.Thread(target=lambda: app.run(port=5000, use_reloader=False), daemon=True).start()
    
    # --- RILEVAMENTO MONITOR E POSIZIONAMENTO ---
    root = tk.Tk()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    root.destroy()

    w_width = 360 # Larghezza fissa sidebar
    
    window = webview.create_window(
        'DX Cluster', 
        'http://127.0.0.1:5000', 
        width=w_width, 
        height=screen_h, 
        x=screen_w - w_width, # Aggancia a destra
        y=0,                  # In alto
        frameless=True, 
        on_top=True, 
        js_api=api
    )
    webview.start()
