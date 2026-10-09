# 依頼: ~/orca 配下の version 管理を決め、Melon / Kiwi が起動できる状態にする

依頼元: Tomato（窓口）/ 2026-10-02
持ち主の指示: 「Potatoやkiwi、melonにもタスク流せてる？」→「出して / 各エージェントを
しっかりフローに盛り込んで」。フローへの組み込みは完了。起動が物理的にできないので引き継ぐ。

------------------------------------------------------------------------
## 1. 何が止まっているか

Melon（レビュー基盤担当）と Kiwi（観測・引継ぎ基盤担当）に依頼を出したが、
両方とも起動時に落ちた。

    $ melon --exec --effort high --cwd ~/orca "<依頼>"
    Reading additional input from stdin...
    Not inside a trusted directory and --skip-git-repo-check was not specified.
    rc=1

    kiwi も同じメッセージで rc=1。

Potato（未関与の技術確認）は --cwd ~/Projects/concafe-techo で正常に起動した。
違いは cwd が git repo かどうか。

------------------------------------------------------------------------
## 2. 実測（2026-10-02）

    $ git -C ~/orca rev-parse --show-toplevel
    fatal: not a git repository (or any of the parent directories): .git

    ~/orca 配下の git repo（深さ3で全数）:
      /Users/kamp/orca/brain-kit        ← これだけ
      （~/orca/workspaces/* は ~/brain の worktree）

    三役の対象ファイルが version 管理下に在るか:
      ~/orca/agents/linear-inreview-reviewer    管理外   ← Melon の対象
      ~/orca/agents/review-relay               管理外   ← Melon の対象
      ~/.claude/skills/Tomato                  管理外   ← Kiwi の対象（見張り）
      ~/orca/ci-runner                         管理外

    codex の trust 設定（~/.codex/config.toml）:
      [projects."/"]                                   trust_level = "trusted"
      [projects."/Users/kamp/Projects/concafe-techo"]   trust_level = "trusted"
      （"/" が trusted でも上のエラーは出る。止めているのは git repo の検査）

    launcher（~/.local/bin/melon、~/.local/bin/kiwi）は --exec も --orca も
    --skip-git-repo-check を渡さない。渡す口が無い。

------------------------------------------------------------------------
## 3. 決めてほしいこと

### 案(1) ~/orca/agents を git repo にする（窓口の推奨）

    利点: エージェントの編集が戻せる。人間より機械が書く場所なので効き方が大きい。
    必要な前作業: .gitignore を先に決める。state / log / token が同じ木に居る。

    追跡してはいけない候補（着手前に全数を洗うこと）:
      ~/orca/agents/review-relay/log/     監査記録
      ~/orca/ci-runner/launch.log         CI runner のログ
      ~/orca/agents/**/state/             packet・verdict・JIT 応答
      *.token / *.key / .env / secrets    token と鍵
      ~/.codex/*.config.toml への symlink の実体（agents 配下に在る）

    **git init の前に secret の全数走査を行うこと。**
    一度 commit すると履歴から消すのが難しい。

### 案(2) launcher が --skip-git-repo-check を渡す

    即動く。ただし戻せない編集を許す。
    Melon / Kiwi は実装する役なので、窓口はこの向きを推さない。
    採るなら「どの役に許すか」を限定し、理由を記録すること。

### 案(3) 対象だけを別 repo にする

    ~/orca/agents だけ、または linear-inreview-reviewer と review-relay だけ。
    範囲が狭いので secret を巻き込む危険が小さい。
    ただし ~/.claude/skills/Tomato（Kiwi の対象）は別の場所なので、Kiwi は別途要る。

------------------------------------------------------------------------
## 4. やってはいけないこと

- --dangerously-bypass-approvals-and-sandbox、--dangerously-bypass-hook-trust、
  -s danger-full-access、sandbox_mode を danger-full-access にする -c 上書き。
  codex-guard（~/.local/share/codex-guard/）が止める。迂回しない。
- respect_workspace_trust: false を渡す。
- ~/.codex/config.toml の [projects] に trust を足す。持ち主の領分。
- 「rejected by user approval settings」を実装の欠陥と読む。持ち主の設定である。
- git init してすぐ commit する。secret の全数走査が先。

------------------------------------------------------------------------
## 5. 決まったら出す依頼 2件（そのまま使える）

依頼本文は必ずファイルに書いて "$(cat <file>)" で渡す。
本文に backtick が在ると shell が実行する。

    melon --exec --effort high --cwd <決めた repo> "$(cat <依頼ファイル>)"
    kiwi  --exec --effort high --cwd <決めた repo> "$(cat <依頼ファイル>)"

### 5-A. Melon へ（レビュー基盤）: CAF-379 の launcher 側を直す

事実: linear-inreview-reviewer の launcher は PASS を出すとき Tests: PASS を要求する
（evidence validation failed: PASS requires CI and Tests PASS）。
しかし Tests 欄の文字列しか見ておらず、実行されたかを見ていない。

CAF-358 / PR #296 の4 packet（すべて同じ head e5f00158...）:

    20261002T112632Z.krynrF   Tests: PASS      通った
    20261002T112207Z.gAux2F   Tests: UNKNOWN   止められた
    20261002T075601Z.7yWRVh   Tests: UNKNOWN   止められた
    20261002T075211Z.Iw6Ppz   Tests: UNKNOWN   止められた

4つとも verdict.raw の Verdict: は PASS。違うのは Tests の1行だけ。

通った run の根拠は1行だけ（逐語、:16）:

    「このテストは validate（pnpm turbo run lint typecheck test build）の中で実行され、
      head SHA の必須 CI 5件はすべて success です。」

Test Files も件数もコマンド出力も無い。CI からの推論である。

止められた run は実行していないことを正直に書いていた（逐語）:

    「今回の環境ではローカル実行の許可が下りず、テストは実行していない。」

この回は判定が CHANGES_REQUIRED だったので門が適用されず、偽の Tests: PASS が素通りした。

帰結: 同じ head、同じ実行実績ゼロで、UNKNOWN と書くと止まり PASS と断定すると通る。
門が正直さを罰して、断定的な書き方を通している。

持ち主の判断（2026-10-02、逐語「案(1)を門に、案(2)は任意の上乗せ」）:

    門は CI の job 単位の結果で判定する。
      gh run view --json jobs で job ごとの name と conclusion を取り packet に入れる
      Tests: PASS は「名指しのテスト job が success であること」で判定する
      skipped は PASS に数えない
      job 一覧が packet に無ければ UNKNOWN
    実際に走らせた回は出力を添えられる。ただし必須にしない
    （launcher が node / pnpm の版まで面倒を見ることになるため）。

落としてはいけない2つ:

    1. CHANGES_REQUIRED の回でも Tests 欄を検証する。
       いまは PASS のときだけ門が噛むので、証拠の質が結論に依存している。
    2. 限界を明記する。job の success は「その job が走った」証拠だが
       「job 内の全テストが走った」証拠ではない。
       この repo は #279 で「CI / full が success でも db と e2e は skipped」を実測している。

止まる条件:

    Tests の要求を外す案は採らない（門を緩める向き）。
    「CI が緑なら Tests は PASS」と明文化する案は採らない（#279 の実測に反する）。

返してほしいもの: 直した path と差分の要点 / 判定が実行の証跡に接地した根拠（どの値を見るか）
/ 明記した限界の文面 / 確かめられなかった範囲。
外部への投稿・Linear の更新・PR 操作はしない。

### 5-B. Kiwi へ（観測・引継ぎ基盤）: 欠陥2件

(1) 進捗の信号の式が誤っている（窓口が書いたもの）

    ~/brain/knowledge/concafe-techo-を触るときの注意.md にこう書いてあった:
      select(.started_at != null) の数を started= として数え、
      started=0 が続けば「止まっている」と読む
    誤り。started_at には queue した時刻が入る。

    実測: run 37007498183 の validate
      status=queued / conclusion=null / runner_name=null
      started_at=2026-10-02T12:34:32Z で 173分 queued のまま
      上の式は started=3 を返し「健全」と読める。1本も走っていなかった。

    正しい信号は status と runner_name。queued が在って in_progress が 0 なら
    止まっている。knowledge 側は訂正済み（brain 629912f）。
    見張りの実装に同じ式が入っていないか確かめ、入っていれば直す。

(2) CI が止まったことを誰も検知していなかった

    2026-10-02、CI が 173分 queue されるまで気づかなかった。
    原因は使い捨て runner を作る supervisor が落ちて launchd に載っていなかったこと:

      ~/Library/LaunchAgents/com.concafe.ci-runner.plist
        ProgramArguments = [python3, ~/orca/ci-runner/supervisor.py, --workers, 2]
        KeepAlive = true / RunAtLoad = true
      launchctl list | grep concafe  → 無し（読み込まれていない）
      ~/orca/ci-runner/launch.log    → RuntimeError: gh exited 1 が 36回、最終 12:34Z

    KeepAlive=true は、ジョブが載っていなければ効かない。

    registered runner が 0 台であることは故障の証拠にならない。使い捨てなので
    job ごとに登録・破棄される（runner 名が毎回変わる: concafe-mm-<hex>）。
    窓口は 0台 を一次信号に使って一度誤った起票をした。

実装してほしいもの: 見張りに「CI が止まっている」の検知を足す。

    queued の job が在って in_progress が 0 で、queued の経過時間が閾値を超えた
    裏付けとして runner_name=null と launchctl への load 状態
    閾値は CAF-339 の形に倣う（最後の成功からの経過時間で判定する）

やらないこと:

    supervisor を起こす・止める・plist を触る（持ち主の領分。検知だけ作る）
    0台 を一次信号にする / started_at を進捗の根拠にする
    「取得できなかった」を「変化なし」と同じに扱う
    （既存の見張りには「取得失敗が10回続いたら止める」が在る。それに倣う）

返してほしいもの: 直した path と差分の要点 / 検知の条件（どの値・どの閾値・何を出すか）
/ 誤報が出る条件（runner の入れ替わりの瞬間など）とその扱い / 確かめられなかった範囲。
外部への投稿・Linear の更新・PR 操作はしない。

------------------------------------------------------------------------
## 6. 返してほしいもの（この依頼そのものへの回答）

- 案(1)(2)(3)のどれを採るか、と理由
- 案(1)または(3)なら: repo の root、.gitignore の中身、secret 走査の方法と結果
- Melon / Kiwi が実際に起動できたことの確認（コマンドと rc）
- 確かめられなかった範囲

------------------------------------------------------------------------
## 7. 参考: すでに済んでいること

- Potato は起動済み（--cwd ~/Projects/concafe-techo）。
  依頼は PR #300 の store-search.dom.test.tsx:171 の flake
  （AssertionError: expected undefined to be 0.5。再実行で success）が
  競合か回帰かの未関与確認。
- 三役のフローへの組み込みは完了:
    ~/.claude/skills/Tomato/SKILL.md:21, 111
    ~/.claude/skills/Tomato/references/named-team.md（新規）
    ~/.claude/skills/Tomato/references/pitfalls.md（手癖1件）
    ~/.claude/skills/Tomato/references/handoff.md（着手可ラベルの誤りを訂正）
- CI runner は復旧済み（持ち主の指示で窓口が launchctl bootstrap を実行）。
  runner 2台稼働、173分 queue されていた run は流れた。
