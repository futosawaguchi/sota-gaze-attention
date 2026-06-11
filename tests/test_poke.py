"""scripts/sota_poke.py の pose 生成テスト（ネットワーク不要）。"""

from types import SimpleNamespace

from scripts.sota_poke import build_poses
from sota.targeter import HEAD_P_LIMIT, HEAD_Y_LIMIT


def _args(**over):
    base = dict(head_y=0, head_p=0, head_r=0, waist_y=None, sweep=False, amp=0.5, interval=1.5)
    base.update(over)
    return SimpleNamespace(**base)


def test_single_pose():
    poses = build_poses(_args(head_y=500, head_p=-100))
    assert poses == [(500, -100, 0, None, "single")]


def test_single_pose_with_waist():
    poses = build_poses(_args(waist_y=400))
    assert poses == [(0, 0, 0, 400, "single")]


def test_sweep_sequence_starts_and_ends_centered():
    poses = build_poses(_args(sweep=True, amp=0.5))
    assert len(poses) == 8
    assert poses[0][:3] == (0, 0, 0)
    assert poses[-1][:3] == (0, 0, 0)
    assert all(pose[3] is None for pose in poses)  # sweep は頭のみ（Waist 無し）


def test_sweep_amplitudes_track_limits():
    poses = build_poses(_args(sweep=True, amp=0.5))
    assert poses[1][0] == int(HEAD_Y_LIMIT[1] * 0.5)   # +Head_Y
    assert poses[3][0] == -int(HEAD_Y_LIMIT[1] * 0.5)  # -Head_Y
    assert poses[5][1] == int(HEAD_P_LIMIT[1] * 0.5)   # +Head_P (上限 110)
    assert poses[6][1] == int(HEAD_P_LIMIT[0] * 0.5)   # -Head_P (下限 -290)


def test_sweep_stays_within_limits():
    for y, p, r, w, _ in build_poses(_args(sweep=True, amp=1.0)):
        assert HEAD_Y_LIMIT[0] <= y <= HEAD_Y_LIMIT[1]
        assert HEAD_P_LIMIT[0] <= p <= HEAD_P_LIMIT[1]
        assert r == 0 and w is None
