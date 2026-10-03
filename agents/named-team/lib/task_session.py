"""One visible Orca terminal per request; preserve the result before cleanup."""
import json
import fcntl
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import queue
from role_contract import find_workspace, role_routing



def call(orca, *args):
    completed = subprocess.run([orca, *args, '--json'], text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    data = json.loads(completed.stdout)
    if data.get('ok') is not True:
        raise RuntimeError(completed.stdout.strip())
    return data['result']


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def launch_task(role, command, cwd, environment, orca, metadata=False, workspace=None, collector=None,
                run_dir=None, project_context=None):
    # Fail before starting a model if the intended visible workspace is unavailable.
    selector = workspace or 'id:' + find_workspace(role, call(orca, 'worktree', 'list'))['id']
    target = call(orca, 'worktree', 'show', '--worktree', selector)['worktree']
    selector = 'id:' + target['id']
    state_root = Path(os.environ.get('NAMED_TEAM_TASK_DIR', str(Path.home() / '.local/share/named-team/tasks')))
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if run_dir is None:
        run = Path(tempfile.mkdtemp(prefix=role + '-', dir=state_root))
    else:
        run = Path(run_dir)
        run.mkdir(mode=0o700)
    request = {'role': role, 'command': command, 'cwd': str(cwd),
                              'roleRouting': role_routing(role),
                              'environment': environment, 'worktreeId': target['id'],
                              'collector': collector or ('claude' if role == 'potato' else 'codex')}
    if project_context is not None:
        request['projectTask'] = project_context
    save(run / 'request.json', request)
    worker = ['exec', sys.executable, str(Path(__file__).resolve()), '--worker', str(run)]
    # exec replaces the terminal shell so exit is an observable PTY condition.
    # Project sessions share the basename "session" and can reuse one checkout.
    # Keep receipt recovery unique to this request, just like tempfile jobs.
    title = role.capitalize() + ' · ' + (run.parent.name if project_context is not None else run.name)
    try:
        terminal = call(orca, 'terminal', 'create', '--worktree', selector,
                        '--title', title, '--command', shlex.join(worker))['terminal']
    except RuntimeError as exc:
        # The renderer can adopt a created tab after the CLI response times out.
        # Never create or send again: recover only the same uniquely titled tab.
        print('タブ作成の応答は未確認。同じタブだけを照合します: ' + str(run), file=sys.stderr, flush=True)
        # Default 60s covers the late-adoption race; tests shorten it.
        wait = float(os.environ.get('NAMED_TEAM_TAB_WAIT_SECONDS') or 60)
        deadline = time.monotonic() + wait
        terminal = None
        try:
            while time.monotonic() < deadline:
                rows = call(orca, 'terminal', 'list', '--worktree', selector)['terminals']
                matches = [row for row in rows if row.get('title') == title]
                if len(matches) == 1:
                    terminal = matches[0]
                    break
                if len(matches) > 1:
                    break
                time.sleep(0.5)
        except (RuntimeError, OSError, ValueError, KeyError):
            save(run / 'launch-aborted.json', {'reason': 'terminal recovery unconfirmed'})
            raise
        if terminal is None:
            # An absent tab can still appear later when Orca restores the layout.
            # Revoke this request before returning; never make a second terminal.
            save(run / 'launch-aborted.json', {'reason': 'terminal creation unconfirmed'})
            raise RuntimeError('タブ作成を確認できない。再起動しない。結果の場所: '
                               + str(run) + '\n' + str(exc))
    handle = terminal['handle']
    if not terminal.get('tabId'):
        save(run / 'launch-aborted.json', {'reason': 'visible tab unconfirmed'})
        raise RuntimeError('見えるタブへの接続を確認できない。再起動せず保持: ' + handle + ' / ' + str(run))
    save(run / 'terminal.json', terminal)
    print(role.capitalize() + ': タブ ' + handle + ' / 結果 ' + str(run), file=sys.stderr, flush=True)
    try:
        deadline = time.monotonic() + 60
        while not (run / 'finished.json').is_file():
            try:
                observation = call(orca, 'terminal', 'read', '--terminal', handle, '--limit', '1')['terminal']
            except RuntimeError:
                if (run / 'finished.json').is_file():
                    break
                raise
            if observation.get('status') == 'exited':
                raise RuntimeError('タブは終了したが結果を保存できていない。タブを保持: ' + handle)
            if not (run / 'started.json').is_file() and time.monotonic() > deadline:
                raise RuntimeError('タスク開始を確認できない。再送せずタブを保持: ' + handle)
            time.sleep(0.5)
        finished = json.loads((run / 'finished.json').read_text())
        # Read the saved report before asking Orca to remove any terminal resources.
        result = (run / 'result.txt').read_text()
        error = (run / 'error.txt').read_text()
        actual = json.loads((run / 'metadata.json').read_text()) if metadata and not finished['returncode'] else None
        # finished is published only after the model exits. Keep the wrapper PTY
        # addressable until close --tab confirms stopping it and durable removal.
        call(orca, 'terminal', 'close', '--terminal', handle, '--tab')
        save(run / 'closed.json', {'handle': handle, 'tabId': terminal['tabId'], 'closed': True})
        if error:
            print(error, file=sys.stderr, end='')
        if not finished['returncode'] or collector == 'stdout':
            print(json.dumps(actual, ensure_ascii=False) if metadata else result, end='\n' if metadata else '')
        return finished['returncode']
    except (RuntimeError, OSError, ValueError, KeyError, KeyboardInterrupt) as exc:
        print('タスクの回収・終了は未確認: ' + str(exc) + '\n結果の場所: ' + str(run), file=sys.stderr)
        return 4


def review_result(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('successful Claude result metadata is missing')
    usage = value.get('modelUsage', {})
    if (value.get('type') != 'result' or value.get('is_error') is not False
            or not isinstance(value.get('session_id'), str) or not value['session_id']
            or not isinstance(usage, dict) or len(usage) != 1
            or next(iter(usage)) not in ('claude-opus-5-5', 'claude-opus-5-5[1m]')
            or not isinstance(next(iter(usage.values())), dict)
            or not isinstance(value.get('result'), str) or not value['result'].strip()):
        raise ValueError('successful single-model Opus 5.5 result metadata is missing')
    return value


def progress(event):
    """Render useful Claude activity, without echoing complete tool arguments."""
    if event.get('type') == 'system' and event.get('subtype') == 'init':
        return 'セッション開始: ' + str(event.get('session_id', '不明'))
    if event.get('type') == 'assistant':
        rows = []
        for block in event.get('message', {}).get('content', []):
            if block.get('type') == 'text':
                rows.append('[作業中・最終検証前] ' + block.get('text', ''))
            elif block.get('type') == 'tool_use':
                rows.append('実行中: ' + str(block.get('name', 'tool')))
        return '\n'.join(rows)
    if event.get('type') == 'user':
        return 'ツールの結果を受信'
    return ''


def lines_with_activity(child):
    lines = queue.Queue()
    def read():
        try:
            for line in child.stdout:
                lines.put(line)
        finally:
            lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    start = time.monotonic()
    while True:
        try:
            line = lines.get(timeout=10)
        except queue.Empty:
            print('応答を待っています / 経過 ' + str(int(time.monotonic() - start)) + ' 秒', flush=True)
            continue
        if line is None:
            return
        yield line


def worker(run):
    """A restored startup command must never replay a model or overwrite evidence."""
    with (run / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('同じタスクは既に実行中。モデルを再起動しません。', flush=True)
            return 4
        try:
            if any((run / name).exists() for name in
                   ('started.json', 'finished.json', 'closed.json', 'launch-aborted.json')):
                raise RuntimeError('実行済み・開始済み・中止済みの依頼を再実行しません')
            # Orca starts the command before terminal create returns its receipt.
            # Only the original runtime handle may start the model after receipt.
            handle = os.environ.get('ORCA_TERMINAL_HANDLE')
            if not handle:
                raise RuntimeError('Orca terminal handle がありません')
            deadline = time.monotonic() + float(os.environ.get('NAMED_TEAM_RECEIPT_WAIT_SECONDS') or 90)
            while not (run / 'terminal.json').is_file():
                if (run / 'launch-aborted.json').exists() or time.monotonic() >= deadline:
                    raise RuntimeError('タブ作成の確認がありません。遅延起動を止めます')
                time.sleep(0.1)
            terminal = json.loads((run / 'terminal.json').read_text())
            if terminal.get('handle') != handle or not terminal.get('tabId'):
                raise RuntimeError('復元された別タブではモデルを起動しません')
            if (run / 'launch-aborted.json').exists():
                raise RuntimeError('タブ作成は中止済みです')
            request = json.loads((run / 'request.json').read_text())
            # Keep an irreversible claim even after a crash. A dead PID is not
            # permission to retry an ambiguous model invocation.
            with (run / 'started.json').open('x') as started:
                json.dump({'pid': os.getpid(), 'handle': handle}, started)
                started.flush()
                os.fsync(started.fileno())
        except (RuntimeError, OSError, ValueError, KeyError) as exc:
            print('タスクを再送せず停止: ' + str(exc), flush=True)
            return 4
        rc = execute_worker(run, request)
        deadline = time.monotonic() + float(os.environ.get('NAMED_TEAM_CLEANUP_WAIT_SECONDS') or 30)
        while not (run / 'closed.json').exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        return rc


def execute_worker(run, request):
    command = request['command'][:]
    env = os.environ.copy()
    if request.get('projectTask') is not None:
        env = {key: value for key, value in env.items() if not key.startswith('GIT_')}
    env.update(request['environment'])
    role = request['role']
    collector = request.get('collector', 'claude' if role == 'potato' else 'codex')
    error = ''
    result = ''
    rc = 3
    print(role.capitalize() + ' のタスクを開始 / 対象: ' + request['cwd'], flush=True)
    if collector == 'claude':
        command[command.index('--output-format') + 1] = 'stream-json'
        command.insert(command.index('--'), '--verbose')
    elif collector == 'codex':
        index = command.index('--')
        command[index:index] = ['--output-last-message', str(run / 'result.txt')]
    final = None
    output = []
    child = None
    try:
        with (run / 'progress.log').open('w') as log:
            child = subprocess.Popen(command, cwd=request['cwd'], env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in lines_with_activity(child):
                log.write(line)
                log.flush()
                if collector == 'claude':
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError('unexpected event')
                        if event.get('type') == 'result':
                            final = event
                        else:
                            rendered = progress(event)
                            if rendered:
                                print(rendered, flush=True)
                    except (ValueError, TypeError):
                        print(line, end='', flush=True)
                else:
                    print(line, end='', flush=True)
                    if collector == 'stdout':
                        output.append(line)
            rc = child.wait()
        if collector == 'stdout':
            # Peach validates its own report/model/evidence before returning it.
            starts = [index for index, line in enumerate(output) if line.startswith('Issue: ')]
            result = ''.join(output[starts[-1]:]) if starts else ''
            if not rc and not result.strip():
                raise ValueError('final Peach report is missing')
        if rc:
            description = 'pipeline 終了' if collector == 'stdout' else '実行失敗'
            error = role.capitalize() + ': ' + description + ' rc=' + str(rc) + '。詳細: ' + str(run / 'progress.log') + '\n'
        elif collector == 'claude':
            final = review_result(final or {})
            save(run / 'metadata.json', final)
            result = final['result'] + '\n'
            print('実モデル検証済みの結果:\n' + result, end='', flush=True)
        elif collector == 'codex':
            result = (run / 'result.txt').read_text()
            if not result.strip():
                raise ValueError('final Codex report is empty')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        rc = 3
        error = role.capitalize() + ': BLOCKED — ' + str(exc) + '\n'
        # A collection failure can happen while the model is still running.
        # Do not publish finished (and authorize PTY cleanup) until it has exited.
        if child is not None and child.poll() is None:
            try:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            except OSError as cleanup:
                print(error + '子プロセスの終了は未確認: ' + str(cleanup), flush=True)
                return 4
    # The finished marker is written last and only after the child exited and reports persisted.
    (run / 'result.txt').write_text(result)
    (run / 'error.txt').write_text(error)
    print(error or '結果を保存しました: ' + str(run / 'result.txt'), flush=True)
    save(run / 'finished.json', {'returncode': rc})
    return rc


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--worker':
        raise SystemExit('Use a named-team task launcher.')
    raise SystemExit(worker(Path(sys.argv[2])))
