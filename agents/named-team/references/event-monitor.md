# concafe-techo の自動検知と担当起動

2026-10-03、Owner が自動検知の導入と最初の対象を concafe-techo のみに指定した。
ここで許可された自動タスクは、変化の現物確認・既存担当と次の行動の整理。
この監視の導入を、製品実装・投稿・Linear 更新・PR 操作・最終判定の追加許可にしない。

## 計画と完了条件

1. 既存の Orca automation、監視、対象と現行の担当契約を確認する。
2. Linear Issue・GitHub Issue/PR・open PR head の CI の取得と差分保存を実装する。
3. 通常の変化は Banana、明示された `type:decision` の Issue は Tomato、
   3回連続の取得失敗とその回復は Banana へ渡す。初回基準と通常の CI 進捗ではモデルを起動しない。
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
| 取得失敗 | Banana | 同じ取得元で3回連続。既知の同じ障害を繰り返し起動しない |
| 上記の取得障害から回復 | Banana | 未配送の障害報告は回復報告にまとめる |

レビュー・上位判断の割当は [team-topology.md](team-topology.md) に従う。
監視 worker は読み取りと材料整理だけを行う。変化の検知は、製品修正・正式レビュー・
上位判断の自動割当を新たに許可するものではない。

旧 pending Kiwi は役名と履歴を保持し、受付だけ Banana へ解決する。
同じ受付を使う active/unknown/未完了 batch があれば後続の起動を保留する。
Kiwi への基盤修正は現物確認後、通常の案件依頼として Banana が割り当てる。

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

## ソース更新と実稼働の区別

上の health→Banana は現行ソースの契約。稼働中 coordinator が旧版を読み込み済みなら、
ソース変更だけでは反映されない。この整合性整理では live DB・automation・監視プロセス・
CI supervisor を変更しない。新しいソースの fixture 検証と、実稼働の観測結果を別々に報告する。

当時の導入計画、実取得・時計・receipt の確認は
[導入時の記録](history/event-monitor-before-20261005.md) に保存した。
記載された ID・件数・状態を現在の観測結果として使わない。
