# Orca を最終品質ゲートとして使う

`Tomato ⇄ Banana → Devin 開発 worktree → Potato worktree → guarded merge / 完了確認` を標準とする。
Devin は一件の調査・実装・検証・PR・指摘修正を直接実行する。
Orca は並行 Issue/Session/branch/PR の対応、受入確認、CI、QA、独立レビューと完了を追う。
通常の実装の分解・再委譲を常設agent経由で行わない。

Orca の Run/Task/Dispatch と worktree 機能は、既存レビュー・独立した保守・観測の必要時だけ利用する。
CLI は `orca-cli` / `orchestration` の版対応ガイドに従い、存在しない Devin provider を worker-start へ渡さない。
ローカル Devin CLI は [Banana 開発](banana-engineering.md)、外部 Issue 接続は既存 [command adapter](devin-operations.md) へ隔離する。
Orca controller はレビューを自動 PASS にせず、未関与の正式経路の現在 SHA の結果を読む。
問題は同じ実装 Session へ返し、別 branch やPRを作らせない。
契約が許す極小修正を Orca が行った場合は、その版の独立レビュー資格を失う。
