# Named agents on Orca

五役の責任・引き渡し先・判定の効力は [references/roles.md](references/roles.md)。
今回の計画は [references/refactor-plan.md](references/refactor-plan.md)。
役割名、workspace 名、provider、effort、skill の場所は `roles.json` が正本。
brain の Tomato/Banana を上位層、Banana 配下の Peach/Kiwi/Potato を専門担当とする。通常の割当・回収は Banana、相談事項の確認は Tomato または Fable。構成・相談の分け方は [共通契約](references/roles.md) に従う。

| 名前 | 責任 | 通常の実行 |
|---|---|---|
| Tomato | 相談・判断材料・受け渡し | Codex gpt-6.1-sol / medium |
| Banana | 承認済み開発の進行・実装・統合 | Codex gpt-6.1-sol / medium |
| Kiwi | 観測・引き継ぎ基盤の実装 | Codex gpt-6.1-sol / medium |
| Peach | In Review Issue の AC 判定 | 既存の evidence pipeline、Claude Opus 5.5 / high |
| Potato | 固定差分の未関与技術確認 | Claude Opus 5.5 / high、Read / Glob / Grep |

Melon の既存定義は維持する。モデルの自動 fallback はしない。
Sol 6.1 は通常 Medium、作業に応じて Low / High / xhigh / Max を使う。
用途・具体例・起動時の選択は [Sol effort 方針](references/sol-effort.md)。
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
対話を続ける場合は明示して起動する。担当ホームの通常の新規タブでも、以下の自動起動を使える。

```sh
tomato --interactive --orca --cwd /Users/kamp/brain
banana --dry-run --cwd /path/to/project --prompt-file /path/to/request.md
peach --dry-run CAF-123 --pr owner/repo#123
```

`--dry-run` は起動設定だけを返す。モデル/Orca セッション・外部取得は行わない。
Codex の effort は仕事に応じて `--effort low|medium|high|xhigh|max` で指定し、
省略時は Medium。明示モデルは `--model <ID>`。
Potato のモデルと effort は固定。Peach の既存 `--backend codex` は明示互換だけ。
`--json` は Potato の検証済み result metadata を返す。

## 担当ホームの新規タブ

Owner の指示により、Orca で担当ホームの通常の新規タブを開くと、その役の対話エージェントを
入力待ちで起動する。Tomato/Banana/Kiwi/Melon は既存 Codex profile の Sol 6.1 / Medium、
Peach/Potato は既存の Claude Opus 5.5 / High と読み取り制限を使う。
依頼や過去のセッションを渡さず、モデルを閉じると通常の shell に戻る。

```sh
/Users/kamp/orca/agents/named-team/install.py --tab-autostart
/Users/kamp/orca/agents/named-team/install.py --check --tab-autostart
```

`~/.zshrc` 末尾の専用 block から `shell/tab-autostart.zsh` を読む。
対話 login zsh、`TERM_PROGRAM=Orca`、terminal handle、完全な worktree ID と
`roles.json` の担当ホームが一致したときだけ適用する。他プロジェクトや担当ホームの
サブディレクトリには適用しない。Orca が明示コマンドを配送する shell-ready wrapper の
`ready` / `identity` を検出したタブでは起動せず、そのコマンドと入れ子の shell を優先する。
同じ handle の再読込・入れ子の shell でも二重起動しない。
既存タブの実行中プロセスには変更を加えない。新しく開くタブから適用する。
Orca の初期コマンド検出は現在の zsh wrapper に合わせており、他の shell には未適用。

Peach の対話タブは Issue の自動取得や署名レビューを開始しない。
実レビューは引き続き `peach <ISSUE-ID>` の evidence pipeline を使う。
concafe の正式な最終レビュー・判断の別 Codex タスク経路も維持する。
未確認フォルダの初回確認が出ることはあり、起動引数で迂回しない。
Codex の対話起動は `check_for_update_on_startup=false` をその回の引数だけに指定し、
更新案内で入力待ちが止まるのを防ぐ。インストール済みのバージョンは変更しない。

通常の install は shell 設定を変更しない。`--tab-autostart` は専用 block だけを追加し、
手編集された block や別の `.zshrc` リンクは保存して変更前に中断する。
`--uninstall` は所有する block とリンクだけを除去し、他の shell 設定を保持する。

`--cwd` は対象コード、`--worktree path:<絶対パス>` は登録済みのタブ配置先。
名前付き launcher で両方を指定した場合は path の一致を検証する。
Peach は packet で読むため checkout を実装用 cwd にせず、`--worktree` は配置先だけを指定する。
Orca が返す完全な worktree ID と唯一の terminal handle で追跡する。remote 環境の shell からは起動しない。

## タスクと回収

案件を受領して担当の作業場所を用意する共通機能は Banana を基準にする。
編集依頼は新規 worktree、読み取り依頼は指定 checkout、既存担当の継続は明示した worktree を使う。
各役のモデル・制限と、一件ごとの実行・回収は同じ実装を使う。

```sh
~/.agents/skills/banana/bin/task --role kiwi --repo /absolute/path/to/repo \
  --task-id watch-fix-001 --from-role tomato --prompt-file /absolute/path/to/request.md
kiwi --repo /absolute/path/to/repo --task-id watch-fix-001 \
  --from-role tomato --prompt-file /absolute/path/to/request.md
```

二つは同じ共通入口へ到達する。同じ repo・依頼 ID は再実行せず、保存した結果か未確認状態を返す。
通常の進行・回収は Banana が持ち、Tomato の単独観測基盤依頼では直接 Kiwi に渡せる。
受領・作成の確認、役の適用、結果、統合前の保持、cleanup は [案件用タスク](references/project-tasks.md)。
Peach の受入判定は既存の `peach <ISSUE-ID>` を使う。正式な concafe review/判断の経路も維持する。

一件ごとに新しいタブを表示し、途中の出力を流す。
結果は `~/.local/share/named-team/tasks/<role>-<id>/` の `result.txt`、`error.txt`、`finished.json` に保存する。
Peach の正式な packet/ledger/verdict は既存の保存先に残り、Orca task の結果はその回の出力を回収する。
Potato は実応答の session/modelUsage を確認し、5.5 以外・複数モデル・不明なら BLOCKED。
子プロセスの終了と結果保存を確認してから、`terminal close --terminal <handle> --tab` で
その回のタブと復元情報を永続的に除去する。モデル終了後の回収待ちは Python wrapper だけが
最大30秒残り、モデルを待機させない。
次のタスクを待機セッションへ追加しない。対話セッションは自動で閉じない。

タブ作成の応答がタイムアウトしたら一意の title で同じタブだけを照合し、再作成・再送しない。
タブ作成時に `--focus` は使わず、表示切替の応答をモデル起動の条件にしない。
モデルを起動できるのは、作成応答で確認した tab と同じ `ORCA_TERMINAL_HANDLE` の worker だけ。
応答を確認できない依頼は中止を記録し、後からタブが現れてもモデルを起動しない。
worker は依頼単位で排他し、開始記録を一度だけ作る。開始済み・完了済み・中止済みの依頼は
タブ復元後も再実行せず、既存の報告を上書きしない。プロセスが消えていても自動再試行しない。
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
`--uninstall` はこの package を指すリンクと専用の shell block だけを外す。

`bin/start-workspaces` は六役の既存ホームを確認し、通常実行では command/profile の配線も行う。カードや待機エージェントは作成しない。
役の起動先は `roles.json` の `workspaceRoot` で固定する。Tomato/Banana は既存の brain worktree、Peach は既存の reviewer project、Kiwi/Potato/Melon は既存の Orca 開発 worktree を担当ホームとして使う。従来の表示名も認識する。skills project はスキルを置く一つのフォルダとして維持し、役ごとのカードを置かない。
Orca 全体の一覧を取得してホームを照合し、同じホームに複数の候補がある場合や一覧が不完全な場合は配線・起動を止める。どの役でもホームが見つからない場合は停止し、代替カードを作らない。別案件の checkout は明示した `--worktree path:<絶対パス>` で指定する。
`--check` は既存ホームと専門担当の進行・回収先を読み取り確認し、`workspaceRoot` / `workspacePurpose=role-home` / `coordinatorWorktreeId` を返す。`state=ready` はホームが見つかったことを示し、モデルの稼働を意味しない。異なる project 間の役の上下関係は `parentRole` で管理し、同一 project 内に限られる Orca の Git ワークスペース親子関係を変更しない。
タスク保存と dry-run の `roleRouting` に上位/専門担当・通常の回収担当・相談先を記録する。この構成は実行中セッションを変更せず、相談先への送信や判断の委任を追加で許可しない。
Orca executable は ORCA_CLI_COMMAND、dev session、Linux、macOS の順に現行ガイドどおり選択し、別 build へ fallback しない。
操作を行う担当はその executable の `orca-cli`、監督付き連携のときだけ `orchestration` を読む。

モデルを起動する実依頼、外部投稿、automation、repo 操作の許可は現在のユーザー指示と対象契約から得る。
この定義は追加許可ではない。

## concafe-techo の自動検知

Owner が指定した concafe-techo のみを対象に、Issue・PR・open PR head の CI を
モデル無しで5分ごとに取得する。変化と担当の稼働を確認して、既存ホームで
Banana / Tomato / Kiwi の読み取りタスクを Orca の supervised worker として起動する。
初回の基準保存・無変化・通常の CI 進捗では起動しない。
計画、配送・排他・回収、運用と検知の限界は [event-monitor.md](references/event-monitor.md)。
