import socket
import threading
import json
import logging

HOST = '0.0.0.0'
PORT = 3333

def get_fake_job():
    return {
        "job_id": "1a2b3c4d",
        "blob": "0606f7cf80f705011de4fa86a4a7...0000000000000000000000000000",
        "target": "80000000",
        "algo": "rx/0",
        "height": 3500000
    }

def handle_client(conn, addr):
    logging.info(f'Nuevo minero conectado: {addr}')
    buffer = b''
    while True:
        try:
            data = conn.recv(4096)
            if not data:
                break
            buffer += data
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line:
                    continue
                msg = json.loads(line.decode())
                method = msg.get('method')
                _id = msg.get('id', 0)
                if method == "login":
                    # Devuelve siempre un trabajo válido
                    resp = {
                        "id": _id,
                        "jsonrpc": "2.0",
                        "result": {
                            "id": "IA-Zar-session",
                            "job": get_fake_job(),
                            "status": "OK"
                        }
                    }
                    conn.sendall((json.dumps(resp) + "\n").encode())
                elif method == "keepalived":
                    resp = {
                        "id": _id,
                        "jsonrpc": "2.0",
                        "result": {"status": "OK"}
                    }
                    conn.sendall((json.dumps(resp) + "\n").encode())
                elif method == "submit":
                    # Aquí puedes loggear el nonce recibido para debug
                    print("Share recibido:", msg)
                    resp = {
                        "id": _id,
                        "jsonrpc": "2.0",
                        "result": {"status": "OK"}
                    }
                    conn.sendall((json.dumps(resp) + "\n").encode())
                else:
                    resp = {
                        "id": _id,
                        "jsonrpc": "2.0",
                        "error": {"code": -1, "message": f"Unsupported method {method}"}
                    }
                    conn.sendall((json.dumps(resp) + "\n").encode())
        except Exception as e:
            logging.warning(f"Error en sesión con {addr}: {e}")
            break
    conn.close()
    logging.info(f'Conexión cerrada: {addr}')

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        logging.info(f'Stratum IA-Zar escuchando en {HOST}:{PORT}')
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
