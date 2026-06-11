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

# --- Sota 可動域（パルス値, SOTA_HANDOVER §5 / SotaController.java）---------
HEAD_Y_LIMIT = (-1400, 1400)
HEAD_P_LIMIT = (-290, 110)
WAIST_Y_LIMIT = (-1200, 1200)   # 腰ヨー（体ごとの回転）。360° 化で頭の超過分を補う。

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
# --- 360° 化（頭＋腰の方位分配）。既定は無効（頭のみ＝従来挙動・wire 不変）---
WAIST_ENABLED = False
PULSE_PER_DEG_WAIST = 1200.0 / 120.0   # 暫定: 腰 ±1200 ↔ ±120°。実測で確定。
HEAD_YAW_MAX_DEG = 80.0                 # 頭が担う最大ヨー（度）。超過分は腰へ。
WAIST_YAW_MAX_DEG = 120.0               # 腰が担う最大ヨー（度）。
WAIST_SIGN = 1.0                        # 腰の回転符号（反転なら -1）。


def _clamp(value, limit):
    lo, hi = limit
    return max(lo, min(hi, value))


def split_yaw(theta_deg, head_yaw_max_deg=HEAD_YAW_MAX_DEG, waist_yaw_max_deg=WAIST_YAW_MAX_DEG):
    """目標ヨー（度）を頭優先で (head_deg, waist_deg) に分配する。

    頭が可動域内（±head_yaw_max_deg）まで担い、超過分を腰（±waist_yaw_max_deg）が補う。
    小角度は頭だけ（waist=0）＝自然。大角度で体ごと向き直る。届かない分は端で頭打ち。
    """
    head_deg = _clamp(theta_deg, (-head_yaw_max_deg, head_yaw_max_deg))
    waist_deg = _clamp(theta_deg - head_deg, (-waist_yaw_max_deg, waist_yaw_max_deg))
    return head_deg, waist_deg


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


def _envb(key, default):
    """環境変数を bool で読む（1/true/yes/on=真）。未設定/空は default。"""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


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
    # 360° 化（頭＋腰）。既定は無効＝頭のみ（従来挙動・wire 不変）。
    waist_enabled: bool = WAIST_ENABLED
    pulse_per_deg_waist: float = PULSE_PER_DEG_WAIST
    head_yaw_max_deg: float = HEAD_YAW_MAX_DEG
    waist_yaw_max_deg: float = WAIST_YAW_MAX_DEG
    waist_sign: float = WAIST_SIGN

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
            waist_enabled=_envb("SOTA_WAIST_ENABLED", WAIST_ENABLED),
            pulse_per_deg_waist=_envf("SOTA_PULSE_PER_DEG_WAIST", PULSE_PER_DEG_WAIST),
            head_yaw_max_deg=_envf("SOTA_HEAD_YAW_MAX_DEG", HEAD_YAW_MAX_DEG),
            waist_yaw_max_deg=_envf("SOTA_WAIST_YAW_MAX_DEG", WAIST_YAW_MAX_DEG),
            waist_sign=_envf("SOTA_WAIST_SIGN", WAIST_SIGN),
        )

    def to_robot(self, gaze_yaw, gaze_pitch):
        """この校正で視線（度）→ (Head_Y, Head_P, Head_R, Waist_Y) パルス値。

        waist 無効時は ``Waist_Y=None``（頭のみ・送信時に Waist_Y キーを含めない）。
        有効時は目標ヨーを頭優先で分配し、頭の超過分を腰が補う（360° 化）。
        """
        if not self.waist_enabled:
            head_y, head_p, head_r = camera_to_robot(
                gaze_yaw,
                gaze_pitch,
                yaw_offset=self.yaw_offset_deg,
                pitch_offset=self.pitch_offset_deg,
                pulse_per_deg_yaw=self.pulse_per_deg_yaw,
                pulse_per_deg_pitch=self.pulse_per_deg_pitch,
                yaw_sign=self.yaw_sign,
                pitch_sign=self.pitch_sign,
            )
            return head_y, head_p, head_r, None

        theta = (gaze_yaw + self.yaw_offset_deg) * self.yaw_sign
        head_deg, waist_deg = split_yaw(theta, self.head_yaw_max_deg, self.waist_yaw_max_deg)
        head_y = _clamp(round(head_deg * self.pulse_per_deg_yaw), HEAD_Y_LIMIT)
        waist_y = _clamp(round(waist_deg * self.pulse_per_deg_waist * self.waist_sign), WAIST_Y_LIMIT)
        pitch_pulse = (gaze_pitch + self.pitch_offset_deg) * self.pulse_per_deg_pitch * self.pitch_sign
        head_p = _clamp(round(pitch_pulse), HEAD_P_LIMIT)
        return head_y, head_p, 0, waist_y

    def make_smoother(self):
        """この校正の EMA/デッドバンドで Smoother を生成。"""
        return Smoother(alpha=self.ema_alpha, deadband_deg=self.deadband_deg)
