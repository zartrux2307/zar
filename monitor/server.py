import os
import time
import json
import threading
import logging
import webbrowser
import requests
import platform
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import psutil

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuración
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(BASE_DIR, 'status/ia_mining_status.json')
LOG_PATH = os.path.join(BASE_DIR, 'status/ia_console.log')
XMRIG_API_URL = "http://127.0.0.1:40500"  # Actualizado al puerto correcto de la API

os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# Inicializar archivos si no existen
if not os.path.exists(STATUS_PATH):
    with open(STATUS_PATH, 'w') as f:
        json.dump({
            "status": "starting",
            "uptime_seconds": 0,
            "mining_time": "00:00:00",
            "threads": "0/0",
            "ram": "0.0/0.0 GB",
            "cpu_usage": "0%",
            "cpu_speed": "0 GHz",
            "cpu_temp": "0°C",
            "hashrate": "0.00",
            "shares": "0",
            "accepted_shares": 0,
            "rejected_shares": 0,
            "difficulty": "0.00",
            "block": "000000",
            "wallet_address": "",
            "pool_url": "",
            "ia_validated": 0,
            "cpu_validated": 0,
            "accuracy": "0.0",
            "hit_rate": "0.0",
            "data_processed": "0.0",
            "threads_progress": 0,
            "ram_progress": 0,
            "ia_progress": 0,
            "cpu_progress": 0
        }, f)

if not os.path.exists(LOG_PATH):
    with open(LOG_PATH, 'w') as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sistema: Monitor IA inicializado\n")

def read_status():
    try:
        with open(STATUS_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e), "status": "error"}

def write_status(data):
    try:
        with open(STATUS_PATH, "w") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logging.error(f"Error writing status: {str(e)}")
        return False

def read_console_log(last_n=100):
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, "r", encoding="utf8") as f:
            lines = f.readlines()
            return lines[-last_n:]
    except Exception as e:
        return [f"Error reading log: {str(e)}"]

def write_log(message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    try:
        with open(LOG_PATH, "a", encoding="utf8") as f:
            f.write(f"{timestamp} {message}\n")
        return True
    except Exception as e:
        logging.error(f"Error writing log: {str(e)}")
        return False

def get_real_system_metrics():
    """Obtiene métricas reales del sistema"""
    cpu_usage = psutil.cpu_percent(interval=1)
    virtual_mem = psutil.virtual_memory()
    ram_used_gb = virtual_mem.used / (1024 ** 3)
    ram_total_gb = virtual_mem.total / (1024 ** 3)
    cpu_freq = psutil.cpu_freq()
    cpu_speed = cpu_freq.current / 1000 if cpu_freq else 0
    cpu_temp = 0
    
    # Obtener temperatura de la CPU
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            # Intentar obtener la temperatura del paquete (CPU)
            for name, entries in temps.items():
                for entry in entries:
                    if entry.label in ['Package', 'Tdie', 'Core 0']:
                        cpu_temp = entry.current
                        break
                if cpu_temp > 0:
                    break
        
        # Para Windows
        if cpu_temp == 0 and platform.system() == "Windows":
            try:
                import wmi
                w = wmi.WMI(namespace="root\\wmi")
                temp_info = w.MSAcpi_ThermalZoneTemperature()[0]
                cpu_temp = (temp_info.CurrentTemperature - 2732) / 10.0
            except:
                pass
    except Exception as e:
        logging.error(f"Error obteniendo temperatura: {str(e)}")
        pass

    return {
        "cpu_usage": f"{cpu_usage:.1f}%",
        "ram": f"{ram_used_gb:.1f}/{ram_total_gb:.1f} GB",
        "cpu_speed": f"{cpu_speed:.2f} GHz",
        "cpu_temp": f"{cpu_temp:.0f}°C",
        "threads": f"{psutil.cpu_count(logical=False)}/{psutil.cpu_count(logical=True)}"
    }

def get_xmrig_data():
    """Obtiene datos de minería de la API de XMRig"""
    try:
        # Usamos el token de acceso de la configuración
        params = {"access-token": "zartrux-ia-proxy"}
        response = requests.get(f"{XMRIG_API_URL}/json", params=params)
        
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logging.error(f"Error obteniendo datos de XMRig: {str(e)}")
        return None

def update_mining_status():
    """Actualiza periódicamente el estado de minería con datos reales"""
    while True:
        try:
            status = read_status()
            if status.get('status') == 'running':
                # Actualizar tiempo de minería
                status['uptime_seconds'] += 5
                status['mining_time'] = time.strftime("%H:%M:%S", time.gmtime(status['uptime_seconds']))

                # Insertar datos reales del sistema
                metrics = get_real_system_metrics()
                status.update(metrics)
                
                # Obtener datos de XMRig
                xmrig_data = get_xmrig_data()
                if xmrig_data:
                    # Actualizar con datos del minero
                    hashrate_total = xmrig_data.get('hashrate', {}).get('total', [0])[0]
                    status['hashrate'] = f"{hashrate_total / 1000:.2f}"  # Convertir a KH/s
                    
                    results = xmrig_data.get('results', {})
                    status['shares'] = str(results.get('shares_total', 0))
                    status['accepted_shares'] = results.get('shares_good', 0)
                    status['rejected_shares'] = results.get('shares_total', 0) - results.get('shares_good', 0)
                    
                    # Actualizar datos del bloque actual
                    job = xmrig_data.get('job', {})
                    if job:
                        difficulty = job.get('difficulty', 0)
                        status['difficulty'] = f"{difficulty / 1000000:.2f}"  # Convertir a millones
                        status['block'] = str(job.get('height', '000000'))
                    
                    # Calcular precisión
                    total_shares = status['accepted_shares'] + status['rejected_shares']
                    if total_shares > 0:
                        accuracy = (status['accepted_shares'] / total_shares) * 100
                        status['accuracy'] = f"{accuracy:.1f}"
                        status['hit_rate'] = f"{accuracy:.1f}"
                    
                    # Actualizar barras de progreso
                    status['threads_progress'] = min(100, int(psutil.cpu_percent()))
                    status['ram_progress'] = min(100, int(psutil.virtual_memory().percent))
                    status['cpu_progress'] = min(100, int(psutil.cpu_percent()))

                write_status(status)

            time.sleep(5)
        except Exception as e:
            logging.error(f"Error in status update loop: {str(e)}")
            time.sleep(10)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    return jsonify(read_status())

@app.route("/api/console")
def api_console():
    log = read_console_log(150)
    return jsonify({"log": log})

@app.route("/api/start_mining", methods=["POST"])
def start_mining():
    data = request.get_json()
    wallet = data.get("wallet", "4xxxxxxxx")
    pool = data.get("pool", "pool.hashvault.pro:80")
    
    status = read_status()
    # Se actualiza el estado, asegurando reiniciar los contadores
    status.update({
        "status": "running",
        "wallet_address": wallet,
        "pool_url": pool,
        "start_time": datetime.now().isoformat(),
        "uptime_seconds": 0,  # <--- Este reinicio es la clave
        "accepted_shares": 0,
        "rejected_shares": 0
    })
    
    write_status(status)
    write_log(f"Sistema: Iniciando minería IA con wallet {wallet} en pool {pool}")
    
    socketio.emit('status_update', status)
    return jsonify({"result": "ok", "message": "Minería IA iniciada"})

@app.route("/api/stop_mining", methods=["POST"])
def stop_mining():
    status = read_status()
    status["status"] = "stopped"
    write_status(status)
    write_log("Sistema: Minería IA detenida")
    socketio.emit('status_update', status)
    return jsonify({"result": "ok", "message": "Minería IA detenida"})

@app.route("/api/set_mode", methods=["POST"])
def set_mode():
    data = request.get_json()
    mode = data.get("mode", "IA").upper()
    status = read_status()
    status["mining_mode"] = mode
    write_status(status)
    write_log(f"Sistema: Modo de minería cambiado a {mode}")
    socketio.emit('mode_changed', {"mode": mode})
    return jsonify({"result": "ok", "mode": mode})

@socketio.on('request_status')
def send_status_event():
    status = read_status()
    emit('status_update', status)

@socketio.on('request_console')
def send_console_event():
    log = read_console_log()
    emit('console_update', {"log": log})

def push_status_loop():
    last_status = {}
    while True:
        try:
            status = read_status()
            if status != last_status:
                socketio.emit('status_update', status)
                last_status = status
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error in status push loop: {str(e)}")
            time.sleep(5)

def push_console_loop():
    last_log = []
    while True:
        try:
            log = read_console_log()
            if log != last_log:
                socketio.emit('console_update', {"log": log})
                last_log = log
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error in console push loop: {str(e)}")
            time.sleep(5)

def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(BASE_DIR, "monitor.log")),
            logging.StreamHandler()
        ]
    )
    
    threading.Thread(target=update_mining_status, daemon=True).start()
    threading.Thread(target=push_status_loop, daemon=True).start()
    threading.Thread(target=push_console_loop, daemon=True).start()
    threading.Thread(target=open_browser, daemon=True).start()
    
    write_log("Monitor IA: Servidor iniciado")
    socketio.run(app, host="127.0.0.1", port=5000, debug=False)
