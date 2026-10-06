"""A completed implementation receives a separate pinned review checkout."""
import hashlib
import json
from pathlib import Path
import re

from checkout_context import require_checkout as observe
from project_identity import is_concafe_path
import project_workspaces as workspaces
from review_routing import review_plan
from task_session import save


def prepare_review(orca, record, job):
    current = observe(record['targetPath'])
    if current['dirty'] or current['headSha'] != record['after']['headSha']:
        raise ValueError('Devin の成果が未コミットまたは回収後に変化。開発 checkout を保全して Banana に返す')
    if current['headSha'] == record['baseSha']:
        return {'nextRole': 'banana', 'status': 'no-implementation-commit',
                'headSha': current['headSha'], 'formalVerdict': 'not-issued'}
    review_job = job / 'review'
    review_job.mkdir(mode=0o700, exist_ok=True)
    path = review_job / 'record.json'
    if path.exists():
        review = json.loads(path.read_text())
        if review.get('stage') != 'created' or review.get('requestedBaseSha') != current['headSha']:
            raise ValueError('レビュー checkout の作成・固定版は未確認。再作成せず保持')
    else:
        review_key = hashlib.sha256((record['key'] + '\0review\0' + current['headSha']).encode()).hexdigest()
        slug = re.sub('[^a-z0-9-]+', '-', record['taskId'].lower()).strip('-')[:24] or 'task'
        review = dict(schemaVersion=1, taskId=record['taskId'], key=review_key, role='review',
                      source=current, commonDir=record['commonDir'], requestedBaseSha=current['headSha'],
                      name='review-' + slug + '-' + review_key[:8], targetPath=record['targetPath'],
                      coordinatorWorktreeId=record['worktreeId'], ownsWorktree=False, stage='accepted')
        save(path, review)  # Never repeat an ambiguous create after this fence.
        workspaces.create_checkout(orca, review, review_job)
    target = observe(review['targetPath'])
    if target['dirty'] or target['headSha'] != current['headSha']:
        raise ValueError('レビュー checkout が固定した成果と一致しない。両方を保持')
    request = review_job / 'request.md'
    request.write_text('Banana / Devin の成果を、実装に未関与の担当として確認する。\n'
                       '開発担当: banana / devin\n依頼 ID: ' + record['taskId']
                       + '\n固定 full HEAD SHA: ' + current['headSha']
                       + '\n開発 checkout: ' + record['targetPath']
                       + '\n結果: ' + str(job / 'session/result.txt')
                       + '\n現在のユーザー指示と対象契約を適用し、自己 PASS・手動 Ready / merge を行わない。\n'
                       + '\n元の依頼:\n' + (job / 'request.md').read_text(), encoding='utf-8')
    kind = 'final' if is_concafe_path(Path(review['targetPath'])) else 'technical'
    plan = review_plan(kind, review['targetPath'], prompt_file=request, sha=current['headSha'])
    handoff = dict(nextRole='review', status='pending-independent-review', headSha=current['headSha'],
                   worktreeId=review['worktreeId'], targetPath=review['targetPath'],
                   implementationWorktreeId=record['worktreeId'], reviewPlan=plan,
                   requestPath=str(request), formalVerdict='not-issued', startsSession=False)
    save(review_job / 'handoff.json', handoff)
    return handoff
