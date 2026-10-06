# 機能と文書の整合性整理（2026-10-05）

Owner の「整合性が取れてるか、機能面やreadmeなどをリファクタリングして」に対応する。
現在の責任は team-topology、機械設定は roles.json、利用方法は README に集約する。

## 計画と完了条件

1. 3窓口の起動・必要時担当・監視・レビューの code/README/skill の食い違いを確認する。
2. レビュー依頼の対象 repository と依頼本文を実行/引渡しへ保持する。
   無視される引数、取り違え、不明な repo 判定をモデル起動前に止める。
3. 旧編成・モデル指定・導入 receipt は履歴へ移し、現行の読み取り先を明確にする。
   同時編集中のレビュー実装・テストを保存し、その方針を Owner の直接指示と混ぜない。
4. 既存 relay テストを必須 --verdict 契約へ合わせ、門を弱めず拒否経路を検証する。
5. 隔離 fixture と全体検査、配線・文書リンク、exact index scan を確認し、今回分だけ保存する。

完了条件は、対象違いを拒否する実装と検証、現行説明の一致、並行差分の保全。
モデル/API 呼出しをテストせず、稼働中セッション・監視・CI supervisor・live DB は変更しない。
製品の最終 verdict、署名 PASS、外部操作の完了はこの検証の結果に含めない。

## 修正

- 共通の project_identity を launcher と review から使用。対象 Git の読取失敗で
  concafe を汎用 Claude 経路へ逃がさない。origin は credential を表示せず識別する。
- 受入 pipeline に --expected-repo を追加し、明示 PR/run と発見候補を照合する。
  別 repository の候補は PR 取得・backend 起動前に止める。
- review 引渡しは依頼本文/path/hash と checkout の観測 SHA/dirty を保持する。
  不適合引数と別 repository の final PR を拒否し、計画自体を最終 verdict と表示しない。
- roles.json の受付、進行担当の循環、重複ホーム、専門担当の待機起動を検証する。
  setup は選択済み Orca CLI を確認し、別 build を要求しない。
- roles は現行契約への入口、effort は用途表、event-monitor は現行運用の説明に整理する。
  旧説明と導入記録は history/ に保存。並行編集は履歴の未コミット差分として保持する。
- README と Potato/Banana の参照先、Review のモデル無し受付の help を揃える。
- relay fixture に逐語 verdict を渡し、必須指定の欠落と要約による欠落も検証する。

## 検証記録

- 全体 `python3 -B -m unittest discover -s tests -p 'test_*.py'` は308件、
  307件成功、Unix socket fixture 1件だけ sandbox の EPERM（rc=1）。
  同一の1件を制限外で個別再検証し、1件成功 / rc=0。assertion failure は0。
- 集中検査は review_entry / review_relay / named_agents / named_workspaces / role_routing
  が72件成功。その後追加した scope/不正 routing 検査を含む review_scope / role_routing
  は12件成功。全体検査は追加分を含む現在の308件を対象にしている。
- shellcheck と bash -n は変更した cli.sh / github.sh で rc=0。
  README・references・role docs のローカルリンク72件は参照切れ0。whitespace check も成功。
- install --check --tab-autostart は16リンクと既存 shell block を確認して rc=0。
  review --inbox、実機 start-workspaces --check は rc=0、確認ホームは3個。
  melon --check は追加ホームを作らず Banana の state=on-demand / handles=[] を返す。
- exact index scan は95ファイル、credential pattern finding / error / symlink は0。
  履歴は変更前の HEAD 本文だけを index に保存し、並行文書変更は履歴の作業コピーに残す。
  他担当の reviewer 実装・テストと未追跡 reviewer_role テストを今回の保存に含めない。
- skill-creator quick_validate は PyYAML 未導入で起動できなかった（rc=1）。
  変更した Potato skill の frontmatter が HEAD と同一であることと本文の参照を確認した。
  この文書整理のために共有 Python 環境や依存を変更していない。

共通の受付・次の依頼・新規タブへ適用する。稼働中モデル・旧専門カード・monitor coordinator
は変更せず、監視のソースを実運用へ反映したとは扱わない。
既存 Peach backend の別作業のモデル/正式 R 方針変更は今回の共通受付へ採用せず、
この会話の Owner CAF-279 指示を優先する。最終 verdict・署名 PASS の確認結果ではない。
