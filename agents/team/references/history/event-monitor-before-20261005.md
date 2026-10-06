# 過去の編成・導入記録（現行契約ではない）

この本文は整合性整理前の記録を保存したもの。現行の担当とモデル指定は
[team-topology.md](../team-topology.md)、利用方法は [README](../../README.md) を参照する。
本文内の旧指定は新しい依頼の契約や許可を上書きしない。

---

> 2026-10-05 更新: 現行の常設3窓口・必要時の専門担当・この会話の Owner 指示は
> [team-topology.md](../team-topology.md) を優先する。以下の旧編成・起動・レビュー割当の記録は、この依頼の現在の割当を上書きしない。

# concafe-techo の自動検知と担当起動

2026-10-03、Owner が自動検知の導入と最初の対象を concafe-techo のみに指定した。
ここで許可された自動タスクは、変化の現物確認・既存担当と次の行動の整理。
この監視の導入を、製品実装・投稿・Linear 更新・PR 操作・最終判定の追加許可にしない。

## 計画と完了条件

1. 既存の Orca automation、監視、対象と現行の担当契約を確認する。
2. Linear Issue・GitHub Issue/PR・open PR head の CI の取得と差分保存を実装する。
3. 通常の変化は Banana、明示された `type:decision` の Issue は Tomato、
   3回連続の取得失敗とその回復は Kiwi へ渡す。初回基準と通常の CI 進捗ではモデルを起動しない。
4. 担当ホームで Orca supervised worker を起動し、既存の稼働と重ねない。
   依頼・requested/effective・Task/Dispatch・結果・回収の証拠を保存する。
5. fixture と隔離状態で不完全な取得・競合・不明な起動/終了・重複を検証する。
6. 実対象の初回基準を保存し、モデル無しの監視ターミナルと5分の Orca automation を設定する。
   登録・稼働・実取得・無変化時のモデル起動0件を確かめる。

完了条件: 許可された一つの repo/project を実取得し、既存の担当ホームに接続した監視が有効。
無変化の回はモデル無し。変化の配送と回収は fixture で検証し、実イベントで未検証の箇所を明記する。

## 実行経路

Orca automation は5分ごとに `event-watch request --scheduler` を呼ぶ。
このコマンドは private な SQLite に観測要求を書き、exit 75 で汎用 provider の起動を止める。
Orca の run history の `skipped` は、この時計ではモデル起動を省略した記録。
監視の成功は coordinator の `lastTickAt` / `lastTickError` と各取得元の `success_at` で確認する。
clock の skipped 表示だけで取得や配送の成功を報告しない。

この版の Orca の `automations run`（手動実行）は precheck を通さず provider を起動する。
この時計に対して手動実行を使わない。即時の観測は下記の `event-watch request` を使う。
設定を誤って手動実行した場合の prompt は、設定異常だけを報告して終了するよう限定する。

Banana の既存ホームに `event-watch serve` のターミナルを一つ置く。
この Python プロセスはモデルを使わず、Orca から渡された自分自身の terminal identity で
専用 Run を作成・再接続する。他のターミナルの `--from` を借用しない。
5分の要求を受けて取得・比較・配送・既存 worker の回収を行う。
担当タスクは既存ホームに `worker-start --run ... --worktree id:<完全ID>` で起動し、
カード・checkout を作らない。model / effort は各役 profile の既定を明示し、
`launch.requested` / `launch.effective` を保存して照合する。

## 観測と役割

| 観測 | 自動起動する担当 | 条件 |
|---|---|---|
| Linear / GitHub Issue の新規・本文・status・label・担当等の更新 | Banana | 初回成功以降に値が変化 |
| `type:decision` の Issue の更新 | Tomato | 相談材料の整理。Fable の実判断は自動代行しない |
| PR 新規・head・本文・draft・label・close/merge 等の更新 | Banana | open PR と前回成功以降の更新を取得 |
| open PR の check-runs / commit status の変化 | Banana | 失敗、取消、要対応、または取得したチェック群の完了。CI 全充足や PASS とは扱わない |
| 取得失敗 | Kiwi | 同じ取得元で3回連続。既知の同じ障害を繰り返し起動しない |
| 上記の取得障害から回復 | Kiwi | 未配送の障害報告は回復報告にまとめる |

汎用 Issue 判定や Potato の技術所見を concafe の正式 R へ転用しない。
正式 R は現行正本の明示 `--pr` を使う別 Opus session。ADR-061 の署名ゲートは撤去済み。
最終判定・Owner 代行判断は、この導入依頼に適用された直接の Owner 指示と
対象契約の条件を別タスクで確認する。監視 worker は読み取りと材料整理だけを行う。
監視イベントだけで正式 R や判断を自動割当する許可はない。旧 CAF-279 のモデル・署名要求を
現行正本へ再導入せず、Astra を選択しない。

## 保存・排他・回収

config は `config/concafe-events.json`。repo と Linear workspace/project/team の ID を固定する。
保存は `~/.local/share/named-team/events/concafe-techo/`（directory 0700、file 0600）。
既存 Tomato watch の live state や CI supervisor へ書き込まない。
ソースごとに最後の成功観測、失敗数、正規化した事実、変更イベント、batch と native receipt を保存する。
本文は hash のみ保存する。値が変わらない再取得ではイベントを増やさない。

初回成功は基準保存だけ。同じ対象の未配送の更新は最新へまとめ、古いものは superseded として記録する。
SQLite の更新と file lock で並行 tick を排他にし、serve は lifetime lock で一つに限定する。
担当が作業中、同じ担当の batch が未完了、または起動/終了が不明なら次の起動を保留する。
起動前に launching を永続化し、タイムアウト後に別 Task を再作成しない。
prepared/unknown の期限切れによる自動再試行も行わない。

native worker の accepted settlement を確認したものだけ `worker-release` で出力を保存・回収する。
稼働 batch の local worker 状態は15秒ごとに確認し、サービスの5分ポーリングと分けて回収する。
absence・接続断を終了と扱わず、他担当や既存ターミナルを close しない。
release 不明時も自動で別の終了操作を試さず、status に残す。

## 確認コマンド

```sh
# 読み取り取得。既定はモデルを起動しない。
/Users/kamp/orca/agents/named-team/bin/event-watch tick
/Users/kamp/orca/agents/named-team/bin/event-watch status
# 監視 coordinator に即時観測を要求する。直接モデルを起動しない。
/Users/kamp/orca/agents/named-team/bin/event-watch request
python3 -B -m unittest discover -s /Users/kamp/orca/tests -p 'test_event_monitor.py'
```

`tick` は当該取得に失敗があれば exit 1。clock の `request --scheduler` は常に非0で、
モデル無しの要求受付に成功すると75、要求を確認できない場合は2。
`status` は取得元と pending/active/unknown/settled、Run/handle、最後の tick を返す。
unknown や release_pending は、その Task/Dispatch の現物と native recovery を調べて扱う。
lease の時間切れや tab 不在だけで配送済みイベントを pending に戻さない。

## 範囲と限界

これはポーリングなので検知まで通常最大5分、取得・担当の稼働による保留が加わる。
API のページ上限・不完全な応答・重複・head 変化は取得失敗として保全する。
PR は open 一覧と前回成功の開始時刻から60秒重ねた更新一覧を使い、短時間で close/merge した PR も拾う。
CI は open PR の現在 head に限り、run 全体・deploy・job log・必須 CI の充足は担当が必要に応じて調べる。
Issue コメントの全文や全履歴は取得しない。本文・status 等とサービスが返す updatedAt の更新を検知する。
観測間に更新して完全に元の値へ戻った内容を復元するイベント監査ではない。

Orca が終了したり coordinator が停止した場合は取得できない。
macOS の権限、認証、provider 設定を自動変更せず、外部投稿や一律の定期通知も行わない。
停止は clock を disabled にしてから、対象 coordinator の完全な handle を確認して扱う。
進行中の worker の停止・破棄や既存の旧 automation の再開は、この clock の変更に混ぜない。

## 2026-10-03 の導入確認

- offline: `test_event_monitor.py` 23件、既存の `test_named*.py` 53件が成功。
  ページ欠落、CI head 競合、モデル不一致、起動不明、同役の並行起動、
  coordinator の実プロセス・専用 Run・要求の一回処理を fixture で検証した。
- 隔離した実取得で Linear 314件・open PR 4件の CI を取得し、
  PR #299 の実 head 更新を pending に保存した。モデルは起動していない。
- 本番の初回基準は 2026-10-03 18:29 JST、Linear 314件・open PR 3件の CI。
  初回起動0件、全取得元の失敗0件。
- clock: `539362d1-267c-4b2a-a847-2c9c3c02fb7b`、Asia/Tokyo、5分間隔、enabled。
  検証時だけ一時的に1分へ変更して、native の scheduled run
  `5acbf165-19a0-45d2-ad9f-6881e4f17393` が `skipped_precheck` / exit 75、
  provider の terminal / dispatchedAt が無いことを確認し、5分へ戻した。
- coordinator: Banana の既存ホーム、`term_2cd2bcfc-0693-4704-a50c-6cb919f0c900`、
  専用 `run_9bf1f325e4b9`。他の terminal identity を借りず、モデル無しで稼働。
- 実 PR #301 / #303 と CI の変化3件を一つの Banana batch にまとめた。
  `ctx_b1fabdf10b3c` / `task_aa6d1d5462c2` が native `ready`、
  requested / effective とも `codex` / `gpt-6.1-sol` / `medium`。
  通常の CI 進捗1件は observed のみで、別のモデルを起動していない。
- 18:35 JST に同 worker の `succeeded` / dispatch `completed` を確認し、
  coordinator が `worker-release` で transcript を captured、terminal を released にした。
  イベント3件は completed。同じ Task の再起動は無い。
- 5分へ戻した後の scheduled run `86e497a0-aba7-4b5b-bdea-c9575b9d897c` も
  exit 75 で汎用 provider を起動せず、要求と handledRequest が一致した。
  18:35:59 JST に全取得元の成功と lastTickError 空、追加起動0件を確認。
  この時の CI 進捗は observed に保存しただけ。
- 全担当ホーム各1件、skills root のカード1件。既存の Banana terminal を維持し、
  監視用 terminal だけを追加した。Peach/Potato/Melon の作業を変更していない。

確認中に二つの問題を扱った。手動 automation run は precheck を迂回してモデルを1回起動し、
防御用 prompt に従って設定異常だけを報告し native completed となった。
また、初版は `worktree ps` の `worktreeId` を `id` と読み違え、worker-start を呼ぶ前に停止した。
必須の起動入力を mutation fence より前に検証するよう修正し、実応答形式の回帰テストを追加した。
呼出前の例外という証拠がある、その未起動 batch だけを履歴を残して復旧した。
native inventory に無いという理由だけで unknown を再配送する処理は追加していない。

18:34 JST の再取得は全取得元で成功し、前回の CI head 競合は回復した。
runtime の観測・起動・回収 receipt は private DB と Git 対象外の reports に保存する。
この検証結果を最終独立レビュー PASS や製品 PR の verdict として扱わない。
