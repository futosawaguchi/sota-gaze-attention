"""targeter の単体テスト（クランプ・EMA・デッドバンド・Head_R）。

校正係数の実値はテスト対象外。ロジック（範囲を守る / 式どおり / 微小変化を無視）を検証する。
"""

import pytest

from sota.targeter import (
    HEAD_P_LIMIT,
    HEAD_Y_LIMIT,
    Smoother,
    camera_to_robot,
)


# --- camera_to_robot: クランプ / Head_R --------------------------------------

@pytest.mark.parametrize("gaze_yaw", [-180, -90, -1, 0, 1, 45, 90, 180])
@pytest.mark.parametrize("gaze_pitch", [-90, -45, 0, 45, 90])
def test_outputs_within_limits_over_domain(gaze_yaw, gaze_pitch):
    head_y, head_p, head_r = camera_to_robot(gaze_yaw, gaze_pitch)
    assert HEAD_Y_LIMIT[0] <= head_y <= HEAD_Y_LIMIT[1]
    assert HEAD_P_LIMIT[0] <= head_p <= HEAD_P_LIMIT[1]
    assert head_r == 0


def test_extreme_yaw_clamps_to_limit():
    # 大きな係数でも可動域端で頭打ちになる。
    assert camera_to_robot(180, 0, pulse_per_deg_yaw=100.0)[0] == HEAD_Y_LIMIT[1]
    assert camera_to_robot(-180, 0, pulse_per_deg_yaw=100.0)[0] == HEAD_Y_LIMIT[0]


def test_extreme_pitch_clamps_to_limit():
    assert camera_to_robot(0, 90, pulse_per_deg_pitch=100.0)[1] == HEAD_P_LIMIT[1]
    assert camera_to_robot(0, -90, pulse_per_deg_pitch=100.0)[1] == HEAD_P_LIMIT[0]


def test_returns_integers():
    head_y, head_p, head_r = camera_to_robot(12.3, -4.5)
    assert all(isinstance(v, int) for v in (head_y, head_p, head_r))


# --- camera_to_robot: オフセット / 符号 / 係数 -------------------------------

def test_yaw_offset_is_added_in_degrees():
    # オフセット 10°、係数 2.0 → (0+10)*2 = 20 パルス。
    assert camera_to_robot(0, 0, yaw_offset=10.0, pulse_per_deg_yaw=2.0)[0] == 20


def test_pitch_sign_flips_direction():
    up = camera_to_robot(0, 10, pulse_per_deg_pitch=2.0, pitch_sign=1.0)[1]
    down = camera_to_robot(0, 10, pulse_per_deg_pitch=2.0, pitch_sign=-1.0)[1]
    assert up == 20 and down == -20


# --- Smoother: EMA -----------------------------------------------------------

def test_first_update_returns_raw():
    s = Smoother(alpha=0.5, deadband_deg=0.0)
    assert s.update(10.0, -4.0) == (10.0, -4.0)


def test_ema_formula():
    s = Smoother(alpha=0.5, deadband_deg=0.0)
    s.update(0.0, 0.0)
    # out = 0.5*new + 0.5*prev = 0.5*10 + 0.5*0 = 5
    assert s.update(10.0, 20.0) == (5.0, 10.0)
    # 次フレーム: 0.5*10 + 0.5*5 = 7.5 / 0.5*20 + 0.5*10 = 15
    assert s.update(10.0, 20.0) == (7.5, 15.0)


# --- Smoother: デッドバンド --------------------------------------------------

def test_deadband_holds_small_change():
    s = Smoother(alpha=1.0, deadband_deg=2.0)
    s.update(0.0, 0.0)
    # 両軸とも ±2° 未満 → 前回出力を維持
    assert s.update(1.5, -1.5) == (0.0, 0.0)


def test_deadband_passes_large_change():
    s = Smoother(alpha=1.0, deadband_deg=2.0)
    s.update(0.0, 0.0)
    # yaw が 2° 以上動いた → 更新（alpha=1 なので生値に追従）
    assert s.update(5.0, 0.0) == (5.0, 0.0)
