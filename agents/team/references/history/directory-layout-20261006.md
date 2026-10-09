# Orca の役割・表示・実ファイル配置（2026-10-06）

Owner の「広い相談窓口 Tomato、独立した開発窓口 Banana、独立 Potato」へ実配置をそろえた。
2026-10-07 JST の Owner 指示により、開発は Codex（Sol）で行い、Orca で Devin は利用しない。
後半の日時付き導入・検証記録は当時の履歴で、Devin の起動・再開・再試行の指示ではない。
同日の追補により、Tomato / Banana は一部重なる担当領域の連携として扱う。
名前付き担当は Tomato / Banana / Potato の3役、常設ホームは Tomato / Banana の2つ。

## 正規のソース

```text
/Users/kamp/orca/agents/team/
├── roles.json                    担当領域・連絡先・受付の正本
├── bin/・lib/・shell/             共有の起動・案件管理・観測
├── config/                       イベント設定・保全した旧 Devin 接続設定
├── references/                   現行契約（history/ は過去の記録）
└── roles/
    ├── tomato/
    │   ├── claude/               Tomato の Fable 対話設定・起動指示
    │   ├── codex/                自動イベント観測の Codex 設定
    │   └── skill/                相談・観測ソース。独立した Git repo
    ├── banana/
    │   ├── codex/
    │   └── skill/                開発窓口・Codex・基盤保守
    └── potato/
        ├── skill/               共通 Potato 窓口（Opus 5.5 / high 固定）
        ├── codex/               未配線の旧 profile の保全
        ├── acceptance/           受入の証拠取得・固定版検証
        │   ├── claude/settings.json 技術・受入レビュー共通の設定
        │   └── state/            保全した台帳・パケット（Git対象外）
        └── relay/                記録検証・中継の部品
            └── log/              保全した履歴（Git対象外）
```

旧バックアップの実体は
`/Users/kamp/orca/history/agent-infrastructure/reviewer-20260929`。
共有の既存案件・Devin・イベント記録は `~/.local/share/named-team/` のまま保持する。
環境変数・台帳形式・実行済み依頼の排他キーを変更しない。

## Orca の表示と checkout

- Tomato / Banana の常設ホームを独立表示。Banana の Tomato 親子メタデータを解除した。
  開発の指示・質問・報告による連携をコメントと `consultation` に記録する。
- 共有ソースのカードは「Orca｜エージェント基盤」。説明に Banana の担当と正規パスを示す。
- 旧 Kiwi / Melon / Potato の checkout は `archives/retired-homes/` に復元用の保管を作り、
  Orca と Git の worktree 登録から撤去した。通常・休止中の一覧に旧ホームを残さない。
- 旧 Review の folder 登録を解除。受入基盤の実体・台帳・互換リンクはソース部品として保存する。
  Potato は案件ごとの独立レビュー checkout を使い、新規常設 reviewer を立てない。
- 新規の開発 checkout は `依頼ID｜開発（Codex）`、
  独立レビュー checkout は `依頼ID｜Potato` と表示する。Git branch 名と作成マーカーを保持する。

Orca の lineage は同じ repo / host / project 内に限定される。
Tomato / Banana のホームは実際に brain の Git worktree なので
`/Users/kamp/orca/workspaces/brain/Tomato` / `Banana` を維持する。
別プロジェクトの開発 checkout は対象プロジェクトの workspace を表示上の親にし、
Banana ホームを `coordinatorWorktreeId` として別途記録する。
`lineageParentWorktreeId` は実際に使う同じ repo の親。Potato は必ず開発 checkout の子にする。
親を確認できない場合は作成と実装起動を止める。

## 既存経路との互換

| 旧住所 | 実体・現在の参照 |
|---|---|
| `agents/named-team` | `agents/team` |
| `agents/team/roles/review` | `agents/team/roles/potato` |
| `agents/team/bin/review` / installed `review` command | 同じ Potato の command |
| `~/.codex/potato.config.toml` / `review.config.toml` | 所有する旧リンクを撤去。現在は `~/.claude/named-team/potato.settings.json` |
| `~/.claude/skills/Tomato` | `agents/team/roles/tomato/skill` |
| `agents/linear-inreview-reviewer` | `agents/team/roles/potato/acceptance` |
| `agents/review-relay` | `agents/team/roles/potato/relay` |
| `agents/linear-inreview-reviewer.bak-20260929` | `history/agent-infrastructure/reviewer-20260929` |
| `AGENT-ROUTING.md` | 現行 `references/team-topology.md`。旧内容は `references/history/agent-routing-20261001.md` |

旧住所には相対互換リンクを残した。実行中セッションと過去の参照は同じ実体へ到達する。
installed command / skill / 担当ごとの profile、所有する zsh 自動起動 block、
Orca の「構成・稼働確認」クイックコマンドは正規パスへ更新済み。
installer は解決先が一致する所有リンクのみ付け替え、未知の設定があれば変更前に停止する。
自動起動の旧 block も、以前の installer が出力した完全一致の形式だけを移行する。
公開名は Potato、共有台帳・排他・引渡しで使う役割 ID は `review` のまま。
Orca の登録スキルは Tomato / Banana / Potato の3つで、旧 Review を別スキルとして登録しない。

## 移動と検査の証拠

rename の直前・直後に通常ファイルの byte hash / mode、リンク先を照合して一致を確認した。
共有ソース66、Tomato60、受入基盤285,722、中継9、旧バックアップ45,808エントリを保全した。
このエントリ数は移動時の通常ファイル・リンクの数。ディレクトリは数えない。
後続の意図したソース更新とは分けて検証した。実 state / packet / 台帳 / log の内容は編集していない。
ソースの事前スナップショットと移動証拠は
`/var/folders/l3/m0m_2xsd23q4wr1rczgxqc180000gn/T/orca-team-layout-uu6wpb7f`。

Orca root の Git 対象は `agents/team` と共有テスト。Tomato は独立 repo のまま外側から除外する。
state / log / backup / workspaces と互換リンクも、新規 Git 対象にしない。index は変更していない。
既存の別タスクの修正と未コミット成果は保全した。

実機で `setup --check` は表示差分なし、既存 Activity タブを再利用。
`install.py --check --tab-autostart`、旧受入 installer の `--check`、
`start-workspaces --check` は exit 0。初回 UI で親子表示・旧ホーム休止・クイックコマンドの正規パスを確認。
その後の Owner 追補で、Tomato / Banana の親子表示を独立表示へ修正した。
検査結果（いずれも exit 0）:

| 検査 | 結果 |
|---|---|
| Orca root: `python3 -B -m unittest discover -s tests -q` | 371件、299.705秒、OK |
| Tomato repo: 同コマンド | 23件、15.314秒、OK |
| 最終の受付表示調整: `test_role_routing.py` | 8件、3.326秒、OK |
| Python AST / JSON / bash・zsh 構文 | 29 Python、10 shell、zsh hook、設定JSONが有効 |
| Orca / Tomato: `git diff --check` | 問題なし |
| Git 新規候補の境界 | state・log・Tomato nested repo の混入なし、index 変更なし |

追加の回帰検査で、互換リンクの正規化、旧自動起動 block の移行、
表示の親子関係の照合、別 repo の親を禁止する native 制約、
対象親 workspace が欠ける場合の作成・実装起動停止を確認した。
実モデル、Devin の実案件、外部投稿、CI supervisor、鍵・trust の変更はこの配置作業で実行していない。
テスト成功を独立レビューの PASS と扱わない。

## 同日の担当領域の追補

Tomato / Banana は、一部重なる担当領域を持つ別窓口として扱う。
Tomato は広い相談・目的・意図、Banana は開発領域の技術判断と進行を担当する。
開発の指示・質問・報告で連携し、Owner は両方に直接依頼できる。
`roles.json` の Banana の `parentRole` は null、双方の相談先は `consultation` に記録する。
常設ホームの native 親子メタデータを解除し、CLI で両ホームの parent=null、表示差分なしを確認した。
配置済みソースは roles/tomato と roles/banana の独立したディレクトリ。
案件の開発・Review checkout の lineage とレビュー独立性は引き続き案件単位で管理する。

関連検査: `python3 -B -m unittest -q test_activity test_named_workspaces test_role_routing test_named_agents test_project_tasks`
（tests ディレクトリ）: 99件、27.750秒、exit 0。単独の各受付が他方のホームを必須にしないこと、
旧親子表示を解除することを含む。両 repo の `git diff --check` は exit 0、index 変更なし。

今回 `setup --check` は、変更前から存在する Activity タブの出力が古く freshness 検査で停止した。
同名タブは増やさず、今回依頼された表示メタデータのみ更新・照合した。
監視タブの再起動やモデル/provider の切替を行ったとは扱わない。

## 全体の再検査と実機反映（2026-10-06、16:36 JST）

Owner の再検査依頼により、担当契約・起動・案件作成・独立レビュー・配置・Orca の実表示を再照合した。
Tomato の受渡し参照とローカル指示、初回記録の現行構成説明に残っていた上下関係の文言を修正した。
Banana のモデル無し受付は Owner / Tomato からの依頼と、Tomato への目的・意図・受入範囲の相談を表示する。
タスク起動テストの旧 `upper` / `parentRole=tomato` の期待値も現行契約に合わせ、
両ホームの独立性・相互相談先・Review の必要時起動を実際の request metadata で検査した。

前項で停止していた Activity は、Orca 再起動後に観測処理ではなくシェルが復元されていた。
同じタブでモデル無しの観測処理を再開し、鮮度検査を維持したまま最新出力を確認した。
表示を「Devin 外部Issue連携」と「Banana / Devin CLI による開発」に分け、
外部 adapter の未接続をローカル CLI の状態と混同しないようにした。
表示変更後も同じタブだけで処理を更新し、同名の稼働タブは1つであることを確認した。

最終 `setup` と `setup --check` は正常終了、表示差分は空。
`install.py --check --tab-autostart` と `start-workspaces --check` も正常終了した。
所有リンク13本、相対互換リンク6本、文書参照23ファイルを照合し、切れた参照はない。
旧 Kiwi / Melon / Potato / 受入 Review ホームには稼働中ターミナルがなく、
登録スキルは Banana / Review / Tomato の3役、常設ホームは独立した Tomato / Banana の2つ。
Orca の画面も更新して同列のホームと最新 Activity を確認した。
クイックコマンドは `/Users/kamp/orca/agents/team/bin/start-workspaces --check` を参照する。
インストール済み Banana の開発 dry-run は `workerBackend=devin` / `startsSession=false` を返した。

| 今回の検査 | 結果（exit 0） |
|---|---|
| Orca root 全体 | 372件、288.354秒、OK |
| Tomato repo 全体 | 23件、13.620秒、OK |
| タスク起動の旧期待値修正後 | 17件、11.981秒、OK |
| 最終 Activity 表示修正後 | 16件、0.176秒、OK |
| Python / bash / zsh / JSON | 29 Python、13 bash、zsh hook、設定JSONが有効 |
| 両 repo の diff / index / Git 境界 | 差分の空白エラーなし、staged変更なし、実 state・log・nested Tomato repo の新規混入なし |

Tomato の現行起動設定は Codex `gpt-6.1-sol` / medium。
Fable をコミュニケーション層へ使う案は未反映で、判断相談先の呼称から provider / model を推測して切り替えていない。
ローカル Devin CLI は配置・起動計画・隔離 fixture を確認した。外部 Issue adapter は引き続き未設定で、
実案件の認証・モデル呼出し・独立 verdict・外部投稿を検証したとは扱わない。
変更前の対象ソース・テストは
`/var/folders/l3/m0m_2xsd23q4wr1rczgxqc180000gn/T/orca-overall-audit-wk95cbct` に保全した。

## Potato への命名反映（2026-10-06）

Owner の命名追補により、公開名・Orca 表示・登録スキル・起動 command・profile・
文書と正規配置を Potato にそろえた。役割 ID `review` と既存台帳・排他・引渡しキーは維持する。
`roles/review` は同じ `roles/potato` への相対リンク、旧 `review` command / profile も同じ担当へ到達する。
旧 Review スキルだけを所有リンクの照合後に外し、登録スキルは Banana / Potato / Tomato の3つ。
常設ホームは独立した Tomato / Banana の2つ、Potato は必要時に開発 checkout 配下へ作る。

`roles/review` の実体を rename し、role root・acceptance・acceptance/state・relay・relay/log の
5ディレクトリの inode / device が移動前後で一致することを確認した。台帳と履歴の内容は編集していない。
命名前のソース・テストとディレクトリ同一性の記録は
`/var/folders/l3/m0m_2xsd23q4wr1rczgxqc180000gn/T/orca-potato-name-q6iw6y47` に保全した。

実機の `setup` / `setup --check`、`install.py --check --tab-autostart` は exit 0、表示差分は空。
所有リンク15本を照合した。新旧 command の inbox はともに「Potato｜受入・技術レビュー」を返す。
`start-workspaces potato --check` は同じ `review` role と既存 Banana 受付を選び、必要時起動を返した。
既存 Activity タブでモデル無し観測処理を更新し、実画面の「品質: Potato」と独立した両ホームを確認した。

初回関連検査では、旧「Potato は廃止名」のテストが新しい有効名を実 Orca に渡し、試験用タブを1つ作った。
テスト fixture プログラムは必須環境変数不足で直ちに失敗し、実モデルは呼ばれていない。
そのタブの終了記録と閉鎖記録を確認し、実ターミナル一覧から消えたことを照合した。
該当 receipt は保全した。テスト共通 fixture に Orca の試験用 executable と一時 task store を指定し、
旧廃止名の期待値を修正したうえで、関連検査と全体検査を完了した。

| 今回の検査 | 結果（exit 0） |
|---|---|
| 関連9モジュール | 169件、45.672秒、OK |
| Orca root 全体 | 374件、277.868秒、OK |
| 有効ソースの構文（state・log・history 除外） | 34 Python の AST、21 bash、zsh hook、設定JSONが有効 |
| 両 repo の diff / index / Git 境界 | 差分の空白エラーなし、staged変更なし、実 state・log・nested Tomato repo の新規混入なし |

旧 command と Potato が同じ role を選ぶ回帰検査と、旧 Review スキルを残さず移行する検査を追加した。
モデル・provider・trust・署名と CI ゲートを変更せず、独立 verdict や外部投稿を実行したとは扱わない。

## Tomato の Fable 起動設定（2026-10-06）

Owner の直接指示により、Tomato の対話・相談・直接依頼とホームの新規タブを
Claude Code の `--model fable --effort medium` に切り替えた。
この実機の Claude Code 2.1.291 の help が `fable` alias を案内していることを確認した。
正規設定は `roles/tomato/claude/settings.json`、起動指示は同じディレクトリの `instructions.md`。
専用 installed profile は `~/.claude/named-team/tomato.settings.json` で、全体の Claude 設定は編集しない。
所有する旧 `~/.codex/tomato.config.toml` link は installer で撤去した。

自動イベント観測は `observationBackend=codex` と従来の Codex profile を明示し、
通信モデルの変更から Claude 自動観測や必須レビューを追加しない。
Fable のタスク結果は単一の実 Fable model metadata、成功・session ID・空でない本文を検査して保存する。
相談結果を正式 verdict にしない。案件記録には実際の backend / model を記録し、
旧 Codex 相談の完了記録を新しい Fable 依頼の結果として使わない。
読み取り案件では command / write tools と MCP を外し、Read / Grep / Glob のみを使用する。

`install.py --check --tab-autostart`、installed `tomato` の対話 dry-run、`setup` / `setup --check` は正常終了。
所有リンク15本、最終表示差分は空。Tomato の native コメントも Fable / medium の相談窓口へ更新した。
既存 Tomato タブが未入力の Codex TUI であることを確認し、`/exit` 後の shell を確認して、
同じ handle `term_2ac88a58-cbc6-42f4-91d4-ef50c9d40e99` で installed `tomato --interactive` を起動した。
Fable / medium と専用 settings を指定する実 Claude process と、native `tui-idle` を確認した。
別の既存タブと過去の会話は保存し、試験用のモデル依頼は送信していない。

ただし Claude 初回画面の表示確認は未完了。Mac がロックされており、Computer Use が
physical input 検知による自動 unlock 停止を返したため、Owner に手動 unlock を依頼した。
設定反映・process 起動と、初回画面完了・実モデル応答を区別する。

| 今回の検査 | 結果（exit 0） |
|---|---|
| 起動・新規タブ・案件・観測など関連7モジュール | 141件、44.219秒、OK |
| Orca root 全体（最終ソース） | 380件、274.066秒、OK |
| 有効ソースの構文（state・log・history 除外） | 34 Python の AST、21 bash、zsh hook、12 JSON が有効 |
| 両 repo の diff / index / Git 境界 | 差分の空白エラーなし、staged変更なし、実 state・log・nested Tomato repo の新規混入なし |

変更前のソース・テストは
`/var/folders/l3/m0m_2xsd23q4wr1rczgxqc180000gn/T/orca-tomato-fable-9gcwwv41` に保全した。
brain / persona、署名鍵、Codex trust、プロジェクトの CI・独立レビュー・人間ゲートは編集していない。

## Orca の画面整理と Fable 実表示の確認（2026-10-06、20:45 JST）

Owner の画面整理依頼により、ワークスペースカードを Compact、追加情報を Hover に変更した。
上部には Tomato｜相談・受け渡し、Banana｜開発・Devin窓口、Orca｜エージェント基盤を
同列でピン留めし、brain / concafe-techo / orca / 旧レビュー用プロジェクトの一覧を折りたたんだ。
右のファイルサイドバーを閉じ、会話と監視表示の幅を確保した。
既存タブの表示名は Tomato｜Fable、Banana｜会話・履歴にそろえ、実画面で照合した。

「devin: Tomato」は Devin セッションではなく、未着手の Codex 初回 trust 画面だった。
trust を変更せず、そのタブと実 process が閉じたことを確認した。
Orca root の Terminal 1 / Terminal 2 は shell prompt と jobs が空であることを確認して閉じた。
最終 native 一覧は既存の Tomato、Banana、Activity の3ターミナルで、会話履歴を保存している。
案件 checkout や稼働中の開発・レビュー処理を削除していない。

Activity に `--screen` を追加し、TTY では同じ画面を更新して最新状況を表示する。
非 TTY と JSON 出力は従来の形式を維持し、構成行に Tomato（相談 / Fable）、
Banana（開発 / Devin）、Potato（独立レビュー）の連携を表示する。
標準の起動設定にも同 flag を追加し、既存のモデル無し観測タブだけを同じ handle で更新した。
実画面の最新時刻、単一の Activity タブ、鮮度検査の成功を確認した。

前項で未確認だった Claude 初回画面は、今回の実画面で
Claude Code 2.1.291 / Fable 5.1 / medium effort と待機中の入力欄を確認できた。
Fable への切替と初回表示の確認は完了。今回の確認用モデル依頼は送信していない。

| 今回の検査 | 結果（exit 0） |
|---|---|
| Activity / ワークスペースの既存検査 | 29件、1.185秒、OK |
| `setup --check` | 所有リンク15本、`displayChanges=[]`、既存 Activity の鮮度検査成功 |
| 両 repo の `git diff --check` | 空白エラーなし |
| native 一覧と実画面 | 未使用タブ3つの閉鎖、表示名、Compact 表示、最新監視画面を照合 |

この表示整理によるモデル・権限・署名・CI ゲートの変更や、追加エージェントの起動はない。
変更はステージング・コミットしておらず、テスト成功を独立 verdict と扱わない。

## 旧ホームの撤去（2026-10-06、20:54 JST）

Owner の「旧ホームあるの嫌だな」という追補により、単に折りたたむ扱いを終了した。
Kiwi / Melon / 旧 Potato の3 checkout を native CLI の worktree rm で
Orca と Git の登録から撤去し、元の checkout ディレクトリが存在しないことを確認した。
未保存変更があった Melon のみ保全後に force を使用し、native 側は Melon branch を保持した。
旧 linear-inreview-reviewer は実画面の「ファイルはディスクに残る」説明を確認して folder 登録だけを解除した。
受入基盤の正規実体、台帳、互換リンクはそのまま保持する。

撤去前の3 checkout、Git bundle、未保存 patch、native metadata、撤去 receipt と検査記録を
`/Users/kamp/orca/archives/retired-homes/20261006-205224` に保管した。
通常ファイル464件の byte hash とリンク先を撤去前に照合し、保管された通常ファイルを撤去後にも照合した。
3ホームの native ターミナルはすべて0件であり、稼働中の案件処理を停止していない。
この保管先は Git 対象外、復元の説明は同ディレクトリの README.md。

setup の表示 specs と親子 metadata 対象から旧ホーム・旧 Review folder を除去した。
Potato の案件ごとの起動・Banana 受付は維持し、常設のレビュー用ホームは残さない。
最終 native 一覧・Git 一覧・実画面の照合で旧ホーム0件、旧 folder 登録なし、
Tomato / Banana / Orca 基盤が存続し、両窓口の parent=null を確認した。

検査は Activity / workspace の既存29件（1.223秒）、`setup --check`、
`start-workspaces potato --check`、`git diff --check` が exit 0。
setup は所有リンク15本、表示差分なし、既存 Activity を再利用。
Potato は `state=on-demand`、Banana の coordinatorWorktreeId を返した。
staging / commit、モデル依頼、独立 verdict、CI supervisor の操作は行っていない。

## 未使用ワークスペースを閉じる追補（2026-10-06）

Owner の「いらないものは閉じて」に従い、使っていない案件カードと Skills 管理を
Orca の Sleep で休止した。チェックアウト・未保存変更・履歴を残して再開できる扱いで、
案件の Done や正式レビュー結果は変更しない。稼働中の named 窓口と Activity を対象から外した。
空の brain main shell も native terminal close で終了し、PTY 終了の receipt を確認した。

表示はプロジェクトでグループ化しない設定にし、休止中のカードを隠す。
「休止中を非表示にしてもデフォルトのブランチは表示したままにする」を off に変更した。
最終の実画面は Tomato / Banana / Orca 基盤の3カードだけで、その他の一覧見出しはない。
既存 Banana の terminal handle を選んで窓口を表示し、新しいモデル依頼や追加ターミナルは作成していない。

native terminal 一覧の最終照合は3件で、全件が Tomato / Banana / Orca 基盤に属し、
未使用 main terminal は0件。`setup --check` は exit 0、所有リンク15本、表示差分なし、
既存 Activity の鮮度確認成功。`git diff --check` も exit 0。
UI とセッションの整理だけであり、追加テストやステージング・コミットは行っていない。

## Claude Code の `/banana` 登録の復旧（2026-10-06）

Owner の「banana消えた？」という画面確認を調べたところ、Banana のホームと共通スキルは
残っていたが、統合時の `installation.py` が Claude 用の `skills/Banana` を撤去対象にしていた。
この整理ミスを修正し、同じ Banana 定義へのリンクを所有インストール対象に戻した。
Claude 用に別担当を増やさず、Codex / Devin の開発経路と Potato の独立レビュー契約を維持する。

`install.py` を実行して `~/.claude/skills/Banana` を正規ソースへ復旧した。
既存 Banana ターミナル `term_629c0085-e768-4d6f-a44c-5debf14650e1` を選び、
入力済みの `/banana` に対して候補と Banana の説明が表示されることを実画面で確認した。
入力・会話・セッションを作り直さず、再起動、モデル依頼、権限設定の変更も行っていない。

既存のインストール再実行・移行検査を補強し、Claude 用 Banana が再び撤去されないことを検査した。
`python3 -B -m unittest -q test_named_agents test_named_tab_startup` は42件、3.137秒、exit 0。
`install.py --check --tab-autostart` は所有リンク16本と既存 tab autostart が正常、exit 0。
変更前の3ファイルは `archives/repairs/banana-claude-skill-20261006-211318` に相対配置を保って保全した。
変更はステージング・コミットしておらず、検査結果を独立 verdict と扱わない。

## Potato の表示窓口を Banana の次に配置（2026-10-06）

Owner の「potatoもorcaの画面でいい位置に配置して」に従い、
Tomato / Banana / Potato / Orca 基盤の順にピン留めを手動配置した。
相談と開発の独立した役割は保持し、実レビューの親子関係は引き続き案件の開発 checkout 配下に記録する。

Potato のカードは `~/.local/share/named-team/entries/potato` を登録したフォルダ窓口。
役割フォルダを直接選ぶと Orca が親 Git repo の基盤カードへ解決するため、
Git 外の表示フォルダから `roles/potato/entry/README.md` の正本へ所有リンクを置いた。
新しい Git repo / checkout や、常駐モデル・追加レビュー担当は作成していない。
`roles.json` の表示先と setup の任意表示対象を更新し、旧受入基盤のアドレスを表示先として使わない。

フォルダの登録で作られた空 shell は内容を確認して閉じ、native receipt の `ptyKilled=true` を確認した。
Orca の「スリープ中を非表示」はターミナルの無いカードも隠すため、表示用の受付 shell を1つ置いた。
`term_0595d88a-fd3d-4459-b5c7-7fa3b1025be2` で `potato --inbox` の手順表示と shell prompt を確認した。
このタブではモデルを起動せず、案内 README も同じ窓口に開いている。
他の既存会話・入力・稼働中処理は保持し、補助一覧は折りたたむだけにした。

実画面で「スリープ中を非表示」on と手動並べ替えのまま、
Tomato / Banana / Potato｜レビュー受付 / Orca 基盤の4カードをこの順に照合した。
インストール・新規タブ・表示・窓口の既存検査は71件、4.555秒、exit 0。
setup は既存 Activity を再利用し、所有リンク17本と Potato の表示名・説明の反映を確認した。
変更前の5ファイルは `archives/repairs/potato-display-20261006-221001` に相対配置を保って保全した。
モデル依頼、外部更新、CI supervisor、署名鍵、独立 verdict、staging / commit は操作していない。

## Potato の Opus 5.5 固定（2026-10-06）

Owner の「レビューエージェントはopus5.5に固定して」を現在のモデル指定として反映した。
技術・受入レビューと最終レビューの引渡しは Claude `claude-opus-5-5` / high。
以前の Sol / Astra のレビュー割当を更新し、通常進行やトップレイヤー判断の割当は保持する。
実装に未関与の別タスク、固定 full SHA、対象プロジェクトの CI・署名・人間ゲートを維持し、
モデル指定を署名権限の委任と解釈しない。

`roles.json` と launcher は既存の `roles/potato/acceptance/claude/settings.json` を共有する。
Claude の primary agent を Potato とし、hook / MCP / slash command を無効化し、
読み取りツールを Read / Glob / Grep に限定する。追加の子 agent や fallback model を指定しない。
技術タスクと内部 batch は実 `modelUsage` を回収し、単一の承認済み Opus 5.5、成功、session ID、
空でない結果を確認できたものだけを公開する。別モデル・混在・不明の結果は停止し、証拠を保持する。
受入の旧 command も明示 Codex backend を外部取得・モデル起動前に拒否する。
既存の案件記録と排他キーは保持し、過去の Sol 実行結果を新しい Claude 指定の結果として再利用しない。

実機 installer は所有する旧 `.codex/potato.config.toml` / `review.config.toml` を撤去し、
`~/.claude/named-team/potato.settings.json` を同じ設定の正本へ配線した。所有リンクは16本。
`setup --check` は表示差分なし、既存 Activity を再利用して exit 0。
`start-workspaces potato --check` は Banana 受付の on-demand を返し、新しい常駐 reviewer は起動していない。
起動前の dry-run で backend=claude、model=claude-opus-5-5、effort=high、primary agent=potato、
fallback flag なし、startsSession=false を確認した。

Orca の Potato カード説明と README の案内、モデル無し受付の `potato --inbox` を更新した。
README を開き直し、アクセシビリティ表示で「Opus 5.5 / high 固定」と既存のピン留め順を確認。
native terminal の screen は新しい案内と通常 shell prompt を返した。
その後の最終 screenshot は Mac がロックされたため取得していない。

起動・案件・受付・受入検査の185件を実行（143.948秒）。旧 Codex のメタデータを前提とした
負例 fixture 1件を明示 Codex 値へ更新し、該当1件を再実行して exit 0（1.561秒）。
他の184件は通過。残りの9モジュール199件は156.148秒、exit 0。
すべて一時 Git / fixture CLI を使い、29ファイルの Python 構文と設定 JSON を確認した。
検査とモデル指定の確認を、実 Opus 応答や独立 verdict の成功証拠として扱わない。
変更前のソースとテストは `archives/repairs/potato-opus55-20261006-221914` に相対配置で保全した。
実モデル依頼、既存会話の再起動、外部更新、鍵配布、CI supervisor、staging / commit は行っていない。
