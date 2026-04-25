# FX Signal Bot — Windows 11 セットアップ手順書（Dropbox経由）

> 対象: Windows 11 25H2 / 64bit / メモリ8GB
> 移送方法: Dropbox
> 所要時間: 1〜2時間

---

## 0. 全体の流れ

```
[Mac側]                          [Windows側]
  ↓                                  ↓
1. Dropboxに必要ファイルを配置      → 2. Dropboxから取得・配置
                                    → 3. Python仮想環境作成
                                    → 4. 依存ライブラリインストール
                                    → 5. 動作確認（テストモード）
                                    → 6. タスクスケジューラ設定
                                    → 7. Mac側のlaunchd停止
```

---

## 1. 前提条件チェック

作業を始める前に以下を確認してください。

| 項目 | 確認方法 | 必須/推奨 |
|------|---------|---------|
| Mac側にDropboxインストール済み | メニューバーのDropboxアイコン | 必須 |
| Windows側にDropboxインストール済み | タスクトレイのDropboxアイコン | 必須 |
| 同じDropboxアカウントでログイン | 両方の「設定」→「アカウント」 | 必須 |
| Dropboxの空き容量 100MB以上 | Dropboxアプリの「アカウント」タブ | 必須 |
| Windows側にPython 3.12 インストール済み | コマンドプロンプトで `python --version` | 必須 |

> **Pythonまだの方**: 別途案内している Step 1（Python 3.12 インストール）を先に完了してください。

---

## 2. 【Mac側】Dropboxへファイル準備

### 2-1. Dropboxフォルダの場所を確認

通常 Macでは以下のいずれか:
- `~/Dropbox/` （旧来）
- `~/Library/CloudStorage/Dropbox/` （新しいmacOS）

Finderの左サイドバーに「Dropbox」が表示されていれば、それをクリックして場所を確認できます。

### 2-2. 移送用フォルダを作成

Dropboxフォルダ内に **`fx-signals`** という名前のフォルダを作成。

### 2-3. ファイルを選別してコピー

**コピーするファイル/フォルダ**（これらは必須）:

```
✅ backtest.py
✅ config.py
✅ evaluate_signals.py
✅ event_filter.py
✅ fetch_data.py
✅ notifier.py
✅ optimize.py
✅ report.py
✅ run.py
✅ signal_engine.py
✅ signal_logger.py
✅ requirements.txt
✅ requirements-runtime.txt
✅ .env                 ← 隠しファイル。Cmd+Shift+. で表示
✅ .env.example
✅ .gitignore
✅ SETUP_WINDOWS.md     ← この手順書
✅ data/                ← フォルダごと（バックテスト履歴）
✅ logs/                ← フォルダごと（過去のシグナル・勝敗記録）
```

**コピーしないファイル/フォルダ**（重要：これらは絶対に転送しない）:

```
❌ venv/                ← Mac専用の仮想環境。Windowsで動かない＆100MB超
❌ __pycache__/         ← Pythonキャッシュ。不要、転送するとエラー要因
❌ *.pyc                ← Pythonコンパイル済みファイル
❌ .DS_Store            ← Mac固有のメタファイル
```

### 2-4. コピー方法

**方法A: Finderで手動選択（推奨・確実）**

1. Finderで `/Users/takahiroichikawa/fx-signals/` を開く
2. `Cmd + Shift + .` （ピリオド）で隠しファイルを表示
3. **`venv` フォルダ以外**を全選択：
   - `Cmd + A` で全選択
   - `Cmd` を押しながら `venv` をクリックして選択解除
4. `Cmd + C` でコピー
5. Dropboxの `fx-signals` フォルダを開いて `Cmd + V` で貼り付け

**方法B: ターミナルで一括コピー（早い）**

```bash
# Dropboxパスは環境に応じて書き換える
cp -R /Users/takahiroichikawa/fx-signals/{*.py,*.txt,*.md,.env,.env.example,.gitignore,data,logs} \
      ~/Dropbox/fx-signals/
```

### 2-5. Dropbox同期の完了を待つ

メニューバーのDropboxアイコンをクリック → 「同期完了」または緑のチェックマークが出るまで待つ。

通常 5〜30秒。`logs/` と `data/` のCSVが大きい場合は数分かかることがある。

---

## 3. 【Windows側】Dropboxからファイル取得

### 3-1. Dropboxの同期確認

タスクトレイ（画面右下）のDropboxアイコンをクリック → 「同期完了」を確認。

`fx-signals` フォルダが Dropbox 内に表示されていればOK。場所は通常:
- `C:\Users\<ユーザー名>\Dropbox\fx-signals\`

### 3-2. 作業フォルダにコピー

Dropboxフォルダで直接作業すると **Dropboxが常時同期して負荷がかかる** ため、別の場所にコピーします。

エクスプローラーで:

1. `C:\` 直下に `fx-signals` というフォルダを新規作成
   - エクスプローラーで `C:\` を開く → 右クリック → 「新規作成」→「フォルダー」→ 名前を `fx-signals`
2. Dropboxの `fx-signals` フォルダを開く
3. **隠しファイル表示をON**: エクスプローラー上部メニュー「表示」→「表示」→「☑ 隠しファイル」
4. 全ファイルを選択 (`Ctrl + A`) → コピー (`Ctrl + C`)
5. `C:\fx-signals\` を開いて貼り付け (`Ctrl + V`)

### 3-3. .env ファイルの確認

`C:\fx-signals\.env` が存在することをエクスプローラーで確認。

存在しない場合：手順 3-2 で隠しファイル表示が OFF だった可能性。再度確認。

---

## 4. 【Windows側】Python仮想環境の作成

### 4-1. コマンドプロンプトを開く

1. `Windowsキー` を押す
2. `cmd` と入力 → Enter

### 4-2. 作業フォルダに移動

```cmd
cd C:\fx-signals
```

### 4-3. 仮想環境を作成

```cmd
python -m venv venv
```

**所要時間**: 30秒〜1分。プロンプトが戻ってきたら完了。

### 4-4. 仮想環境を有効化

```cmd
venv\Scripts\activate
```

成功すると、プロンプトの先頭に `(venv)` が表示されます。

```
(venv) C:\fx-signals>
```

> ⚠️ **PowerShellを使っている場合**、初回は実行ポリシーエラーが出ることがあります。その場合はコマンドプロンプト（cmd）を使うのが確実です。

---

## 5. 【Windows側】依存ライブラリのインストール

### 5-1. pip を最新化

```cmd
python -m pip install --upgrade pip
```

### 5-2. 依存ライブラリをインストール

**シンプル版（推奨）** — 最新の互換バージョンを自動選択:

```cmd
pip install -r requirements-runtime.txt
```

**所要時間**: 2〜5分。numpy, pandas のビルドで時間がかかります。

### 5-3. インストール確認

```cmd
pip list
```

以下のライブラリが含まれていればOK:
- `pandas`
- `numpy`
- `yfinance`
- `ta`
- `python-dotenv`

---

## 6. 【Windows側】動作確認（テストモード）

### 6-1. テスト実行

```cmd
python run.py --test
```

### 6-2. 期待される出力

```
============================================================
  FX Signal Bot - テストモード
============================================================

[2026-04-25 hh:mm:ss] チェック #1
  データ取得中... 3ペア取得完了
    USDJPY: xxx.xxx (最新: ...)
    EURUSD: x.xxxxx (最新: ...)
    GBPJPY: xxx.xxx (最新: ...)
  シグナルなし（または「>>> シグナル検出! <<<」）

============================================================
  テスト完了
  本番起動: python run.py
============================================================
```

### 6-3. Discord通知の確認

シグナルが検出された場合、設定済みのDiscordチャンネルに通知が飛ぶことを確認。

---

## 7. 【Windows側】タスクスケジューラ設定

> このセクションは Step 7 として別途案内します。動作確認まで成功したら、Claude にその旨を伝えてください。

設定するタスクは2つ：

| タスク名 | 内容 | 実行間隔 |
|---------|------|--------|
| FX Signal Bot - Scan | `run.py --once`<br>（5分ごとにシグナルスキャン） | 5分 |
| FX Signal Bot - Evaluate | `evaluate_signals.py`<br>（過去シグナルの勝敗評価） | 1時間 |

> ⚠️ 現状の `run.py` は無限ループ実行のため、タスクスケジューラ運用には `--once` モードの追加が必要です。これは Phase 1 の最終調整時に Claude が実装します。

---

## 8. 【Mac側】launchd 停止（最後）

Windows側の動作が24時間安定したことを確認した後に実施。

```bash
# 既存のlaunchdジョブを確認
launchctl list | grep fx

# 停止（実際のジョブ名に置き換え）
launchctl unload ~/Library/LaunchAgents/com.fx-signals.run.plist
launchctl unload ~/Library/LaunchAgents/com.fx-signals.evaluate.plist
```

> ⚠️ Mac停止前に、Windowsで2〜3回シグナル＆評価が問題なく動作したことを確認してから。

---

## 9. トラブルシューティング

### 9-1. `python` コマンドが見つからない

→ Python インストール時に「Add python.exe to PATH」のチェックを忘れた可能性。
**対処**: Python を一度アンインストールし、インストーラーで再インストール（PATH追加チェックを必ず入れる）。

### 9-2. Microsoft Store が開く（`python` 実行時）

**対処**: 「設定」→「アプリ」→「アプリ実行エイリアス」→「アプリ インストーラー python.exe」「python3.exe」を**両方OFF**。

### 9-3. `pip install` で SSL エラー

**対処**: 一時的にトラスト追加:
```cmd
pip install -r requirements-runtime.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

### 9-4. `yfinance` でデータが取れない

**対処**: ネットワーク・プロキシ設定を確認。会社PCの場合はファイアウォールが原因の可能性。

### 9-5. `.env` が読めない

→ ファイル名が `.env.txt` になっていないか確認（Windowsは拡張子を隠す癖あり）。
**対処**: エクスプローラー「表示」→「☑ ファイル名拡張子」をオン → 確認 → 必要ならリネーム。

### 9-6. 文字化けする（コマンドプロンプト）

**対処**: コマンドプロンプトで `chcp 65001` を実行してUTF-8モードに切り替え。

---

## 10. 完了後の状態

✅ Windows PCで `python run.py --test` がエラーなく動作する
✅ シグナル検出時に Discord 通知が届く
✅ `logs/signals.csv` `logs/results.csv` が Mac から引き継がれている

ここまで来たら **Step 7（タスクスケジューラ設定）** へ進んでください。
