# ADR-002: ローカル記事閲覧数を集計する

- Status: Accepted
- Date: 2026-09-06
- Decision Owners: repository maintainers
- Related Issues/PRs: N/A
- Supersedes: N/A
- Superseded by: N/A
- Extends: ADR-001

## Context

カテゴリ別の記事を関心の高い順でも確認したいが、RSSには配信元の閲覧数が含まれない。
ADR-001は保存対象を配信メタデータに限定し、操作状態はお気に入りと保存キーワードだけを
`localStorage`へ置くと定めている。したがって、ローカル操作から派生する値をSQLiteへ加えること、
その更新用POST境界、プライバシー上の性質を明示的に補足する必要がある。

## Decision

- 記事の「閲覧数」は、配信元の閲覧実績ではなく、このアプリのHTTP(S)記事リンクが選択され、
  同一originの計数リクエストが成功した累計回数と定義する。ページ到達、読了、利用者数は表さない。
- SQLite schema v2で `articles.view_count INTEGER NOT NULL DEFAULT 0` を追加する。v1の既存行と
  新規記事はいずれも0から始め、記事本文、閲覧日時、個人識別子、参照元は保存しない。
- `POST /api/articles/{id}/views` は既存のloopback `Host` 制約に加え、完全一致の同一 `Origin`、
  `application/json`、空JSONオブジェクトだけを受け付ける。存在する記事をSQLiteの単一更新文で
  原子的に1加算し、存在しないIDは404にする。
- 計数は外部記事を開く処理から分離したbest-effort操作とし、失敗時もnavigationを止めない。
- カテゴリ絞り込みは完全一致とする。閲覧数順は `view_count DESC` の後に、既存の最新順である
  `published_at NULLを後、published_at DESC、id DESC` を適用して決定的にする。
- カテゴリと最新順、カテゴリと閲覧数順の複合indexをschema v2で作成する。キーワード検索の
  対象・部分一致・AND条件は変更しない。

## Rationale

集計値を記事と同じSQLiteへ置けば、ブラウザの違いや `localStorage` 消去に左右されず、APIが
ページング前に一貫した閲覧数順を計算できる。イベント履歴ではなく累計値だけを持つことで、
目的を満たしながら行動履歴の詳細と保存量を増やさない。既存の同一origin空JSON POST境界を
再利用すると、外部originからローカル状態を変更できる面を広げずに済む。

## Consequences

### Positive

- カテゴリ一覧を最新順とローカルでの関心順の両方で確認できる。
- DB更新は競合するクリックを失わず、並び順は同数時にも安定する。
- 配信元に追加アクセスせず、外部の計測値と誤認しない表示にできる。

### Negative

- DBは記事ごとのローカルな関心を推測できる情報を無期限に保持する。
- APIを直接呼ぶ操作も加算されるため、配信元閲覧数や一意利用者数としては利用できない。
- schema v1だけを理解する旧アプリは、schema v2のDBをそのまま開けない。

### Neutral / Follow-on effects

- お気に入りと保存キーワードは引き続き `localStorage` だけに置く。
- 計数成功後の画面内表示は更新するが、閲覧数順の再配置は次回一覧取得時に反映される。

## Alternatives Considered

### ブラウザlocalStorageだけに保存する

サーバー側の永続化変更は不要だが、ブラウザやprofileごとに値が分かれ、ページング前の全記事を
SQLiteで並べ替えられないため採用しない。

### クリックイベントを時刻付きで全件保存する

詳細な分析はできるが、本要件に不要な閲覧履歴と保存量を増やすため採用しない。

### 配信元の閲覧数を取得する

RSSに存在せず、追加scraping/APIはADR-001の固定feed境界と利用条件上の制約に反するため採用しない。

## Implementation Notes

domainの検索条件がカテゴリと並び順を表し、application portが加算操作を公開する。SQLとmigrationは
infrastructure、query/POST検証とJSON変換はinterfacesに置く。新しい外部依存は導入しない。

## Validation

schema v1から既存行を保つmigration、既定値とindex、カテゴリ完全一致、両方の安定順序、並行加算、
存在しない記事、query境界、同一origin空JSON POST、JSON契約、UIの非阻害呼び出しを自動テストする。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 閲覧数を配信元の人気指標と誤認 | 誤った解釈 | UIと文書で「ローカル閲覧」と明示 |
| 外部originからの加算 | ローカル状態の汚染 | loopback Host、完全一致Origin、空JSONを必須化 |
| 更新競合による加算消失 | 並び順の不正確化 | SQLiteの `view_count = view_count + 1` を単一文で実行 |
| DBやbackupから関心を推測 | プライバシー漏えい | 詳細履歴を保存せず、ローカルファイル保護を明記 |

## Security / Privacy Impact

ネットワーク公開範囲は変えない。記事単位の累計回数は閲覧傾向を示し得るため個人利用データとして
扱うが、時刻、利用者識別子、IPアドレス、参照元は記録せず外部へ送信しない。DBの無期限保持と
backup保護は記事メタデータと同様に利用者が管理する。

## Operational Impact

schema v2へのmigrationが起動時に一度実行され、既存行へ0の既定値と2個の複合indexを追加する。
外部service、資格情報、追加processは不要である。

## Migration / Rollback

### Migration

アプリ起動時にv1の `articles` へ `view_count` を既定値0で追加し、複合indexを作成してから
`PRAGMA user_version = 2` とする。既存記事行と重複キーは変更しない。

### Rollback

失敗時はアプリを停止し、migration前のbackupへ戻す。migration後に旧v1アプリへ戻す必要がある場合、
まずv2 DBをbackupし、v1 schemaの新規DBへ `view_count` 以外の列をコピーして `user_version = 1` とする。
ローカル閲覧数はv1に表現できないため失われる。実行中DBを直接downgradeしない。

## Documentation Changes

- [x] `ARCHITECTURE.md`
- [x] `README.md`
- [x] API/user documentation
- [ ] `docs/rules/architecture.md`（実装規則の変更なし）

## Decision History

| Date | Status | Notes |
| --- | --- | --- |
| 2026-09-06 | Accepted | Local aggregate view-count persistence and POST boundary |
