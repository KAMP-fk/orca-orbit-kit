# Sol 6.1 の effort 選択

2026-10-03 JST の Owner 指示。Codex `gpt-6.1-sol` の通常設定は `medium`。
役の名前ではなく、今回の仕事の規模・曖昧さ・考慮する要素・失敗コストで選ぶ。

| Effort | 向いている用途 | 具体例 |
|---|---|---|
| `low` | 答えがほぼ決まっている作業 | 文章修正、要約、情報抽出、単純なコード修正、ログ整理 |
| `medium` | 普段の開発・業務の標準 | 実装、PRレビュー、設計案、バグ調査、要件整理 |
| `high` | 複数要素を考慮する難しい仕事 | 原因不明バグ、DB設計、アーキテクチャ判断、大きめのリファクタ |
| `xhigh` | 品質優先の複雑な成果物 | 大規模コードレビュー、複数サービス横断調査、設計レビュー、重要な意思決定資料 |
| `max` | 失敗コストが高い・かなり難しい問題 | 難解な障害調査、巨大コードベース解析、研究・アルゴリズム、最終検証 |

## 起動への適用

- 依頼を起動する担当が上の表で選び、通常は `medium`、異なる場合は `--effort` で明示する。
  情報抽出なら `low`、複数サービス横断の調査なら `xhigh` のように、その依頼の内容で選ぶ。
- 役の通常 profile は `gpt-6.1-sol` / `medium`。この運用の標準段階は Low〜Max とする。
- 自動検知からの現物確認・既存担当・次の対応の整理は `medium`。
  初回基準保存・差分比較・無変化の観測はモデルを起動しない。
- 起動要求と実効 model / effort を確認する。スキル読込や設定ファイルの変更だけで、
  実行中セッションの effort が変更されたとは扱わない。
- この表は Sol 6.1 内の effort 選択。対象契約で指定された別モデル・別タスク・独立性・
  CI・署名・人間ゲートも適用する。concafe-techo の CAF-279 による最終独立 verdict と
  上位判断のモデル指定は保持し、Sol `max` の最終検証を署名 verdict の代わりにしない。

```sh
banana --effort low --cwd /absolute/path/to/repo --prompt-file /absolute/path/to/request.md --dry-run
kiwi --effort xhigh --cwd /absolute/path/to/repo --prompt-file /absolute/path/to/request.md --dry-run
melon --effort max --cwd /absolute/path/to/repo --prompt-file /absolute/path/to/request.md --dry-run
```

`--dry-run` は設定確認のみ。実行するときは依頼と権限を確認し、同じ指定から `--dry-run` を外す。
