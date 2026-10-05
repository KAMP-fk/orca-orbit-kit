# Named agents on Orca

常設の窓口は **Tomato・Banana・Review の3つ**。
現行の責任・起動条件・レビューの効力は [team-topology.md](references/team-topology.md)、
3窓口への移行記録は [three-entry-plan.md](references/three-entry-plan.md)、
機能・文書の整合性整理は [consistency-refactor.md](references/consistency-refactor.md)。
`roles.json` が役・常設/必要時・受付先・profile/skill の正本。
専門担当の能力とコマンドは残すが、固定ホームや待機モデルを必要条件にしない。

| 窓口/専門担当 | 責任 | 起動 |
|---|---|---|
| Tomato | Owner の相談、目的・前提・判断材料、開発の受け渡し | 常設ホームの新規タブで Codex 対話入力待ち |
| Banana | 開発の分解・割当・通常実装・検証・統合・完了追跡 | 常設ホームの新規タブで Codex 対話入力待ち |
| Review | 受入確認・技術確認・最終判定の受付 | 既存 Peach ホーム。依頼なしではモデルを起動しない |
| Kiwi | 観測・自動検知・鮮度・取得失敗・履歴・引継ぎ基盤の実装 | Banana の依頼ごとの案件 worktree |
| Melon | レビュー packet・CI 照合・判定基盤の実装 | Banana の依頼ごとの案件 worktree |
| Peach / Potato | AC の受入確認 / 固定差分の独立技術確認 | Review で必要な種別だけ明示選択 |

Fable は判断時だけの相談先。Owner 判断待ちでは [owner-decision.md](references/owner-decision.md)
に従い、Fable 確認後に推奨案と理由付きの選択肢を提示する。返答なしを承認と読まない。

## 案件の受付

通常の製品実装は Banana。Kiwi/Melon は該当する基盤の変更だけ担当する。
一件ごとの依頼を UTF-8 ファイルで渡し、編集は隔離 worktree、読み取りは対象 checkout を使う。

```sh
banana --repo /absolute/checkout --task-id product-fix-001 --prompt-file /absolute/request.md
kiwi --repo /absolute/checkout --task-id watch-fix-001 --from-role banana --prompt-file /absolute/request.md
melon --repo /absolute/checkout --task-id packet-fix-001 --from-role banana --prompt-file /absolute/request.md
# 上記と同じ Banana 基準の共通実装
~/.agents/skills/banana/bin/task --role kiwi --repo /absolute/checkout \
  --task-id watch-fix-001 --from-role banana --prompt-file /absolute/request.md --dry-run
```

対象・編集範囲・AC・実際の委任・完了条件を揃える。受領済み checkout/依頼 ID の packet は
そこで実行し、再投入してさらに worktree を作らない。通常の割当・結果回収・統合は Banana。
共通処理、排他、成果保持、cleanup は [project-tasks.md](references/project-tasks.md)。
依存・統合・native Run/Task/Dispatch が必要な場合は [orca-operating-model.md](references/orca-operating-model.md)。
モデルを変えても、実装者の独立性や権限は変わらない。

## レビューの受付

```sh
review --inbox
review --kind acceptance --repo /absolute/checkout --issue ABC-123 --dry-run
review --kind technical --repo /absolute/checkout --prompt-file /absolute/review.md --dry-run
review --kind final --repo /absolute/checkout --sha <current-full-HEAD-SHA> --pr owner/repo#123 --dry-run
```

種別は必須。受入確認と技術確認を両方自動起動しない。
受入確認は `--issue`、技術確認は `--prompt-file`、最終判定は `--sha` を必須にする。
受入確認の `--pr` / `--sha`、技術確認の `--issue` / `--pr` など、用途と合わない指定は拒否する。
最終判定の `--pr owner/repo#N` は checkout の origin と一致させる。
引渡し計画には checkout の観測 SHA・未コミット変更の有無、依頼本文・path・hash を残す。
最終判定と concafe のレビューの非 dry-run は exit 3（引渡し待ち）。計画をレビュー完了や PASS と扱わない。
共通入口は新規 subagent・別タスクへの送信・署名・Ready/merge を自動実行しない。

モデルと独立性は [team-topology.md の Owner 指示](references/team-topology.md#この依頼に適用する-concafe-owner-指示) に従う。
concafe は指定モデルと独立性を確認する正式な別 Codex タスク経路へ返す。
他プロジェクトの個別依頼だけ、既存 Peach evidence pipeline / Potato の技術確認を選択できる。
受入確認は origin の GitHub repository を `--expected-repo` として pipeline に渡す。
候補 PR が別 repository に属すれば取得・モデル起動前に停止する。PR のレビュー SHA は
pipeline が一次証拠から固定するため、checkout の観測 SHA と同じとは限らない。
旧 `peach` / `potato` は互換コマンド。共通受付による整理を、旧 backend 実装を移行済みという意味にしない。

## 新規タブと配線

```sh
/Users/kamp/orca/agents/named-team/install.py --tab-autostart
/Users/kamp/orca/agents/named-team/install.py --check --tab-autostart
/Users/kamp/orca/agents/named-team/bin/start-workspaces --check
/Users/kamp/orca/agents/named-team/bin/start-workspaces melon --check
```

`start-workspaces` の既定確認は Tomato・Banana・Review の3ホームだけ。
Review の canonical role key は互換の `peach`。表示名は `Review｜受入・技術レビュー`、旧 Peach 名も認識する。
専門担当を明示した確認は、その受付先と `state=on-demand` を返す。旧専門ホームの存在は不要。
同名・別 project のカードを代替ホームにせず、候補重複・不完全な一覧・受付欠落では停止する。
`state=ready` は受付が見つかった意味で、モデルの稼働を意味しない。

所有する `.zshrc` block は `shell/tab-autostart.zsh` を読む。
Orca の対話 login zsh、terminal handle、完全な worktree ID と exact home path が一致した場合だけ適用。
Tomato/Banana は依頼なしの Codex 対話、Review はモデル無しの案内で shell に戻る。
Kiwi/Melon/Potato の旧ホームやサブディレクトリでは自動起動しない。
明示した初期コマンド、同じ handle の再読込、入れ子の shell を優先し二重起動しない。
既存の実行中セッション・タブ・成果は変更しない。新規タブから適用する。

install は所有する command/skill/profile リンクと opt-in shell block だけを扱う。
`review` はモデル無しの CLI で、専用 model profile や追加 role/card は作らない。
base config・trust・approval・sandbox・認証・秘密値は変更しない。別のファイル/リンクは保持し中断する。
Tomato の skill 正本と記憶は別 repo/brain に残す。専門担当が人格・日誌を継承することはない。

## 実行と回収

依頼付きの通常起動は一件ごとの見える実行タブ。手動対話の継続は `--interactive --orca` を明示する。
新規の編集依頼は `--repo` の共通入口を使う。互換の `--cwd` / `--task` は
指定済み checkout での直接実行で、編集用 worktree を新しく作る入口ではない。
`--dry-run` は起動設定/経路計画のみで、Orca/model/サービス/state を変更しない。
Sol の通常 effort は medium、用途別は [sol-effort.md](references/sol-effort.md)。
モデル/provider の自動 fallback、Git/trust/permission の迂回はしない。

結果は private な `~/.local/share/named-team/tasks/` / `projects/` に保存する。
同じ依頼 ID は排他・開始記録で再実行を防ぐ。不明な作成/起動を再送しない。
子プロセス終了と結果保存を確認して、その回の owned terminal だけを閉じる。
変更・未統合 commit・ignored file・他担当の terminal を持つ worktree は保持する。
回収と製品の完了、実装テストと独立 verdict を区別する。

## concafe の自動検知

対象は Owner が指定した concafe-techo のみ。Issue/PR/CI をモデル無しで取得・比較する。
通常変化と取得障害/回復は Banana、相談分類は Tomato。Kiwi は基盤修正の明示依頼時だけ使う。
旧 pending Kiwi の履歴は保持し、Banana と同じ受付で未完了/unknown batch があれば次を起動しない。
初回基準・無変化・通常 CI 進捗ではモデルを起動しない。

監視ソースを更新しても、稼働中 coordinator が読み込んだコードは自動では変わらない。
この整理では live DB、automation、監視プロセス、CI supervisor を変更・再起動しない。
保存・排他・回収と実稼働確認は [event-monitor.md](references/event-monitor.md)。
旧編成・導入 receipt は同文書からリンクする履歴に保存し、現在の状態とは区別する。
