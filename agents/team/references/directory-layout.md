# Orca の役割・表示・実ファイル配置

現行の役は Tomato / Banana / Potato、常設ホームは Tomato / Banana。
開発は Banana の Codex 経路を使う。配線の正本は [roles.json](../roles.json)、
担当と品質ゲートは [team-topology.md](team-topology.md)。
この案内は現在の住所を示す。2026-10-06 の移動・表示変更・検査の全文は
[history/directory-layout-20261006.md](history/directory-layout-20261006.md) に保全した。

## 正規のソース

```text
/Users/kamp/orca/
├── README.md / AGENTS.md / VERSION-CONTROL.md
├── agents/team/
│   ├── roles.json                  担当・連絡先・起動設定の正本
│   ├── bin/・lib/・shell/           共通 CLI・案件管理・観測
│   │   └── lib/state_io.py          JSON の atomic 保存・上書き禁止の公開
│   ├── config/                     イベント設定・保全した旧接続設定
│   ├── references/                 現行契約。history/ は過去の記録
│   └── roles/
│       ├── tomato/
│       │   ├── claude/              対話設定・起動指示
│       │   ├── codex/               イベント観測の設定
│       │   └── skill/               相談・観測ソース。独立した Git repo
│       ├── banana/codex/・skill/    開発窓口・Codex・基盤保守
│       └── potato/
│           ├── skill/・entry/       レビュー窓口と案内
│           ├── codex/              未配線の旧 profile
│           ├── acceptance/         受入証拠・固定版検証
│           └── relay/              記録検証・中継
├── tests/                          共通基盤のオフライン検査
├── docs/history/                   完了した Git 導入の引継ぎ
├── docs/operations/ci/              CI 費用資料・画像。Git 対象外
└── tools/ci/                       ローカル act 調査用スクリプト・Dockerfile
```

案件・イベント・連絡の台帳は `~/.local/share/named-team/` に置く。
受入の `state/`、relay の `log/`、`workspaces/`、`ci-runner/`、
`reports/`、`archives/`、`history/` は Git 対象外。
旧基盤の実体は `history/agent-infrastructure/reviewer-20260929`。
ライブ台帳・パケット・ログ・署名鍵・persona をソース整理で移動・編集しない。

## Orca の表示と checkout

| 入口 | 正規の住所 |
| --- | --- |
| Tomato | `~/orca/workspaces/brain/Tomato` |
| Banana | `~/orca/workspaces/brain/Banana` |
| Potato の表示窓口 | `~/.local/share/named-team/entries/potato` |
| 共有基盤 | `~/orca` |

Tomato / Banana は独立した brain の Git worktree。
Potato の入口はモデル無し受付で、実レビューは案件ごとの別 checkout を使う。
旧 Kiwi / Melon / Potato のホームは `archives/retired-homes/` に保管済み。
Orca の表示順は Tomato、Banana、Potato、Orca 基盤。

別プロジェクトの開発 checkout は同じ repo / host / project の workspace を表示上の親にし、
Banana ホームは `coordinatorWorktreeId` に記録する。
`lineageParentWorktreeId` は実際に使う同じ repo の親で、レビュー checkout は開発 checkout の子。
親を確認できないときは作成・実装起動を止める。
既存 checkout・セッションの住所は、この資料の整理では変更しない。

## 旧住所との互換

| 旧住所 | 正規の住所 |
| --- | --- |
| `agents/named-team` | `agents/team` |
| `agents/team/roles/review` | `agents/team/roles/potato` |
| `agents/team/bin/review` / installed `review` | 同じ `potato` command |
| `agents/linear-inreview-reviewer` | `agents/team/roles/potato/acceptance` |
| `agents/review-relay` | `agents/team/roles/potato/relay` |
| `agents/linear-inreview-reviewer.bak-20260929` | `history/agent-infrastructure/reviewer-20260929` |
| `AGENT-ROUTING.md` | `agents/team/references/team-topology.md` |
| `HANDOFF-agents-git-20261002.md` | `docs/history/HANDOFF-agents-git-20261002.md` |
| `GITHUB-ACTIONS-COST-PLAN.md` | `docs/operations/ci/GITHUB-ACTIONS-COST-PLAN.md` |
| `actions-budget-zero.jpg` | `docs/operations/ci/actions-budget-zero.jpg` |
| `CONCAFE-ACT.Dockerfile` | `tools/ci/CONCAFE-ACT.Dockerfile` |
| `concafe-act-validate.sh` | `tools/ci/concafe-act-validate.sh` |

旧住所には相対リンクを残す。installed command / skill / profile は正規ソースを参照し、
installer は解決先の一致する所有リンクだけを変更する。
公開名は Potato、耐久記録と排他に使う役割 ID は `review` のまま。
旧 Codex の Potato / Review profile は未配線で、現在の設定は
`~/.claude/named-team/potato.settings.json`。対象プロジェクトの最終 verdict の契約を優先する。

## 検査

`agents/team/bin/check` は Python・設定 JSON・shell の構文と両 repository のテストを検査する。
`--quick` は構文と差分の検査だけを行う。
共有 JSON 保存の検査は `tests/test_state_io.py`、移動後の CI ツールは
`tests/test_ci_tools.py`。いずれも一時 fixture を使い、実モデル・外部投稿・実 CI は呼ばない。
検査成功を独立レビューの PASS と扱わない。
