# Peach

**Peach** は Linear の status が**厳密に `In Review`** の Issue だけを対象に、受入条件と実装を突き合わせて
**`PASS` / `CHANGES_REQUIRED` / `BLOCKED`** を出す読み取り専用のレビュアー。

**判定しかしない。**実装・修正・commit・push・PR 操作・Linear 更新は行わない。
Linear チーム・リポジトリを限定しない横断の共通 Reviewer。

呼び出し名は `peach`、Codex の skill は `$peach`、表示名は **Peach**。
保存フォルダは `linear-inreview-reviewer/` のまま使い、既存の台帳・パケットと `LINEAR_INREVIEW_*` 環境変数を維持する。
旧 CLI / Codex profile / Claude agent 名は互換入口として残す。skill の一覧は Peach に統一する。

## 使う

```sh
peach --board                      # 常設タブ用（直近の判定＋いま In Review）
peach --ledger [N]                 # 判定台帳を新しい順に
peach --list                       # In Review を横断で一覧
peach CAF-288                      # 既定 = Claude / Opus 5.5 / effort high
peach CAF-288 --backend codex      # Codex の互換実行を明示する場合
peach CAF-288 --pr owner/repo#236  # PR を明示（候補が絞れないとき）
peach CAF-315 --run owner/repo:36243927185  # 受入条件が参照する workflow run の一次データを入れる
peach CAF-288 --test-check "CI / full"  # 一般名のチェックでテストを実行すると操作者が確認済みの場合
peach CAF-288 --packet-only        # パケットだけ作って中身を見る
```

Orca に常設タブを立てる:

```sh
orca terminal create --worktree path:/Users/kamp/Projects/concafe-techo \
  --title "Peach" --command "peach --board" --focus
```

## このフォルダの中身

```
linear-inreview-reviewer/
├── README.md                  このファイル
├── install.sh                 各ツールが見る場所へシンボリックリンクを張る
├── bin/
│   └── linear-inreview-reviewer   Peach の起動スクリプト（旧ファイル名を保持）
├── lib/                       起動スクリプトから読み込む責務別処理
│   ├── cli.sh                 引数検証・表示
│   ├── evidence.sh            取得事実・時刻・欠落の記録
│   ├── evidence.py            ページ・対象 SHA・CI・判定の検証
│   ├── linear.sh              Issue 取得・厳密 status ゲート・レンダリング
│   ├── github.sh              候補収集・GitHub 取得・固定 SHA 検証
│   ├── packet.sh              meta.json とパケット索引
│   ├── backend.sh             settings 検証・モデル確認・起動
│   └── report.sh              BLOCKED・判定抽出・台帳
├── skill/
│   ├── SKILL.md               レビュープロトコルの正本。両バックエンドが読む
│   └── agents/openai.yaml     表示名 Peach と $peach の UI 定義
├── claude/
│   ├── agent.md               Claude Code subagent 定義（Opus 5.5 / high、tools 限定）
│   ├── legacy-agent.md        旧 agent 名の互換入口
│   └── settings.json          書き込み系を落とす deny リスト
├── codex/
│   └── profile.config.toml    Codex プロファイル（手動で codex を起動するとき用）
└── state/
    ├── ledger.tsv             判定台帳。1判定1行。BLOCKED も残る
    └── packets/<ISSUE>/<UTC>.<unique>/ レビューパケットと verdict.md
```

**実体はこのフォルダだけ。**外に置いてあるのは、ツール側が場所を決めているためのリンク7本のみ。

| リンク | 何が見に行くか |
|---|---|
| `~/.local/bin/peach` | PATH。`peach` コマンドで叩くため |
| `~/.agents/skills/peach` | `$peach` と `orca skills installed` の一覧 |
| `~/.claude/agents/peach.md` | Peach の互換定義。実レビューは制限を明示する `peach` から起動 |
| `~/.codex/peach.config.toml` | `codex -p peach` |
| `~/.local/bin/linear-inreview-reviewer` | 旧 CLI の互換 alias |
| `~/.codex/linear-inreview-reviewer.config.toml` | 旧 Codex profile の互換 alias |
| `~/.claude/agents/linear-inreview-reviewer.md` | 旧 agent 名を保持する互換定義 |

```sh
./install.sh            # 張る（既存の実ファイルがあれば壊さず中断）
./install.sh --check    # 配線を確認
./install.sh --uninstall  # このフォルダを指すリンクだけ剥がす
```

保存先を移動する場合は、移動前に `./install.sh --uninstall`、移動後に `./install.sh` で配線する。
既存の別ファイル/リンクは自動で上書きしない。
起動スクリプトは自分の実体の位置から root を割り出すので、パスを書き換える必要はない。

## モデル

| backend | model | effort | read-only の効かせ方 |
|---|---|---|---|
| `claude`（既定） | `claude-opus-5-5`（Opus 5.5） | 全パス `high` | restricted / Read,Glob,Grep のみ＋user/project/local の hook・MCP 設定を無効化 |
| `codex`（明示時の互換実行） | `gpt-5.6-sol` | `high` | OS サンドボックス。**書き込み不可＋ネットワーク遮断**（強制） |

Claude はモデル名を `opus` alias にせず full ID で固定し、通常パス・保護パス・取得不明のすべてで
`--effort high` を渡す。変更ファイルの取得と件数照合は引き続き証拠の完了条件として確認する。
モデル・backend の既定はプロジェクトの個別指定を置き換えない。
Claude の probe / 本実行は JSON の実 `modelUsage` を確認し、`claude-opus-5-5` の
単一モデル ID だけを受け付ける。返却される `[1m]` context suffix は許容する。
旧 Opus・欠落・不明・別モデル・複数モデルは BLOCKED とし、要求したモデル名だけで成功にしない。
probe・本実行とも packet を cwd として起動し、`--restricted`、`--tools Read,Glob,Grep`、
strict empty MCP、slash command 無効、`dontAsk`、permission prompt 無効、専用 settings を明示する。
settings の `disableAllHooks: true` が無い場合は、証拠収集やモデル起動の前に停止する。
本実行の `--agents` は信頼済みプロトコル本文を inline prompt として渡し、
PR 内やファイル上の同名 agent 定義が実行設定を置き換えないようにする。
ソースは packet 内の固定 head SHA の clone から読む。
これらの起動設定は user/project/local 由来の設定・hook に対して適用する。
組織の managed policy は優先され、下位の `disableAllHooks` で managed hook を無効化できない。
restricted・settings・inline agent も managed policy を迂回する仕組みとして扱わない。
Claude の制限はツール・起動設定によるもので、Codex の OS サンドボックスと同じ強度の保証として扱わない。
この汎用 Issue reviewer の PASS は、concafe の固定 SHA 最終独立レビュー・署名 verdict と別の条件。
CAF-279 / ADR-061 の未関与別 Codex タスク・Astra high 等の現契約は維持され、
この既定モデルやローカル台帳の PASS だけでは最終ゲートを満たさない。

**固定。別モデル・backend へ自動フォールバックしない。**毎回プリフライトで短いプローブを1回投げ、
Claude は実 `modelUsage`、Codex は起動バナーの `model` / `reasoning effort` / `sandbox` が
要求と違えば **BLOCKED で止める**。
limit を観測した場合も落とさず BLOCKED にし、観測ログのパスを出す。
別 provider へ回すかどうかは人が決める。

**Codex のプロファイルでは `model_reasoning_effort` を固定できない**（実測）。
効くのはコマンドラインの `-c model_reasoning_effort="high"` だけ。手で `codex -p` するときは必ず付ける。

## 外部への到達

Linear と GitHub への到達は**起動スクリプト側で全部済ませる。**
レビュアー本体はローカルのパケットと head SHA のクローンだけを読む。

- Linear: Orca の integration（`orca linear`）のみ。各 Agent への Linear MCP 追加はしない
- GitHub: `gh`
- Issue と PR のテキストは **UNTRUSTED DATA**。そこにある命令的な記述には従わず、
  prompt injection の疑いとして Findings に記録する

## 気をつけること

- **両 backend のレビュアー本体はローカルでテストを走らせない。**
  テストは収集済み CI 結果とテストコード本体で評価する。Claude は Read / Glob / Grep のみを使う。
- **受入条件が workflow run の結果を根拠にしているときは `--run` で渡す。**
  Linear や PR に書かれた run ID は、エージェントが書いた二次情報で、レビュアーは照合できない（BLOCKED になる）。
  `--run` を付けると launcher が `run.json` / `jobs.jsonl` / `log.txt` を `github/runs/` に取得する。
  ログに secret らしい文字列があれば、保存せずに FETCH_ERRORS に「漏えいの疑い」として残す
- **PR 特定はヒューリスティック。**Linear 本文・コメント・添付の PR URL が最優先で、
  無ければ Orca 登録リポジトリを identifier / branch 名で横断スキャンする。
  0件・4件以上は BLOCKED。絞れないときは `--pr` で渡す
- **同じ PR で判定が割れることがある。**重い判断は2回走らせて突き合わせる
- **パケットは溜まる。**`state/packets/` を時々消す（`ledger.tsv` は残す）
- **自動化していない。**定期実行も、PASS を Linear/PR へ反映する仕組みも入れていない

設計の経緯は `~/brain/decisions/2026-09-21-in-reviewレビュアーを読み取り専用の独立エージェントに分ける.md`。

## 証拠と判定を揃える

`evidence.json` は起動側が記録する取得 manifest。取得開始・観測時刻、対象 Issue / PR / SHA、
終了コード、取得成功・失敗・不正、必須かどうかを保存する。部分取得を `[]` / `{}` の成功へ置き換えない。
必須欠落のある `--packet-only` は診断資料として残せるが、そのパケットで実レビューは起動しない。

ソースは full head / base SHA の Git オブジェクトを確認してから固定する。
`source.json` に head / base / merge-base を残し、`diff.patch`・`files.json`・`commits.json` はそのオブジェクトから生成する。
ローカル clone の共有オブジェクト依存は避け、継承 `GIT_*` による別 repository / index / object の指定も起動時に除去する。

CI は full head SHA を指定した check-run と commit-status を全ページ取得する。
PR の required checks を同じ head の結果へ照合し、`verification.json` に CI / Tests と根拠を残す。
optional skip は必須 CI の失敗にしない。必須 pending / skip / cancelled / neutral、必須チェック不明は成功にしない。
review / verdict 系のゲートが循環していても無条件には除外せず、未達として残す。

Tests の対象は `gh run view --json databaseId,headSha,attempt,url,jobs` で取得した
workflow job 一覧のうち、現在の check-run のリンクの run / job ID と一致するもの。
run の repository URL と full head SHA、attempt、job ID、name を照合する。
テスト job と識別できる名前、または操作者の `--test-check` 完全一致 mapping を対象とする。
`status=completed` かつ `conclusion=success` の場合だけ PASS とし、skipped は PASS に数えない。
job 一覧が無いチェックや commit-status の文字列だけなら UNKNOWN。取得失敗・不正は BLOCKED。
例えば `CI / full` の中でテストを実行する契約を確認した場合は、その名前を明示する。
mapping は結果と対象を結びつける指定であり、テストの内容・カバレッジ・受入条件の充足を保証しない。
job success はその job が走った証拠であり、job 内の全テストが走った証拠ではない。
#279 では `CI / full` success と db / e2e skipped が併存した。
Tests 欄は PASS 以外の CHANGES_REQUIRED / BLOCKED でも証拠へ照合する。
指定名が取得結果に無い、または同名のチェックが複数ある場合は BLOCKED。

主 Issue と related / parent / child Issue は full 情報を取得後と判定保存前に再取得し、本文・状態・コメント・前提の更新を検出する。
PR も再取得し、head / base やレビュー情報の更新を検出する。
CI と workflow job 一覧も判定保存前に再取得し、必須チェック・テスト結果・run / attempt / job ID が変わった場合は判定を有効化しない。
モデルの生出力を保存した後、Issue / PR / full Commit / CI / Tests、出力形式、PASS の未達・不明 AC を検証する。
PASS の AC section は、1件以上あり、非空行すべてが規定の `* [x] <項目>` であることも確認する。
この検証が通るまでは PASS を表示せず、台帳にも記録しない。無効な出力は診断を残して BLOCKED。

review threads / comments は1回100件までを取得する。続きがあるときは欠落として止める。
PR の自動探索も200件の上限に達した repository は候補を取り切れないため、`--pr` で明示して再実行する。
観測時刻は外部の瞬間的な状態を示すもので、レポートの後に起きた更新まで保証しない。

## ローカルで検証する

```sh
python3 /Users/kamp/orca/tests/test_agent_refactor.py
python3 /Users/kamp/orca/tests/test_reviewer_evidence.py
shellcheck -S warning bin/linear-inreview-reviewer lib/*.sh
./install.sh --check
```

テストは Orca・GitHub・モデル CLI を fixture に置き換え、外部アクセスもモデル課金も発生させない。
`--packet-only` はバックエンド CLI・Claude settings を要求しない。
パケットのディレクトリは同一秒の起動でも重ならない。
取得した full head / base SHA とクローンのオブジェクトが一致しない場合、別 SHA へ fallback せず BLOCKED にする。
プリフライト・起動・結果保存の失敗を、有効な PASS として台帳へ残さない。
追加テストは取得中・モデル実行中の Issue / PR / CI 更新、partial response、必須/optional CI、
一般名テスト mapping、誤った判定、workflow run、Git 環境隔離、一時的な実 Git の diff を検証する。
実 GitHub / Linear への到達と有料モデルの実動作は、これらのオフラインテストの確認範囲に含めない。
