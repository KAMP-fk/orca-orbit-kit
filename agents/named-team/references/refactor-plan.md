# Agent refactor — 2026-10-03 JST

依頼: Tomato / Banana / Kiwi / Peach / Potato の棲み分け、業務分担、Orca 最適化。人格・記憶・live state と最終署名ゲートは変更対象外。

1. 現物と運用契約を確認し、入力・責任・成果物・引き渡し先を役割表にする。
2. 各 skill の選択条件と境界を共通契約に合わせる。Tomato の人格原本はそのまま、Banana の開発手順は版管理可能な正本へ移し、旧 path を互換リンクにする。
3. 役割メタデータと Orca executable 選択を一箇所に集める。Tomato/Banana の command・skill・profile を追加する。依頼ファイル入力と Peach の見える task 実行を用意する。
4. fixture のみで配線、文字列の保存、新しいタブ、失敗・曖昧な回収、モデル固定を検査する。既存の観測・レビュー証拠の回帰検査も実行する。
5. ローカル配線を反映し、read-only check と dry-run で確かめる。モデル起動・外部投稿・PR/Linear 操作はこの検証に含めない。

完了条件: 五役に重複しない入口があり、共通契約から必要な手順へ辿れる。Orca の既存動作とモデル/独立性の条件を保全し、配線・回収・既存回帰を実検査で確認する。検査結果は独立レビュー PASS と呼ばない。

## 実行状況

1–3 は実装済み。`roles.md` と各 skill に責任・成果物・引き渡し先を反映。
`roles.json` / `lib/role_contract.py` を起動とカード準備の共通入力にした。
Tomato/Banana の入口、`--prompt-file`、Peach の `--orca`、無効な途中 PASS を最終結果に混ぜない回収を追加。
既存の Peach/Potato の provider、モデル固定、read-only、証拠ゲートは保持。

ローカル配線は15リンク、Peach は既存の7リンクを check で確認。
Orca の五役＋既存 Melon のカードも check で確認。
追加カード作成時の空の shell 3件は terminal show で確認してからその handle だけを閉じ、ptyKilled=true を確認。
既存タスクは停止・再依頼・モデル変更していない。

モデル/外部サービスの実呼出し・外部投稿・独立署名 verdict はこの実装検証に含めない。

## 検証結果

以下は fixture と一時状態を使った実装側の検査。独立レビュー承認ではない。

| cwd | コマンド/検査 | 結果 |
|---|---|---|
| /Users/kamp/orca | `python3 -B -m unittest discover -s tests -p 'test_*.py'` | 193件、rc=0 |
| /Users/kamp/.claude/skills/Tomato | `python3 -B -m unittest discover -s tests -p 'test_*.py'` | 23件、rc=0 |
| /Users/kamp/orca | 最終の参照先修正後: `python3 -B -m unittest discover -s tests -p 'test_named*.py'` | 39件、rc=0 |
| /Users/kamp/orca | 同修正後: `python3 -B -m unittest discover -s tests -p 'test_agent_refactor.py' -k claude` | 6件、rc=0 |
| 両 source repo | `git diff --check` | rc=0 |
| /Users/kamp/orca | `shellcheck --severity=warning`（Peach entry、cli/github/linear/backend module） | rc=0 |
| 五役の skill | skill-creator の `quick_validate.validate_skill`、UI YAML の読込 | 5件成功、rc=0。PyYAML は一時ディレクトリで使用 |
| /Users/kamp/orca | `agents/named-team/install.py --check`、Peach `install.sh --check` | 15 + 7リンク、rc=0 |
| /Users/kamp/orca | `agents/named-team/bin/start-workspaces --check` | 五役 + Melon、rc=0 |
| インストール済み command | 五役の `--dry-run` | 全件 rc=0、startsSession=false |

検査対象: Literal な依頼ファイル、対象 path、provider/effort の維持、モデル metadata の拒否、
一件ごとの可視タブ、曖昧な作成と回収、結果欠落、無効な途中 PASS の除外、既存の CI/Tests 証拠ゲート、観測の履歴と取得失敗。
実モデルの稼働・実サービスでの取得・既存セッションへの新定義の再読込は未検証。
