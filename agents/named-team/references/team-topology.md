# 常設3窓口と必要時の専門担当

2026-10-05、Owner の編成縮小依頼を反映した現行契約。
旧「全役の固定ホームが必須」「全ホームの新規タブでモデル起動」は適用しない。
役の能力と、常設の受付、実際にモデルを動かす仕事を分ける。
正本は `roles.json`。実行中のセッション・モデル・関与歴が変更されたとは扱わない。

| 常設の窓口 | 責任 | 新規タブ |
|---|---|---|
| Tomato | Owner との相談、目的・前提・判断材料の整理、開発の受け渡し | Codex の対話入力待ち。依頼の自動送信・復元はしない |
| Banana | 開発の分解・割当・通常実装・検証・統合・完了追跡 | Codex の対話入力待ち。専門基盤の変更だけ専門担当へ渡す |
| Review | 受入確認・技術確認・最終判定の受付と経路選択 | モデル無しの案内。既存 Peach ホームを使い、新しい役/card を作らない |

## 必要な担当だけ起動する

- Kiwi は観測・自動検知・鮮度・取得失敗・履歴・配送/回収基盤の実装担当。
  通常の製品コードや毎回のイベント確認を渡さない。受付・回収は Banana。
- Melon は証拠 packet・CI 照合・レビュー形式・ゲートの基盤実装担当。
  Banana 配下。自分が修正した基盤の最終独立判定を兼ねない。
- Peach は Issue の AC と成果・一次証拠の照合。Potato は固定差分の不具合・回帰確認。
  受付は Review、通常の回収・指摘対応の進行は Banana。両方を一律に必須起動しない。
- Fable は判断時の相談先。常設役を増やさない。Owner 判断待ちでは
  [owner-decision.md](owner-decision.md) に従い、確認後に推奨案と理由付きの選択肢を Owner に提示する。
  返答がないことを承認と読まない。

専門担当のコマンド/スキルは互換として残す。固定ホームは不要。
Kiwi/Melon の編集は [Banana 共通入口](project-tasks.md) で依頼ごとの worktree を使う。
受領済み checkout と依頼 ID がある担当はその場で実行し、再帰的に作業場を作らない。
Banana の進行と実装を分けるときも人格を増やさず、案件の実行セッションを分ける。
異なる担当の同一 checkout での並行編集を避け、統合は Banana が固定版・検査・残件を確認する。

## レビューの共通入口

```sh
review --inbox
review --kind acceptance --repo /absolute/checkout --issue ABC-123 --dry-run
review --kind technical --repo /absolute/checkout --prompt-file /absolute/request.md --dry-run
review --kind final --repo /absolute/checkout --sha <current-full-HEAD-SHA> --dry-run
```

`acceptance` は受入条件の確認、`technical` は技術所見、`final` は正式最終判定の引渡し。
`--pr` を受入確認に追加して最終判定へ暗黙に昇格させない。
この窓口は最終 reviewer の関与歴を証明しない。対象・固定 SHA・一次証拠・必要な
実モデル/effort・実装/修正との独立性は正式経路で確認する。
最終判定と concafe のレビューは、この CLI が別タスクへ自動送信・起動しない。
JSON の引渡し計画を返し、実実行では exit 3（引渡し待ち）、dry-run は exit 0。
引渡し計画、exit 0、受入 PASS、技術所見なしを最終署名 verdict や完了と扱わない。

## この依頼に適用する concafe Owner 指示

この会話で直接提供された CAF-279 の指示を、旧ローカル資料や他セッションの変更より優先する。
通常の進行・調査・実装・CI・監視は Sol medium、複雑な技術作業/途中確認は Sol high。
固定 full head SHA の最終独立レビューと署名 verdict は未関与の別 Codex タスクの Astra high、
委任された具体的な上位判断は別 Codex タスクの Astra medium。
Claude は Owner の個別依頼だけ。通常の自動起動・必須レビューへ追加しない。
新規 subagent/追加依頼、自己 PASS、手動 Ready/merge を禁止し、CI・署名・fail-closed・
自動 Ready/guarded auto-merge・人間ゲートを維持する。鍵や製品 repo の設定は変更しない。
汎用 Potato の launcher も concafe checkout を識別して別 Codex 経路へ戻す。
他プロジェクトの正式モデル・ゲートは、そのプロジェクトの現在の契約で確認する。

## 監視と既存ホーム

Issue/PR/CI のモデル無し比較は維持。相談分類は Tomato、通常変化と取得障害/回復は Banana。
障害を見つけただけで Kiwi に修正依頼を自動送信しない。
旧 pending Kiwi は履歴の役名を保持したまま Banana ホームを使える。
旧 active/unknown を含め、同じ受付を使う未完了 batch があれば次を起動しない。
DB の消去・期限切れ再配送・曖昧な起動の再試行をしない。

`start-workspaces --check` は3窓口だけを必須確認する。専門担当を明示した確認では、
その受付・回収先と `state=on-demand` を返し、旧ホームを新しく作らない。
古い Kiwi/Melon/Potato の worktree・タブ・成果は保持する。新規タブのモデル起動だけ停止。
作業完了・結果保存・未保存成果・実プロセス・他担当を確認する前に削除や終了をしない。
監視プロセスが旧コードを読み込んで稼働中なら、ソース更新だけで変更済みとは扱わない。
この変更では稼働中 coordinator や CI supervisor を再起動しない。

通常の同時実行は2〜3件を目安とし、使用量・依存・レビュー枠・PC 負荷で決める。
これは scheduler の全体上限を新設したという意味ではない。
