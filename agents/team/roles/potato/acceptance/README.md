# Potato の受入基盤

公開窓口は `potato --kind acceptance`。このフォルダは証拠取得、パケット作成、
固定 SHA・CI・判定検証の実装を持つ。独立した常設 Peach を起動しない。
技術確認と正式な最終レビューも同じ Potato 窓口で種別を選ぶ。
[現行の担当契約](../../../references/team-topology.md) を適用する。

```text
roles/potato/
├── skill/・codex/          共通 Potato 窓口
├── acceptance/            この受入パイプライン
│   ├── bin/・lib/          証拠取得と検証
│   ├── skill/              受入プロトコル
│   ├── claude/・codex/     既存 backend の互換定義
│   └── state/              保全した台帳とパケット（Git対象外）
└── relay/                  記録と署名ゲートを確認する中継部品
```

正規配置は `/Users/kamp/orca/agents/team/roles/potato/acceptance`。
旧 `agents/linear-inreview-reviewer` は実行中タブと過去の参照のための互換リンク。
`LINEAR_INREVIEW_*` 環境変数、内部識別子、台帳・パケット形式を維持する。
低水準の一覧・台帳・packet-only は `bin/linear-inreview-reviewer` を明示して使う。
旧 Peach / linear-inreview-reviewer の公開 command・skill・profile リンクは撤去済み。

`install.sh` は `../../../install.py` に委譲する。チーム全体で所有するリンクだけを配線する。
知らないファイルに衝突すれば変更前に止まる。既存履歴を削除しない。

```sh
python3 /Users/kamp/orca/agents/team/install.py --check --tab-autostart
./bin/linear-inreview-reviewer --ledger
./bin/linear-inreview-reviewer CAF-123 --packet-only --pr owner/repo#123
```

受入範囲と固定版の一次証拠から判定レポートを返す。実装・修正・外部反映は別担当。
2026-10-06 の Owner 指示により、レビューは Claude Opus 5.5（`claude-opus-5-5`）/ high 固定。
低水準の旧 command も別 backend の起動を拒否する。
concafe の現在 full SHA の最終独立レビューは、未関与の別タスクへ同じ Opus 5.5 / high を指定して引き渡す。
モデル指定は署名権限や最終 verdict の証拠を代替しない。
互換 backend の詳細は [既存パイプラインの記録](references/legacy-pipeline.md) を参照する。
fixture による検査は `python3 -B -m unittest discover -s tests -q`（Orca root）。

Involvement は対象の方針・実装・修正・指摘対応・中継依頼への関与を reviewer 自身が表明する。
すべてに関与していない場合だけ `NOT_INVOLVED`、関与がある場合は `INVOLVED`、確認不能は `UNKNOWN`。
Summary に未関与の定型文「本セッションは対象の方針・実装・修正・指摘対応・中継依頼のいずれにも関与していない。」を1行書く。
関与がある場合は何に関与したか、確認不能の場合は何を確認できないかを代わりに書き、対応する Involvement を記入する。
関与があれば正式な未関与担当へ返し、UNKNOWN は BLOCKED とする。
