# モデル無しのイベント監視

`event-watch` の Linear/GitHub/PR/CI取得・差分・耐久outbox・取得失敗履歴と排他を維持する。
初回基準と無変化、通常CI進捗はモデルを起動しない。失敗閾値は現行 config の3回。

| イベント | 受付 | 動作 |
|---|---|---|
| type:decision | Tomato | 既存の読み取り相談worker。実装・外部投稿を行わない |
| Linear unstarted / agent:devin（旧ラベル） | Bananaの開発候補 | outboxのみ。旧ラベルを Devin 起動許可にしない。既存担当・AC・委任・排他を確認し、実装は Codex 経路で扱う |
| PR / CI / health / その他Issue | Orca Potato (review) | 品質受信箱に残す。モデル/Approve/mergeを自動起動しない |
| 旧 pending Peach/Devin/Kiwi/Banana | 既存記録 | 履歴を維持。再送や暗黙のモデル起動をしない |

既存 active batch の native worker settlement / release accounting は保持する。
unknown/launching を期限切れと見なして再送しない。DBや台帳を直接編集しない。
`event-watch status` はoutbox件数とbatch、受信box詳細は実DBの読み取りで確認する。
外部 Devin Session の既存台帳は保全する。2026-10-07 JST の Owner 指示により
Devin は Orca で利用せず、時計・候補ラベル・既存 pending から起動・再開・再試行しない。

2026-10-05 JST に確認した既存 automation は
`539362d1-267c-4b2a-a847-2c9c3c02fb7b`（concafe-techo｜自動検知の時計）。
5分ごと、enabled=true、precheckは `event-watch request --scheduler`、最後の表示は skipped_precheck。
旧 Banana home を参照している。設定の読取だけを実施し、停止・変更・再起動はしていない。
ソースと稼働中 coordinator の読込済みコードは別物。
新adapter未接続の間に旧実装ルートへ戻したり、起動を再試行したりしない。

Owner の 2026-10-07 の直接依頼による [Banana の自律進行](banana-continuation.md) は
別の opt-in 経路。時計の `request --scheduler` が、既存 Banana の待機と進められる仕事を
確認して継続を依頼する。outbox の候補を自動実装許可へ変えず、新しい worker を時計から
起動しない。無効時の既存監視の動作は維持する。

切替時は [運用手順](devin-operations.md) のdrainを使い、既存担当と不明batchを先に回収する。
旧導入記録は [history/event-monitor-before-20261005.md](history/event-monitor-before-20261005.md)。
