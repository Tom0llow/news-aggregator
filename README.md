# news-aggregator

自分専用の、日本語ニュースを見出し単位で保存・検索するローカルWebアプリです。
ログイン機能はなく、`127.0.0.1` だけで待ち受けます。記事本文と画像は取得・保存しません。

## 必要環境

- Python 3.11以上
- [uv](https://docs.astral.sh/uv/)

外部の実行時依存はなく、Python標準ライブラリだけで動作します。

```powershell
uv sync --locked
```

## 起動

```powershell
uv run news-aggregator serve
```

ブラウザで `http://127.0.0.1:8765` を開きます。起動後、初回取得をバックグラウンドで
開始し、その後は30分ごとに取得します。`Ctrl+C` でサーバーと取得処理を停止します。

DB保存先とポートは変更できます。`--host` はIPv4 loopback以外を拒否します。

```powershell
uv run news-aggregator serve --db D:\news-data\news.db --port 9000
```

全フィードを1回だけ取得する場合:

```powershell
uv run news-aggregator fetch --db data\news.db
```

ネットワーク障害などで一部フィードが失敗した場合も、残りの取得は続きます。単発取得は
一部失敗をJSONで表示し、終了コード1を返します。

## 保存と検索

- SQLite DBの既定保存先は `data/news.db` です。
- タイトル、プレーンテキストの概要、元記事URL、ソース、発行元、日時、カテゴリ、タグ、
  重複キー、取得状態だけを保存します。本文・画像・enclosureは保存しません。
- 記事は自動削除しません。同じ保守的な正規化URLはDBの一意制約で重複登録しません。
- DB本体、WAL、SHM、journalの合計容量は画面上で確認できます。
- 検索対象はタイトル・概要・カテゴリ・タグです。空白区切りはAND、各語は部分一致です。
- 日付検索は日本時間の一日を境界に使います。日時不明の記事は、日付指定なしの検索には
  含まれ、画面では「日付不明」と表示します。
- お気に入りと保存キーワードは版付きのブラウザ `localStorage` だけに保存します。
  サーバーDBにはユーザー情報を持ちません。ブラウザのサイトデータを消すと失われます。

長期保存データを保全する場合は、アプリを停止してから `news.db` をバックアップしてください。

## ニュースソースと利用条件

| ソース | 状態 | 取得方針 |
| --- | --- | --- |
| Yahoo!ニュース | 有効 | 公式カテゴリRSS。リンクはYahoo!のポータル記事。RSS日時は「ポータル提供日時」と表示 |
| GIGAZINE | 有効 | 公式RSS 2.0。本文・画像は保存しない |
| ITmedia | 有効 | 私的ローカル利用限定。配信タイトルと発信元を保持し、概要は安全側で空欄 |
| Ledge.ai | 無効 | 公式RSS/APIと利用許可を未確認のため、ネットワークアクセスしない |
| Publickey | 有効 | 公式Atom。`summary` のみ使い、`content` は無視 |
| ASCII.jp | 有効 | 公式RSS。`ttl=60分` を優先し、成功後60分未満は取得を見送る |

固定した公式フィードURL以外を取得するAPIはありません。ログイン、会員限定ページ、CAPTCHA、
HTML本文、コメントにはアクセスしません。このアプリを外部公開・共有・商用利用する前には、
各配信元の最新条件を改めて確認してください。

## 検証

テストは実ネットワークへアクセスしません。

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run pytest --cov=src --cov-report=term-missing --cov-report=xml
```

設計判断は `ARCHITECTURE.md` と
`docs/decisions/ADR-001-local-news-aggregation-architecture.md` を参照してください。
