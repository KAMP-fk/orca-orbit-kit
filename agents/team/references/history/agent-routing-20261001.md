# Orca の Claude・Codex・Devin 構成

更新: 2026-10-01。`concafe-techo` は Owner が明示採用した CAF-361 / ADR-065 の新規 issue フローを優先する。プロジェクト固有の正本は `AGENTS.md` と `docs/WORKFLOW.md`。この対応表を他プロジェクトや既存の進行中タスクへ自動適用しない。

## concafe-techo の新規 issue

| 段             | 起動時の model / effort                                                    | 仕事と境界                                                                                  |
| -------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| P 方針         | `--agent claude --model opus --effort medium`。複雑な整理は理由付き high   | 承認済み AC の範囲で方法・影響ファイル・検証方法を packet にする。T4 Owner 代行承認ではない |
| I 実装         | `--agent codex --model gpt-6.1-sol --effort medium`。複雑な技術作業は high | 実装、検査、PR/CI 対応、指摘修正                                                            |
| R 独立レビュー | `linear-inreview-reviewer <ID> --backend claude --pr <owner/repo#N>`       | P・I・修正に未関与の別 Opus session が固定 full head SHA を確認。未関与の親が直接受領・中継 |
| 親進行         | Sol medium、複雑な技術作業は Sol high                                      | WIP・共有境界・担当管理。自己 PASS をしない                                                 |
| Owner 代行判断 | Owner 本人、条件成立時だけ未関与の別担当                                   | repo の T4 の通知経路・実待機時間・停止実害の3条件、Fable → Opus → Sol と人間ゲートを維持   |

P/I は Orca の supervised worker に上表を明示する。R は標準 launcher の既定 backend に頼らず `--backend claude` を必ず指定する。共有 launcher の default backend/model は変更しない。R の `opus` が実環境で最新 Opus に解決することを確認し、effort は既存 launcher の通常 path medium、保護 path（`.github/`・`.agents/`・`.claude/`・`AGENTS.md`・`docs/WORKFLOW.md`・`docs/adr/`・`supabase/migrations/`）または判定不能 high を使う。

起動ごとに `launch.requested` / `launch.effective`、実際の ID / effort、task / session ID と同じ issue の関与歴を記録する。R の JSON `modelUsage` / `meta.json` も照合する。P session は I・R・同じ issue の T4 Opus 段を兼ねない。供給断・認証失敗・未対応 ID・ネットワーク・timeout を含め、Owner が代替を選ぶまで別モデル / provider を起動しない。自動 fallback や silent alternate を使わず、未達を記録して依存しない準備を続ける。新規 subagent 起動・追加依頼はしない。

新規 PR は作成時から `review:required` を付け、レビュー回避のため外さない。marker は PASS ではなく、分類ラベルも必要。`risk:high` または marker は現在 head の full SHA の `review:passed` success status を待つ。拡張は main 統合後に発効する。marker がない既存 `risk:low` PR、他の live task と session の設定は変更しない。

R の指摘は Sol へ返し、新 head の `pnpm check`・必須 CI・再レビューを行う。CAF-320 の限定 carryover は維持する。reviewer 自身は GitHub へ書き込まず、未関与の親が verdict を直接受領し、PASS と SHA を照合してコメントと status を中継する。CI・自動 Ready / guarded auto-merge・人間ゲートを維持し、手動 Ready / merge、署名 verdict・鍵配布、旧 Claude Actions・月次 Routine は再導入しない。Mac mini の native CI/perf 実行配置・予算と Actions $0 超過停止は変更しない。

## 起動時の観測と履歴

- 2026-10-01 の P は Claude Code 2.1.286、`claude --model opus --effort medium`、session の ID は `claude-opus-5-5`（Opus 5.5）と packet に報告された。I は Orca の requested / effective がともに `gpt-6.1-sol` / high。CLI は 0.159.2 の環境。各新規起動ではその時点の ID を再確認する。
- 2026-09-30 の Codex CLI 0.154.0 の `gpt-6.1-sol` HTTP 400 は過去の実測であり、現在の可否を決める根拠にしない。現在の `~/.codex/config.toml` の model は P が `gpt-6.1-sol` を観測したが、既定値だけを実効値と扱わない。
- P が観測した 2026-09-29 版標準 launcher は backend 既定 `codex`、Claude alias `opus`、path 別 effort、settings preflight と `mcp__*` deny を持つ。repo 内 review.md の歴史的な未実装段落は本 issue では未更新で、別 follow-up が必要。起動時に実 settings を照合する。
- 旧一般案の Fable による指揮や独立レビュー既定、T1〜T3 の自動候補切替は、concafe-techo の新規 issue では本表が更新する。他の依頼や live task は自動変更しない。
- Devin CLI 3000.11.3 の `gpt-6-1-sol-medium` は以前の読み取りプローブに応答したが、Orca の native supervised worker 対応ではなく、課金枠は未確認。CAF-361 では追加起動せず、新規標準 I に使わない。Owner の別契約がある場合は監視・差分回収・独立レビューを別途具体化する。

T4 の条件・人間ゲートは repo の現行正本に従い、通常の Opus P packet を Owner 代行承認へ転用しない。既存 session の設定変更や外部停止を文書変更だけで完了扱いしない。
