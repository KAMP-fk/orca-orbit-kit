# Banana の自律進行

Owner の 2026-10-07 の直接依頼により、委任済みの concafe-techo 開発を、
既存 Banana の完了後も継続する。新しい常設担当やモデルを時計から作らない。
`banana continue` が継続運転を管理し、実装・成果回収・PR・CI・レビュー・完了確認は
Banana が現在の担当と対象契約に沿って行う。

```sh
banana continue enable --note 'Owner の直接依頼と、対象・委任範囲'
banana continue status
banana continue tick
banana continue pause --note 'Owner の停止指示'
banana continue settle --id <delivery-id> --outcome progressed --note '成果と次の担当・行動'
```

実装 WIP は **2 本**。候補検知だけで依存・AC・既存担当・共有ファイルの競合を
確認済みとしない。枠が空いたら Banana が現物で確認して次の Todo を補充する。
CI・レビュー・人間判断待ちは案件単位で保持し、独立した別案件を進める。
新規 subagent 起動・追加依頼、自己 PASS、手動 Ready/merge、権限迂回を禁止する。
通常の新規進行・実装は Sol medium、複雑な技術作業は Sol high。
concafe の最終独立レビュー・署名は最新の直接 Owner 指示（CAF-279）に従う
未関与の別 Codex タスクの Astra high、上位判断は別タスクの Astra medium。
古い source のモデル割当から上書きしない。稼働中担当の設定を変更したとは扱わない。

既存の5分時計 `event-watch request --scheduler` の独立した opt-in 経路を使う。
通常のイベント取得・outbox・旧 worker accounting は維持する。
precheck は常に非0（通常75）で終了し、automation の汎用 provider を起動しない。
有効時の外部観測は最大90秒なので、時計の precheck timeout は **100秒** にする。
無効時と `--state-root` による fixture 検証は実際の継続運転に触れない。
時計は毎回新しい CLI process から現在の source を読むため、既存の監視や
モデルセッションを再起動せずにこの経路を反映できる。

継続運転の正本は `~/.local/share/named-team/continuation/concafe-techo/control.json`。
排他 lock、Owner 委任、有効/休止、送信前 fence、Orca の送信 receipt と完了結果を保持する。
既存 packet・案件台帳・brain・鍵をこの controller から書き換えない。
人が状態ファイルを編集する代わりに CLI を使う。

- 既存 Banana の正確な workspace / pane / agent / terminal incarnation を照合する。
  main turn の作業中・入力途中・複数担当・不完全な一覧・旧 runtime なら送信しない。
  背景のCI/レビュー待ちでカードが監視中でも、main turn の終了と native `tui-idle` を
  両方確認できれば別案件を進められる。既存の監視を取り消したり重ねたりしない。
- `input_accepted` と `turn_started` と案件の完了は別物。通常は Banana が送信 ID を
  `settle` で返す。返答を伴う新しい完了が native 状態で確認できた場合も回収できる。
  異なる process incarnation で古い送信の完了を代用しない。
  開始未確認の受付済み送信は、保存した本文と request ID の `--retry-request` で
  同じ receipt を観測する。他の人間の turn や背景処理をその依頼の開始証拠にしない。
- `waiting` / `blocked` の結果は、観測した Issue・PR・CI・成果に変化があるまで静かに待つ。
  通常 CI の queued → running だけでは再開しない。3回続けて観測上の進展が無い場合も
  同じ依頼を繰り返さず、次の変化を待つ。
- 送信が曖昧なら fence を保持し、再送や別 agent 起動をしない。`enable` でも
  未確認の送信を消さない。元の receipt / terminal を確認して復旧する。
- Owner の停止・native の人間による interruption は休止を保持する。
  CLI の停止要求は時計が観測 lock を持っていても保存し、送信直前にも照合する。
  `enable` の直接委任で再開する。PC / Orca の停止中は実行できない。

隔離 fixture のテストは `tests/test_banana_continuation.py`。
実運用の有効化・時計の設定・native 送信受付・実際の turn 開始は、
それぞれ現在の receipt で確かめる。テスト成功だけを稼働成功や独立 verdict としない。
