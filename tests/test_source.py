"""sota/source.py のテスト。

- parse_line: wire 形式（行区切り JSON 配列）の復元（torch 不要・決定的）。
- subscribe: ミニ TCP サーバ相手のラウンドトリップ（torch 不要）。
- 相互運用: gaze360 の実 GazeResultPublisher と疎通（torch がある時だけ実行）。
"""

import json
import os
import socket
import sys
import threading

import pytest

from sota.source import parse_line, subscribe

_FULL = {
    "person_id": 1, "gaze_yaw": 12.3, "gaze_pitch": -4.5,
    "inout": 0.81, "confidence": 0.92, "head_yaw": 11.0, "head_pitch": 2.0,
}


# --- parse_line --------------------------------------------------------------

def test_parse_line_empty_array():
    assert parse_line("[]") == []


def test_parse_line_blank_is_empty():
    assert parse_line("   \n") == []


def test_parse_line_normal():
    rs = parse_line(json.dumps([_FULL, {**_FULL, "person_id": 2, "confidence": 0.5}]))
    assert len(rs) == 2
    assert rs[0].person_id == 1 and abs(rs[0].gaze_yaw - 12.3) < 1e-9
    assert rs[1].person_id == 2


def test_parse_line_ignores_unknown_and_missing_optional():
    obj = {k: _FULL[k] for k in ("person_id", "gaze_yaw", "gaze_pitch", "inout", "confidence")}
    obj["future_field"] = 999  # 契約はフィールド追加可
    rs = parse_line(json.dumps([obj]))
    assert rs[0].head_yaw is None and rs[0].head_pitch is None
    assert not hasattr(rs[0], "future_field")


# --- subscribe round-trip（ミニ TCP サーバ）---------------------------------

def _serve_lines(lines):
    """127.0.0.1 の空きポートで listen し、接続が来たら lines を送って閉じる。port を返す。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        try:
            conn, _ = srv.accept()
            with conn:
                for ln in lines:
                    conn.sendall(ln.encode("utf-8"))
        finally:
            srv.close()

    threading.Thread(target=run, daemon=True).start()
    return port


def test_subscribe_roundtrip():
    frames = [json.dumps([_FULL]) + "\n", json.dumps([]) + "\n"]
    port = _serve_lines(frames)
    got = []
    subscribe("127.0.0.1", port, got.append, reconnect=False, max_frames=2)
    assert len(got) == 2
    assert got[0][0].person_id == 1 and abs(got[0][0].gaze_pitch + 4.5) < 1e-9
    assert got[1] == []


# --- gaze360 実 publisher との相互運用（torch がある時だけ）------------------

def test_interop_with_real_publisher():
    pytest.importorskip("torch")  # publisher の import は src/gaze/__init__ 経由で torch を要する
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gaze360"))
    from src.gaze.result import GazeResult as GR
    from src.gaze.publisher import GazeResultPublisher

    pub = GazeResultPublisher(0)  # 0 = 空きポート
    pub.start()
    try:
        port = pub._server.getsockname()[1]
        pub.publish([GR(person_id=1, gaze_yaw=5.0, gaze_pitch=1.0, inout=0.9, confidence=0.8)])
        got = []
        subscribe("127.0.0.1", port, got.append, reconnect=False, max_frames=1)
        assert got and got[0][0].person_id == 1 and abs(got[0][0].gaze_yaw - 5.0) < 1e-9
    finally:
        pub.stop()
