"""app.py の配線テスト（ハード・gaze360 依存なし）。

make_handler が select_primary→inout ゲート→targeter→sender を正しく繋ぐかを、
スタブ（偽の GazeResult / select_primary / sender）で確認する。
"""

from types import SimpleNamespace

import pytest

from app import _parse_hostport, make_handler
from sota.targeter import Calibration, Smoother


class _FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, head_y, head_p, head_r=0, waist_y=None):
        msg = {"Head_Y": head_y, "Head_P": head_p, "Head_R": head_r}
        if waist_y is not None:
            msg["Waist_Y"] = waist_y
        self.sent.append(msg)
        return msg


def _gaze(yaw, pitch, inout):
    return SimpleNamespace(gaze_yaw=yaw, gaze_pitch=pitch, inout=inout, confidence=0.9)


def test_parse_hostport():
    assert _parse_hostport("localhost:8090") == ("localhost", 8090)
    assert _parse_hostport("10.0.0.5:9000") == ("10.0.0.5", 9000)


def test_parse_hostport_requires_port():
    with pytest.raises(ValueError):
        _parse_hostport("localhost")


def test_no_send_when_no_primary():
    sender = _FakeSender()
    handle = make_handler(sender, Smoother(), lambda r: None, Calibration(), verbose=False)
    handle([])
    assert sender.sent == []


def test_no_send_when_inout_below_threshold():
    sender = _FakeSender()
    calib = Calibration()
    low = _gaze(10.0, 0.0, calib.inout_min - 0.01)
    handle = make_handler(sender, Smoother(), lambda r: low, calib, verbose=False)
    handle([low])
    assert sender.sent == []


def test_sends_clamped_pulses_when_gated():
    sender = _FakeSender()
    calib = Calibration()  # waist 無効（既定）
    g = _gaze(10.0, 5.0, 0.9)
    smoother = Smoother(deadband_deg=0.0)  # 平滑化の保留を避ける
    handle = make_handler(sender, smoother, lambda r: g, calib, verbose=False)
    handle([g])
    assert len(sender.sent) == 1
    # 初回 Smoother は生値を返す → calib.to_robot(10,5) と一致するはず。
    head_y, head_p, head_r, waist_y = calib.to_robot(10.0, 5.0)
    assert waist_y is None  # waist 無効 → Waist_Y は送らない
    assert sender.sent[0] == {"Head_Y": head_y, "Head_P": head_p, "Head_R": head_r}


def test_forwards_waist_when_enabled():
    sender = _FakeSender()
    # 頭の可動域(80°)を超える方位 → 腰が補う。
    calib = Calibration(waist_enabled=True, head_yaw_max_deg=80.0)
    g = _gaze(120.0, 0.0, 0.9)
    handle = make_handler(sender, Smoother(deadband_deg=0.0), lambda r: g, calib, verbose=False)
    handle([g])
    assert "Waist_Y" in sender.sent[0] and sender.sent[0]["Waist_Y"] != 0
