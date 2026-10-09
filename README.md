# Orca / Orbit private source kit

Orca の自作エージェント構成と Orbit を再構築するための private ソースパッケージ。
編集元はこの checkout と固定 SHA の source submodule。実データ・認証・製品本体は含めない。

- [導入・編集・更新・削除](docs/package/INSTALL.md)
- [Tailscale](docs/package/TAILSCALE.md) / [依存と対応範囲](docs/package/DEPENDENCIES.md)
- [バックアップ](docs/package/BACKUP-RESTORE.md) / [由来](docs/package/PROVENANCE.md)
- [権利方針](LICENSE) / [第三者表記](THIRD_PARTY_NOTICES.md)

`apps/orbit` は既存の `KAMP-fk/orbit-console`、Tomato skill は `KAMP-fk/tomato-skill`。
どちらも private source submodule で、clone は `--recurse-submodules` を指定する。
source 内で編集・検査・commit/push した後、親側で参照 SHA を更新する。
`git diff --submodule=diff` と各 source の `git status` で変更を確認できる。
自動 commit/push はしない。Orca 製品の自動更新や runtime state はこの source 更新と別。

```sh
python3 scripts/doctor.py
scripts/setup --check
scripts/check
```

# Orca エージェント基盤

Tomato・Banana・Potato の役別ソースと、案件管理・観測・オフライン検査を管理する。
構成の入口は [エージェントの README](agents/team/README.md)、担当の正本は
[roles.json](agents/team/roles.json)。開発は Banana の Codex 経路を使う。

| 配置 | 内容 |
| --- | --- |
| `agents/team/` | 共通 CLI・ライブラリ・設定・役別ソース |
| `tests/` | 共通基盤のオフライン回帰検査 |
| `docs/` | [運用資料と完了した引継ぎの案内](docs/README.md) |
| `tools/ci/` | ローカル `act` 調査用スクリプトと Dockerfile |
| `workspaces/` | Orca が管理するプロジェクト別 checkout（Git 対象外） |
| `reports/`・`task-reports/` | ローカル検査・作業の記録（Git 対象外） |
| `archives/`・`history/` | 復元用の保管と旧基盤（Git 対象外） |
| `ci-runner/` | 既存 runner の運用環境（Git 対象外） |
| `brain-kit/` | 独立した既存 repository |

Tomato の `agents/team/roles/tomato/skill/` も独立した Git repository。
ライブ台帳・パケット・ログ・鍵・persona はソース整理の対象に含めない。
Git の境界は [VERSION-CONTROL.md](VERSION-CONTROL.md)、作業契約は [AGENTS.md](AGENTS.md)。

```sh
agents/team/bin/check --quick  # Python・JSON・shell 構文と差分
agents/team/bin/check          # 加えて Orca / Tomato のオフラインテスト
agents/team/install.py --check --tab-autostart
agents/team/bin/start-workspaces --check
```

現行の住所と互換リンクは [directory-layout.md](agents/team/references/directory-layout.md)。
完了した移行記録は `agents/team/references/history/` に分けて保存する。
