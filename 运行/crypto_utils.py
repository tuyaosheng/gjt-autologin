"""学生名单的简单混淆编码，仅用于防止直接用文本工具读出明文，不是安全加密。"""

import base64
import json

_KEY = b"gjt-login-helper-2026"


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encode_roster(roster: dict) -> str:
    raw = json.dumps(roster, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(_xor(raw, _KEY)).decode("ascii")


def decode_roster(encoded: str) -> dict:
    raw = _xor(base64.b64decode(encoded), _KEY)
    return json.loads(raw.decode("utf-8"))
