"""Sota に既知パルスを送って「向き・符号・可動域」を確かめる校正用ツール。

gaze360 を一切使わず、SotaController(9980) へ直接 UDP/JSON を送る。Sota 到着日に
「+Head_Y でどちらに首が回るか（符号）」「±1400 でどこまで届くか（gain/可動域）」
「+Head_P が上か下か（pitch 符号）」を切り分けるのに使う。

例:
    python scripts/sota_poke.py --head-y 500            # 単発（首を右(or左)へ）
    python scripts/sota_poke.py --head-p -100           # 単発（下(or上)へ）
    python scripts/sota_poke.py --sweep                 # 中心→+Y→中心→-Y→+P→-P→中心
    python scripts/sota_poke.py --sweep --interval 1.5  # 各ステップ 1.5s 間隔
    python scripts/sota_poke.py --head-y 500 --ip 192.168.11.5   # 宛先を明示
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sota.sender import SotaSender  # noqa: E402
from sota.targeter import HEAD_P_LIMIT, HEAD_Y_LIMIT  # noqa: E402


def build_poses(args):
    """CLI 引数から送信する (Head_Y, Head_P, Head_R, Waist_Y, label) の系列を作る。

    Waist_Y は None なら送信時に省略（頭のみ）。sweep は頭のみ。
    """
    if args.sweep:
        _, ymax = HEAD_Y_LIMIT
        pmin, pmax = HEAD_P_LIMIT
        amp_y = int(ymax * args.amp)      # 可動域の amp 割だけ振る（既定 0.5）
        amp_p_up, amp_p_down = int(pmax * args.amp), int(pmin * args.amp)
        return [
            (0, 0, 0, None, "center"),
            (amp_y, 0, 0, None, f"+Head_Y {amp_y}（右?）"),
            (0, 0, 0, None, "center"),
            (-amp_y, 0, 0, None, f"-Head_Y {-amp_y}（左?）"),
            (0, 0, 0, None, "center"),
            (0, amp_p_up, 0, None, f"+Head_P {amp_p_up}（上?）"),
            (0, amp_p_down, 0, None, f"-Head_P {amp_p_down}（下?）"),
            (0, 0, 0, None, "center"),
        ]
    return [(args.head_y, args.head_p, args.head_r, args.waist_y, "single")]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sota にパルスを送る校正ツール（gaze360 不要）")
    parser.add_argument("--head-y", type=int, default=0, help="Head_Y パルス（左右）")
    parser.add_argument("--head-p", type=int, default=0, help="Head_P パルス（上下）")
    parser.add_argument("--head-r", type=int, default=0, help="Head_R パルス（傾き・通常 0）")
    parser.add_argument("--waist-y", type=int, default=None, dest="waist_y",
                        help="Waist_Y パルス（腰・左右）。指定時のみ送る（360°化の符号/可動域確認）")
    parser.add_argument("--sweep", action="store_true",
                        help="中心→±Head_Y→±Head_P の系列を順に送る（符号/可動域の確認）")
    parser.add_argument("--amp", type=float, default=0.5,
                        help="sweep の振り幅（可動域に対する割合・既定 0.5）")
    parser.add_argument("--interval", type=float, default=1.5, help="sweep の各ステップ間隔（秒）")
    parser.add_argument("--ip", default=None, help="宛先 IP（既定: 環境変数 SOTA_IP）")
    parser.add_argument("--port", type=int, default=None, help="宛先ポート（既定: SOTA_PORT/9980）")
    args = parser.parse_args(argv)

    sender = SotaSender(host=args.ip, port=args.port)
    print(f"[poke] -> Sota {sender.host}:{sender.port}")
    poses = build_poses(args)
    for i, (y, p, r, w, label) in enumerate(poses):
        msg = sender.send(y, p, r, waist_y=w)
        print(f"[poke] {label}: {msg}")
        if args.sweep and i < len(poses) - 1:
            time.sleep(args.interval)
    sender.close()


if __name__ == "__main__":
    main()
