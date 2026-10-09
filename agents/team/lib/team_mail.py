"""Durable local role mail, independent of terminal sockets and permission modes.

Messages and receipts are immutable files published atomically. This is a local
coordination record, not an authorization, review verdict or external notification.
"""
import datetime as dt
import json
from pathlib import Path
import re
import uuid
from zoneinfo import ZoneInfo
from state_io import publish_json

ROLES = ('owner', 'tomato', 'banana', 'potato')
JST = ZoneInfo('Asia/Tokyo')
ID = re.compile(r'^[0-9a-f]{32}$')


def default_root():
    return Path.home() / '.local/share/named-team/communication'


def now():
    return dt.datetime.now(JST).isoformat(timespec='microseconds')


def publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    publish_json(path, value)


def message(root, identifier):
    if not ID.fullmatch(identifier):
        raise ValueError('message ID が不正')
    return json.loads((root / 'messages' / (identifier + '.json')).read_text(encoding='utf-8'))


def send(root, sender, recipients, subject, body, reply_to=None, source=None, relay=None, needs_reply=None):
    recipients = list(dict.fromkeys(recipients))
    if sender not in ROLES or not recipients or any(role not in ROLES for role in recipients):
        raise ValueError('宛先・送信元は owner / tomato / banana / potato')
    if not subject.strip() or not body.strip():
        raise ValueError('件名と本文は空にしない')
    if sender == 'potato' and (relay != 'banana' or not source):
        raise ValueError('Potato の返答は Banana が原文ファイルから中継する')
    if reply_to:
        original = message(root, reply_to)
        if sender not in original['to'] or recipients != [original['from']]:
            raise ValueError('返答は元の宛先から元の送信者へ返す')
    item = {'id': uuid.uuid4().hex, 'at': now(), 'from': sender, 'to': recipients,
            'subject': subject, 'body': body, 'reply_to': reply_to,
            'source': source, 'relay': relay,
            'needs_reply': needs_reply if needs_reply is not None else reply_to is None}
    publish(root / 'messages' / (item['id'] + '.json'), item)
    return item


def acknowledge(root, role, identifier, note):
    item = message(root, identifier)
    if role == 'potato' or role not in item['to']:
        raise ValueError('受領確認は実際の宛先が行う。Potato は返答原文を Banana に返す')
    if not note.strip():
        raise ValueError('受領確認に次の担当・行動、または保留理由を書く')
    path = root / 'receipts' / (identifier + '-' + role + '.json')
    receipt = {'id': identifier, 'role': role, 'at': now(), 'note': note}
    try:
        publish(path, receipt)
    except FileExistsError:
        return json.loads(path.read_text(encoding='utf-8'))
    return receipt


def records(root, role=None, unread=False, day=None):
    if day is not None and dt.date.fromisoformat(day).isoformat() != day:
        raise ValueError('日付は YYYY-MM-DD')
    items = [message(root, path.stem) for path in sorted((root / 'messages').glob('*.json'))]
    replies = {}
    for item in items:
        if item.get('reply_to'):
            replies.setdefault(item['reply_to'], []).append(item)
    rows = []
    for item in items:
        receipts = []
        for recipient in item['to']:
            receipt_path = root / 'receipts' / (item['id'] + '-' + recipient + '.json')
            if receipt_path.exists():
                receipts.append(json.loads(receipt_path.read_text(encoding='utf-8')))
        item['receipts'] = receipts
        if role and role not in item['to']:
            continue
        # A reply is also proof of receipt, including a relayed Potato reply.
        item['replies'] = [reply['id'] for reply in replies.get(item['id'], [])]
        reply_roles = {reply['from'] for reply in replies.get(item['id'], [])}
        receipt_roles = {receipt['role'] for receipt in receipts}
        item['pending_roles'] = [recipient for recipient in item['to'] if recipient not in reply_roles
                                 and (item.get('needs_reply', True) or recipient not in receipt_roles)]
        if unread and role not in item['pending_roles']:
            continue
        if day and not (item['at'][:10] == day or any(receipt['at'][:10] == day for receipt in receipts)
                        or any(reply['at'][:10] == day for reply in replies.get(item['id'], []))):
            continue
        rows.append(item)
    return sorted(rows, key=lambda item: (item['at'], item['id']))


def relay_potato(root, path, recipients, subject, reply_to=None):
    path = path.expanduser().resolve()
    text = path.read_text(encoding='utf-8')
    # Keep the returned communication block verbatim; it cannot grant a PASS.
    match = re.search(r'^## 連絡[ \t]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if match and match.group(1).strip():
        body = match.group(1)
    elif re.search(r'^Issue: .+\n', text, re.M) and re.search(
            r'^Verdict: (PASS|CHANGES_REQUIRED|BLOCKED)\s*$', text, re.M):
        # Acceptance has a strict existing output format. Relay the complete
        # original report rather than adding a communication field to its gate.
        body = text
    else:
        raise ValueError('Potato の原文に空でない「## 連絡」または受入レポートが必要')
    return send(root, 'potato', recipients, subject, body, reply_to,
                source=str(path), relay='banana')
