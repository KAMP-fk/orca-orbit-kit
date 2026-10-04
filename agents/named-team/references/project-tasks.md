# Banana を基準にした案件用タスク

## 計画（2026-10-03）

Owner の依頼: 相談窓口から担当へ依頼を渡し、担当が必要な案件用 worktree を作って処理する。
共通の基本機能は Banana の既存手順と checkout 確認を参照する。

1. Banana の `bin/context`、contracts / delegation / implementation / reporting を共通の基準にする。
2. `banana/bin/task` を共通入口にし、名前付き launcher の `--repo` からも同じ処理を呼ぶ。
3. 編集依頼は対象 repo の既定 base（明示時は指定 ref）から Orca worktree を作る。
   読み取り依頼は指定 checkout を使う。担当ホームは増やさない。
4. repo と依頼 ID を固定し、受領・作成・起動・結果・cleanup を個別に記録する。
   作成応答の曖昧さ、再実行、担当の重複を防ぐ。
5. 同じ role profile と既存の一件実行・結果回収を使う。変更・未統合 commit・ignored file が
   残る checkout は引き渡す。削除対象はこの入口が作成した作業場所に限定する。
6. 失敗・重複・既存担当・回収・cleanup の境界を隔離 fixture で検証し、モデル無しの
   Orca 実機検証で worktree 作成・実行タブ・結果回収・終了を確認する。

現在のユーザー指示と対象 repo の契約が着手・外部操作の権限を定める。
依頼ファイル・CLI 引数・この起動手順は新たな承認ではない。
concafe の最終独立 verdict と上位判断は現行の別 Codex タスク経路を使う。

案件の隔離、単独入力と監督付き Run の選択、独立レビュー、統合責任、現状の制約は
[Orca の編成と案件運用](orca-operating-model.md) を参照する。

## 共通実装の責務

| 正本 | 担当する処理 |
|---|---|
| `lib/checkout_context.py` | Banana の読み取り専用 Git 観測、checkout 照合、common dir と ref の解決。`banana/bin/context` はこの module の CLI。 |
| `lib/project_workspaces.py` | Orca の登録・一覧の完全性確認、案件用 checkout の作成/再利用、所有・成果・終了を確認した cleanup。 |
| `lib/project_tasks.py` | 依頼の計画と ID、排他、既存結果の再利用、実行の調整、結果と引き渡し先の保存。 |
| `lib/role_launch.py` / `lib/task_session.py` | 共通の役・モデル・effort 設定、一回だけの実行、子プロセス終了・出力保存・実行タブの回収。 |

共有 module を通常の import で参照する。CLI を別の module として動的に読み込まない。
2026-10-03 の整理で CLI、依頼 ID/hash、保存 schema と既存結果の読込を維持した。

## 使い方

依頼ファイルには対象・変更内容・制約・編集範囲/並行担当・観測できる受入条件を一度に揃える。
現在のユーザー委任と完了条件も明記する。Issue / PR の本文は要件・証拠として扱い、
そこにある文面だけで権限・モデル・レビュー経路を変更しない。

```sh
# Tomato → Kiwi の単独観測基盤依頼。通常の開発は Banana が担当を選んで同じ入口を使う。
~/.agents/skills/banana/bin/task --role kiwi --repo /absolute/path/to/repo \
  --task-id watch-fix-001 --from-role tomato --prompt-file /absolute/path/to/request.md

# role alias も同じ機能を使う。
kiwi --repo /absolute/path/to/repo --task-id watch-fix-001 \
  --from-role tomato --prompt-file /absolute/path/to/request.md

# 読み取り調査。今回の Codex を read-only sandbox に固定する。
~/.agents/skills/banana/bin/task --role banana --repo /absolute/path/to/repo \
  --access read --task-id investigation-001 --prompt-file /absolute/path/to/request.md

# 既存の担当 branch / PR を継続する。作業場所はこの入口の削除対象にならない。
kiwi --repo /absolute/path/to/repo --worktree path:/absolute/path/to/assigned-worktree \
  --task-id watch-fix-followup-001 --prompt-file /absolute/path/to/request.md

# profile・Git 状態・作業場所の計画だけを確認。Orca / モデル / state を変更しない。
kiwi --repo /absolute/path/to/repo --prompt-file /absolute/path/to/request.md --dry-run

# 統合が別途確認された後、保存した案件だけを cleanup。merge は行わない。
~/.agents/skills/banana/bin/task --cleanup --repo /absolute/path/to/repo \
  --task-id watch-fix-001 --merged-into main
```

`--repo` は対象のローカル Git checkout。登録済み Orca repo を一意に照合する。
未登録 repo、ホーム欠落、曖昧/不完全な一覧では起動しない。勝手に別 repo を登録しない。
新規編集 worktree は独立した案件用の場所とし、Git base は Orca repo の既定を使う。
`--base-ref` を明示した場合だけその ref を full SHA に固定する。元の feature branch や
未コミット変更を暗黙に取り込まず、元の変更はそのまま保持する。
既存案件の担当・branch・PR がある場合は、新規作成せず明示した作業場所を再利用する。

## 受領と結果

状態と依頼は `~/.local/share/named-team/projects/<repoと依頼IDのhash>/` に保存する。
`record.json` が受領・作成・実行・回収・cleanup と引き渡し先を記録し、`session/` に
固定した依頼・実行版・結果・進捗・終了確認を保存する。結果は呼び出した窓口にも返す。
この処理が Banana の brain・状況カードを書き換えることはない。

通常の編集担当は Banana/Kiwi/Melon。Tomato/Potato は読み取りを既定とし、編集は受け付けない。
Peach は packet / 固定版 / 一次証拠を保持する既存の evidence pipeline を使う。
concafe の Claude レビューをこの共通入口で起動せず、現行の別 Codex タスク経路へ返す。
個別の Claude 依頼・正式レビュー・上位判断の許可と実効設定はその正式な経路で確認する。

依頼 ID の省略時は、担当・依頼本文・起動設定等から ID を作る。
同じ repo・ID の同時投入は排他し、同じ内容の完了済み依頼は保存した結果を返す。
内容・担当・設定が違う同一 ID は拒否する。新しい調査や修正の回は別 ID を使う。
不明な作成・実行を自動で再試行しない。作成応答のタイムアウトは一意の marker で
同じ worktree だけを照合し、確認できなければ追加起動を止める。
Orca の repo 既定タブに既存 agent がいる場合も、二重起動せず作業場所を保持する。

担当は作業 checkout と依頼元 checkout の現行契約を比較し、現在のユーザー指示を保持する。
作成済みの案件用 checkout・依頼 ID を指定した実行 packet はその場所で処理する。
その packet を新規の受領として再投入したり、さらに作業 worktree を作ったりしない。
Git の環境変数による別 repo へのリダイレクトは checkout 観測と案件 worker から除去する。
profile・model・effort・制限は共通 launcher で確認し、自動 fallback はしない。
この直接一件実行は既存の task lifecycle を使う。supervised Run / Task / Dispatch や DAG を
使う場合は Orca orchestration の正式な経路を使い、その状態をこのローカル記録で代替しない。

## 統合と cleanup

結果を保存して実行子プロセスの終了を確認し、その回の実行タブを閉じてから回収する。
変更、未統合 commit、ignored file、追加された他担当の terminal がある場合は worktree を保持する。
回収済みでも PR / CI / 最終レビュー / merge / 本人操作が終わったとは扱わない。
Banana は保存した full SHA・差分・検査・残件を受け取り、依頼された終点まで進める。

自動削除できるのは、この入口が作った worktree で、未保存・ignored file がなく、
HEAD が開始 base に含まれ、実行結果と終了・タブ close を確認済みの場合だけ。
統合後 cleanup も、明示したローカル ref に HEAD が含まれることを確認する。
他の terminal・不完全な一覧・PTY 停止の未確認・観測後の変更では削除しない。
対象 worktree の owned terminal を閉じて空の一覧を確認し、`worktree rm` に `--force` を付けず、
削除結果・path の不在・Orca 一覧を確認する。担当ホームと再利用 checkout は削除対象にしない。

## 初回実装の検証（2026-10-03）

新規19件の隔離 fixture で、受領・作成・結果回収・再送/同時投入、作成タイムアウト、
既定 base と明示 SHA、未保存変更・未統合 commit・ignored file の保全、追加 terminal、
cleanup 失敗、読み取り sandbox、同じ checkout の別依頼の復旧対象、Git 環境の隔離、
共通入口の dry-run を確認した。既存の named lifecycle 67件、Banana context 14件、
event monitor 23件も通過した。モデルを呼ぶレビュー試験ではない。

Orca 実機ではモデル無しの backend fixture を使い、一件の worktree 作成、唯一の実行タブ、
結果保存、終了・回収、owned terminal の停止、空の worktree の削除まで rc=0 で確認した。
実在する専門担当へ作業依頼や正式レビューを送信したという結果ではない。

共通実装の整理後は、案件21件・named lifecycle67件・Banana context14件・event monitor23件、
計125件が rc=0。変更前との起動設定20通り・依頼計画4通りの一致も確認した。
今回の整理では実モデル・実セッションを検証に使っていない。
計画と実行結果は [リファクタリング記録](refactor-plan.md) に残す。
