# Tomato・Banana・Potato の連絡と記録

Owner 2026-10-07 の依頼により、3役の依頼・質問・返答・受領確認を共通の耐久受信箱へ残す。
セッションの socket や権限モードが違っても原文を読み返せる。正本は
`~/.local/share/named-team/communication/messages/*.json`、受領確認は `receipts/*.json`。
役名は送信者の申告であり、署名・承認・独立性の証明ではない。

## 送る・受ける・返す

Tomato と Banana は起動時、作業の区切り、完了報告前に自分の未受領分を読む。
受け取ったら、次の担当と行動、または保留理由を付けて受領確認する。
受領確認は完了報告ではない。回答・成果は元の ID に返し、依頼から返答までをつなぐ。

```sh
team-mail inbox --role tomato
team-mail inbox --role banana
team-mail send --from tomato --to banana --subject '対象と依頼' --body-file /absolute/request.md --source /absolute/decision.md
team-mail ack --role banana --id <message-id> --note 'Banana が対象と AC を確認。次は技術調査'
team-mail reply --from banana --id <message-id> --body-file /absolute/answer.md --source /absolute/report.md
team-mail log --date 2026-10-07
```

本文には対象、依頼または質問、確認した事実、根拠（path / PR / full SHA / run）、
次の担当・行動、返答が必要かを書く。受信箱へ保存しただけなら「保存済み・受領未確認」と報告する。
`inbox` は未受領・未返答を表示し、回答が必要な依頼は受領確認のあとも残る。
通知だけなら `send --no-reply` を使い、受領確認で完了する。`--all` は完了済みも表示する。
重要な進行変更・停止・完成・判断待ち・見逃しは相手へ伝え、通常の作業記録は各役の報告へ残す。
Tomato ⇄ Banana は意図・受入範囲・進行、Banana ⇄ Potato は固定対象・質問・指摘・修正条件、
Tomato ⇄ Potato は評価・見逃し・規準の質問を交換する。

セッション間 SendMessage と Orca の通知は注意を向ける補助。保留・失効・受領不明でも
本文を受信箱に残す。権限モードを揃えるために確認や sandbox を弱めない。
相手の返答を待つ依頼・質問・返答を保存したら、`orca-cli` で本人と対応付けた既存端末に
「共通受信箱に連絡あり、ID: …」の短い合図を `terminal send` で送る。
SendMessage の承諾待ちを主経路にせず、受信箱の原文を主経路にする。
端末は `terminal list/read` で既存の担当と agent を確認し、通常 shell や Potato のモデル無し受付には入力しない。
未送信の入力がある端末にも合図を打ち込まない。本文を保持し、その入力や現在の作業の区切りを待つ。
受付と turn 開始は受領確認とは別。合図が不明でも本文は保持し、同じ入力を重複送信しない。
外部の Slack / email / PR / Linear への投稿や、新規担当・常設窓口の起動をこの文書から許可しない。

## Potato の読み取り専用を保つ

Potato は受信箱や brain に書かず、読み取りツールで自分宛の JSON を読む。
レビュー開始時に Banana が対象の連絡 ID と本文を固定依頼へ含める。実行中の新しい連絡が
判定範囲を変えるなら結果へ明記し、変更後の正式な依頼に戻す。レビュー中の PR / Issue は書き換えない。
技術確認では Potato は結果の末尾に `## 連絡` を付け、元の連絡 ID、宛先、返答・不足資料・次の担当を原文で返す。
受入 pipeline は既存の厳密な出力形式を維持し、返答・不足資料は Summary / Findings に書く。
判断が必要な規準・評価への質問は Tomato 宛、技術的な質問・指摘は Banana 宛にする。

Banana は結果を受け取った区切りで `## 記録`、または受入レポート全原文を既存の `review/記録/` へ逐語転記し、
`## 連絡` または受入レポート全原文を同じく逐語中継する。双方へ返す場合は宛先ごとに元の ID を指定する。

```sh
team-mail relay-potato --source-file /absolute/potato-result.md --to tomato --subject '規準への返答' --id <tomato-message-id>
team-mail relay-potato --source-file /absolute/potato-result.md --to banana --subject 'レビューの返答' --id <banana-message-id>
```

`relay-potato` は原文の `## 連絡`、受入 pipeline では全レポートを保存し、送信者 Potato、中継者 Banana、原文 path を残す。
Potato 名義の自由な本文作成は拒否する。返答は受領の証拠にもなるが、PASS の投稿や中継とは別経路。
この受信箱の記録を最終 verdict、Owner の承認、CI 成功として使わない。

## 日報と日誌への集約

Banana は進行・停止・完成・判断待ちを `dev/報告/YYYY-MM-DD.md` へ区切りごとに追記し、main へ寄せる。
Potato の原文記録は Banana が既存経路で `review/記録/YYYY-MM-DD.md` に転記して main へ寄せる。
Tomato は **Sol 6.1 / medium** の `journal compose` で、日報と `Tomato/10_日誌/` の日誌を作成する。
両方に3役の活動記録、重要な連絡の往復、未返答・停止理由・次の担当と出典を含める。
報告なしと活動なしを混同しない。モデルの要約を新しいレビュー判定にしない。
作成・検査・追記の手順は [日誌作成](../roles/tomato/skill/references/journal.md)。
