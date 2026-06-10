"""疎結合モードの入力源: gaze360 publisher を購読し list[GazeResult] を復元する。

gaze360 の `GazeResultPublisher`（src/gaze/publisher.py）が TCP で配信する
「1 行 = 1 フレーム = GazeResult の JSON 配列」を読み、各行を `list[GazeResult]` に
復元して `on_results(results)` コールバックへ渡す（all-local の on_results と同じ口）。

torch も gaze360 も import しない（軽量）。GazeResult は消費側ミラー（sota.gaze_result）を使う。
"""

import json
import socket
import time

from sota.gaze_result import from_dict


def parse_line(line):
    """publisher の 1 行（JSON 配列）→ list[GazeResult]。空行・空配列は []。"""
    line = line.strip()
    if not line:
        return []
    return [from_dict(obj) for obj in json.loads(line)]


def subscribe(host, port, on_results, *, reconnect=True, backoff=1.0, max_frames=None):
    """publisher へ TCP 接続し、各フレームを on_results(list[GazeResult]) に渡す（ブロッキング）。

    Parameters
    ----------
    host, port : 接続先（gaze360 の --publish-port、SSH -L 転送先など）。
    on_results : Callable[[list[GazeResult]], None]
        1 フレームごとに呼ぶ消費側コールバック。
    reconnect : bool
        切断時に再接続する（既定 True）。False なら 1 接続で終了。
    backoff : float
        再接続前の待機秒。
    max_frames : int | None
        受信フレーム数の上限（テスト用。None で無制限）。
    """
    count = 0
    while True:
        try:
            with socket.create_connection((host, port)) as sock:
                # 行区切りで読むため text モードの file-like を使う。
                with sock.makefile("r", encoding="utf-8") as stream:
                    for line in stream:
                        on_results(parse_line(line))
                        count += 1
                        if max_frames is not None and count >= max_frames:
                            return
        except (ConnectionError, OSError) as e:
            if not reconnect:
                raise
            print(f"[sota] publisher 切断/接続失敗: {e}. {backoff}s 後に再接続...")
        except KeyboardInterrupt:
            print("\n[sota] 終了します...")
            return

        if not reconnect or (max_frames is not None and count >= max_frames):
            return
        time.sleep(backoff)
