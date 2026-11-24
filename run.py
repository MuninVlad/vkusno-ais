"""Запуск сервера по HTTPS (TLS 1.2+).

    python run.py                 — https://localhost:8443
    python run.py --port 9443
"""
import argparse
import ssl

from werkzeug.serving import WSGIRequestHandler, make_server

from app import config, create_app
from gen_cert import generate
import init_db


def tls_context():
    cert, key = generate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2          # TLS 1.0/1.1 запрещены
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


class Handler(WSGIRequestHandler):
    timeout = 30            # «зависшее» соединение закрывается через 30 с и не занимает поток


def make_https_server(app, host="127.0.0.1", port=8443, ctx=None):
    """Многопоточный HTTPS-сервер. TLS-рукопожатие выполняется в потоке соединения,
    а не в главном потоке (иначе параллельные подключения браузера сбрасываются)."""
    ctx = ctx or tls_context()
    srv = make_server(host, port, app, threaded=True, request_handler=Handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
    srv.ssl_context = ctx
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8443)
    args = ap.parse_args()
    if not config.DB_PATH.exists():
        init_db.main()
    srv = make_https_server(create_app(), args.host, args.port)
    print(f"АИС «Вкусно и быстро»: https://localhost:{args.port}  (Ctrl+C — остановить)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
