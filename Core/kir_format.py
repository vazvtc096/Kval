from __future__ import annotations

import hashlib
import struct

from .constants import MAGIC_AST, MAGIC_RPN

KIR_CONTAINER_MAGIC = b"KIR"
KIR_CONTAINER_VERSION = 1
_HEADER_STRUCT = struct.Struct(">3sBBI32s")
_SUPPORTED_PAYLOAD_MAGICS = {MAGIC_AST, MAGIC_RPN}


def encode_kir_payload(payload_magic: int, payload: bytes) -> bytes:
    if payload_magic not in _SUPPORTED_PAYLOAD_MAGICS:
        raise ValueError(f"unsupported payload magic: {payload_magic}")
    digest = hashlib.sha256(payload).digest()
    header = _HEADER_STRUCT.pack(
        KIR_CONTAINER_MAGIC,
        KIR_CONTAINER_VERSION,
        payload_magic,
        len(payload),
        digest,
    )
    return header + payload


def decode_kir_payload(raw: bytes) -> tuple[int, bytes]:
    if len(raw) < _HEADER_STRUCT.size:
        raise ValueError("invalid .kir container: header too short")
    magic, version, payload_magic, payload_len, digest = _HEADER_STRUCT.unpack_from(raw, 0)
    if magic != KIR_CONTAINER_MAGIC:
        raise ValueError("invalid .kir container: bad magic")
    if version != KIR_CONTAINER_VERSION:
        raise ValueError(f"unsupported .kir container version: {version}")
    if payload_magic not in _SUPPORTED_PAYLOAD_MAGICS:
        raise ValueError(f"invalid .kir container payload type: {payload_magic}")
    payload = raw[_HEADER_STRUCT.size :]
    if len(payload) != payload_len:
        raise ValueError("invalid .kir container: payload length mismatch")
    if hashlib.sha256(payload).digest() != digest:
        raise ValueError("invalid .kir container: checksum mismatch")
    return payload_magic, payload


def is_kir_container(raw: bytes) -> bool:
    return len(raw) >= 3 and raw[:3] == KIR_CONTAINER_MAGIC
