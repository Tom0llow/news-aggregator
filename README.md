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
  重複キー、取得状態に加え、このアプリから記事リンクを開いた累計回数を保存します。
  本文・画像・enclosureは保存しません。
- 記事は自動削除しません。同じ保守的な正規化URLはDBの一意制約で重複登録しません。
- DB本体、WAL、SHM、journalの合計容量は画面上で確認できます。
- 検索対象はタイトル・概要・カテゴリ・タグです。空白区切りはAND、各語は部分一致です。
- 記事カード下部のカテゴリボタンで完全一致のカテゴリ一覧へ絞り込み、最新順または
  閲覧数順に切り替えられます。同じ閲覧数の記事は最新順で安定して表示します。
- 「閲覧数」は配信元の数値ではなく、このローカルアプリから記事リンクを開いた累計回数です。
  新規・既存記事は0回から始まり、計数に失敗しても外部記事を開く動作は妨げません。
- 日付検索は日本時間の一日を境界に使います。日時不明の記事は、日付指定なしの検索には
  含まれ、画面では「日付不明」と表示します。
- お気に入りと保存キーワードは版付きのブラウザ `localStorage` だけに保存します。
  サーバーDBにはユーザー情報を持ちません。ブラウザのサイトデータを消すと失われます。

ローカル閲覧数は記事単位の集計値だけをSQLiteへ保存し、閲覧日時、個人識別子、参照元は
記録しません。ただし記事ごとの関心を推測できるデータなので、DBとバックアップは他の保存記事と
同様に利用者自身で保護してください。

長期保存データを保全する場合は、アプリを停止してから `news.db` をバックアップしてください。

## ローカルJSON API

`GET /api/articles` は既存の検索parameterに加えて、`category` の完全一致絞り込みと
`sort=latest|views` を受け付けます。`sort` 省略時は `latest` です。

`POST /api/articles/{id}/views` は記事リンク選択時のローカル閲覧数を1加算します。他の更新APIと
同様に、同一originから `Content-Type: application/json` で空オブジェクト `{}` を送る必要があり、
存在しない記事IDには404を返します。

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
`docs/decisions/ADR-001-local-news-aggregation-architecture.md`、
`docs/decisions/ADR-002-local-article-view-counts.md` を参照してください。
