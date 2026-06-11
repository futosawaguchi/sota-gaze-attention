# 校正＆デバッグ手順（Sota 実機）

「人が見ている方向に Sota の頭が向く」ように調整する手順。**コードは触らず `.env` の `SOTA_*` を編集**して直す。
変換ロジックは [sota/targeter.py](../sota/targeter.py) の `camera_to_robot` / `Calibration`、デプロイは [docs/sota-deploy.md](sota-deploy.md)。

## 0. 変換の仕組み（何を調整するのか）

```
gaze_yaw/pitch(度) → (+offset) → (×pulse_per_deg) → (×sign) → クランプ → Head_Y/Head_P(パルス)
                                                                          ↑ EMA/デッドバンドで平滑化
送信は inout ≥ SOTA_INOUT_MIN のときだけ。Head_R は常に 0。
```

`.env` の校正変数（未設定は仮値の既定。テンプレは [.env.example](../.env.example)）:

| 変数 | 役割 | 既定 |
|---|---|---|
| `SOTA_YAW_OFFSET_DEG` / `SOTA_PITCH_OFFSET_DEG` | 取付ズレ（カメラ前方と Sota 正面の差）を度で補正 | 0 / 0 |
| `SOTA_PULSE_PER_DEG_YAW` / `_PITCH` | 度→パルス係数（gain）。大=機敏, 小=鈍い | 15.56 / 3.67 |
| `SOTA_YAW_SIGN` / `SOTA_PITCH_SIGN` | 左右/上下が逆なら `-1` | 1 / 1 |
| `SOTA_EMA_ALPHA` | 平滑化（小=滑らか/遅い, 大=機敏/揺れる） | 0.4 |
| `SOTA_DEADBAND_DEG` | この未満の変化は送らない（カクつき防止） | 2.0 |
| `SOTA_INOUT_MIN` | 視線がフレーム内の確率の下限（動かない時は下げる） | 0.3 |

## 1. 到着直後：配線と符号を gaze 無しで確認（poke）

THETA や gaze360 を使わず、まず Sota だけで疎通と向きを確かめる。

1. Sota を起動し [docs/sota-deploy.md](sota-deploy.md) の手順で `SotaController` を起動（`./java_run.sh jp.vstone.sotatest.SotaController` → "UDP listening..."）。
2. Mac の `.env` に `SOTA_IP=<SotaのIP>`（`SOTA_PORT=9980`）。
3. （任意）別ターミナルで送信内容を見る: `python scripts/sota_listen.py` ※実機と同時に使うなら別ホスト/ポートで。
4. **符号・可動域チェック**:
   ```bash
   python scripts/sota_poke.py --sweep        # 中心→+Y→中心→-Y→+P→-P→中心
   ```
   観察し記録する:
   - `+Head_Y` で首が**右**に回るか左に回るか → 左右が逆なら `SOTA_YAW_SIGN=-1`。
   - `+Head_P` で**上**を向くか下を向くか → 逆なら `SOTA_PITCH_SIGN=-1`。
   - `±(可動域×0.5)` でどこまで動くか（gain の当たり）。
   ```bash
   python scripts/sota_poke.py --head-y 1400  # 端まで（可動域の確認）
   ```

## 2. THETA を Sota と同位置に設置して gaze 追従（粗）

- **カメラは Sota の真上/すぐ横に、向きを揃えて**設置（direction-only の視差ゼロ近似。SOTA_HANDOVER §1）。
- `python app.py --local` を起動。人に正面・左・右・上・下を順に見てもらい、頭が追うか観察。

## 3. 校正（§9）：`.env` を詰める

人に**既知方向**を見てもらいながら `.env` を調整 → アプリ再起動、を繰り返す:

1. **正面**を見てもらう → 頭が正面を向くよう `SOTA_YAW_OFFSET_DEG` / `SOTA_PITCH_OFFSET_DEG`。
2. **左右**を見てもらう → 向きが合うよう `SOTA_PULSE_PER_DEG_YAW`（行き過ぎ＝下げる / 足りない＝上げる）。逆向きなら `SOTA_YAW_SIGN=-1`。
3. **上下** → `SOTA_PULSE_PER_DEG_PITCH` と `SOTA_PITCH_SIGN`。
4. **背後**（到達不能方向）→ クランプで端に止まることを確認。
5. 動きが**ガタつく/速すぎ/遅すぎ** → `SOTA_EMA_ALPHA` / `SOTA_DEADBAND_DEG`。

> 校正値は `--local` / `--subscribe` で**共通**（targeter を共有）。一度合わせれば疎結合でもそのまま使える。

## 4. デバッグ：症状 → 直す場所

| 症状 | 原因 | 対処（`.env`） |
|---|---|---|
| 左右が**逆** | yaw 符号 | `SOTA_YAW_SIGN=-1` |
| 上下が**逆** | pitch 符号 | `SOTA_PITCH_SIGN=-1` |
| 正面なのに**横/上を向く** | 取付ズレ | `SOTA_YAW_OFFSET_DEG` / `SOTA_PITCH_OFFSET_DEG` |
| **動きすぎ/すぐ端に張り付く** | gain 過大 | `SOTA_PULSE_PER_DEG_*` を下げる |
| **ほとんど動かない（が少しは動く）** | gain 過小 | `SOTA_PULSE_PER_DEG_*` を上げる |
| **カクつく** | 平滑不足 | `SOTA_EMA_ALPHA` 下げ / `SOTA_DEADBAND_DEG` 上げ |
| **追従が遅い** | 平滑過多 | `SOTA_EMA_ALPHA` 上げ |
| **全く動かない** | UDP/起動/検出/ゲート | 下の切り分けへ |

### 「全く動かない」の切り分け（最重要）

**Mac 側ログに `[sota] ... -> {'Head_Y':..}` が出ているか**で二分する:

- **出ている** → 送信はできている。Sota 側を疑う:
  - `.env` の `SOTA_IP` が実機と一致しているか。
  - Sota 側で `SotaController` が起動し "UDP listening..." か。
  - 同一 LAN か / UDP 9980 がファイアウォールで塞がれていないか。
  - `python scripts/sota_poke.py --head-y 500` で動くか（動けば gaze 側、動かねば Sota/network 側）。
- **出ていない** → アプリ側。人が検出されていない（カメラ画角/明るさ）か、`inout` が低い（`SOTA_INOUT_MIN` を一時的に下げる）か、視線がフレーム外。`app.py --local` のフレームログ（`人物N: ...`）で確認。

## 5. 参考: そのまま動く道具

```bash
python scripts/sota_poke.py --sweep         # 符号・可動域の素振り（gaze 不要）
python scripts/sota_poke.py --head-y 500    # 単発
python scripts/sota_listen.py               # 送信パケットを覗く（fake-Sota）
python app.py --local                       # THETA リアルタイムで実走
```
