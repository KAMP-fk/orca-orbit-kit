# Banana → Devin / Orca 移行調査と責務表

2026-10-05 JST の履歴。2026-10-06 の現行担当は [3役の契約](team-topology.md)。
以下の旧担当名は移行当時の記録で、新しい起動指示ではない。

2026-10-05 JST。主対象は `/Users/kamp/orca`、関連は `concafe-techo` と
既存Tomatoの版管理されたhandoff参照。コードとCLI一次情報を確認して整理した。
ここでいうソース移行と、実Devin接続/稼働切替は別の成果。

## 変更前の実態

```text
Owner / Tomato / Linear
        │
     Banana (Codex Sol)
        ├─ 通常実装・検証・PR/CI・統合・完了追跡
        ├─ Kiwi (観測基盤) / Melon (証拠基盤) の必要時割当
        └─ Review受付 → Peach / Potato / プロジェクト固有最終レビュー
                                 │
                           GitHub guarded Actions
                                 │
                            merge → Linear Done
```

Bananaは管理だけのagentではなかった。role/profile/skillで通常実装も行い、共通task入口で
repo/task ID排他、Orca worktree作成、visible terminal、結果保存、safe cleanupを持っていた。
Devin API/MCP/webhook/専用Automationは対象ソースに存在しなかった。
TomatoはBananaの下流実装agentではなく、Ownerの相談・前提・判断材料と記憶領域を持つ別窓口。
Kiwiは観測実装、Melonは証拠実装、PeachはAC、Potatoは固定差分の技術レビュー。

## 調査した接点

| 対象 | 変更前の根拠と責務 |
|---|---|
| Banana実装・prompt | `roles.json`、旧 `roles/banana/codex/profile.config.toml` と `skill/SKILL.md` / references / bin |
| 起動と配線 | `bin/agent`, `install.py`, `bin/tab-agent`, `shell/tab-autostart.zsh`, `lib/role_launch.py`, `role_contract.py` |
| worktree/branch/排他/結果 | `project_tasks.py`, `project_workspaces.py`, `checkout_context.py`, `task_session.py` と offline tests |
| Linear/GitHub読取 | `event_monitor.py`, `config/concafe-events.json`。Orca CLIでLinear、gh apiでPR/Issue/check/statusを取得 |
| 外部書込の責務 | 旧Banana skillが担当へ指示。monitor自体はGitHub/Linearへ書込まない |
| Review接続 | `bin/review`, `review_routing.py`, `linear-inreview-reviewer` evidence/packet/backend と `review-relay` |
| automation/daemon | 現行Orca automation1件、5分のmodel-free clock。precheckはevent-watch request --scheduler。既存Banana homeのserveを参照 |
| env/secrets | 既存Codex/Claude profile設定、Orca CLI、ghの既存認証を参照。秘密値を取得せず参照構造だけ確認 |
| GitHub Actions | concafeのCI、auto-ready/auto-merge、sync-risk-label、Cloudflare deploy。許可branch/分類/full CI/current-SHA review gateを確認 |
| AGENTS/README/docs | OrcaローカルGit境界、named-team担当/受付/監視/共通task、Tomatoのengineering handoff、concafeのAGENTS/WORKFLOW/orchestration/TESTING/package構造 |

Orcaはこのマシンのnamed-agent/review sourceを追跡するローカルrepoで、remoteは未設定。
WebアプリやCloudflare/Supabaseなどの製品コードは今回の変更対象ではない。
LaunchAgents/ローカルCodex automationsのBanana参照探索では対象の起動設定を追加確認できなかった。
外部クラウド設定全体を不存在と断言しない。

## 全責務の再配置

| 分類 | 旧責務 | 移行先 / 実装 |
|---|---|---|
| A Devin | Ticket取得/本文/AC/関連Docs/AGENTS/repo調査 | implementation adapter ticket/start、直接実装instructions |
| A Devin | 対象選定/担当/branch/worktree/実装 | Todo+専用label+AC+担当確認、原子claim、同一Issue/session/branch。remote checkoutは実adapter |
| A Devin | lint/typecheck/test/build、修正、PR作成 | 現在SHAのvalidationとlinked Draft PRをobserve。pnpm check必須。実workerは実adapter |
| A Devin | PR提出後In Review | 品質snapshotと現在SHA検証後、set_linear_state read-back |
| A Devin | review指摘修正/PR更新 | reviseを同じSession/branch/PRへ一度だけ返す。新実装agentへ委譲しない |
| B Orca | AC/diff/CI/必要なWeb/Mobile/E2E、独立レビュー | 既存Review/evidence経路＋別quality adapterの一次観測receipt |
| B Orca | 修正要求/統合結果/最終merge可否 | Changes Requested / 固定SHAの正式品質receipt。controllerは承認/mergeしない |
| B Orca | merge後AC/状態/Done/cleanup判断 | MERGED+doneReady+mergeCommit+evidence後にDone。remote成果の保全/cleanupは運用契約 |
| C 廃止 | 常設Banana model role/profile/skill/prompt、依頼再委譲の標準 | roles.jsonから削除、旧role tree削除、新規タブ自動起動なし |
| C 廃止 | 通常イベントからBanana/Codex実装者を自動起動 | PR/CI/healthは品質outbox。Devin候補も接続検証前は起動しない |
| C 廃止 | Banana専用skill binの共通機構所有 | 汎用bin/context / bin/taskへ抽出。役を必要条件にしない |
| D 維持 | worktreeの排他/不明起動fence/結果保持/safe cleanup | 独立基盤保守で既存shared moduleを利用。製品IssueはDevin fence |
| D 維持 | model-free取得/差分/outbox/health/worker accounting | monitorの基盤を維持。旧pending/unknownの履歴を保持、再起動しない |
| D 維持 | Tomatoの相談・人格・記憶、独立したKiwi/Melon保守 | engineering handoffだけ更新。brain/persona原本/live stateは触らない |
| D 維持 | 必須CI/current-SHA/独立性/署名・人間・自動merge gate | GitHub workflow、鍵、CI supervisor/deploymentを変更しない |

新しい構造は `Linear → Devin Session → PR → Orca → guarded Merge → Linear Done`。
状態・PR・接続契約・並行と二重実行・外部TODOは [devin-operations.md](devin-operations.md)。

## 今回の実装と未達

ソース側のrouting、排他、状態遷移、別品質receipt、同一Sessionへの修正返却、設定、
責務文書、旧role/prompt除去とinstallerのowned-link retirementを実装した。
新adapterは標準ライブラリの小さなcommand boundaryで、新DB/queue/service/dependencyを追加していない。
API仕様、provider/model名、認証envを捏造していない。

実Devin接続は未設定。実Session、実PR、実review/merge、Done更新、実機install、
既存automationの停止/移設/再起動は実施していない。
外部設定と独立した本番相当の品質adapterの接続が必要。
旧automationは読取時enabled。ソース変更だけで稼働中コード/実agentが変わったとは扱わない。

## リスクと残件

- 実adapter未接続の間は新しいDevin開始をできない。未接続を成功に見せず、source移行とactivationを分ける。
- 異なるPC/state root間の二重実行はlocal flockだけで防げない。実接続側の原子claimが導入条件。
- unknownな開始/返送は保全して停止する。read-only reconcileを実装済みで、実adapterのreceipt照合への接続が必要。
- 旧担当をdrainし、Issue/session/branch/PRを照合してから新routeを有効化する。古い起動を自動再送しない。
- quality adapterのreceiptは正式な一次証拠だけから作り、Devinの自己PASSを禁止する。
- concafeのrepo文書と今回直接提供されたCAF-279にはモデル/署名運用の差分がある。新規レビューは直接指示を優先し、既存有効verdictを無効化しない。外部ゲートを勝手に復元/緩和しない。
- 旧Bananaのbrain/live成果と移行前historyは記録として保持する。名称の全消去を実運用の安全より優先しない。

検証結果と変更ファイルは [devin-validation.md](devin-validation.md) に記録する。
