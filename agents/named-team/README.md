# Melon / Kiwi / Potato

Orca 関連の開発で使う名前付き Codex role。2026-10-02 の追加担当を再利用できるよう、skill・profile・起動コマンドを用意した。
Tomato・Banana は既存の名前と人格を維持する。

| 名前 | 担当 | Codex の既定 |
|---|---|---|
| Melon | レビュー基盤・証拠パケット・CI照合の実装改善 | gpt-6.1-sol / medium |
| Kiwi | 観測の鮮度・状態履歴・引継ぎ基盤の実装改善 | gpt-6.1-sol / medium |
| Potato | 実装に未関与の別担当として技術確認 | gpt-6.1-sol / high、read-only |

## 呼び出す

Codex のチャットでは `$melon` / `$kiwi` / `$potato` を指定する。表示名は Melon / Kiwi / Potato。
現在のセッションに新しい skill がまだ表示されない場合は、新しいチャットで読み込む。
skill の適用は今のチャットに役割の手順を読み込む操作で、モデル・effort・sandbox や関与歴を切り替えない。
別セッションと profile が必要なときは、以下の起動コマンドを使う。

ターミナルでは同名コマンドを使う。依頼が無ければ対話画面を開く。

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

`--dry-run` は起動引数を JSON で返し、セッションを作らない。
`--exec` は Codex を非対話で起動する。Codex 自身の workspace / Git / trust 条件を適用する。
`--orca` は指定 workspace に名前付き terminal を作り、同じ role の Codex を起動する。
Orca ではこの host に登録済みの checkout / folder の path を使う。
`--worktree path:<絶対パス>` だけ指定すると、その path を Codex の cwd にも使う。
`--cwd` だけ指定すると、その path を Orca の対象にも使う。両方を渡す場合は一致を検証する。
この helper はローカル配線用で、remote 環境を選んだ shell では起動しない。
検査済みの Codex profile ディレクトリと実行ファイルの絶対パスを起動先にも渡す。
Orca の receipt は terminal 作成の証拠であり、依頼の開始・完了は terminal 出力で確認する。

同名の既存セッションを再開する仕組みではなく、各起動は新しい Codex セッションになる。
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
`--exec` を別の Codex sandbox 内から呼ぶと、Git 検査を通っても runtime 初期化の権限で
停止する場合がある。起動 rc と実 model / effort を確認し、制約を迂回して起動しない。
