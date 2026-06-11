"""SotaSender のループバック検証（Sota 実機不要）。

localhost に UDP 受信ソケットを立て、SotaSender が送った 1 フレームを受信し、
JSON のキー・型・可動域を確認する。
"""

import json
import socket

from sota.sender import SotaSender

# Sota 可動域（SOTA_HANDOVER §5 / CLAUDE.md）。送信値がこの範囲内であることを確認する。
LIMITS = {"Head_Y": (-1400, 1400), "Head_P": (-290, 110), "Head_R": (-300, 350)}


def _recv_one(head_y, head_p, head_r=0, waist_y=None):
    """受信ソケットを立てて 1 フレーム送受信し、復元した dict を返す。"""
    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.bind(("127.0.0.1", 0))  # 任意の空きポート
    recv.settimeout(2.0)
    try:
        _, port = recv.getsockname()
        with SotaSender(host="127.0.0.1", port=port) as sender:
            sent = sender.send(head_y, head_p, head_r, waist_y=waist_y)
        data, _ = recv.recvfrom(4096)
        return sent, json.loads(data.decode("utf-8"))
    finally:
        recv.close()


def test_keys_and_types():
    sent, got = _recv_one(120, -30, 0)
    assert set(got.keys()) == {"Head_Y", "Head_P", "Head_R"}
    assert all(isinstance(v, int) for v in got.values())
    assert got == sent  # 送信値と受信値が一致


def test_float_inputs_are_cast_to_int():
    _, got = _recv_one(12.7, -4.2, 0.0)
    assert got["Head_Y"] == 12 and got["Head_P"] == -4 and got["Head_R"] == 0


def test_head_r_defaults_to_zero():
    _, got = _recv_one(0, 0)
    assert got["Head_R"] == 0


def test_values_within_limits():
    _, got = _recv_one(1400, -290, 0)
    for key in ("Head_Y", "Head_P", "Head_R"):
        lo, hi = LIMITS[key]
        assert lo <= got[key] <= hi


def test_waist_y_omitted_by_default():
    _, got = _recv_one(0, 0)
    assert "Waist_Y" not in got  # 既定は wire 不変（頭のみ）


def test_waist_y_included_when_given():
    _, got = _recv_one(0, 0, waist_y=300.7)
    assert got["Waist_Y"] == 300 and isinstance(got["Waist_Y"], int)
