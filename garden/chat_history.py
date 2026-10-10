"""Bounded, atomic local cache for the public LAN room, separate from the pond save."""
import json
import logging
from pathlib import Path
import tempfile
import uuid

MAX_HISTORY = 200
MAX_TEXT = 1000


def valid_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def valid_name(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 48
            and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def valid_text(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_TEXT
            and not any(0xD800 <= ord(c) <= 0xDFFF for c in value))


def valid_record(value):
    return (isinstance(value, dict) and valid_uuid(value.get('sender'))
            and valid_uuid(value.get('id')) and valid_name(value.get('name'))
            and valid_text(value.get('text')) and type(value.get('sent_at')) is int
            and 0 < value['sent_at'] < 4102444800000)


def message_record(value):
    return {key: value[key] for key in ('sender', 'id', 'name', 'text', 'sent_at')}


def record_order(value):
    return value['sent_at'], value['id']


class ChatArchive:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.identity = str(uuid.uuid4())
        self.records = []
        self.error = ''
        self.writable = True
        if self.path is None:
            return
        try:
            if not self.path.exists():
                return
            if self.path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('聊天缓存过大')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or data.get('v') != 1
                    or not valid_uuid(data.get('identity')) or not isinstance(data.get('messages'), list)
                    or len(data['messages']) > MAX_HISTORY or not all(map(valid_record, data['messages']))):
                raise ValueError('聊天缓存格式无效')
            self.identity = data['identity']
            unique = {record['id']: message_record(record) for record in data['messages']}
            self.records = sorted(unique.values(), key=record_order)
        except (OSError, ValueError, RecursionError) as exc:
            self.writable = False  # Preserve a damaged cache for recovery.
            self._error(exc)

    def _error(self, exc):
        self.error = str(exc)
        logging.warning('Could not read/write chat history %s: %s', self.path, exc)

    def save(self, records):
        if self.path is None:
            return True
        if not self.writable:
            return False
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(dict(v=1, identity=self.identity, messages=records[-MAX_HISTORY:]),
                          stream, ensure_ascii=False)
            temporary.replace(self.path)
            self.error = ''
            return True
        except (OSError, ValueError) as exc:
            self._error(exc)
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    self._error(exc)
