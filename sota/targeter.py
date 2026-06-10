"""カメラ視線（度）→ Sota サーボパルス値への変換と平滑化。

gaze360 が出す視線方位（THETA カメラ座標系・度、yaw 正=右 / pitch 正=上）を
Sota のサーボパルス値（Head_Y / Head_P / Head_R）へ変換する。

- ``camera_to_robot``: 取付オフセット加算 → 度×係数（パルス化）→ 可動域クランプ → Head_R=0。
- ``Smoother``: EMA ＋ デッドバンドで首のガタつきを抑える（gaze360 側に平滑化は無い）。

**係数・オフセット・pitch 符号は要実機校正（SOTA_HANDOVER §9）のプレースホルダ。**
ここで保証するのは「クランプ・EMA・デッドバンドのロジック」だけ。校正値の実数は別途確定する。
"""

# --- Sota 可動域（パルス値, SOTA_HANDOVER §5）------------------------------
HEAD_Y_LIMIT = (-1400, 1400)
HEAD_P_LIMIT = (-290, 110)

# --- 校正プレースホルダ（要実機校正 §9）-----------------------------------
# 取付オフセット: THETA 前方(yaw=0) と Sota 正面の差（度）。校正前は 0。
YAW_OFFSET_DEG = 0.0
PITCH_OFFSET_DEG = 0.0
# 度→パルス係数（1 度あたりのパルス値）。暫定の仮定:
#   Head_Y ±1400 ↔ ±90°、Head_P +110 ↔ +30°。実測で確定する。
PULSE_PER_DEG_YAW = 1400.0 / 90.0
PULSE_PER_DEG_PITCH = 110.0 / 30.0
# pitch 符号: gaze は正=上。Sota 側の上下対応は校正で確認（必要なら -1 にする）。
PITCH_SIGN = 1.0


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
    pitch_sign=PITCH_SIGN,
):
    """視線方位（度）→ (Head_Y, Head_P, Head_R) パルス値（int）。

    1. 取付オフセットを加算（カメラ前方と Sota 正面の差を吸収）。
    2. 度 → パルス（係数を掛ける）。pitch は符号補正。
    3. Sota 可動域にクランプ。Head_R は 0 固定。
    """
    yaw_pulse = (gaze_yaw + yaw_offset) * pulse_per_deg_yaw
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
