"""fake-Sota: UDP を待ち受け、届いた JSON（Head_* パルス）を表示するモニタ。

実機 Sota の代わりに「アプリが何を送っているか」を目視するための道具。
all-local/subscribe の出力確認や、poke の動作確認（loopback）に使う。

例:
    python scripts/sota_listen.py                 # 0.0.0.0:9980 で待受
    python scripts/sota_listen.py --port 9980
    # 別ターミナルで: SOTA_IP=127.0.0.1 python scripts/sota_poke.py --sweep
"""

import argparse
import json
import os
import socket
import time

DEFAULT_PORT = int(os.environ.get("SOTA_PORT", 9980))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sota 宛 UDP を表示する fake-Sota モニタ")
    parser.add_argument("--host", default="0.0.0.0", help="待受アドレス（既定 0.0.0.0）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"待受ポート（既定 {DEFAULT_PORT}）")
    args = parser.parse_args(argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    print(f"[listen] {args.host}:{args.port} で待受中（Ctrl+C で終了）", flush=True)
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            ts = time.strftime("%H:%M:%S")
            try:
                msg = json.loads(data.decode("utf-8"))
                fields = " ".join(f"{k}={v}" for k, v in msg.items())
                print(f"[{ts}] {addr[0]}:{addr[1]}  {fields}", flush=True)
            except (ValueError, UnicodeDecodeError):
                print(f"[{ts}] {addr[0]}:{addr[1]}  <非JSON {len(data)}B> {data[:60]!r}", flush=True)
    except KeyboardInterrupt:
        print("\n[listen] 終了します。")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
