# Orca の表示とエージェント観測

2026-10-05 Owner追加依頼の「表示・セットアップ・動きの追跡」を対象にする。

## 実機の表示

| 表示 | 役割 |
| --- | --- |
| Orca｜エージェント基盤 | Banana担当の共有ソース。Activityタブでエージェントの変化を観測 |
| Tomato｜相談・受け渡し | Fable / medium による幅広い相談・目的・判断材料。開発領域でBananaと連携 |
| Potato案件worktree | 固定SHAの成果を独立確認・Bananaへの指摘 |
| Banana｜開発窓口 | 開発案件の受領、Codex実装、レビューworktreeへの引渡し |
| Skills｜スキル管理 | スキルの管理 |

タイトル・コメントと Orca の親子メタデータを現行構成に合わせる。Tomato / Banana の常設ホームは独立表示。
両者は異なる担当領域を持ち、開発の指示・質問・報告で連携する。
別 repo の共有基盤は独立カード。Potato の常設ホームは作らず、案件ごとに独立レビュー checkout を使う。
旧 Kiwi / Melon / Potato の checkout は復元用の保管後に撤去し、旧受入基盤の folder 登録も解除した。
保管は `archives/retired-homes/` に置き、setup の表示対象には含めない。
現行の Git branch / checkout の住所と既存ターミナルは保全する。
ホームは厳密なlocal pathで選び、欠落・重複・不完全なinventoryなら変更前に停止する。
旧BananaカードにClaudeが観測されてもDevinへ名前を付け替えない。
既存時計automationや旧coordinatorを新コードへ再起動したとは扱わない。

## セットアップ

```sh
python3 -B agents/team/bin/setup --check
python3 -B agents/team/bin/setup
python3 -B agents/team/bin/setup --home /private/tmp/isolated-named-team
```

実機setupは事前検査、ownedリンクの追加と旧 Maintenance / Kiwi / Melon / Peach 配線の撤去、カード表示、
モデル無し監視タブの作成・再利用、監視出力の鮮度確認を行う。
同名監視タブが複数ある、既存タブの観測が古い、所有外リンクに衝突する場合は停止する。
既存Devin CLIの `~/.local/bin/devin` は対象にしない。
独自controllerは `devin-flow`、観測は `activity`。base config・trust・認証・署名鍵に触れない。
部分適用・応答不明の後は `--check` とタブの状態を確認し、作成や起動を盲目的に再送しない。

## 観測の範囲

`Activity｜エージェント状況` は10秒間隔で読み取り、変化時にスナップショットを表示する。
Orca の標準タブでは `--screen` を使い、同じ画面を更新して最新の状況と3役の流れを表示する。
通常の CLI 出力は追記形式を維持し、端末以外の出力へ画面制御コードを送らない。
変化がなくても60秒ごとに取得時刻を更新する。通常表示は活動・待機と直近3件の終了記録。
Orcaのイベント時刻と今回の観測時刻を分け、過去のhook状態を現在のモデル応答と扱わない。

```sh
activity --once
activity --json
```

- Orcaの全localカードのネイティブagent hook状態を取得。remote hostは対象外。
- Devin controllerのIssue・Session・branch・PR・SHA・state・記録時刻を表示。
- 2026-10-07 JST の Owner 指示により Devin は利用しない。通常観測は保存済みのローカル台帳だけを読む。
  保全した `--observe-devin` は外部 adapter を呼ぶ旧機能で、現在の運用では使わない。
  unknown 起動や done を再送・再開しない。
- 基盤Taskのrole・stage・cleanup・worktree識別情報を表示。
- プロンプト、tool入力、会話、feedback、認証値は表示しない。

Devinのcontroller状態とremote workerStateを分ける。観測は台帳・Linear・PRを変更しない。
`sync`、修正指示、レビュー、署名、Ready、merge、Doneはこの監視から実行しない。
ベンダーDevin CLIの任意の未連携Sessionはcontrollerの管理下と扱わない。
現状はadapter未接続・起動不可、対象repoのcontroller実行記録なし。
ベンダーCLIのインストールや表示成功は外部接続成功を意味しない。

`NAMED_TEAM_DEVIN_CONFIG` / `NAMED_TEAM_DEVIN_STATE_DIR` はcontrollerとActivityで共用する。
`NAMED_TEAM_PROJECT_TASK_DIR` はTask観測と既存Task機構で共用する。
既定台帳は `~/.local/share/named-team/devin` と `projects`。
CLIで別の `--config` / `--state-root` を使う場合、観測側にも同じ値を設定する。
設定ファイルに秘密値を格納せず、adapter側で認証を管理する。

Orca再起動で監視タブのcommandが復元されても、読み取り観測だけを行う。
タブを閉じた場合はsetupで再配置する。停止したタブがshellとして残る場合はsetupが
古い出力を検出するので、その監視タブだけを確認して復旧する。
