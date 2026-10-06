# Banana に Devin を組み込む開発経路

2026-10-06 JST の Owner 追補を初回の統合案より優先する。
Tomato は幅広い相談・目的の整理、Banana は独立した開発窓口。両者の領域は一部重なり、
開発の指示・質問・報告で連携する。Owner は Banana に直接依頼できる。
Potato は Banana が受け付けた案件の独立 checkout で必要時だけ起動する。
旧 Kiwi / Melon の基盤保守を Banana にまとめ、名前付き担当は3役のままにする。

```text
Tomato ⇄ Banana
           └─ 開発 checkout（Devin CLI）
                └─ 固定 full SHA の独立 Potato checkout
                         └─ 指摘を Banana へ / 正式判定は対象契約の別タスクへ
```

## 開発を受ける

```sh
banana --inbox
banana develop --repo /absolute/repo --task-id feature-001 --from-role tomato --prompt-file /absolute/request.md --dry-run
banana develop --repo /absolute/repo --task-id feature-001 --from-role tomato --prompt-file /absolute/request.md
banana review --repo /absolute/repo --task-id feature-001 --dry-run
banana review --repo /absolute/repo --task-id feature-001
```

`develop` はローカルで発見したベンダー `devin` の `--print -- <prompt>` を使う。
2026-10-06 の実機 `devin --help` で非対話実行、prompt 区切り、既定の workspace trust を確認した。
Codex 用 model / effort を渡さず、trust / permission を迂回しない。
バイナリなし、信頼・認証未確認、非ゼロ終了、空の結果は成功にしない。Codex / Claude へ fallback しない。
Devin の認証・モデル実設定はベンダーに委ね、設定や token を source へコピーしない。
実装エンジンと、調査・保守に使う Banana の Codex Sol medium は別に扱う。

`--repo` は Orca に登録済みの Git checkout を指定する。
共通の repo/task ID lock と耐久 fence を使い、作成・起動の曖昧な応答を再送しない。
Banana を進行担当として専用 checkout を作る。Orca の親子表示は同じ repo / host / project 内に限るため、
別プロジェクトの開発 checkout はその対象 workspace を親にする。Banana との関係は coordinator として記録する。
同じ repo の案件は Banana ホームを親にできる。元の未コミット変更はコピーしない。
concafe は task-id に `CAF-<番号>` の案件 ID を指定し、既存 CI 互換の `codex/caf-<番号>-<識別子>` branch を使う。
Devin は渡された checkout だけで実装・必要な検査・成果 commit を行う。
受入条件、push / PR / 外部更新の実際の委任は元の依頼と現行プロジェクト契約に従う。

## レビューへ渡す

Devin の結果と終了を保存してから、clean な実装 commit の現在 full SHA を確かめる。
未コミット成果は保持して Banana に返す。commit が増えていない場合はその結果を Banana に返す。
commit が増えた場合はその SHA から別の Potato checkout を作り、開発 checkout の子として記録する。
実装の変更や commit を削除せず、両 checkout を統合・レビュー待ちとして保全する。

保存先は共通案件の `record.json`、`session/result.txt` と `review/handoff.json`。
引渡しには元の依頼、実装担当、開発 checkout、固定 SHA、結果の場所を含める。
`banana review` は依頼内容・開発成果・レビュー checkout が保存時から変化していないことを再確認する。
汎用技術確認は新しい読み取り専用の Opus 5.5 / high の案件として Potato に渡し、同じ task ID の再実行を防ぐ。
指摘は Banana が受け、同じ案件の成果を使って修正する。

concafe は `final` の引渡し packet とし、最新 Owner 指示の Opus 5.5 / high を指定して未関与の別タスクに渡す。
ここで最終 verdict を発行したり、別 Codex チャットへ自動送信したりしない。
別タスク待ちは通常実行 exit 3、計画だけの dry-run は exit 0。
必須 CI・固定 SHA 署名・自動 Ready / guarded auto-merge・人間ゲートは維持する。

## 外部 Issue adapter と既存実行

既存 `devin-flow` / `banana devin start|sync|status|reconcile` は
[外部 Issue adapter](devin-operations.md)。ローカル CLI の案件とは別の台帳・排他契約を使う。
外部 adapter は未設定のまま。ローカル CLI 組込を実 Cloud Session / PR / merge の成功証拠にしない。
同じ Issue に既存実行がある場合は新開始を重ねず、現物と担当を確認する。
旧 coordinator・時計 automation・既存セッションはこの変更では停止・再起動していない。
新規タブの Banana 受付はモデル無し。既存セッションが新しい指示を再読込したとは扱わない。

## 検証と保全

この変更はモデル・外部サービスを使わず、fixture CLI と一時 Git / Orca で検査する。
全体検査 `python3 -B -m unittest discover -s tests -q` は
367件・281.793秒・exit 0（OK）。新規検査は CLI 選択、開発 / Potato の親子関係、
固定 SHA、read-only 引渡し、未コミット成果・空結果・失敗の保全、曖昧な作成の fence、
同一案件の重複防止、concafe branch / 別 Astra verdict の経路を含む。
Python 構文29ファイル、公開 command の実行属性、文書のローカル参照を確認。
`git diff --check` は Orca / Tomato の両リポジトリで exit 0。

実機 `install.py --tab-autostart` は所有を確認した Maintenance の3リンクを撤去し、
Banana の command / skill / profile を復帰した。`install.py --check --tab-autostart` は exit 0。
Orca の `skills installed` は Banana / Potato / Tomato の3役を返した。
`setup` は既存 Activity タブを再利用し、既存 Banana ホームを開発窓口として表示。
`setup --check` は表示差分なし・exit 0。`start-workspaces --check` は Tomato / Banana の2ホームと
当時の Banana の進行先・相談先が Tomato であることを返した。この直属配置は後の Owner 追補で更新した。`banana --inbox` も exit 0。
これらの実機反映はモデルを起動せず、既存セッション / 監視の再起動もしていない。
実 Devin の認証・課金実行・成果・実レビュー / PR / merge は今回検証していない。
初回統合の実測は [初回記録](agent-consolidation.md) を保全した。
変更前の source / test と Tomato 技術参照のスナップショットは
`/var/folders/l3/m0m_2xsd23q4wr1rczgxqc180000gn/T/orca-banana-integration-t24s2muf`。
既存の未コミット成果と混ぜて commit せず、brain・鍵・実台帳を復元用にコピーしない。
