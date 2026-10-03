# Melon / Kiwi / Potato

Orca 関連の開発で使う名前付き role。2026-10-02 の追加担当を再利用できるよう、skill・profile・起動コマンドを用意した。
Tomato・Banana は既存の名前と人格を維持する。

| 名前 | 担当 | 実行の既定 |
|---|---|---|
| Melon | レビュー基盤・証拠パケット・CI照合の実装改善 | gpt-6.1-sol / medium |
| Kiwi | 観測の鮮度・状態履歴・引継ぎ基盤の実装改善 | gpt-6.1-sol / medium |
| Potato | 実装に未関与の別担当として技術確認 | Claude Opus 5.5 / high、Read / Glob / Grep |

## 呼び出す

Codex のチャットでは `$melon` / `$kiwi` / `$potato` を指定する。表示名は Melon / Kiwi / Potato。
現在のセッションに新しい skill がまだ表示されない場合は、新しいチャットで読み込む。
skill の適用は今のチャットに役割の手順を読み込む操作で、モデル・effort・sandbox や関与歴を切り替えない。
別セッションと profile が必要なときは、以下の起動コマンドを使う。

ターミナルでは同名コマンドを使う。依頼を渡すと、役ごとの Orca 作業場所にタスク専用タブを新設する。
2026-10-03 の Owner 指示により、1タスクにつき新しいセッションを起動し、結果を保存・回収してからそのタブを閉じる。
常駐の待機セッションへ依頼を追加しない。次のタスクは別セッションで起動する。

```sh
melon --cwd /Users/kamp/orca 'レビュー基盤の取得失敗処理を改善して'
kiwi --cwd /Users/kamp/.claude/skills/Tomato 'watch の状態履歴を調べて改善して'
potato --cwd /Users/kamp/orca '指定した完成差分を独立に確認して'
```

複雑な技術作業は `--effort high`、今回の明示モデル指定は `--model <ID>` で渡す。
自動 fallback はしない。profile の effort に加え CLI 引数でも指定する。

```sh
melon --dry-run '今回の依頼'
kiwi --exec --cwd /path/to/workspace '今回の依頼'
potato --orca --worktree path:/Users/kamp/orca --cwd /Users/kamp/orca '今回の技術確認'
```

`--dry-run` は起動引数とタスク運用の設定を JSON で返し、セッションを作らない。
通常の依頼、`--task`、旧 `--exec`、依頼付き `--orca` はすべて見えるタスク専用タブで実行する。
Orca の作業場所は既定で Melon / Kiwi / Potato の名前付きカード。対象コードの cwd は `--cwd` で固定する。
`--worktree path:<絶対パス>` を指定するとタブの場所もその登録済み checkout / folder に変更する。
両方を渡した場合は path の一致を検証する。remote 環境を選んだ shell では起動しない。
新しいタブを開いて表示し、Codex の実行出力、Potato のセッション開始・ツール実行・途中の応答を逐次表示する。
Potato は終了時の session / modelUsage を検証する。途中の表示は最終レビュー承認ではない。
`--json` は Potato の検証済み result metadata を返す。モデル・effort・権限を迂回する変更はしない。

結果と進捗は `~/.local/share/named-team/tasks/<role>-<id>/` に保存する。
`result.txt` / `error.txt` / `finished.json` を保存し、子プロセスとタブの終了を確認してから、そのタブだけを閉じる。
起動コマンドは結果を呼び出し元へ返し、タブを閉じても結果は残る。
タブ作成の応答がタイムアウトした場合は同じ一意のタブを照合し、再作成・再送しない。
開始・終了・回収・close を確認できないときはタブと結果を保持し、未確認として返す。

依頼なしの手動起動や明示的な `--interactive` は対話用。自動で閉じない。
`bin/start-workspaces` はカードの作成・確認だけを担当し、待機用エージェントを起動しない。

Potato の独立性は実際の関与歴で判断し、名前だけを根拠に承認しない。
汎用技術レビューは concafe の固定 SHA 最終署名 verdict を代替しない。正式な依頼は repo と最新 Owner 指示の別タスク・実モデル・effort・未関与性の条件に従う。

## 配線と正本

```sh
/Users/kamp/orca/agents/named-team/install.py
/Users/kamp/orca/agents/named-team/install.py --check
```

正本はこのフォルダの `roles/<name>/skill/` と `roles/<name>/codex/profile.config.toml`。
`~/.agents/skills/<name>`、`~/.codex/<name>.config.toml`、`~/.local/bin/<name>` の9リンクを作る。
base config や既存 agent を変更しない。別のファイル/リンクがあれば全体の配線前に中断する。
`--uninstall` はこの package を指すリンクだけを外す。

モデル実行を伴う実依頼、外部投稿、automation、repo 操作の許可は、現在のユーザー指示と対象契約から得る。
この定義を新しい操作許可として扱わない。
# Git 管理された作業場所

2026-10-03 の引継ぎで、`/Users/kamp/orca` のエージェント実装・共有オフラインテストと
`/Users/kamp/.claude/skills/Tomato` の観測ソースを別々のローカル Git repository にした。
runtime state / logs / packets / backups / secrets は除外する。方針は各 `VERSION-CONTROL.md`。
実装依頼は、Melon が `--cwd /Users/kamp/orca`、Kiwi が
`--cwd /Users/kamp/.claude/skills/Tomato` を使う。通常の Git 検査は維持する。
タスク launcher を別の Codex sandbox 内から呼ぶと、Git 検査を通っても runtime 初期化の権限で
停止する場合がある。起動 rc と実 model / effort を確認し、制約を迂回して起動しない。
