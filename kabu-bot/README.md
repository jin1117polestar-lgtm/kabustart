# 日本株 仮想売買ボット（0円運用）

GitHub Actions 上で平日の大引け後に自動実行される仮想売買ボットです。
PCを閉じていても動き、運用コストは0円、AIトークンも消費しません。

**これは仮想売買です。実際の発注は行いません。過去の成績は将来の利益を保証しません。**

## 仕組み

- 平日 15:50 JST に GitHub Actions が起動（数分の遅延あり）
- yfinance で日足データを取得
- 移動平均クロス(5日/25日) + RSIフィルターでシグナル判定
- 仮想資金100万円で仮想約定し、`portfolio.json` に記録
- 結果を Discord に通知、`logs/` に日次レポートを保存

## セットアップ手順（所要 約10分）

### 1. GitHubリポジトリを作る
1. GitHub にログイン → New repository
2. **Private** を選択（公開したくない場合）。無料枠は月2,000分で、
   このボットは1回1〜2分なので余裕で収まります
3. このフォルダの中身をすべてアップロード
   （`.github/workflows/trade.yml` の階層を崩さないこと）

### 2. Discord Webhook を作る
1. Discord で通知用サーバー/チャンネルを用意
2. チャンネル設定 → 連携サービス → ウェブフック → 新しいウェブフック
3. 「ウェブフックURLをコピー」

### 3. リポジトリに Webhook URL を登録
1. リポジトリの Settings → Secrets and variables → Actions
2. New repository secret
3. Name: `DISCORD_WEBHOOK_URL` / Secret: コピーしたURL

### 4. 動作確認（手動実行）
1. リポジトリの Actions タブ → virtual-trade → Run workflow
2. 実行後、Discord に通知が届けば成功

以降は平日15:50頃に自動実行されます。

## ルールの調整

`config.json` を編集するだけで反映されます。

| 項目 | 意味 |
|---|---|
| tickers | 対象銘柄（東証は「コード.T」形式） |
| initial_capital | 仮想資金（円） |
| max_positions | 同時保有の上限銘柄数 |
| sma_short / sma_long | 移動平均の期間 |
| rsi_buy_max | この値以上のRSIでは買わない |
| rsi_sell_min | この値を超えたら売る |

デフォルト銘柄: トヨタ(7203) / ソニーG(6758) / ソフトバンクG(9984) /
三菱UFJ(8306) / 信越化学(4063)

## バックテスト

ルール変更前に過去データで検証できます（手元PC or Codespaces で実行）:

```bash
pip install yfinance pandas
python backtest.py        # 過去3年
python backtest.py 5y     # 過去5年
```

## リセットしたいとき

`portfolio.json` を削除してコミットすれば、次回実行時に
仮想資金100万円から再スタートします。

## 既知の制約

- yfinance のデータは非公式・遅延ありの参考値です
- 1株単位で仮想売買します（実際の日本株は原則100株単位。
  単元未満株サービスを使う場合を除く）
- 手数料・税金・スリッページは考慮していません
- 祝日はデータが更新されないため自動的に「様子見」になります
