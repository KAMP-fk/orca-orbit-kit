# Orca の3役と開発経路

持ち主の決定 [[2026-10-07-Devinを開発フローから外す]] を適用する。
配線は [roles.json](../roles.json)、案件の実行と引渡しは [banana-engineering.md](banana-engineering.md)。

- Tomato は幅広い相談・意図・判断材料の整理を担当する（Fable / medium）。
- Banana は Tomato と並ぶ独立した開発窓口で、Owner の直接依頼も受ける。
  Codex（Sol）で開発を進め、旧 Kiwi / Melon の基盤保守を担当する。
  意図・受入範囲は Tomato に相談し、開発の依頼・質問・報告で連携する。
- Potato は実装・修正に未関与の独立レビュー担当（汎用技術確認は Opus 5.5 / high）。
  固定 full SHA の別 checkout を読み、指摘を Banana に返す。自己 PASS を行わない。

`banana develop` は Codex を使う。専用 checkout・成果保持・レビュー引渡しは
実装エンジンに依存せず開発の印で選ぶ。Devin は開発に使わず、既存 CLI・設定・履歴を残す。
新しい常設 role は増やさない。既存 automation / session の停止・再起動はこの source 変更から推定しない。

最終レビュー・署名 verdict のモデル、effort、独立性と起動方式は対象プロジェクトの現行契約と
最新のユーザー指示を優先する。concafe の固定 SHA 最終 verdict は CAF-279 / ADR-061 の
未関与の別 Codex タスク（Astra high）、上位判断は Astra medium の別タスクに従う。
必須 CI・固定 SHA 署名・自動 Ready / guarded auto-merge・人間ゲートを維持する。
技術確認や計画を正式 PASS に転用しない。

2026-10-01 時点の旧内容は [history/agent-routing-20261001.md](history/agent-routing-20261001.md)。
