"""targeter の単体テスト（クランプ・EMA・デッドバンド・Head_R）。

校正係数の実値はテスト対象外。ロジック（範囲を守る / 式どおり / 微小変化を無視）を検証する。
"""

import pytest

from sota.targeter import (
    HEAD_P_LIMIT,
    HEAD_Y_LIMIT,
    WAIST_Y_LIMIT,
    Calibration,
    Smoother,
    camera_to_robot,
    split_yaw,
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


def test_yaw_sign_flips_direction():
    right = camera_to_robot(10, 0, pulse_per_deg_yaw=2.0, yaw_sign=1.0)[0]
    left = camera_to_robot(10, 0, pulse_per_deg_yaw=2.0, yaw_sign=-1.0)[0]
    assert right == 20 and left == -20


# --- Calibration: .env ロード / to_robot -------------------------------------

def test_calibration_defaults_match_camera_to_robot():
    calib = Calibration()  # waist 無効 → 頭部 3 値は camera_to_robot と一致、waist は None
    head_y, head_p, head_r, waist_y = calib.to_robot(10.0, 5.0)
    assert (head_y, head_p, head_r) == camera_to_robot(10.0, 5.0)
    assert waist_y is None


def test_calibration_from_env_overrides(monkeypatch):
    monkeypatch.setenv("SOTA_YAW_SIGN", "-1")
    monkeypatch.setenv("SOTA_PULSE_PER_DEG_YAW", "2.0")
    monkeypatch.setenv("SOTA_INOUT_MIN", "0.5")
    monkeypatch.setenv("SOTA_EMA_ALPHA", "0.25")
    calib = Calibration.from_env()
    assert calib.yaw_sign == -1.0 and calib.pulse_per_deg_yaw == 2.0
    assert calib.inout_min == 0.5 and calib.ema_alpha == 0.25
    # yaw=10, sign=-1, gain=2 → -20
    assert calib.to_robot(10.0, 0.0)[0] == -20


def test_calibration_from_env_ignores_invalid(monkeypatch):
    monkeypatch.setenv("SOTA_YAW_SIGN", "")          # 空
    monkeypatch.setenv("SOTA_PITCH_SIGN", "abc")     # 不正
    calib = Calibration.from_env()
    assert calib.yaw_sign == 1.0 and calib.pitch_sign == 1.0  # 既定にフォールバック


def test_calibration_make_smoother_uses_params():
    calib = Calibration(ema_alpha=0.9, deadband_deg=3.0)
    s = calib.make_smoother()
    assert s.alpha == 0.9 and s.deadband_deg == 3.0


# --- 360°: split_yaw（頭＋腰の分配）-----------------------------------------

def test_split_yaw_head_only_within_range():
    # |theta| <= head_max → 頭だけ、腰 0。
    assert split_yaw(50.0, head_yaw_max_deg=80.0, waist_yaw_max_deg=120.0) == (50.0, 0.0)


def test_split_yaw_overflow_to_waist():
    # theta=120, head_max=80 → 頭 80 / 腰 40。
    assert split_yaw(120.0, head_yaw_max_deg=80.0, waist_yaw_max_deg=120.0) == (80.0, 40.0)


def test_split_yaw_waist_clamps():
    # theta=300, head_max=80, waist_max=120 → 頭 80 / 腰 120（超過は端で頭打ち）。
    assert split_yaw(300.0, head_yaw_max_deg=80.0, waist_yaw_max_deg=120.0) == (80.0, 120.0)


def test_split_yaw_symmetric_negative():
    assert split_yaw(-120.0, head_yaw_max_deg=80.0, waist_yaw_max_deg=120.0) == (-80.0, -40.0)


# --- 360°: Calibration.to_robot（4-tuple / waist）--------------------------

def test_to_robot_returns_four_with_none_waist_when_disabled():
    head_y, head_p, head_r, waist_y = Calibration().to_robot(10.0, 5.0)
    assert waist_y is None
    assert (head_y, head_p, head_r) == camera_to_robot(10.0, 5.0)


def test_to_robot_splits_when_enabled():
    calib = Calibration(
        waist_enabled=True, head_yaw_max_deg=80.0, waist_yaw_max_deg=120.0,
        pulse_per_deg_yaw=10.0, pulse_per_deg_waist=8.0,
    )
    head_y, head_p, head_r, waist_y = calib.to_robot(120.0, 0.0)
    # theta=120 → head_deg 80*10=800, waist_deg 40*8=320。
    assert head_y == 800 and waist_y == 320 and head_r == 0


def test_to_robot_waist_within_limit():
    calib = Calibration(waist_enabled=True, pulse_per_deg_waist=1000.0)  # 過大係数でも端で止まる
    _, _, _, waist_y = calib.to_robot(170.0, 0.0)
    assert WAIST_Y_LIMIT[0] <= waist_y <= WAIST_Y_LIMIT[1]


def test_from_env_reads_waist(monkeypatch):
    monkeypatch.setenv("SOTA_WAIST_ENABLED", "1")
    monkeypatch.setenv("SOTA_PULSE_PER_DEG_WAIST", "9.0")
    monkeypatch.setenv("SOTA_HEAD_YAW_MAX_DEG", "70")
    calib = Calibration.from_env()
    assert calib.waist_enabled is True
    assert calib.pulse_per_deg_waist == 9.0 and calib.head_yaw_max_deg == 70.0


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
