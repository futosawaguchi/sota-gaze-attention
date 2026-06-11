"""Sota への UDP 送信。

`SotaController.java`（Sota 側）が UDP port 9980 で待ち受け、JSON
`{"Head_Y": int, "Head_P": int, "Head_R": int}` を受信してサーボを駆動する。
値は度ではなく**サーボパルス値**。可動域のクランプは targeter 側で行う前提だが、
ここでも int 化のみ行う（範囲は呼び出し側の責務）。
"""

import json
import os
import socket

DEFAULT_PORT = 9980


class SotaSender:
    """Sota へ頭部姿勢を UDP/JSON で送る送信器。"""

    def __init__(self, host=None, port=None):
        """
        Parameters
        ----------
        host : str | None
            Sota の IP。None なら環境変数 ``SOTA_IP``（既定 ``127.0.0.1``）。
        port : int | None
            UDP ポート。None なら環境変数 ``SOTA_PORT``（既定 9980）。
        """
        self.host = host or os.environ.get("SOTA_IP", "127.0.0.1")
        self.port = int(port if port is not None else os.environ.get("SOTA_PORT", DEFAULT_PORT))
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, head_y, head_p, head_r=0, waist_y=None):
        """頭部姿勢（パルス値）を 1 フレーム送信する。

        Parameters
        ----------
        waist_y : int | None
            腰ヨー（パルス値）。None なら ``Waist_Y`` キーを送らない（頭のみ・wire 不変）。
            指定時のみ JSON に ``Waist_Y`` を含める（360° 化で頭の可動域を超えた分を腰で補う）。

        Returns
        -------
        dict
            実際に送ったメッセージ（ログ・テスト用）。
        """
        msg = {"Head_Y": int(head_y), "Head_P": int(head_p), "Head_R": int(head_r)}
        if waist_y is not None:
            msg["Waist_Y"] = int(waist_y)
        self._sock.sendto(json.dumps(msg).encode("utf-8"), (self.host, self.port))
        return msg

    def close(self):
        self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
