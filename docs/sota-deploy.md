# Sota 実機デプロイ手順

[java/SotaController.java](../java/SotaController.java) を Sota に転送・コンパイルして起動し、
本アプリ（Mac）から UDP(9980) で頭部姿勢を送れる状態にする手順。**Sota 到着後**に実施する。

> このコントローラは `futosawaguchi/sota-face-tracking` の実績ある実装を**無改修**で再利用したもの。
> JSON キー `Head_Y / Head_P / Head_R`（パルス値）が本アプリの `SotaSender` 出力と一致するため、
> Sota 側の改修は不要。LED / Motion（`nod` `shake_head` `bye_bye` など）も受けられる（将来拡張用）。

## 0. 前提

- Sota と Mac が同一 LAN にある。
- カメラ（THETA X）は Sota とほぼ同位置・同向きに設置（direction-only の視差ゼロ近似）。

## 1. Sota を起動して IP を確認

1. 電源ボタンを押す。
2. 上下ボタンを 3 秒長押し → 起動。
3. 読み上げ／画面で **IP アドレス**を取得（以後 `<SOTA_IP>`）。

## 2. SSH で接続

```bash
ssh root@<SOTA_IP>
# password: edison00   （vstone 既定。変更済みなら各自のもの）
```

## 3. Java を転送してコンパイル

```bash
# Mac 側（このリポジトリのルートで）
scp java/SotaController.java root@<SOTA_IP>:<vstone サンプルの src ディレクトリ>/
```

```bash
# Sota 側（ssh 接続後）。パッケージは jp.vstone.sotatest。
# 配置先・classpath・コンパイル方法は Sota 内の vstone SDK レイアウトに依存するため、
# 既存サンプル（jp.vstone.sotatest.* など）と同じ場所・同じ手順に合わせること。
#   例) 既存サンプルが置かれている src ツリーに SotaController.java を置き、
#       SDK 付属のビルド手順（javac -cp <RobotLib.jar 等> ...）でコンパイルする。
```

> ⚠️ **環境依存ポイント**: Sota 内のディレクトリ構成・jar の場所・コンパイルコマンドは個体/SDK 版で異なる。
> 既存の動作サンプルの置き場所とビルド手順に倣うのが確実。`import jp.vstone.RobotLib.*` が解決できる
> classpath でコンパイルする。

## 4. Sota 側で起動（UDP 9980 待受）

```bash
./java_run.sh jp.vstone.sotatest.SotaController
# => 標準出力に "SotaController ready. UDP port: 9980" / "UDP listening..." が出れば待受開始
```

起動時に Sota は初期姿勢（正面・LED 緑）になる。受信した JSON の `Head_*` で頭部サーボを更新する
（Java 側でも `LIMIT_VALUE` に再クランプ。`Head_Y[-1400,1400] / Head_P[-290,110] / Head_R[-300,350]`）。

## 5. Mac 側アプリを起動

```bash
cp .env.example .env        # 初回のみ
# .env を編集: SOTA_IP=<SOTA_IP>  /  SOTA_PORT=9980
```

```bash
# all-local（THETA を Mac で直結。要 gaze360 依存導入。CLAUDE.md 参照）
python app.py --local

# 疎結合（GPU で gaze360 --publish-port → SSH -L → 購読）
python app.py --subscribe localhost:8090
```

Sota の頭が人の視線方向に追従すれば疎通 OK。

## 6. 動作チェックと校正

- 校正前は仮係数のため向きは粗い（クランプに張り付くこともある＝想定内）。
- 既知方向（正面/左/右/上/下）を見てもらい、`yaw_offset` / `pitch_offset` / `pulse_per_deg_*` /
  pitch 符号を [sota/targeter.py](../sota/targeter.py) で調整（SOTA_HANDOVER §9）。
- 校正値は `--local` / `--subscribe` で**共通**（targeter を共有）。

## トラブルシュート

- **頭が動かない**: Mac の `.env` の `SOTA_IP`、Sota 側で "UDP listening..." が出ているか、同一 LAN か、UDP 9980 がファイアウォールで塞がれていないか。Mac 側ログ `[sota] ... -> {'Head_Y':...}` が出ているかを先に確認（出ていれば送信はできている）。
- **数値が反映されない**: 送る値は**整数**（`SotaSender` が int 化済み）。Java の regex パーサは小数を弾く。
- **モーション中に固まる**: Java はモーション再生中サーボ更新をスキップする仕様（`isBusy`）。
