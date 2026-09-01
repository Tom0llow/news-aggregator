# ADR-001: ローカルニュース集計アーキテクチャ

- Status: Accepted
- Date: 2026-08-31
- Decision Owners: repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A

## Context

このアプリは、自分専用の日本語ニュースリーダーとしてローカルPCで動く。認証や外部公開は
不要であり、6ソースの見出しメタデータを定期取得し、無期限に検索できる必要がある。一方、
ニュース配信元の利用条件を守り、本文・画像・会員ページを扱わず、許可されていない収集へ
拡張できない境界が必要である。

Python 3.11以上と標準ライブラリだけで、単一プロセスとして保守できることも制約である。

## Decision

### 配置とWeb境界

- アプリは `http.server.ThreadingHTTPServer` をIPv4 loopbackにだけbindする。`Host` も
  loopbackリテラルに限定し、DNS rebindingによるローカル到達を拒否する。
- 認証、CORS許可、任意URL取得、外部スクリプト・画像は導入しない。手動取得は同一originから
  空のJSONをPOSTする固定APIだけにする。
- JSON APIと固定静的ファイルは `interfaces`、取得調停は `application`、所有型と純粋な規則は
  `domain`、SQLite・RSS・HTTP・schedulerは `infrastructure` に置く。composition rootは
  `main.py` だけとし、import時に副作用を開始しない。

### 永続化

- SQLiteをWAL modeで使い、`PRAGMA user_version` による順次migrationを行う。
- 記事本文と画像は保存しない。タイトル、プレーンテキスト概要、表示用URL、ソース、発行元、
  ソース種別、日時とその意味、取得日時、カテゴリ、タグ、重複キー、取得エラー欄だけを持つ。
- 記事の期限切れ・削除処理は作らない。フィード単位の最終試行、最終成功、エラー、スキップ、
  件数を別テーブルに保持する。容量はDB本体・WAL・SHM・journalの実ファイル合計とする。

### 取得と利用条件

- URLはコード内の固定allow-listとし、HTTP(S) RSS 2.0、RDF/RSS、Atomだけを読む。redirectは
  拒否し、識別可能なUser-Agent、15秒の既定timeout、5 MiBの上限を設ける。
- 30分のin-process schedulerとprocess内の取得lockを使う。フィード例外を個別に状態保存し、
  後続フィードを続ける。
- Yahoo!ニュースは9カテゴリの公式RSSを使う。リンクはYahoo!ポータル記事として保持し、
  元媒体URLとは扱わない。タイトル末尾から発行元を派生してよいが配信タイトルは変更しない。
  `pubDate` は元媒体の公開日時ではなく「ポータル提供日時」として保存・表示する。
- GIGAZINEは公式RSS 2.0を使う。
- ITmediaは私的なローカルRSSリーダーとして使い、発信元と配信タイトルを保持する。広告を意味で
  除外せず、descriptionは安全な概要と判断せず空欄にする。外部公開・共有・商用化を前提にしない。
- Publickeyは公式Atomの `summary` だけを使い、`content` は解析・保存しない。categoryのschemeが
  あればtag表現に残す。
- ASCII.jpは公式RSSの `ttl=60分` を優先し、直近成功から60分未満は30分jobでもskipする。
  enclosureと画像は無視する。
- Ledge.aiは公式RSS/APIと利用許可を確認できていないため、ソース状態には表示するが無効とする。
  許可確認前はHTML、sitemap、robotsで禁止されたAPIへ一切アクセスしない。

### 重複とURL

表示用の生URLとDB一意制約を持つ `duplicate_key` を分ける。重複キーはscheme/hostの大小、
既定port、fragment、および明確な追跡parameter（`utm_*`, `fbclid`, `gclid`, `yclid`）だけを
正規化する。path表記や残りのquery順序を変えず、内容の異なる記事を誤結合しないことを優先する。

### 日時・検索・ブラウザ状態

- aware datetimeをUTCで保存する。タイムゾーンなしのフィード日時はUTCとみなす。JSTの日付検索は
  `Asia/Tokyo` の日境界をUTCへ変換する。IANA timezone databaseを同梱しないWindowsでは、現代の
  日本時間と等価な固定UTC+9へ安全にfallbackする。日時不明はNULLとし、日付未指定なら検索対象に含める。
- タイトル・概要・カテゴリ・タグの各フィールドを対象に、空白区切り各語のAND、語ごとの
  literal部分一致を行う。日付指定時は日時不明を含めない。
- 保存キーワードとお気に入りは版付き `localStorage` だけに保存し、APIやSQLiteへ送らない。
  UIは動的値を `textContent` で構築し、記事URLをHTTP(S)に再検証して `noopener noreferrer` で開く。

## Rationale

単一利用者・単一PCという配置ではSQLiteと標準HTTPサーバーが十分であり、外部依存や別serviceを
増やさずにtransaction、一意制約、検索、状態表示を実現できる。固定allow-listとソースごとの
保守的な扱いは、一般的なscraperへ変質する危険を抑える。日時の意味とportal/directを型として
保持することで、Yahoo!の提供日時やリンクを元媒体の情報と誤認しない。

## Consequences

### Positive

- オフラインで決定的にテストでき、秘密情報やアカウントを必要としない。
- 一つのフィード障害が全取得を止めず、状態と容量をブラウザから確認できる。
- DB一意制約により、競合時にも同一重複キーを二重登録しない。

### Negative

- 標準ライブラリのXML/HTTP/UI実装を保守する必要がある。
- SQLiteのLIKE検索は大規模データで全文検索engineより遅くなり得る。
- process停止中の定期取得や複数processのscheduler調停は提供しない。
- redirectを必要とするように公式URLが変更された場合、allow-listの更新が必要になる。

### Neutral / Follow-on effects

- 無期限保存のbackupと容量管理は利用者が行う。
- 配信元条件やfeed URLが変わった場合は、実装・文書・契約テストを同時に更新する。

## Alternatives Considered

### Web framework・ORM・外部scheduler

実装量を減らせるが、この単一利用者構成には依存・upgrade面が過大であるため採用しない。

### HTML scraping

本文や構造の取得範囲が広がり、利用条件・robots・変更耐性のリスクが増す。公式feedのある5ソース
だけを有効にし、許可未確認のLedge.aiは無効とする方が要件に適する。

### aggressiveなURL正規化

queryのsort・一般parameter除去・pathの統合は重複を多く消せる一方、別記事を誤結合し得るため
採用しない。

## Validation

実ネットワークを使わず、RSS 2.0/RDF/Atom、無視対象、URL、日本語判定、SQLite一意制約・検索、
部分失敗、TTL、状態・容量、loopback HTTP、schedulerを自動テストする。Ruff、strict mypy、pytest、
branch coverage 80%以上を継続条件とする。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 配信条件・feed仕様変更 | 取得停止または条件違反 | 固定catalog、個別状態、文書化、明示的更新 |
| DB肥大化 | disk不足 | 自動削除せず容量を可視化し、利用者がbackup/容量管理 |
| 悪意あるfeed文字列 | XSSや資源消費 | byte/text上限、HTML plain化、textContent、CSP |
| ローカルserviceへの外部origin操作 | 意図しない取得 | loopback Host、JSON POST、CORSなし、origin確認 |

## Security / Privacy Impact

ネットワーク露出をloopbackへ限定する。認証情報・個人profile・本文・画像を持たない。記事メタデータは
無期限保持されるため、DBファイルのアクセス権とbackupはローカル利用者が管理する。

## Operational Impact

単一processを起動している間だけ30分schedulerが動く。source/feed状態と保存容量をUI/APIで確認する。
外部インフラ費用はない。

## Migration / Rollback

初期product schemaなので既存記事dataのmigrationはない。将来は `user_version` を一段ずつ更新する。
rollback時はprocessを停止してDBをbackupし、互換schemaを読むversionへ戻す。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `README.md`
- [x] API/user documentation

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-08-31 | Accepted | Initial local application architecture |
