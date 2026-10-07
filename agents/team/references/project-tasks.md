# Banana の開発・保守と共通案件手順

Banana の Codex 開発は [banana-engineering.md](banana-engineering.md)。
同じ機構を Banana の観測・証拠基盤保守と、Tomato / Potato の読み取りにも使う。

`bin/task`、`lib/checkout_context.py`、`lib/project_tasks.py`、`lib/project_workspaces.py` は
旧受付から抽出した共通機構。実装担当人格を呼ばない。
対象 repo / task ID で flock と耐久 record を使い、曖昧な worktree作成や起動を再送しない。
編集は Orca 管理の案件 worktree、読み取りは指定 checkout。
受領済み checkout と task ID がある担当はその場を使い、再帰的に新しい worktree を作らない。
共通の契約確認は [contracts.md](contracts.md)。

```sh
agents/team/bin/task --role banana --repo /absolute/checkout --task-id observation-001 --from-role tomato --prompt-file /absolute/request.md --dry-run
agents/team/bin/task --role banana --repo /absolute/checkout --task-id evidence-001 --from-role review --prompt-file /absolute/request.md --dry-run
agents/team/bin/task --cleanup --repo /absolute/checkout --task-id observation-001 --merged-into <verified-ref>
```

保存先は `~/.local/share/named-team/projects/<repo/task hash>/record.json` と `session/result.txt`。
保守の回収先は Banana、開発の印を持つ成果は専用 Potato checkout に渡す。
Tomato / Banana は異なる担当領域を持つ独立した窓口。開発依頼・意図の質問・成果報告で連携し、
Owner は Banana に直接依頼できる。Potato は Banana に指摘を返す。
旧 record の coordinatorRole / worktreeId と履歴は書換えない。
開発は plan / record の `development: true` で区別し、実装 backend に依存しない。
専用 checkout、CAF の案件 ID / branch、成果保持、固定 SHA のレビュー引渡しをこの印で選ぶ。
`banana review` は印のない旧 `workerBackend: devin` 記録も開発として読む。
通常の Codex 保守・読み取りは開発扱いにしない。
根拠は [[2026-10-07-Devinを開発フローから外す]]。
排他は同じ repo/task ID 単位。既存 Devin controller の外部原子claim・台帳は変更しない。

変更・未統合commit・ignored file・他担当terminal・不明な実行が残れば保持する。
結果保存と自分のterminal終了を確認し、所有する安全な worktreeだけ削除する。
既存 checkoutや役のホームはcleanup対象にしない。
統合・独立レビュー・CI・merge後の完了確認は観測した事実で区別する。
