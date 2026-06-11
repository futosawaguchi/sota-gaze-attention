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

> 既存プロジェクト（sota-face-tracking / sota-attention-guidance）と同じ実機を使う場合、
> **既にコンパイル済みの同一クラスが Sota にある**ので転送・コンパイルは不要 → 手順 4 へ。
> 本リポジトリの [java/SotaController.java](../java/SotaController.java) はそれらとバイト同一。

新規にデプロイ／作り直す場合（参考実機のパス `~/SotaSample`）:

```bash
# Mac 側（このリポジトリのルートで）。配置先は SotaSample の src ツリー（jp/vstone/sotatest）。
scp java/SotaController.java root@<SOTA_IP>:/home/root/SotaSample/src/jp/vstone/sotatest/
```

```bash
# Sota 側（ssh 接続後）。SDK 付属のビルド手順でコンパイル（classpath は RobotLib の jar）。
cd /home/root/SotaSample
# 既存サンプルのビルド方法に倣う（例: javac -cp <RobotLib.jar 等> src/jp/vstone/sotatest/SotaController.java）
```

> ⚠️ **環境依存ポイント**: ディレクトリ構成・jar の場所・コンパイルコマンドは個体/SDK 版で異なる。
> 既存の動作サンプル（`jp.vstone.sotatest.*`）の置き場所とビルド手順に倣うのが確実。

## 4. Sota 側で起動（UDP 9980 待受）

```bash
cd /home/root/SotaSample/bin
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

**まず gaze 無しで素振り**（配線・符号の確認。THETA 不要）:

```bash
python scripts/sota_poke.py --sweep    # 中心→±Head_Y→±Head_P。首が動けば疎通 OK
```

その後 gaze 追従:

```bash
# all-local（THETA を Mac で直結。要 gaze360 依存導入。CLAUDE.md 参照）
python app.py --local

# 疎結合（GPU で gaze360 --publish-port → SSH -L → 購読）
python app.py --subscribe localhost:8090
```

Sota の頭が人の視線方向に追従すれば疎通 OK。向き・符号・追従の調整は [docs/calibration.md](calibration.md)。

## 6. 動作チェックと校正

- 校正前は仮係数のため向きは粗い（クランプに張り付くこともある＝想定内）。
- 既知方向（正面/左/右/上/下）を見てもらい、`yaw_offset` / `pitch_offset` / `pulse_per_deg_*` /
  pitch 符号を [sota/targeter.py](../sota/targeter.py) で調整（SOTA_HANDOVER §9）。
- 校正値は `--local` / `--subscribe` で**共通**（targeter を共有）。

## トラブルシュート

- **頭が動かない**: Mac の `.env` の `SOTA_IP`、Sota 側で "UDP listening..." が出ているか、同一 LAN か、UDP 9980 がファイアウォールで塞がれていないか。Mac 側ログ `[sota] ... -> {'Head_Y':...}` が出ているかを先に確認（出ていれば送信はできている）。
- **数値が反映されない**: 送る値は**整数**（`SotaSender` が int 化済み）。Java の regex パーサは小数を弾く。
- **モーション中に固まる**: Java はモーション再生中サーボ更新をスキップする仕様（`isBusy`）。
