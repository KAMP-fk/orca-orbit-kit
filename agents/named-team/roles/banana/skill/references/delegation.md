# 分担する

現在のユーザー指示と [contracts.md](contracts.md) で決めた分担・モデル・起動方式に従う。
スキルを読んだだけで subagent の許可や新しい provider の使用許可を得たことにしない。
既存の担当を再利用し、独立に進められる調査・実装に分けると時間や品質に利点があるときに分担する。
小さな変更なら無理に分けない。

Orca の supervised worker を使うタスクでは、対象環境の `orchestration` スキルを読み、
実際の Run / task / terminal 状態を追跡する。別 checkout の作成は `orca-cli` に従う。
他の環境でのローカル開発は、その環境で承認されたエージェント機構を使う。
Orca 上の監督付き連携を別製品の subagent 状態で代替しない。
名前付き role の直接タスクは `--prompt-file` で一件ごとの新しいタブに渡す。
通常の案件受付は [Banana の共通入口](../../../../references/project-tasks.md) の
`~/.agents/skills/banana/bin/task --role <担当> --repo <対象> --task-id <依頼ID> --prompt-file <依頼>` を使う。
編集担当は案件用 worktree で実行し、読み取りは `--access read` で指定 checkout を使う。
既存の担当 branch / PR を継続する場合はその `--worktree path:<絶対パス>` を明示して再利用する。
成果のある worktree は保持し、回収後に統合・最終検証・必要な cleanup を進める。
プロジェクトが別 Codex タスクを要求する場合はその正式な経路を使う。
concafe の新規 subagent / 追加依頼の禁止を名前付き launcher で迂回しない。

役割は [共通契約](/Users/kamp/orca/agents/named-team/references/team-topology.md) で選ぶ。
Kiwi は観測・引き継ぎ基盤、Peach は In Review Issue の AC 判定、Potato は固定差分の技術確認。
この三役は Banana の配下の専門担当。通常の開発進行では Banana が割当と回収を持つ。
相談事項は意図・前提の整理なら Tomato、材料が揃った具体的な選択なら Fable に確認する。
判断と決定者を回収して進行へ反映し、未決の判断を承認扱いにしない。
持ち主から直接依頼を受けた担当はその依頼元へ結果を返してよい。並行する進行責任者は増やさない。

## 渡す情報

- 対象 repo / checkout / branch / issue / PR と承認済み AC。
- 編集してよいファイル、並行担当、触ってはいけない共有領域。
- 必要なローカル指示とプロジェクト契約のパス。子が読めるか確認し、親のコンテキスト継承を仮定しない。
- model / effort の契約と、起動要求・実効設定・担当識別子。供給断を理由に自動 fallback しない。
- 実装・検査・commit / push・外部操作の範囲と完了条件。
- 報告する根拠、未確認事項、残件。権限拒否を迂回しない。

子は `~/brain` に書かない。状況カード・報告・knowledge は Banana が自分で記録する。
同じファイルの並行編集を避け、共有 FS では変更の反映を確認してから統合する。
送信の受理・タスク起動・成果物・完了は、それぞれ実際の状態で確認する。

## 独立性

実装・修正担当は、同じ変更の最終独立レビューや承認を兼ねない。
モデルを変えること、役割名を変えること、別窓を開くことだけでは未関与の証明にならない。
レビュー担当が修正した場合は実装側へ移り、別の未関与担当にレビューを渡す。
[review.md](review.md) の固定 SHA と証拠の引き渡しを使う。

専門担当は必要時だけ起動する。通常の製品実装は Banana、観測基盤修正は Kiwi、レビュー基盤修正は Melon。
レビューの受付は `review --kind acceptance|technical|final` に揃え、両方の専門レビューを毎回自動起動しない。
