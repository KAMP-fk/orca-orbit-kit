# Orca を最終品質ゲートとして使う

`Tomato ⇄ Banana → Codex 開発 worktree → Potato worktree → guarded merge / 完了確認` を標準とする。
2026-10-07 JST の Owner 指示により、Orca の運用で Devin は利用しない。
Banana の Codex（Sol）が一件の調査・実装・検証・PR・指摘修正を担当する。
Orca は並行 Issue/checkout/branch/PR の対応、受入確認、CI、QA、独立レビューと完了を追う。
通常の実装の分解・再委譲を常設agent経由で行わない。

Orca の Run/Task/Dispatch と worktree 機能は、既存レビュー・独立した保守・観測の必要時だけ利用する。
CLI は `orca-cli` / `orchestration` の版対応ガイドに従う。
開発は [Banana の Codex 経路](banana-engineering.md) を使う。
既存 Devin CLI・[command adapter](devin-operations.md)・設定・履歴は保全するが、起動・再開・再試行・fallback に使わない。
Orca controller はレビューを自動 PASS にせず、未関与の正式経路の現在 SHA の結果を読む。
問題は同じ実装 Session へ返し、別 branch やPRを作らせない。
契約が許す極小修正を Orca が行った場合は、その版の独立レビュー資格を失う。
