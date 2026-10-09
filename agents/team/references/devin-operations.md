# Devin の外部 Issue adapter（利用しない既存機構）

2026-10-07 JST の Owner 指示により、Orca で Devin は利用しない。
以下は保全した外部 Issue / Cloud adapter の仕様と旧導入手順で、接続・起動・再開・再試行の指示ではない。
既存 CLI・設定・台帳を保全し、必要時にローカル記録だけを読む。旧 TODO は実行しない。
現在の開発窓口は Banana。開発は Codex を使い、レビュー worktree への引渡しは
[Banana の開発手順](banana-engineering.md) に従う。
Banana の廃止や Review 常設ホームへの移設は、最新 Owner 指示で撤回済み。
旧切替 TODO を現在の自動実行指示にしない。

## 接続の境界

`bin/devin` / `lib/devin_flow.py` は自分たちの **command-adapter protocol v1**。
Devin の API、MCP、Automation、webhook の仕様を表していない。
既存接続がなく、接続用の executable/認証/組織設定も今回の依頼には渡されていないため、
実 API client を創作しない。確認した利用可能な接続に合わせた adapter を後から差し替える。

`config/devin.json` は非秘密の repo/状態/検証/branch 規則だけを持つ。
`implementationAdapter` と `qualityAdapter` は別の argv 配列。shell文字列ではない。
空配列や実行ファイルの不在、同じ配列、未設定ラベルなら起動前にexit 3。
ready/working/review/doneの状態mapping重複も起動前に拒否し、Doneを着手対象にしない。
Devin はローカル Codex/Claude profile を使わない。fallbackもしない。

実adapterは専用の私有configに設定し、source/configへtokenを書かない。
認証は adapter の環境または既存secret managerから取得する。
このcontrollerは token/envの名前を規定しない。`DEVIN_API_KEY`等を実インターフェースの確認前に必須にしない。
実際のAPI採用時に認証名・権限・費用・撤去手順を追加する。
共有機構の環境変数は既存の `ORCA_CLI_COMMAND`、`NAMED_TEAM_PROJECT_TASK_DIR`、
`NAMED_TEAM_TASK_DIR` と fixture用 timeout override。新しいsecret envは追加していない。

## 配置するadapterの契約

stdin に1件のJSONを渡す。stdoutは1個のJSONだけ。exit 0かつ `ok=true`、repo/issue一致が必須。
ログ・認証エラー・トークンをstdoutに混ぜない。stderr/不正応答をcontrollerは表示しない。
1呼出し55秒。timeoutを失敗確定や再起動許可と解釈しない。

全request: `schemaVersion=1`, `operation`, `repo`, `issue`, `execution`, `session`, `branch`, `pr`, `linearScope`（設定したworkspace/team/project ID）。
全response: `ok`, `repo`, `issue`。以下の追加fieldを返す。

| Adapter / operation | Request追加field | Response追加field / 条件 |
|---|---|---|
| implementation / ticket | なし | `state`, `labels`（配列）、`acceptanceCriteria`（空白だけでない文字列または文字列配列）、`activeExecution`（担当なしは明示的null）。設定のworkspace/team/project内で取得する |
| implementation / start | `ticket`, `workingState`, `branchPattern`, `requiredValidation`, `instructions` | 同じ `execution`, `session`, `branch`, `claimConfirmed=true`, `state=In Progress`（設定名）。**repo/issueの原子claimと同一executionのidempotencyを実接続側で実装する** |
| implementation / observe | 同じSession/branch/PR | `session`, `branch`, `workerState`, `headSha`, `pr`, `validation`。PR前はprなし、workerStateはworking/validating |
| implementation / revise | `revision`, `feedback`, `headSha` | 同じ `session`, `branch`, `revision`。新Session/branch/PRを作らず、同じrevisionを重複送信しない |
| implementation / set_linear_state | `targetState` | 更新後に読み直した `state`。現在stateを確認しCanceled/Doneから退行させず、同じtargetはwrite不要 |
| implementation / lookup_start | 同じexecution | 既存原子claimの `execution`, `session`, `branch`, `claimConfirmed=true`。新起動を行わない |
| implementation / lookup_revision | 同じrevision | `accepted=true`, 同じ `session`, `branch`, `revision`。再送を行わない |
| quality / inspect | workerとは別の接続で同じPRを取得 | `pr`, `branch`, `headSha`, `linkedIssue`, `prState=OPEN/MERGED/CLOSED`, `decision=pending/changes_requested/approved`, `evidenceRef` |

`validation` は `[{"command":"pnpm check","exitCode":0,"headSha":"<40hex>"}]`。
必要なコマンドはrepoのpackage/workflow/ACから決める。fixtureのcommand成功を本番検証に流用しない。
必要なWeb/Mobile/E2E/buildはAC/変更範囲に合わせ、品質adapterの `validationPassed` に含める。
`pnpm check`はconcafeのpush前必須。Devinは検査失敗を修正して同じbranchで再実行する。

品質adapterはDevinの自己報告を承認にしない。現GitHub PR/CIと正式な独立レビュー記録から読む。
`changes_requested`には具体的 `feedback` と固定headの `evidenceRef` が必要。
`approved`には現在headと等しい `reviewedSha`、`independent=true`, `ciPassed=true`,
`acceptancePassed=true`, `validationPassed=true`, `evidenceRef` が必要。
これはOrcaゲートの観測receiptで、controllerが署名verdictを発行するという意味ではない。

MERGED時の `doneReady=true`, `mergeCommit`, `evidenceRef` は、GitHub mergeの現物、
AC/必要なmerge後QA、正式独立ゲートと人間ゲートの充足をOrcaが確認した場合だけ返す。
MERGEDという文字列だけではDoneにしない。Devinから品質receiptを受け取らない。

実adapter導入時には、scope固定、既存担当/branch/PRの再利用、PRからIssueへのリンクとDraft・分類label、
取消/完了からのstatus退行防止、API timeoutとread-back、複数ホストでの原子claimを検証する。
同じlocal state rootを使うcontrollerはflockで排他するが、独立したPC間の排他はこのlockでは保証しない。
分散claimを実装/確認していないadapterを有効にしない。

## 状態遷移と排他

```text
start_pending → implementing → in_review → awaiting_merge → merged → done
       │                           │
       └→ start_unknown            └→ revision_pending → fixing → in_review
                                              └→ revision_unknown
```

- 台帳keyはrepo（大小文字正規化）+ Issue identifier（大文字正規化）。task本文や呼出し元が変わっても同じIssueのfenceを使う。
- state rootは `~/.local/share/named-team/devin/<hash>/record.json`。directory 0700、record 0600。atomic replaceとfile/directory fsyncで外部呼出し前のfenceを保存。
- startは外部呼出し前にfenceを保存。再startは既存recordを返す。unknownでも新Sessionを作らない。
- 異なるIssueは別lock/Session/branch/PR/executionで並行実行できる。全体queue/databaseは新設していない。
- 同じPR・Session・branchを追い、repo/Issue/SHAの混在を拒否する。
- 未確認開始以外のrecordにSession/branchが無ければ、外部取得・同期・返送の前に拒否し、破損した記録を保持する。
- 検証が欠落/失敗/旧SHAなら `validation_failed`、Review/Done更新を行わない。Orcaからの修正要求は検証失敗中でも元Sessionへ返す。
- 各品質取得前に旧reviewedSha/reviewEvidenceを消す。head更新、レビュー撤回、品質取得失敗では以前の承認を現在の承認として残さず、現在headの独立判定とCIを待つ。
- acceptedな同じfeedback/head/evidenceは一度だけrevise。返送先は元Session。
- merge操作はしない。既存guarded Actionsの結果を品質adapterで読んでからDoneにする。
- Done writeが未確認ならmerged recordを保持し、次syncでmerge/AC/Linear現物を読み直す。adapterもidempotent read-backを実施する。

start_pending/start_unknown/revision_pending/revision_unknownは自動回復しない。
原子claim側で `execution` / `revision` の受理状況を照合し、同じSessionだけを復旧する運用が必要。
台帳削除・Issue ID変更・state root変更をretry方法にしない。未確認claimがあれば新startを禁止する。
`devin reconcile --issue CAF-123 --config /private/config/devin.json` は lookup_start / lookup_revision で元の受理receiptだけを読む。本人性が確認できた同じSession/branchだけを復旧し、新起動や返送はしない。照合不能はfenceを保持し、Ownerへexecution IDと現物確認を渡す。

`status`は接続不要で既存recordを読む。start/syncには実adapterと検証済みmappingが必要。
controllerはsourceの変更や成果を消さず、Devinのremote checkoutや成果のcleanupはrepo契約と所有者確認後に行う。

## PRと状態

Linearは2026-10-05 JSTのCLI読取で `Todo`, `In Progress`, `In Review`, `Done` を確認した。
workspace/team/project IDはconfigに固定。`Ready`というstatusは存在を確認していないので前提にしない。
ラベルは既存 `agent:codex` / `agent:claude` に合わせ `agent:devin` を導入予定だが、現時点では存在しない。
この読取時点で `agent:devin` は未導入。現在の source config の `requiredLabel` は `!implement`。
接続時には実 scope の現物と採用を照合する。既存agent:codexを転用しない。
`orca-review` / `blocked`等の新labelは作成していない。

concafeは1 Issue = 1 branch = 1 worktree = 1 Draft PRを維持する。
既存auto-ready/auto-mergeの許可branchは `claude/`, `codex/`, `kakeru9917/`。
今回の設定は互換の `codex/caf-<number>-<description>` を使う。branch名前空間は担当モデルの認証ではない。
Devin用namespaceへの変更を口実にCIガードを緩めない。

PRにはLinear Issue、変更内容と技術判断、現在SHAの検証結果、残件とリスク、必要なscreenshotsを含める。
`review:required`と分類label、CI/独立レビュー/人間ゲートは対象の現行契約に従う。
controllerは自動Ready/merge workflow、Cloudflare/deployment、権限・署名鍵・CI supervisorを変更しない。

## 実運用の切替TODO

1. 有効なDevin接続と利用権限・secret方式・費用を確認し、直接実装するimplementationAdapterを配置する。
2. Orca品質adapterを既存Review/evidence/CI/QA/最終判定経路へ接続する。実装者が承認receiptを作れない権限分離を確認する。
3. `agent:devin`を実workspaceへ採用し、requiredLabelを設定する。既存statusをmappingへ使う。
4. 旧Banana担当/進行中Issue/branch/PR/unknown batchを一覧し、drainする。曖昧な起動を再送せず、Devin新startと既存担当を重ねない。
5. isolated installの検査後、ownedリンクだけを実機で切替する。旧session/home/state/persona/成果は保全する。
6. 旧Banana homeのcoordinatorと時計automationをモデル無しReview受付へ移す。CLIガイドに従い、実停止・移設・再起動・新コード読込・新receiptを確認する。
7. 低リスクの1件でstart→PR→Orca指摘→同じSession修正→現在SHAのレビュー/CI→guarded merge→Doneを実証する。その後並列を拡大する。

2026-10-05の表示・セットアップ追加依頼で、5の実機ownedリンク切替は完了した。
インストール済みのベンダーDevin CLIは保全し、独自controllerは `devin-flow` 名にした。
実装・品質adapterへの接続、実Session・実PR・実mergeと旧時計移設は未実施。
旧automationは読取時enabledで、停止/移設完了と報告しない。
rollbackで旧Bananaへ自動fallbackしない。新startを止め、既存Session/PR/台帳を保全し、Ownerの判断へ戻す。
