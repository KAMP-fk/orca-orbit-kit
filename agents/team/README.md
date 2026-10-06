# Orca のエージェント構成

名前付き担当は **Tomato・Banana・Potato の3役**。常設ホームは Tomato と Banana の2つ。

| 担当 | 仕事 | 起動 |
|---|---|---|
| Tomato | Fable / medium で幅広い相談・目的・判断材料を整理、開発領域でBananaと連携 | 既存の相談ホーム |
| Banana | 開発窓口、Devin実装、ワークツリー管理、基盤保守 | 既存 Banana ホーム。新規タブはモデル無し受付 |
| Potato | Opus 5.5 / high 固定で受入・技術確認、正式独立レビューへの引渡し | Banana の案件配下に専用 checkout。必要時だけ |

旧 Kiwi と Melon は Banana、旧 Peach の受入判定と旧 Potato の技術確認は現在の Potato にまとめた。
Devin は Banana の実装エンジン。独立した常設 role を増やさない。
[責務と品質ゲート](references/team-topology.md) / [統合と移行](references/agent-consolidation.md) /
[実ファイル配置・表示](references/directory-layout.md)。

```text
Tomato ⇄ Banana → 開発 worktree（Devin）→ 固定 SHA の Potato worktree
            ↑                                │
            └────────── 修正要求 ────────────┘
```

Banana が対象と完了条件を整え、Devin が調査・実装・検証・指摘修正を担当する。
Orca は AC、現在 SHA、CI、必要な QA、独立レビュー、merge 後の完了確認を持つ。
[ローカル開発とレビュー](references/banana-engineering.md) は実機のベンダー Devin CLI を使う。
別の [外部 Issue adapter](references/devin-operations.md) は既存状態を維持する。
未設定の adapter は exit 3 で停止し、fixture 成功を接続成功と扱わない。
既存 vendor CLI を保全し、controller は `devin-flow` として配線する。

```sh
devin-flow start --issue CAF-301 --config /private/config/devin.json
devin-flow sync --issue CAF-301 --config /private/config/devin.json
banana --inbox
banana develop --repo /absolute/checkout --task-id feature-001 --from-role tomato --prompt-file /absolute/request.md --dry-run
banana review --repo /absolute/checkout --task-id feature-001 --dry-run
banana --repo /absolute/checkout --task-id watch-fix-001 --prompt-file /absolute/request.md --dry-run
plan --team CAF --repo KAMP-fk/concafe-techo        # Banana の朝の数え（読むだけ。bin/plan）
potato --inbox
potato --kind acceptance --repo /absolute/checkout --issue CAF-123 --dry-run
potato --kind technical --repo /absolute/checkout --prompt-file /absolute/review.md --dry-run
potato --kind final --repo /absolute/checkout --sha <current-full-HEAD-SHA> --pr owner/repo#123 --dry-run
```

保守は [共通案件手順](references/project-tasks.md) の worktree 排他と結果回収を使う。
Potato の技術・受入レビューは Opus 5.5（`claude-opus-5-5`）/ high 固定。受入確認は既存 evidence pipeline を使う。
concafe のレビューと全プロジェクトの final は正式な未関与の別タスク経路へ渡す。
技術確認やテスト成功を署名付き最終 verdict にしない。

`roles.json` が現行役の正本。role 定義、launcher、配線計画を共有する。
Tomato の対話と直接依頼は Claude Code の `--model fable --effort medium` を使う。
専用設定は `roles/tomato/claude/settings.json`、所有する installed profile は
`~/.claude/named-team/tomato.settings.json`。全体の Claude 設定は変更しない。
新規タブの対話も同じ launcher を使い、Codex への fallback や依頼の自動送信をしない。
自動イベント観測は独立した `observationBackend` / `observationProfile` で既存 Codex Sol を維持する。
Fable の会話設定を、プロジェクトの判断委任・独立レビュー・自動モデル起動の許可に読み替えない。
レビュー担当の公開名・コマンド・スキル・正規ディレクトリは Potato / `potato` / `roles/potato`。
旧 `review` コマンドと `roles/review` は同じ担当への互換経路。
Potato の専用設定は `roles/potato/acceptance/claude/settings.json` を共有し、
`~/.claude/named-team/potato.settings.json` へ登録する。旧 Codex の Potato / Review profile は所有リンクだけを撤去する。
別モデル指定は起動前に拒否し、実モデルの不明・別モデル・混在は結果を公開せず停止する。
耐久記録の role ID `review` と既存案件のキーを維持し、旧名のスキルを重複登録しない。
`install.py` は所有リンクだけを追加・撤去し、知らないファイルやリンクがあれば変更前に停止する。
Banana の共通スキルは Claude Code の `~/.claude/skills/Banana` にも登録し、
既存 Claude セッションから `/banana` で使える。Potato も `~/.claude/skills/potato` から同じ `roles/potato/skill` を指す
（2026-10-07。brain-kit v11 が置いた別定義の potato / kiwi は退役。[[2026-10-07-役はOrcaの3役を正としKiwiは常設しない]]）。
Potato の規準・記録・評価は `~/brain/review/`（規準 版 2）。起動 backend と Devin / Codex の実装経路は
`roles.json` の契約を維持し、Claude 用の別担当や必須レビュー経路は作らない。
Potato の表示窓口は `~/.local/share/named-team/entries/potato` のフォルダカード。
案内の正本は `roles/potato/entry/README.md` で、インストーラが所有リンクを登録する。
Orca のピン留めは Tomato、Banana、Potato、Orca 基盤の順に配置する。
表示窓口に常駐モデルや新しい Git checkout を作らず、実レビューは案件ごとの独立 checkout を使う。
受付タブはモデル無しの `potato --inbox` と通常 shell。休止中を隠す表示設定でも窓口を残す。
旧ホームの履歴・未コミット変更・session・台帳・鍵をソース更新で消さない。
`setup` は既存ホームの事前検査、表示の更新、モデル無し Activity タブの作成・再利用を行う。

```sh
agents/team/bin/setup --home /tmp/isolated-home
agents/team/install.py --check --tab-autostart
agents/team/bin/start-workspaces --check
python3 -B -m unittest discover -s tests -q
agents/team/bin/check              # 構文 + 両 repo のテスト + git diff --check をまとめて
```

[表示と観測](references/orca-activity.md) は接続未設定・古い出力・取得失敗を明示する。
`event-watch` はモデル無し取得・差分・耐久 outbox を維持する。
新規の品質イベントは `review`、明示 decision は Tomato、実装候補は Banana へ記録する。
旧 pending 記録は保全し、イベントからモデルや Devin を暗黙に起動しない。
稼働中の旧 coordinator が新コードへ切り替わったとは扱わない。
