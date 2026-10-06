# Devin移行の検証結果と変更ファイル

2026-10-05 JST。ローカルfixtureの実行結果。独立review/verdict PASSや実Devin接続の証明ではない。

| 検査 | 結果 / 終了コード |
|---|---|
| 変更前全体 `python3 -B -m unittest discover -s tests -q` | 308件、1件エラー。既存Tomato fixtureのUnix socket bindがsandboxでEPERM。製品/移行の失敗ではない |
| 移行後全体（fixtureのためsandbox外）同コマンド | 330件、成功、exit 0 |
| 追変更の対象 `PYTHONPATH=tests python3 -B -m unittest test_devin_flow test_named_agents test_project_tasks -q` | 78件、成功、exit 0。unknown復旧・atomic record・owned retired-link除去・foreign link保全を含む |
| 移行時点のDevin対象 `python3 -B -m unittest discover -s tests -p test_devin_flow.py -q` | 26件、成功、exit 0。read-only statusと検証失敗中の修正返却を含む |
| 後続リファクタリング全体 `python3 -B -m unittest discover -s tests -q` | 344件、成功、exit 0。273.107秒。最後のmonitor/共通案件整理と最終追加修正は下記対象検査で確認 |
| 最終チェック対象 `PYTHONPATH=tests python3 -B -m unittest test_devin_flow test_named_agents test_event_monitor test_project_tasks -q` | 116件、成功、exit 0。21.657秒。Devin 35件とinstaller/monitor/共通案件の回帰を含む |
| 表示・セットアップ追加依頼 `PYTHONPATH=tests python3 -B -m unittest test_activity test_named_agents test_named_workspaces test_named_tab_startup test_devin_flow test_event_monitor test_project_tasks -q` | 152件、成功、exit 0。24.443秒。読み取り観測、同一Session、未確認表示、秘密値非表示、既存Devin CLI保全、モデル無し監視、重複防止、停止監視の検出を含む |
| 実機 `bin/setup --check` と再度 `bin/setup` | 両方exit 0。8カード反映済み、変更残りなし、同じ監視handleを再利用。Orca root既存2タブ＋Activity1タブ |
| 実機 `install.py --check --tab-autostart` | exit 0。所有17リンクと既存タブstartupを確認。ベンダーDevin CLI保全、旧Banana所有4リンクを撤去 |
| Python AST構文確認 | named-team 22ソース、成功。bytecodeや実runtimeは作らない |
| JSON構文確認 | named-team JSON、成功 |
| Bash/zsh構文確認 | reviewer lib/*.sh / tab-autostart.zsh、成功、exit 0 |
| `git diff --check` | Orca / Tomato / concafe隔離worktree、成功、exit 0 |
| concafe文書patch適用時の `git apply --check` | 成功、exit 0。agentを起動しない隔離worktreeへ適用、主checkoutは変更なし。適用済みpatchの重複コピーは後続整理で削除 |
| concafe対象4文書のPrettier `--check` | 成功、exit 0。既存node_modulesの実行ファイルを利用、依存追加なし |

Devinテストは実行開始・同一Issue排他・別Issue並行・原子claim receipt・既存担当/取消/完了の拒否、
PRリンクとrepo/SHA照合、現在SHAの検証失敗、同じSessionへの指摘返却、返送重複防止、
未確認開始/返送のfenceとread-only復旧、独立review/CI/AC/QAの欠落、head更新時の失効、
merge後条件とDone read-back、認証出力の非露出、接続未設定のfail closedを検証する。
実API・実model・GitHub/Linear書込・署名・mergeをfixtureから実行しない。
テスト中のMelon開始/BLOCKED表示はfake backend/回収失敗の期待fixtureで、実agentではない。

Orcaソースにpackage.json/pnpmのlint/typecheck/buildは存在しないため、Python testsと構文/配線検証を使う。
concafeのアプリコード/依存/CIは変更していない。4文書の変更だけなので対象MarkdownのPrettier検査を使い、pnpm lint/typecheck/build/checkと実CIは未実行。
push前pnpm checkの契約は保持する。PR作成/pushを行っておらず、実CI成功やmergeを報告しない。

開始前からあったreviewerの実装・history・testsはhash比較で保持を確認した。
既存変更のあるreviewer README / skillには責務説明の行だけを追記修正し、実装を上書きしていない。
台帳/log/token/key/persona/brain/CI supervisor/trust/approval/sandbox設定には書き込んでいない。

表示・セットアップ追加依頼では、実機ownedリンク、Orcaカードの名称・説明と
新規のモデル無しActivityタブだけを変更した。監視タブ自身のみ表示更新のため再起動した。
旧Banana/Tomato/Reviewや専門担当の既存セッション、カードのstatus/pin/lineageは保全。
Devin外部adapter未接続・対象実行記録なしを実タブの出力で確認。
旧時計automationは停止・移設していない。実agent起動・外部書込・実PR・mergeは行っていない。

## 今回のOrca変更ファイル（初期からの別担当変更を除外）

- `AGENTS.md`
- `VERSION-CONTROL.md`
- `agents/linear-inreview-reviewer/README.md`
- `agents/linear-inreview-reviewer/skill/SKILL.md`
- `agents/named-team/README.md`
- `agents/named-team/bin/agent`
- `agents/named-team/bin/activity`
- `agents/named-team/bin/context`
- `agents/named-team/bin/devin`
- `agents/named-team/bin/setup`
- `agents/named-team/bin/tab-agent`
- `agents/named-team/bin/task`
- `agents/named-team/config/devin.json`
- `agents/named-team/install.py`
- `agents/named-team/lib/checkout_context.py`
- `agents/named-team/lib/activity.py`
- `agents/named-team/lib/workspace_display.py`
- `agents/named-team/lib/devin_flow.py`
- `agents/named-team/lib/event_monitor.py`
- `agents/named-team/lib/project_tasks.py`
- `agents/named-team/references/consistency-refactor.md`
- `agents/named-team/references/contracts.md`
- `agents/named-team/references/devin-migration.md`
- `agents/named-team/references/devin-operations.md`
- `agents/named-team/references/orca-activity.md`
- `agents/named-team/references/event-monitor.md`
- `agents/named-team/references/history/consistency-refactor.md`
- `agents/named-team/references/history/refactor-plan.md`
- `agents/named-team/references/history/three-entry-plan.md`
- `agents/named-team/references/orca-operating-model.md`
- `agents/named-team/references/owner-decision.md`
- `agents/named-team/references/project-tasks.md`
- `agents/named-team/references/refactor-plan.md`
- `agents/named-team/references/roles.md`
- `agents/named-team/references/sol-effort.md`
- `agents/named-team/references/team-topology.md`
- `agents/named-team/references/three-entry-plan.md`
- `agents/named-team/roles.json`
- `agents/named-team/roles/banana/codex/profile.config.toml`
- `agents/named-team/roles/banana/skill/SKILL.md`
- `agents/named-team/roles/banana/skill/agents/openai.yaml`
- `agents/named-team/roles/banana/skill/bin/context`
- `agents/named-team/roles/banana/skill/bin/task`
- `agents/named-team/roles/banana/skill/references/automation.md`
- `agents/named-team/roles/banana/skill/references/contracts.md`
- `agents/named-team/roles/banana/skill/references/delegation.md`
- `agents/named-team/roles/banana/skill/references/implementation.md`
- `agents/named-team/roles/banana/skill/references/issues.md`
- `agents/named-team/roles/banana/skill/references/reporting.md`
- `agents/named-team/roles/banana/skill/references/review.md`
- `agents/named-team/roles/kiwi/codex/profile.config.toml`
- `agents/named-team/roles/kiwi/skill/SKILL.md`
- `agents/named-team/roles/melon/skill/SKILL.md`
- `agents/named-team/roles/potato/claude/agent.md`
- `agents/named-team/roles/potato/skill/SKILL.md`
- `agents/named-team/roles/tomato/codex/profile.config.toml`
- `tests/test_banana_context.py`
- `tests/test_activity.py`
- `tests/test_checkout_context.py`
- `tests/test_devin_flow.py`
- `tests/test_event_monitor.py`
- `tests/test_named_agents.py`
- `tests/test_named_tab_startup.py`
- `tests/test_named_task_sessions.py`
- `tests/test_named_workspaces.py`
- `tests/test_project_tasks.py`
- `tests/test_role_routing.py`

- `agents/named-team/references/devin-validation.md`

## Tomato側（責務とengineering handoffだけ）

- `/Users/kamp/.claude/skills/Tomato/SKILL.md`
- `/Users/kamp/.claude/skills/Tomato/references/handoff.md`
- `/Users/kamp/.claude/skills/Tomato/references/named-team.md`
- `/Users/kamp/.claude/skills/Tomato/references/fable.md`

## concafe側（agentなしの隔離worktreeへ適用）

AGENTS.md、README.md、docs/WORKFLOW.md、新規 docs/operations/devin-orca-migration.md を更新した。
ユーザーの明示許可後、Orca CLIでrepo設定を読み取り、agent指定なし・setup skipで作成した。
worktree: `/Users/kamp/orca/workspaces/concafe-techo/devin-orca-handoff`。
主checkoutへ直接書かず、既存worktree契約を保持した。適用済み文書のpatchコピーは二重管理を避けるため削除した。

## 後続のリファクタリング確認（2026-10-05）

- 記録のschema/repo/Issue/状態確認、同一Session確認、開始claim確認、未確認状態の定義を共通化。未使用のsnapshot fallback、prepared状態、重複保存、テストの未使用importを除去した。
- 同じSHAでもレビュー撤回・不完全な承認・品質取得失敗があれば旧承認情報を消す。同じ修正要求を再送せず、fixing状態を復元する。
- 設定の型/空白/regex/実行権限、TicketのAC/label/明示的な担当なし、全actionの不正な記録・不明actionを検査し、外部起動前に停止する。
- installerは必要なリンクだけを作る。存在しない旧リンクの作成・即削除と不要な旧skills directoryを作らず、Claude設定先の指定を撤去先にも使う。
- model-free inboxだけならworkspace一覧を取得しない。Tomato一役の重複batch確認と、共通案件の同じ受付workspaceの重複検索を除去した。
- 適用済みconcafe文書のpatchコピーを削除。旧Bananaの撤去用リンク定義・履歴identity・日付付き記録は実運用の保全に必要なので保持する。

## 最終チェック（2026-10-05）

fixtureでDoneをreadyStatesへ設定すると再開できること、確定記録のSession/branchをnullへ破損させても同期できることを再現し、修正した。
ready/working/review/doneの状態mapping重複と、確定済みexecutionのSession/branch欠落を外部呼出し前に拒否する。
未確認開始のnull Sessionは元executionのfenceとして保持し、既存reconcileの回帰を通した。
対象116件、22 Pythonソース/JSON構文、差分検査、concafe4文書のPrettier、active Markdownリンク、他担当変更の保全を確認した。
コード上の検査であり、未関与タスクの正式独立verdict、実Devin接続、実CI、署名、mergeの証明ではない。

本番有効化TODOと移行リスクは [devin-operations.md](devin-operations.md)。
