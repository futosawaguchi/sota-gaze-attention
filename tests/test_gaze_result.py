"""消費側 GazeResult ミラーと select_primary の単体テスト。"""

from sota.gaze_result import GazeResult, from_dict, select_primary


def _obj(**over):
    base = {
        "person_id": 1, "gaze_yaw": 10.0, "gaze_pitch": -5.0,
        "inout": 0.8, "confidence": 0.9, "head_yaw": 11.0, "head_pitch": -4.0,
    }
    base.update(over)
    return base


def test_from_dict_full():
    r = from_dict(_obj())
    assert (r.person_id, r.gaze_yaw, r.gaze_pitch, r.inout, r.confidence) == (1, 10.0, -5.0, 0.8, 0.9)
    assert (r.head_yaw, r.head_pitch) == (11.0, -4.0)


def test_from_dict_missing_optional_is_none():
    o = _obj()
    del o["head_yaw"]
    del o["head_pitch"]
    r = from_dict(o)
    assert r.head_yaw is None and r.head_pitch is None


def test_from_dict_ignores_unknown_fields():
    # 契約はフィールド追加可 → 余剰キーは無視して復元できること。
    r = from_dict(_obj(future_field=123, another="x"))
    assert isinstance(r, GazeResult) and r.person_id == 1


def test_select_primary_picks_max_confidence():
    a = from_dict(_obj(person_id=1, confidence=0.4))
    b = from_dict(_obj(person_id=2, confidence=0.95))
    c = from_dict(_obj(person_id=3, confidence=0.7))
    assert select_primary([a, b, c]).person_id == 2


def test_select_primary_empty_is_none():
    assert select_primary([]) is None
