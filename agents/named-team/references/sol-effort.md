# Sol 6.1 の effort 選択

Owner 指示の用途別基準。通常は `medium`。役名ではなく今回の仕事で選ぶ。

| Effort | 向いている用途 | 具体例 |
|---|---|---|
| `low` | 答えがほぼ決まっている作業 | 文章修正、要約、情報抽出、単純なコード修正、ログ整理 |
| `medium` | 普段の開発・業務の標準 | 実装、PRレビュー、設計案、バグ調査、要件整理 |
| `high` | 複数要素を考慮する難しい仕事 | 原因不明バグ、DB設計、アーキテクチャ判断、大きめのリファクタ |
| `xhigh` | 品質優先の複雑な成果物 | 大規模コードレビュー、複数サービス横断調査、設計レビュー、重要な意思決定資料 |
| `max` | 失敗コストが高い・かなり難しい問題 | 難解な障害調査、巨大コードベース解析、研究・アルゴリズム、最終検証 |

## 起動への適用

`--effort` を明示した依頼だけ設定を変える。新規依頼の requested/effective を照合し、
設定ファイルの変更を実行中セッションの変更と扱わない。
無変化の監視・初回基準保存・差分比較ではモデルを起動しない。

```sh
banana --repo /absolute/checkout --effort low --prompt-file /absolute/request.md --dry-run
kiwi --repo /absolute/checkout --effort xhigh --from-role banana --prompt-file /absolute/request.md --dry-run
melon --repo /absolute/checkout --effort max --from-role banana --prompt-file /absolute/request.md --dry-run
```

通常の Sol 設定、プロジェクト固有の最終判定・上位判断モデルは
[team-topology.md](team-topology.md) の Owner 指示と対象の現行契約に従う。
この表の `max` を最終署名 verdict や上位判断の代わりにしない。
汎用 Potato の個別依頼は別 backend の互換経路で、Sol effort 表の対象ではない。
[整理前の説明](history/sol-effort-before-20261005.md) は履歴として保存する。
