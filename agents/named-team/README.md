# Named agents on Orca

五役の責任・引き渡し先・判定の効力は [references/roles.md](references/roles.md)。
今回の計画は [references/refactor-plan.md](references/refactor-plan.md)。
役割名、workspace 名、provider、effort、skill の場所は `roles.json` が正本。

| 名前 | 責任 | 通常の実行 |
|---|---|---|
| Tomato | 相談・判断材料・受け渡し | Codex gpt-6.1-sol / medium |
| Banana | 承認済み開発の進行・実装・統合 | Codex gpt-6.1-sol / medium |
| Kiwi | 観測・引き継ぎ基盤の実装 | Codex gpt-6.1-sol / medium |
| Peach | In Review Issue の AC 判定 | 既存の evidence pipeline、Claude Opus 5.5 / high |
| Potato | 固定差分の未関与技術確認 | Claude Opus 5.5 / high、Read / Glob / Grep |

Melon の既存定義は維持する。モデルの自動 fallback はしない。
skill を適用しても今のチャットの model/effort・関与歴・権限は切り替わらない。
concafe の正式な最終レビュー・判断は現行の別 Codex タスク経路を使う。

## 呼び出し

Codex のチャットでは `$tomato` / `$banana` / `$kiwi` / `$peach` / `$potato`。
新しい skill がまだ表示されない場合は次のチャットで読み込む。
人格と記憶の原本は brain に残す。定義の編集だけで日誌・窓口を更新しない。

ターミナルの依頼は UTF-8 ファイルで渡せる。内容を shell 展開せず、改行と引用を保持する。

```sh
banana --cwd /path/to/project --prompt-file /path/to/request.md
kiwi --cwd /Users/kamp/.claude/skills/Tomato --prompt-file /path/to/request.md
potato --cwd /path/to/project --prompt-file /path/to/review.md
peach --orca CAF-123 --pr owner/repo#123
```

依頼付きの通常起動、`--task`、旧 `--exec`、依頼付き `--orca` は一件ごとの新しい見えるタブ。
対話を続ける場合は明示して起動する。

```sh
tomato --interactive --orca --cwd /Users/kamp/brain
banana --dry-run --cwd /path/to/project --prompt-file /path/to/request.md
peach --dry-run CAF-123 --pr owner/repo#123
```

`--dry-run` は起動設定だけを返す。モデル/Orca セッション・外部取得は行わない。
Codex の複雑な実装は `--effort high`、明示モデルは `--model <ID>`。
Potato のモデルと effort は固定。Peach の既存 `--backend codex` は明示互換だけ。
`--json` は Potato の検証済み result metadata を返す。

`--cwd` は対象コード、`--worktree path:<絶対パス>` は登録済みのタブ配置先。
名前付き launcher で両方を指定した場合は path の一致を検証する。
Peach は packet で読むため checkout を実装用 cwd にせず、`--worktree` は配置先だけを指定する。
Orca が返す完全な worktree ID と唯一の terminal handle で追跡する。remote 環境の shell からは起動しない。

## タスクと回収

一件ごとに新しいタブを表示し、途中の出力を流す。
結果は `~/.local/share/named-team/tasks/<role>-<id>/` の `result.txt`、`error.txt`、`finished.json` に保存する。
Peach の正式な packet/ledger/verdict は既存の保存先に残り、Orca task の結果はその回の出力を回収する。
Potato は実応答の session/modelUsage を確認し、5.5 以外・複数モデル・不明なら BLOCKED。
保存・回収・子プロセスの終了を確認してから、その回のタブだけを閉じる。
次のタスクを待機セッションへ追加しない。対話セッションは自動で閉じない。

タブ作成の応答がタイムアウトしたら一意の title で同じタブだけを照合し、再作成・再送しない。
開始・保存・終了・close を確認できなければタブと結果を保持して未確認と返す。
起動要求、タブ作成、モデル応答、完了、cleanup を別々の事実として扱う。
rc=0 や指摘なしを独立 PASS・署名・Ready/merge と読まない。

## 配線と正本

```sh
/Users/kamp/orca/agents/named-team/install.py
/Users/kamp/orca/agents/named-team/install.py --check
/Users/kamp/orca/agents/linear-inreview-reviewer/install.sh --check
/Users/kamp/orca/agents/named-team/bin/start-workspaces --check
```

`install.py` は Tomato/Banana/Kiwi/Potato/Melon の command・skill・role profile を配線する。
Tomato の skill 正本は独立 Git repo の `~/.claude/skills/Tomato`。
Banana の正本は `roles/banana/skill`。従来の `~/.claude/skills/Banana` は互換リンク。
Kiwi/Potato/Melon の正本も `roles/<name>`。Peach の配線と packet は既存 package が持つ。
base config、trust、approval、sandbox 設定は変更しない。
全対象を先に確認し、無関係のファイル/リンクがあれば配線前に中断する。
`--uninstall` はこの package を指すリンクだけを外す。

`bin/start-workspaces` は六役のカードの準備・確認だけを行い、待機エージェントを起動しない。
Orca executable は ORCA_CLI_COMMAND、dev session、Linux、macOS の順に現行ガイドどおり選択し、別 build へ fallback しない。
操作を行う担当はその executable の `orca-cli`、監督付き連携のときだけ `orchestration` を読む。

モデルを起動する実依頼、外部投稿、automation、repo 操作の許可は現在のユーザー指示と対象契約から得る。
この定義は追加許可ではない。
