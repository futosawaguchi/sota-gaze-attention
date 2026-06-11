# GPU 疎結合（publish / subscribe）手順

本番構成: **GPU `gundam` が gaze360 を実行し視線を配信 → ローカル(Mac)が購読 → Sota へ UDP**。
ローカルは torch 不要・軽量（[sota/source.py](../sota/source.py)）。**Sota が無くても、出力先を fake-Sota
（loopback `scripts/sota_listen.py`）にすれば疎通確認できる**（検証済み 2026-06-11）。

実値（gundam のユーザ/IP、THETA IP）は**このリポジトリには書かない**。`~/Desktop/gaze360/run_gpu.sh` と
リポジトリの `.env` を参照（`<...>` を自分の値に置換）。

## 構成

```
[GPU gundam]  python -m src.pipeline --publish-port 8090 --stream-port 8081
   ↑ ssh -R <TUN>:<THETA_IP>:80     （THETA→GPU。GPU が Mac 経由でカメラに到達）
   |  remote: export THETA_IP=localhost:<TUN>
   ↓ TCP 8090（gundam が直接到達可能なら -L 不要）
[Mac] python app.py --subscribe <GUNDAM_IP>:8090   （Sota 無し時は fake-Sota へ）
```

## 前提

- **ネットワーク**: Mac から gundam（VPN/LAN）と THETA（`<THETA_IP>`）の**両方に到達できること**
  （`-R` 逆トンネルは Mac 側から THETA に届く必要がある）。`ping <GUNDAM_IP>` と
  `curl -m5 http://<THETA_IP>/osc/info`（401 が返ればカメラ生存）で確認。
- **gundam の gaze360**: `~/gaze360` が `≥46ed129`（`--publish-port` 入り）。`git pull` で更新。
  - ⚠️ **gundam で `pip install -r requirements.txt` はしない**。gaze360 の requirements は `numpy==2.4.6`
    など **Python≥3.11** をピン留めしており、gundam の venv（Python 3.10）では入らない。
    gundam は既存の依存で動くのでインストール不要。

## 1. GPU 側: publisher 起動（自分のターミナルで・パスワード入力）

```bash
ssh -t -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -R <TUN>:<THETA_IP>:80 \
  <GUNDAM_USER>@<GUNDAM_IP> \
  "cd ~/gaze360 && source venv/bin/activate && export CUDA_VISIBLE_DEVICES=0 && export THETA_IP=localhost:<TUN> && exec python -m src.pipeline --publish-port 8090 --stream-port 8081"
```

- `<TUN>` は任意の空きポート（例 45678）。
- **`--stream-port` を必ず付ける**: 無いと gundam（ヘッドレス）で `cv2.imshow` が
  `qt.qpa.xcb: could not connect to display` で落ちる。付けると MJPEG 化されヘッドレスで動く。
- **`export THETA_IP=localhost:<TUN>` を明示**: gundam の `.env`/古い環境変数（前回の別ポート）を上書きする
  （`load_dotenv` は既存の環境変数を上書きしないため、先の export が勝つ）。
- 成功表示: `[GazeResultPublisher] TCP 8090 で視線データを配信中` ＋ `人物1: 方位角 ... を見ている` が流れる。

## 2. ローカル側: 購読 → Sota（or fake-Sota）

`.env` の `SOTA_IP` を実 Sota に。**Sota が無い時は fake-Sota** で疎通だけ見る:

```bash
# 端末A: fake-Sota（送信パケットを表示）
python scripts/sota_listen.py --port 9980

# 端末B: 購読（gundam が直接到達できる場合）
SOTA_IP=127.0.0.1 python app.py --subscribe <GUNDAM_IP>:8090
```

- gundam の 8090 が直接届かない（ファイアウォール等）場合のみ、別端末で
  `ssh -L 8090:localhost:8090 <GUNDAM_USER>@<GUNDAM_IP>` を張り、`--subscribe localhost:8090`。
- 実 Sota なら `.env` に実 `SOTA_IP` を入れて `python app.py --subscribe <GUNDAM_IP>:8090`。
  校正は all-local と共通（[docs/calibration.md](calibration.md)）。

## トラブルシュート

- **gundam で `qt.qpa.xcb ... could not connect to display`** → `--stream-port` を付け忘れ。
- **THETA `Connection refused`（localhost:別ポート）** → 古い `THETA_IP` を見ている。`export THETA_IP=localhost:<TUN>` を明示し、`-R <TUN>:<THETA_IP>:80` のポートと一致させる。
- **THETA timeout/refused（`<THETA_IP>:80`）** → Mac から THETA に届いていない（Wi-Fi 不安定 or 経路）。`curl http://<THETA_IP>/osc/info` で確認、再実行。
- **`--publish-port: unrecognized arguments`** → gundam の gaze360 が古い。`git pull`（`46ed129` 以上）。
- **`numpy==2.4.6` install エラー** → gundam で requirements を入れようとしている。入れない（前提参照）。
- **購読しても送信されない** → 人物が居ない（`[]`）か `inout < SOTA_INOUT_MIN`。`[sota] ...` ログが出るか確認。

## 補足

- SSH を鍵認証にすれば（`ssh-copy-id`）パスワード入力が不要になり自動化しやすい。
- EMA は ±180° の巻き戻りを線形平均するため、真後ろ付近で大きく値が飛ぶ瞬間がある（既知の小課題）。
