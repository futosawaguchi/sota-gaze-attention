"""消費側の軽量 GazeResult ミラーと主対象選択。

疎結合（subscribe）では gaze360 を import せず、publisher が配信する JSON（wire 契約）を
この軽量 dataclass に復元する。gaze360 の `src.gaze.result` は `src/gaze/__init__.py` 経由で
GazeEstimator（torch）を巻き込むため、購読側からは import しない。**wire JSON こそが契約**で、
フィールドは追加され得る → 既知フィールドのみ取り、未知は無視、`head_*` 欠損は None。

`select_primary` は「どの人物を追うか」の消費側ポリシー（SOTA_HANDOVER: 1人選択は consumer の責務）。
all-local / subscribe の両モードで共有する（gaze360 の GazeResult にも duck-typing で効く）。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GazeResult:
    """1人分の視線推定結果（gaze360 の公開契約のミラー）。座標は度・カメラ座標系。"""

    person_id: int
    gaze_yaw: float            # 視線先の方位角 [-180,180]（正=右）★主役
    gaze_pitch: float          # 視線先の仰角   [-90, 90]（正=上）  ★主役
    inout: float               # 視線がフレーム内にある確率 [0,1]
    confidence: float          # 人物検出の信頼度 [0,1]
    head_yaw: Optional[float] = None
    head_pitch: Optional[float] = None


def from_dict(obj):
    """publisher の 1 要素（dict）→ GazeResult。未知フィールドは無視、`head_*` 欠損は None。"""
    return GazeResult(
        person_id=obj["person_id"],
        gaze_yaw=obj["gaze_yaw"],
        gaze_pitch=obj["gaze_pitch"],
        inout=obj["inout"],
        confidence=obj["confidence"],
        head_yaw=obj.get("head_yaw"),
        head_pitch=obj.get("head_pitch"),
    )


def select_primary(results):
    """追う「主たる人物」を1人選ぶ。最小実装は confidence 最大。

    将来は「最大 bbox / 画面中心への近さ / 正面度」等のポリシーへ差し替え可能
    （その場合 GazeResult に必要フィールドを追加して参照する）。
    """
    if not results:
        return None
    return max(results, key=lambda r: r.confidence)
