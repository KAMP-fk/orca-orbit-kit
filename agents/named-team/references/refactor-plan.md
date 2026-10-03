# Agent refactor — 2026-10-03 JST

依頼: Tomato / Banana / Kiwi / Peach / Potato の棲み分け、業務分担、Orca 最適化。人格・記憶・live state と最終署名ゲートは変更対象外。

Owner の後続依頼「依頼を受領した担当が案件用 worktree を作る。基本機能は Banana を参照する」は、
[案件用タスクの計画・実装・検証](project-tasks.md) に記録した。共通受付・作業場所の用意・
結果回収・重複防止・統合前の保持・所有する worktree の安全な cleanup を実装済み。

## 共通実装のリファクタリング計画（2026-10-03）

Owner の依頼「一旦リファクタリングしよ」により、直前に追加した共通受付を整理する。

1. 既存の案件・起動・checkout・監視の検査を実行し、変更前の動作を固定する。
2. Banana の checkout 確認を共有 module に置き、CLI は薄い入口にする。
   Git 状態確認、Orca の worktree/terminal 操作、依頼の進行・結果管理を分離する。
3. 依頼 ID と保存先の導出、排他、完了結果の再利用、起動設定の重複を整理する。
4. CLI 引数、起動設定、依頼 hash、保存 schema、二重起動防止と削除条件を保持して、
   同じ隔離 fixture と配線・dry-run で検証する。モデルや稼働中セッションは検証に使わない。

対象は named-team の共通実装と Banana の checkout 入口。並行中の reviewer の変更は保持する。
この計画の検査は実装側の確認であり、独立 verdict ではない。

実行結果:

- 変更前123件の検査は rc=0。Git 観測を `checkout_context.py`、Orca の操作を
  `project_workspaces.py` へ移し、`project_tasks.py` は受付・実行・回収の調整に絞った。
- CLI の動的 import を除去。依頼の key/保存先と排他を共通化し、起動設定の検証を
  `role_launch.py` に集約した。保存 schema と既存の role/model/effort は維持した。
- 変更後は案件21件、named lifecycle67件、Banana context14件、event monitor23件、
  計125件が rc=0。一覧が不完全な場合の作成・起動・削除抑止を2件追加した。
- `25a6eec` と起動設定20通りを比較し、command・環境・metadata が一致。
  移動した Git 観測3関数は AST が一致。配線 check と `git diff --check` は rc=0。
  依頼計画も4通りが一致し、ID/hash・保存先・schema の互換性を確認した。

検証は隔離 fixture と読み取り比較だけで実施。実モデルの呼出し、実セッションの作成・停止、
既存の live state の移行は行っていない。

## 初回のリファクタリング計画

1. 現物と運用契約を確認し、入力・責任・成果物・引き渡し先を役割表にする。
2. 各 skill の選択条件と境界を共通契約に合わせる。Tomato の人格原本はそのまま、Banana の開発手順は版管理可能な正本へ移し、旧 path を互換リンクにする。
3. 役割メタデータと Orca executable 選択を一箇所に集める。Tomato/Banana の command・skill・profile を追加する。依頼ファイル入力と Peach の見える task 実行を用意する。
4. fixture のみで配線、文字列の保存、新しいタブ、失敗・曖昧な回収、モデル固定を検査する。既存の観測・レビュー証拠の回帰検査も実行する。
5. ローカル配線を反映し、read-only check と dry-run で確かめる。モデル起動・外部投稿・PR/Linear 操作はこの検証に含めない。

完了条件: 五役に重複しない入口があり、共通契約から必要な手順へ辿れる。Orca の既存動作とモデル/独立性の条件を保全し、配線・回収・既存回帰を実検査で確認する。検査結果は独立レビュー PASS と呼ばない。

## 実行状況

1–3 は実装済み。`roles.md` と各 skill に責任・成果物・引き渡し先を反映。
`roles.json` / `lib/role_contract.py` を起動とカード準備の共通入力にした。
Tomato/Banana の入口、`--prompt-file`、Peach の `--orca`、無効な途中 PASS を最終結果に混ぜない回収を追加。
既存の Peach/Potato の provider、モデル固定、read-only、証拠ゲートは保持。

ローカル配線は15リンク、Peach は既存の7リンクを check で確認。
Orca の五役＋既存 Melon のカードも check で確認。
追加カード作成時の空の shell 3件は terminal show で確認してからその handle だけを閉じ、ptyKilled=true を確認。
既存タスクは停止・再依頼・モデル変更していない。

モデル/外部サービスの実呼出し・外部投稿・独立署名 verdict はこの実装検証に含めない。

## 検証結果

以下は fixture と一時状態を使った実装側の検査。独立レビュー承認ではない。

| cwd | コマンド/検査 | 結果 |
|---|---|---|
| /Users/kamp/orca | `python3 -B -m unittest discover -s tests -p 'test_*.py'` | 193件、rc=0 |
| /Users/kamp/.claude/skills/Tomato | `python3 -B -m unittest discover -s tests -p 'test_*.py'` | 23件、rc=0 |
| /Users/kamp/orca | 最終の参照先修正後: `python3 -B -m unittest discover -s tests -p 'test_named*.py'` | 39件、rc=0 |
| /Users/kamp/orca | 同修正後: `python3 -B -m unittest discover -s tests -p 'test_agent_refactor.py' -k claude` | 6件、rc=0 |
| 両 source repo | `git diff --check` | rc=0 |
| /Users/kamp/orca | `shellcheck --severity=warning`（Peach entry、cli/github/linear/backend module） | rc=0 |
| 五役の skill | skill-creator の `quick_validate.validate_skill`、UI YAML の読込 | 5件成功、rc=0。PyYAML は一時ディレクトリで使用 |
| /Users/kamp/orca | `agents/named-team/install.py --check`、Peach `install.sh --check` | 15 + 7リンク、rc=0 |
| /Users/kamp/orca | `agents/named-team/bin/start-workspaces --check` | 五役 + Melon、rc=0 |
| インストール済み command | 五役の `--dry-run` | 全件 rc=0、startsSession=false |

検査対象: Literal な依頼ファイル、対象 path、provider/effort の維持、モデル metadata の拒否、
一件ごとの可視タブ、曖昧な作成と回収、結果欠落、無効な途中 PASS の除外、既存の CI/Tests 証拠ゲート、観測の履歴と取得失敗。
実モデルの稼働・実サービスでの取得・既存セッションへの新定義の再読込は未検証。

## 既存ワークスペースの重複修正 — 2026-10-03 JST

初回のカード準備では skills project だけを検索したため、brain の Tomato/Banana と
reviewer project の Peach を見落とし、同じ役のカードを skills 側へ追加していた。
Owner の指摘を受け、`roles.json` にホーム path と旧表示名を明示し、Orca 全体の
一覧から固定ホームを照合するよう修正。タスク起動も同じ解決処理を使う。
同じホームの候補重複・不完全な一覧は作成/起動前に停止し、brain/reviewer ホームが
ない場合に別 project へ代替カードを作らない。

この作業で追加した Tomato/Banana/Peach の3カードは、folder project の card 除去が
元フォルダを削除しない実装であることを確認してから、Orca CLI の `worktree rm` を
exact id 指定、force/hook なしで実行。各応答は removed=true。
再取得した全一覧で三役それぞれ未アーカイブ workspace が1件、従来の path のまま
であることと、skills フォルダが残ることを確認。既存ホームは除去・改名していない。

| 検査 | 結果 |
|---|---|
| `python3 -B -m unittest discover -s tests -p 'test_named*.py'` | 48件、rc=0 |
| `python3 -B -m unittest discover -s tests -p 'test_agent_refactor.py' -k orca_peach` | 2件、rc=0 |
| `agents/named-team/bin/start-workspaces --check` | 六役の既存ホームを確認、rc=0 |
| `agents/named-team/install.py --check` | 15リンク、rc=0 |
| `git diff --check` | rc=0 |

自動起動の automation は未追加。モデルを使った起動テストも行っていない。

## 上位層と専門担当の構成 — 2026-10-03 JST

Owner の指定: brain に上位層の Tomato/Banana、その下に Peach/Kiwi/Potato。
相談事項は Tomato または Fable に確認する。

実行計画と結果:

1. 既存の共通契約、五役、Fable の判断手順とホームを確認した。
2. `roles.json` の `layer` / `parentRole` / `consultation` に構成を定義し、
   五役の skill、関係する profile、Banana の分担と Tomato/Fable の受渡し手順へ反映した。
   通常の割当と成果回収は Banana、意図・前提・説明の整理は Tomato、材料が揃った
   具体的な選択は委任された Fable の経路を使う。専門レビューの独立性は維持する。
3. 既存ホームを使う確認出力とタスク/dry-run に構成情報を追加した。
   `start-workspaces --check` は専門三役の `coordinatorWorktreeId` が既存の
   brain/Banana の完全な ID を指すことを確認する。
4. 関連する fixture テスト、スキル検査、配線、既存ホームと dry-run を確認した。

Orca のネイティブな親子設定は同じ repo・host・project に限られる。
異なる project の既存ホームへ親を設定する試行は拒否され、再取得した一覧の親は
変更されていない。無効な設定操作を行う実装は取り除き、役の構成は共通メタデータと
依頼・報告の経路で管理する。新しいカード・モデルセッションは作成していない。

| 検査 | 結果 |
|---|---|
| `python3 -B -m unittest discover -s tests -p 'test_named*.py'` | 50件、rc=0 |
| `python3 -B -m unittest discover -s tests -p 'test_agent_refactor.py' -k orca_peach` | 2件、rc=0 |
| skill-creator `quick_validate.validate_skill` | 五役成功、一時 PyYAML のみ使用 |
| profile TOML と Python の構文読込 | 3 profile / 5 entry・module 成功、既定モデル・effort を保持 |
| `start-workspaces --check` / 両 installer `--check` | 既存六役 / 15 + 7リンク、rc=0 |
| インストール済み五役の dry-run | 上位/専門担当・通常の回収担当・相談先を確認、startsSession=false |
| 両 source repo の `git diff --check` | rc=0 |

定義は次の起動・依頼から使用する。相談送信・Fable の実判断・自動検知/起動はこの反映では実行していない。

## skills の同名カード再出現の整理 — 2026-10-03 JST

Owner の画像で skills が3件表示されていることを確認。CLI の全一覧では正規の folder root 1件と、
今回追加して除去した Tomato/Banana の旧完全 ID の2件が、表示名 skills で再出現していた。
元の tab ID も同じで、復元された空のシェルが各1件、agent は無し。
前回の `worktree rm` 応答と直後の一覧だけでは、残るタブの復元情報・表示まで確認できていなかった。

余分な2件の完全 ID だけに `terminal close --worktree id:<完全なID> --all` を実行。
それぞれ closed=1 / stopped=1 / retiredSurfaces=true を確認してから `worktree rm` を実行し、removed=true を確認した。
再取得した一覧で skills という表示名は正規の root 1件、Kiwi/Potato/Melon の既存カードと
元の skills フォルダは保持。六役の `start-workspaces --check` は rc=0。

画面の再取得は macOS Accessibility の permission_denied によりできていない。
「CLI 一覧で1件」を確認済みの範囲とし、画面自体の確認済みとは扱わない。作業中の既存エージェントは停止していない。

## 担当ホームの統一と再発防止 — 2026-10-03 JST

Owner の依頼: 残っている同名ワークスペースの改善を計画して実行する。

計画:

1. Orca 全体の登録、完全 ID、各 terminal と agent の稼働を確認する。
2. Kiwi/Potato/Melon の既存 Orca 開発 worktree を担当ホームに統一する。
   brain の Tomato/Banana と reviewer project の Peach は維持する。
   Melon の進行中タスク・ブランチ・作業場所・terminal はそのまま引き継ぐ。
3. 同名の skills 側の三カードは、未使用であることを再確認し、完全 ID を使って
   terminal の復元情報を閉じてから folder card の登録だけを除去する。
   skills の元フォルダと root card は維持する。
4. 表示名・説明を共通契約へ揃え、起動先とホーム確認に反映する。
   ホーム欠落時の自動カード作成を取り除き、別 project に担当を増やさない。
5. 隔離 fixture、配線確認、dry-run、再取得した全登録と terminal の一致を検証する。

完了条件: 各担当の未アーカイブのホームが一つ、skills は root card 一つ。
既存の稼働 terminal と Git worktree を維持し、専門三役の回収先は brain/Banana。
確認範囲は CLI の登録と実装検査とし、画面のピクセル確認とは区別する。

実行結果:

- Kiwi/Potato/Melon の `workspaceRoot` を既存の `~/orca/workspaces/orca/<Role>` へ変更。
  `start-workspaces` から repo/card の自動作成処理を取り除き、全役のホームと回収先を配線前に確認する。
- skills 側の三カードは folder project に属し、agent は0件。
  Kiwi の空の shell 1件だけを閉じ、三カードそれぞれの `retiredSurfaces=true` と `removed=true` を確認。
- 既存六役の表示名と comment を責任表に合わせた。モデル設定・実行中の設定は変更していない。
  直後の全一覧で各役のホームは1件、skills の未アーカイブ card は root 1件。
  六役の worktree ID・instance ID・path・Git head・branch・native parent と terminal handle 集合は前後で一致した。
  操作記録は除外対象の `/Users/kamp/orca/reports/role-home-cleanup-20261003.json` に保存。

| 検査 | 結果 |
|---|---|
| `python3 -B -m unittest discover -s tests -p 'test_named*.py'` | 53件、rc=0 |
| `python3 -B -m unittest discover -s tests -p 'test_agent_refactor.py' -k orca_peach` | 2件、rc=0 |
| `start-workspaces --check` | 六役の既存ホームと Banana の回収先、rc=0 |
| 両 installer の `--check` | 15 + 7リンク、rc=0 |
| インストール済み五役の dry-run | 統一後のホーム・構成、全件 startsSession=false / rc=0 |

これは登録整理と実装側の検査。独立 review PASS ではない。
画面自体は Accessibility の既知の permission_denied により未確認。
Issue/PR/CI の変化を検知する automation はこの整理で追加していない。

## 過去タスクの再実行を防ぐ — 2026-10-03 JST

Owner の依頼: Kiwi/Potato/Melon のタブと裏の稼働を確認する。
旧セッションの停止対象は、Owner が選択した「完了確認済みの Codex 3つだけ」。

計画と実行結果:

1. native terminal/layout、実プロセス、各タスクの開始・完了記録を照合した。
   Kiwi/Potato のホームは空の shell。Potato の実作業は指定された Melon checkout の別タブにあり、
   そのタブへ切り替えた。タブと一致しない旧 Codex 3つは完了イベントを再照合して停止し、終了を確認。
   担当・完了を未確認の旧 Claude 3つは停止していない。
2. Melon の過去タスク5件が復元コマンドで起動したことを、worker PID と出力更新で確認した。
   完了済み2件と Potato 1件の再実行、および作成未確認だった2件の遅延起動。
   停止範囲を広げる前に5件とも自然終了し、現在の三ホームはモデル無しの shell 待機。
   既存タスクの出力が再実行によって上書きされた点は、除外対象の調査記録に残した。
3. 起動は一度だけ作成し、`--focus` の応答待ちと不在を根拠にした二度目の作成を取り除いた。
   worker は確認した terminal handle が一致するまでモデルを起動しない。
   依頼単位の排他・一度だけの開始記録で、同時起動、完了済みの復元、開始後クラッシュの再試行を防ぐ。
   未確認の作成は中止を記録し、遅れて復元されてもモデルを起動しない。
4. 子プロセス終了後はモデルを残さず、回収用 wrapper だけを最大30秒維持する。
   結果を読んでから、そのタブだけを `terminal close --terminal <handle> --tab` で永続的に閉じる。
   実機の短い確認コマンドで、先に PTY が失効する競合を確認してこの回収待ちを追加した。
5. 完了済みの結果の保持、同時実行、一度開始した依頼、handle 不一致、作成タイムアウト後の遅延起動、
   子プロセス終了後の wrapper 待機と cleanup 失敗を隔離 fixture で確認した。

| 検査 | 結果 |
|---|---|
| `python3 -B -m unittest discover -s tests -p 'test_named*.py'` | 59件、rc=0 |
| `python3 -B -m unittest discover -s tests -p test_event_monitor.py` | 23件、rc=0 |
| `python3 -B -m unittest discover -s tests -p test_agent_refactor.py -k orca_peach` | 2件、rc=0 |
| native Orca、Python の短い確認コマンド | モデル呼び出し無し、結果保存・close・wrapper 終了、rc=0 |
| native terminal/layout 再取得 | Kiwi/Potato/Melon の agent は0、確認タブは無し、既存 shell を保持 |

調査記録: `/Users/kamp/orca/reports/role-runtime-inspection-20261003.json`。
独立 review PASS ではなく、Orca 自体の復元処理を修正・再起動したという報告でもない。

## 2026-10-03 新規タブの対話エージェント起動

Owner の依頼: 担当ホームで新規タブを開いた時点で、Tomato/Banana と同様に
Claude または Codex の担当エージェントが入力待ちになっている構成にする。

計画と実施:

1. 既存の role profile と Orca の新規 terminal の shell 起動を確認した。
   既定タブの設定 UI は Accessibility 権限で取得できず、Orca 内の対話 login zsh の
   起動処理で担当ホームだけに適用する方式を選んだ。
2. `roles.json` の exact home と Orca の worktree/terminal identity を照合する
   `bin/tab-agent` と `shell/tab-autostart.zsh` を追加した。依頼・resume 引数を渡さず、
   既存の role profile と Claude の model/effort/読み取り制限を使う。
3. Orca の明示コマンド用 zsh wrapper の `ready` / `identity` を検出して起動を見送る。
   同じ terminal handle の再読込・入れ子の login shell も二重起動しない。
4. installer の `--tab-autostart` で `.zshrc` の専用 block だけを配線した。
   既存設定と file mode の保持、再実行、check、owned uninstall、競合保存を確認した。
   Codex の対話起動だけ更新確認を抑え、インストール済みバージョンを維持する。
5. Kiwi/Melon/Potato の通常の新規タブを開き、入力待ちの実画面と `tui-idle` を確認した。
   Codex の初回更新案内はスキップした。Potato は専用ホームの初回 folder 確認後に
   `@potato` / Opus 5.5 / high の入力待ちを確認した。作業依頼は送信していない。
   調査・明示コマンドの検証タブは、その handle の `--tab` close だけで除去した。

検証:

| 検証 | 結果 |
|---|---|
| `test_named_*.py` | 67件、rc=0（新規タブの隔離 fixture 8件を含む） |
| `test_event_monitor.py` | 23件、rc=0 |
| `test_agent_refactor.py` | 46件、rc=0 |
| 六役の新規タブ fixture | 正しい profile / model / effort、依頼無し |
| named installer `--check --tab-autostart` / Peach installer `--check` | 15リンク + 専用 block / 7リンク、rc=0 |
| 六役の `start-workspaces --check` | 既存ホームを照合、rc=0 |
| Kiwi / Melon の実画面 | GPT-6.1-Sol / medium、入力待ち |
| Potato の実画面 | @potato / Opus 5.5 / high、入力待ち |
| 三タブの `terminal wait --for tui-idle` | 全て satisfied=true |
| Kiwi の明示 printf コマンド付きタブ | printf を実行して通常 shell に戻る。モデルは起動せず |
| `.zshrc` / hook の `zsh -n` | rc=0 |

反映範囲は現在の Orca の通常の新規 zsh タブ。既存の実行中タブと他の project の
既定 agent 設定は変更しない。Peach の実レビューは従来の evidence pipeline を使い、
concafe の最終独立 verdict と上位判断の別 Codex タスク経路を維持する。
モデルを呼ぶレビュー試験や署名 verdict の発行ではない。
モデルを使った再実行テストは行わず、未確認の旧 Claude 3つを停止済みとは扱わない。
