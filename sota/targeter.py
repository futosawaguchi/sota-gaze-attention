"""カメラ視線（度）→ Sota サーボパルス値への変換と平滑化。

gaze360 が出す視線方位（THETA カメラ座標系・度、yaw 正=右 / pitch 正=上）を
Sota のサーボパルス値（Head_Y / Head_P / Head_R）へ変換する。

- ``camera_to_robot``: 取付オフセット加算 → 度×係数（パルス化）→ 可動域クランプ → Head_R=0。
- ``Smoother``: EMA ＋ デッドバンドで首のガタつきを抑える（gaze360 側に平滑化は無い）。

**係数・オフセット・pitch 符号は要実機校正（SOTA_HANDOVER §9）のプレースホルダ。**
ここで保証するのは「クランプ・EMA・デッドバンドのロジック」だけ。校正値の実数は別途確定する。
"""

import os
from dataclasses import dataclass

# --- Sota 可動域（パルス値, SOTA_HANDOVER §5）------------------------------
HEAD_Y_LIMIT = (-1400, 1400)
HEAD_P_LIMIT = (-290, 110)

# --- 校正プレースホルダ（要実機校正 §9。実値は .env で上書き）---------------
# 取付オフセット: THETA 前方(yaw=0) と Sota 正面の差（度）。校正前は 0。
YAW_OFFSET_DEG = 0.0
PITCH_OFFSET_DEG = 0.0
# 度→パルス係数（1 度あたりのパルス値）。暫定の仮定:
#   Head_Y ±1400 ↔ ±90°、Head_P +110 ↔ +30°。実測で確定する。
PULSE_PER_DEG_YAW = 1400.0 / 90.0
PULSE_PER_DEG_PITCH = 110.0 / 30.0
# 符号: gaze は yaw 正=右 / pitch 正=上。Sota 側の対応は校正で確認（反転なら -1）。
YAW_SIGN = 1.0
PITCH_SIGN = 1.0
# 平滑化・ゲートの既定。
EMA_ALPHA = 0.4
DEADBAND_DEG = 2.0
INOUT_MIN = 0.3        # 視線がフレーム内にある確率の下限（これ未満は送らない）


def _clamp(value, limit):
    lo, hi = limit
    return max(lo, min(hi, value))


def camera_to_robot(
    gaze_yaw,
    gaze_pitch,
    yaw_offset=YAW_OFFSET_DEG,
    pitch_offset=PITCH_OFFSET_DEG,
    pulse_per_deg_yaw=PULSE_PER_DEG_YAW,
    pulse_per_deg_pitch=PULSE_PER_DEG_PITCH,
    yaw_sign=YAW_SIGN,
    pitch_sign=PITCH_SIGN,
):
    """視線方位（度）→ (Head_Y, Head_P, Head_R) パルス値（int）。

    1. 取付オフセットを加算（カメラ前方と Sota 正面の差を吸収）。
    2. 度 → パルス（係数を掛ける）。yaw/pitch は符号補正（反転時 -1）。
    3. Sota 可動域にクランプ。Head_R は 0 固定。
    """
    yaw_pulse = (gaze_yaw + yaw_offset) * pulse_per_deg_yaw * yaw_sign
    pitch_pulse = (gaze_pitch + pitch_offset) * pulse_per_deg_pitch * pitch_sign
    head_y = _clamp(round(yaw_pulse), HEAD_Y_LIMIT)
    head_p = _clamp(round(pitch_pulse), HEAD_P_LIMIT)
    head_r = 0
    return head_y, head_p, head_r


class Smoother:
    """EMA ＋ デッドバンドで (yaw, pitch) を度の領域で平滑化する。

    - EMA: ``out = alpha*new + (1-alpha)*prev``（alpha 小=滑らか/遅い, 大=機敏/揺れる）。
    - デッドバンド: 新しい生値が前回出力から両軸とも ±deadband 未満なら前回出力を維持
      （微小ノイズでの首の揺れを防ぐ）。
    """

    def __init__(self, alpha=0.4, deadband_deg=2.0):
        self.alpha = alpha
        self.deadband_deg = deadband_deg
        self._yaw = None
        self._pitch = None

    def update(self, gaze_yaw, gaze_pitch):
        """新しい観測を取り込み、平滑化後の (yaw, pitch) を返す。"""
        if self._yaw is None:
            self._yaw, self._pitch = gaze_yaw, gaze_pitch
            return self._yaw, self._pitch

        within_deadband = (
            abs(gaze_yaw - self._yaw) < self.deadband_deg
            and abs(gaze_pitch - self._pitch) < self.deadband_deg
        )
        if within_deadband:
            return self._yaw, self._pitch

        self._yaw = self.alpha * gaze_yaw + (1.0 - self.alpha) * self._yaw
        self._pitch = self.alpha * gaze_pitch + (1.0 - self.alpha) * self._pitch
        return self._yaw, self._pitch

    def reset(self):
        self._yaw = None
        self._pitch = None


def _envf(key, default):
    """環境変数を float で読む。未設定/空/不正なら default。"""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Calibration:
    """校正パラメータ一式（既定=プレースホルダ）。実値は ``.env`` から上書きする。

    実機でズレた時は **コードでなく .env を編集**して直す（docs/calibration.md の症状→対応表）。
    """

    yaw_offset_deg: float = YAW_OFFSET_DEG
    pitch_offset_deg: float = PITCH_OFFSET_DEG
    pulse_per_deg_yaw: float = PULSE_PER_DEG_YAW
    pulse_per_deg_pitch: float = PULSE_PER_DEG_PITCH
    yaw_sign: float = YAW_SIGN
    pitch_sign: float = PITCH_SIGN
    ema_alpha: float = EMA_ALPHA
    deadband_deg: float = DEADBAND_DEG
    inout_min: float = INOUT_MIN

    @classmethod
    def from_env(cls):
        """``SOTA_*`` 環境変数から校正を構築（未設定は既定）。"""
        return cls(
            yaw_offset_deg=_envf("SOTA_YAW_OFFSET_DEG", YAW_OFFSET_DEG),
            pitch_offset_deg=_envf("SOTA_PITCH_OFFSET_DEG", PITCH_OFFSET_DEG),
            pulse_per_deg_yaw=_envf("SOTA_PULSE_PER_DEG_YAW", PULSE_PER_DEG_YAW),
            pulse_per_deg_pitch=_envf("SOTA_PULSE_PER_DEG_PITCH", PULSE_PER_DEG_PITCH),
            yaw_sign=_envf("SOTA_YAW_SIGN", YAW_SIGN),
            pitch_sign=_envf("SOTA_PITCH_SIGN", PITCH_SIGN),
            ema_alpha=_envf("SOTA_EMA_ALPHA", EMA_ALPHA),
            deadband_deg=_envf("SOTA_DEADBAND_DEG", DEADBAND_DEG),
            inout_min=_envf("SOTA_INOUT_MIN", INOUT_MIN),
        )

    def to_robot(self, gaze_yaw, gaze_pitch):
        """この校正で視線（度）→ (Head_Y, Head_P, Head_R) パルス値。"""
        return camera_to_robot(
            gaze_yaw,
            gaze_pitch,
            yaw_offset=self.yaw_offset_deg,
            pitch_offset=self.pitch_offset_deg,
            pulse_per_deg_yaw=self.pulse_per_deg_yaw,
            pulse_per_deg_pitch=self.pulse_per_deg_pitch,
            yaw_sign=self.yaw_sign,
            pitch_sign=self.pitch_sign,
        )

    def make_smoother(self):
        """この校正の EMA/デッドバンドで Smoother を生成。"""
        return Smoother(alpha=self.ema_alpha, deadband_deg=self.deadband_deg)
