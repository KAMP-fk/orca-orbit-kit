# Orca の編成と案件の運用（2026-10-04）

Owner 提供の「Orca エージェント編成 参考情報」を、既存の役割・案件受付と
実際に使う CLI の契約に照合した運用資料。参考情報はモデル切替・権限拡大・
新規 worker 起動・既存タスク停止の追加許可ではない。
現在の Owner 指示、対象 repo の契約、実効モデルと関与歴を優先する。

## 固定する窓口と案件の作業場所

Tomato は相談・設計の窓口、Banana は開発の分解・進行・統合の責任者。
Kiwi は観測・引継ぎ、Melon はレビュー基盤、Peach/Potato は既存の判定・技術確認を持つ。
常設ホームは Tomato・Banana・Review の3つ。専門担当は必要時だけ起動し、固定ホームを必要としない。
現行の受付と Owner 方針は [team-topology.md](team-topology.md)。編集案件は原則一件に一つの worktree と一つの実行担当を置き、
必要な案件だけブラウザを使う。読み取り調査・固定差分レビュー・既存案件の継続は
契約に従って既存 checkout を使える。案件用 checkout を渡された担当はそこで処理する。

同じ branch/checkout に複数の編集担当を置かない。1 Issue を複数作業に分ける場合は、
互いの結果を待たずに進められるものだけ分ける。依存する作業は順番を記録する。
役の親子関係、Orca の作業場所の親子関係、Git base と統合先を区別する。
独立案件は repo の既定 base、積み重ねる案件は確認した親と base を使う。

## 隔離と監督を選ぶ

| 今回の目的 | 経路 | 確認する終点 |
|---|---|---|
| 既存の担当へ一回の入力・所有権の受け渡し | `orca-cli` の worktree/terminal。準備済み TUI への `terminal send` | 正しい handle と入力の受理。着手の証明が必要なら同じ送信の `turn_started` |
| 一件の依頼を実行して出力を回収 | 既存の [Banana 共通受付](project-tasks.md) | 結果保存・実行終了・タブ close・成果の引き渡し |
| 複数担当、所有権、依存、Inbox、質問/回答、decision gate の監督 | Orca の Run / Task / Dispatch と `worker-start` | 各 active Dispatch の正式な完了報告、残件、回収/保持の決定 |

一件受付の `record.json` はその実行と回収の記録。Orca の Run/Task/Dispatch や
監督付き worker の正式な完了状態を代替しない。必要な場合だけ現行 `orchestration` を読む。
Run を作るだけでは worker は配置・起動されない。所有権の受け渡しだけの依頼で、
監督用の Run/Task を自動追加しない。

監督付き worker は live preamble の executable・Task・Dispatch・handle を使う。
完了報告は Dispatch ごとに一度だけ、成功/失敗を明示する。
coordinator は報告を照合し、再利用・依頼された保持・`worker-release` のいずれかを決める。
不明な release に直接の `terminal close` を代用しない。

## 分担と統合

Banana は対象、委任、編集範囲、依存、観測できる AC、終了条件を揃えて担当へ渡す。
子の成果をまとめる統合作業は別の工程/Task として明示し、統合責任は Banana に戻す。
固定版と差分、検査結果、競合、残件を確認してから依頼された終点を判定する。
worker の「終わった」、入力待ち、exit 0、受入判定、最終レビューは別の事実として扱う。

独立レビューは未関与の別担当で、最初は同じ固定差分・AC・一次証拠から判定する。
実装者や他のレビュー担当の結論・推奨・作業メモを、初回判定の根拠として先渡ししない。
修正や指摘の照合では必要な証拠を共有し、その担当の関与歴を更新する。
レビュー枠と統合作業の余力を確認してから、実装を並行投入する。

複数案の競争は、曖昧なバグや複数の妥当な解があり、比較の基準を先に定められる場合だけ
検討する。同じ開始 full SHA と依頼を使い、選ぶ担当と比較・検査を明示する。
通常の分担を競争へ自動変更せず、新規 subagent や追加依頼を禁じる契約を迂回しない。
採用しない案も未保存成果・稼働・統合状態を確認してから既存の cleanup 手順で扱う。

## モデル、判断待ち、使用量

参考情報の「設計は Claude、実装は Codex」は一般例。通常の Codex 完結方針など、
Owner の現在の割当を優先し、役名だけで Claude/Astra や別 provider へ切り替えない。
通常の進行・大量実装と、必要な最終レビュー・具体的判断のモデル/effort を分ける。
高いモデルを定期監視・調整の反復処理へ常時使わない。
対話ホームの入力待ちと、モデルが仕事を実行している状態を区別する。

同時実行は3件程度を最初の検討基準とし、実際の使用量・reset・PC 負荷・依存・
レビュー枠で減らす。これは実装済みの scheduler 上限ではなく、起動前の運用判断。
使用上限から引き継ぐ場合は、版・未コミット成果・実行状態・残件を保存し、
元担当の状態と次の担当を確認する。不明な実行を二重起動したり、自動 fallback したりしない。

Owner 判断が必要なら [Fable と推奨案付き選択肢の手順](owner-decision.md) を使う。
監督付き Task では native の ask/reply や decision gate と対応させ、Owner の返答と
決定者を残す。承認分類器の拒否を避ける目的で agent・モデル・起動経路を替えない。

## 運用上の確認と現状の差

- 画面・ウィンドウの close や不在だけで終了と判断しない。実プロセス・handle・結果・
  native の終了/回収状態を確認する。timeout・連絡不能を終了や再試行の根拠にしない。
- `.worktreeinclude`、ignored file のコピー、setup、依存ディレクトリの共有は対象 repo の
  実設定で確認する。「node_modules は必ず一回の install」「.env を必ずコピー」は前提にしない。
  認証・鍵・環境値をログへ出したり、参考例を理由に複製・変更したりしない。
- モバイルは既存案件の進捗・追指示・判断返しを中心とし、作業場所の新規作成・PC の稼働・
  pairing と実行 host は確認した事実だけを案内する。課金条件も今回の CLI 調査では確認していない。
- 現行の共通受付は役の profile・制限・結果保存のため、裸の worktree 作成と専用 terminal 作成の
  二段階を使う。途中に fallback shell が残る場合があり、厳密な「1 worktree = 1 terminal」は未達。
  既定タブは確認なしに閉じず、既存 agent がいたら二重起動せず保持する。
- built-in launcher が必要な設定を満たす場合は agent-first の作成が適切。
  共通受付を監督付き `worker-start` に置き換える場合は、役 profile・tool 制限・一回だけの実行・
  完了/回収・失敗時の残存資源の契約を先に揃える。今回の資料反映で runtime を移行したとは扱わない。

## 照合した一次資料

2026-10-04 JST、`/usr/local/bin/orca` 1.4.219 が返した `orca-cli`、`orchestration`、
`references/coordinator-loop.md`、`references/placement-and-remote.md` と
`orchestration worker-start --help` を読み取った。実行・送信・Run 作成はしていない。

この版の `worker-start` は `--model` / `--effort` を持つ。`--effort` は `--model` が必要で、
既存 `--terminal` 再利用とは併用できない。新規起動の requested と effective を照合する。
一方、`worktree create --agent` には per-call model/effort や任意の role argv 転送がない。
具体的な呼出しは、Owner の指定・対象契約・現行 CLI のガイドを読んでから決める。
