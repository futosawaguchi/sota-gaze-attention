"""sota-gaze-attention エントリポイント。

使い方:
  python app.py --local                  # all-local: gaze360 を import し一体実行（要 gaze360 依存）
  python app.py --local --source x.mp4   # THETA の代わりに録画動画で実行
  python app.py --subscribe HOST:PORT    # 疎結合（未実装・Phase A.5）

gaze360 は ``from src.xxx`` の相対 import 構成なので、冒頭で ``gaze360/`` を sys.path に通す。
重い依存（GazePipeline=torch 等）の import は ``--local`` 分岐の中でのみ行う
（``--help`` や配線確認を torch 無しで通せるようにするため）。
"""

import argparse
import os
import sys

from sota.sender import SotaSender
from sota.targeter import Calibration

# gaze360 の src.xxx を解決可能にする（重い import はここではしない）。
GAZE360_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gaze360")
if GAZE360_DIR not in sys.path:
    sys.path.insert(0, GAZE360_DIR)


def make_handler(sender, smoother, select_primary, calib, verbose=True):
    """1 フレーム分の list[GazeResult] を targeter→sender へ流すコールバックを作る。

    select_primary を引数で受けるのは、app.py のトップレベルで gaze360 を
    import しない（--help を軽く保つ）ため。校正・ゲートは ``calib``（.env 由来）に従う。
    """

    def handle(results):
        primary = select_primary(results)
        if not (primary and primary.inout >= calib.inout_min):
            return
        yaw, pitch = smoother.update(primary.gaze_yaw, primary.gaze_pitch)
        head_y, head_p, head_r = calib.to_robot(yaw, pitch)
        msg = sender.send(head_y, head_p, head_r)
        if verbose:
            print(
                f"[sota] gaze=({primary.gaze_yaw:.1f},{primary.gaze_pitch:.1f}) "
                f"-> smooth=({yaw:.1f},{pitch:.1f}) -> {msg}"
            )

    return handle


def run_local(source):
    """all-local モード: gaze360 を import して on_results で受ける。"""
    from dotenv import load_dotenv

    # 重い依存（torch 等）はここで初めて import する。
    from src.pipeline import GazePipeline
    from sota.gaze_result import select_primary  # 主対象選択は消費側ポリシー（両モード共有）

    load_dotenv()
    calib = Calibration.from_env()
    sender = SotaSender()
    smoother = calib.make_smoother()
    print(
        f"[sota] all-local モード: source={source or 'THETA'} "
        f"-> Sota {sender.host}:{sender.port}"
    )
    handler = make_handler(sender, smoother, select_primary, calib)
    GazePipeline(source=source, on_results=handler).run()


def _parse_hostport(target):
    """``HOST:PORT`` を (host, port:int) に分解する。"""
    if ":" not in target:
        raise ValueError(f"--subscribe は HOST:PORT 形式で指定してください（例: localhost:8090）。受領: {target!r}")
    host, _, port = target.rpartition(":")
    return host or "localhost", int(port)


def run_subscribe(target):
    """疎結合モード: gaze360 publisher を購読して on_results 互換で処理する。

    torch も gaze360 も import しない（軽量）。GazeResult は消費側ミラーで復元する。
    """
    from dotenv import load_dotenv

    from sota.gaze_result import select_primary  # 主対象選択は消費側ポリシー（両モード共有）
    from sota.source import subscribe

    host, port = _parse_hostport(target)
    load_dotenv()
    calib = Calibration.from_env()
    sender = SotaSender()
    smoother = calib.make_smoother()
    print(f"[sota] subscribe モード: {host}:{port} -> Sota {sender.host}:{sender.port}")
    handler = make_handler(sender, smoother, select_primary, calib)
    subscribe(host, port, handler)


def main():
    parser = argparse.ArgumentParser(description="Sota 共同注意アプリ（gaze→UDP）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--local", action="store_true",
        help="all-local: gaze360 を import して一体実行（要 gaze360 依存）",
    )
    mode.add_argument(
        "--subscribe", metavar="HOST:PORT",
        help="疎結合: gaze360 publisher (--publish-port) を購読（torch 不要・軽量）",
    )
    parser.add_argument(
        "--source", default=None,
        help="動画ファイルパス（--local 時。省略で THETA カメラ）",
    )
    args = parser.parse_args()

    if args.local:
        run_local(args.source)
    else:
        run_subscribe(args.subscribe)


if __name__ == "__main__":
    main()
