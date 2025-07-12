from flask import Flask, jsonify, render_template
import psutil
import time
import threading
import socket
from datetime import datetime

app = Flask(__name__)

# Estado del minero
miner_status = {
    "hashrate": 0,
    "accepted_shares": 0,
    "rejected_shares": 0,
    "cpu_usage": 0,
    "cpu_temp": 0,
    "threads": 0,
    "current_pool": "",
    "last_share": None,
    "alerts": []
}

def get_cpu_temperature():
    try:
        if os.name == 'nt':
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            return w.MSAcpi_ThermalZoneTemperature()[0].CurrentTemperature / 10 - 273.15
        else:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return int(f.read().strip()) / 1000
    except Exception:
        return 60

def update_metrics():
    global miner_status
    while True:
        # Actualizar métricas
        miner_status['cpu_usage'] = psutil.cpu_percent(interval=1)
        miner_status['cpu_temp'] = get_cpu_temperature()
        
        # Comprobar alertas
        if miner_status['cpu_temp'] > 85:
            miner_status['alerts'].append({
                "type": "critical",
                "message": f"High CPU temperature: {miner_status['cpu_temp']}°C",
                "timestamp": datetime.now().isoformat()
            })
        
        time.sleep(5)

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/metrics')
def metrics():
    return jsonify(miner_status)

@app.route('/api/pools')
def pools():
    return jsonify([
        {"name": "Pool 1", "url": "stratum+tcp://pool1.com:3333", "active": True},
        {"name": "Pool 2", "url": "stratum+tcp://pool2.com:5555", "active": False}
    ])

@app.route('/api/alerts')
def alerts():
    return jsonify(miner_status['alerts'])

@app.route('/api/performance')
def performance():
    return jsonify({
        "hashrate": miner_status['hashrate'],
        "shares": {
            "accepted": miner_status['accepted_shares'],
            "rejected": miner_status['rejected_shares']
        }
    })

if __name__ == '__main__':
    # Iniciar hilo de actualización de métricas
    threading.Thread(target=update_metrics, daemon=True).start()
    
    # Obtener IP local para acceso en red
    host = socket.gethostbyname(socket.gethostname())
    print(f"Monitor running at http://{host}:5000")
    
    app.run(host='0.0.0.0', port=5000)