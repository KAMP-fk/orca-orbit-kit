# エージェント統合の初回記録（2026-10-06 JST）

この記録は初回統合時点。Owner の追補により Banana を開発窓口として復帰し、
現在は独立した Tomato ⇄ Banana（Codex 開発）と、案件ごとの Potato。
2026-10-07 JST の Owner 指示により Devin は利用しない。
現行は [Banana 統合](banana-engineering.md)。以下の表・ホーム数・検証は初回時点の記録。

Owner の「いらないエージェントを統廃合」「合わせてリファクタリング」の直接依頼。
対象は Orca の名前付きエージェント定義・起動・レビュー受付・配線・関連する技術手順。
既存 Devin 移行とレビュー証拠の未コミット変更を保全した。

| 変更前 | 現在 | 理由 |
|---|---|---|
| Tomato | Tomato | 相談と実装・独立承認の境界を維持 |
| Kiwi / Melon | Maintenance | 観測・証拠・引継ぎ基盤の実装を統合。案件管理を二重に持たない |
| Peach / Potato | Review | レビュー種別で処理を選び、常設人格を増やさない |
| 旧 Banana | 廃止を維持 | 製品実装は外部 Devin。履歴と既存稼働は別に確認する |

`roles.json` は3役、常設ホームは Tomato / Review の2つ。
Maintenance は必要時の案件 checkout。Devin Session や正式最終レビューの別タスクは、待機用 role として登録しない。
Review の技術確認は read-only の Sol high。実装担当がその成果を独立承認しない。
concafe の全レビューと、全プロジェクトの final は現行の別タスク経路へ渡す。

## 共通化した機構

- Codex launcher を一本化し、旧 Potato 固有の起動・profile・backend 分岐を撤去。
- 編集担当は `roles.json` の access から決め、role 名の列挙を案件管理に重複させない。
- `installation.py` に現行・廃止リンクを宣言し、旧 reviewer installer も同じ入口へ委譲。
- 受入 wrapper は `acceptance-task`、公開窓口は `review --kind acceptance / technical / final`。
- 新規品質 outbox は `review`。旧 Peach / Banana / Kiwi の耐久記録を書換えず、旧担当を再起動しない。
- Codex の結果 metadata は正式 verdict ではないことを明示する。
- 現行の文書・Tomato の技術的な受け渡し参照を新しい担当へ更新。旧移行の検証記録は history へ保全。

## 実機反映の確認

`install.py --tab-autostart` は、所有を確認した旧 command / skill / profile 16リンクを撤去した。
`install.py --check --tab-autostart` は exit 0。Orca の skills installed は Tomato / Maintenance / Review の3役を返し、旧名は登録されていない。
`setup` は既存 Activity タブを再利用。`setup --check` は表示差分なし・exit 0。
`start-workspaces --check` は既存の Tomato / Review の2ホームを返した。モデルを起動していない。

Orca の UI で旧 Kiwi / Melon / Potato の3ホームを Sleep にし、Inactive の表示を確認した。
「スリープ中を非表示」を有効にし、旧3ホームが通常一覧から消えたことを確認。
workspace / branch / 未コミット変更 / タブの復元情報は保全した。
旧「Melon・Kiwi・Potato の起動／復元」Quick Command は、
`start-workspaces --check` の「Orca｜構成・稼働確認」に更新し、保存後の表示を確認した。

旧 Banana の稼働中観測・時計 automation はこの整理で停止・移設していない。
Devin の外部接続は既存の未設定状態。CI supervisor / 署名鍵 / GitHub / Linear / 本人ゲートは変更していない。
休止中カードは表示フィルターを解除して復元できる。ソース更新を全既存セッションの再読込と扱わない。

## 検証

すべてのモデル・サービス呼出しは fixture、一時 Git / state / ソケットに隔離した。
初回の全体検査は既存 relay テストの古い成功データと、sandbox 内の Unix ソケット作成で失敗した。
relay 実装は変更せず、現行 CAF-308 の3識別行を成功データに追加した。
各行の欠落がモデル起動・status投稿前に拒否されることも検査する。
ソケットは適切な実行権限で一時ディレクトリ内だけを検査する。
最終全体検査 `python3 -B -m unittest discover -s tests -q` は
356件・285.147秒・exit 0（OK）。一時ソケットを含む隔離 fixture の検査は
必要なローカル実行権限で行った。
Python 構文、shell 構文、実行ファイル属性と文書のローカル参照も確認した。
`git diff --check` は Orca / Tomato の両リポジトリで exit 0。

この依頼では正式な独立 verdict を発行せず、テスト成功を自己 PASS にしない。
モデルの実呼出しや実サービスへの投稿を検証に使っていない。

## 保全と復元

着手時の source / test スナップショット:
`/var/folders/l3/m0m_2xsd23q4wr1rczgxqc180000gn/T/orca-agent-consolidation-5h1i9of1`。
旧 role 定義は Git の履歴とこのスナップショットに残る。
他担当の未コミット成果と混ぜて commit していない。
復元は対象の差分を確認してから行い、runtime 台帳、鍵、persona / brain をコピーしない。
