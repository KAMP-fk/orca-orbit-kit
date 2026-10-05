# 常設3窓口への整理（2026-10-05）

Owner の「その方向で計画立てて修正・改善して」を受けて実施する。
常設は Tomato、Banana、Review の3窓口。専門知識は削除せず、Kiwi/Melon と
Peach/Potato の専門実行を依頼ごとに使う。Fable は判断時だけの相談先。

## 計画

1. 役割契約に常設/必要時・受付先を明示し、Melon の所属を Banana に統一する。
   Review は既存 Peach ホームを再利用する。新しい role/card は増やさない。
2. ホームの必須確認を3窓口に限定する。専門担当の旧ホームを必要条件にせず、
   新規タブの専門モデル自動起動を止める。Review は依頼種別を選ぶモデル無しの受付。
3. `review` 共通入口で acceptance / technical / final を明示選択する。
   二重レビューを自動起動せず、final はプロジェクト契約の別タスクへの引渡し計画にする。
   concafe はこの会話の Owner 指示 CAF-279 が優先。通常 Sol medium、複雑な技術確認
   Sol high、最終独立署名 verdict は未関与の別 Codex タスク Astra high、上位判断は
   別 Codex タスク Astra medium。汎用 Claude 経路へ送らない。
4. モデル無し監視の取得障害は Banana に集約し、Kiwi は基盤修正の依頼時だけ起動する。
   既存の pending/active/unknown や不明な起動は消去・再配送しない。
5. 隔離 fixture で3ホームだけの動作、専門担当ホーム無しの実行、二重起動抑止、
   review の経路・Owner 方針・最終レビューの非自動実行を検証する。
   配線・実機の読み取り確認、差分確認と exact index scan 後にローカル commit。

## 完了条件と運用境界

- 既存の3ホームだけで配線確認でき、専門担当は固定ホームを必要としない。
- 新しい専門ホームのタブを開いてもモデルを起動しない。Tomato/Banana の対話起動は維持。
- Review の既存ホームで Claude を待機起動せず、明示した依頼だけ専門経路に渡す。
- 受入確認・技術所見・最終署名 verdict を混同しない。実装者の自己 PASS を認めない。
- 作業中セッション・worktree・成果・live DB・CI supervisor・automation は変更しない。
  古いカードの削除や稼働中プロセスの終了を、この設定変更の完了と混同しない。
- モデルや実サービス呼び出しを使ったテスト、外部投稿、PR/Linear 操作は行わない。

## 実行記録

計画1〜5の設定・共通入口・文書・隔離検証・配線確認を実施した。

- `roles.json` の6個の専門名/互換 key は維持し、常設ホームは Tomato/Banana/Review の3個。
  Melon の所属は Banana、専門担当は必要時のみ。新しい role/card/profile は増やしていない。
- Review は旧 Peach の既存 full worktree ID を再利用して表示名を更新。
  実機 `start-workspaces --check` は3ホームのみ、`melon --check` は Banana の受付と
  `state=on-demand` を返し、いずれも rc=0。既存 terminal の close は行っていない。
- `review` の実リンクを追加し、16リンクと既存 tab-autostart block の check が rc=0。
  `review --inbox` のモデル無し受付も rc=0。一般の final と concafe review は
  別タスクへの計画のみで、実実行では exit 3。固定 SHA 不一致や直接 Potato の
  concafe 起動を拒否することを検証した。
- 最終の関連検査は
  `PYTHONPATH=tests python3 -B -m unittest test_named_agents test_named_tab_startup test_named_task_sessions test_named_workspaces test_project_tasks test_event_monitor test_review_entry test_role_routing test_banana_context`
  が146件 / rc=0。専門ホームなしの編集・直接タスク・回収、旧 Kiwi outbox の保全と
  Banana との起動排他、最終レビューを自動実行しない経路を含む。
- 全体の `python3 -B -m unittest discover -s tests -p 'test_*.py'` は294件 / rc=1。
  既存 review-relay の8テストで19 assertion failure（必須 `--verdict` を fixture が未指定）、
  ソケット fixture 1件で sandbox の EPERM。relay 本体とそのテストが HEAD から未変更であることを
  hash 比較で確認した。必須ゲートを弱めず、別作業の実装/テストは保持した。
  ソケットの1件だけを制限外で再検証し、1件 / rc=0。
- README/新契約/計画のローカルリンク9件は参照切れ0。Git diff の whitespace check も rc=0。
  exact index は89ファイルを走査し、credential finding/error/symlink は0。
  他担当の未コミットレビュー実装と、共有文書の既存本文変更は commit に含めない。

新規タブと次の依頼には新構成を適用する。稼働中の対話セッション・旧専門カード・
作業成果・監視 coordinator/automation/DB・CI supervisor は維持した。
監視の新しい health→Banana の振り分けはソースと fixture の検証までで、
読み込み済み coordinator に反映したとは扱わない。正式最終レビューや署名 PASS の結果でもない。
