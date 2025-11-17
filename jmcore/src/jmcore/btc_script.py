"""
Bitcoin script utilities for fidelity bonds.
"""

from __future__ import annotations

import hashlib
import struct


def mk_freeze_script(pubkey_hex: str, locktime: int) -> bytes:
    """
    Create a timelocked script using OP_CHECKLOCKTIMEVERIFY.

    Script format: <locktime> OP_CHECKLOCKTIMEVERIFY OP_DROP <pubkey> OP_CHECKSIG

    Args:
        pubkey_hex: Compressed public key as hex string (33 bytes)
        locktime: Unix timestamp for the locktime

    Returns:
        Script as bytes
    """
    op_checklocktimeverify = 0xB1
    op_drop = 0x75
    op_checksig = 0xAC

    pubkey_bytes = bytes.fromhex(pubkey_hex)
    if len(pubkey_bytes) != 33:
        raise ValueError(f"Invalid pubkey length: {len(pubkey_bytes)}, expected 33")

    locktime_bytes = _encode_scriptnum(locktime)

    script = bytearray()
    script.extend(_push_data(locktime_bytes))
    script.append(op_checklocktimeverify)
    script.append(op_drop)
    script.extend(_push_data(pubkey_bytes))
    script.append(op_checksig)

    return bytes(script)


def redeem_script_to_p2wsh_script(redeem_script: bytes) -> bytes:
    """
    Convert a redeem script to P2WSH scriptPubKey.

    Args:
        redeem_script: The redeem script bytes

    Returns:
        P2WSH scriptPubKey (OP_0 <32-byte-hash>)
    """
    op_0 = 0x00

    script_hash = hashlib.sha256(redeem_script).digest()

    script = bytearray()
    script.append(op_0)
    script.extend(_push_data(script_hash))

    return bytes(script)


def _encode_scriptnum(n: int) -> bytes:
    """
    Encode an integer as a script number (variable length little-endian).

    Args:
        n: Integer to encode

    Returns:
        Encoded bytes
    """
    if n == 0:
        return b""

    neg = n < 0
    absvalue = abs(n)

    result = bytearray()
    while absvalue:
        result.append(absvalue & 0xFF)
        absvalue >>= 8

    if result[-1] & 0x80:
        result.append(0x80 if neg else 0x00)
    elif neg:
        result[-1] |= 0x80

    return bytes(result)


def _push_data(data: bytes) -> bytes:
    """
    Create a data push operation.

    Args:
        data: Data to push

    Returns:
        Push opcode + data
    """
    data_len = len(data)

    if data_len <= 75:
        return bytes([data_len]) + data
    elif data_len <= 0xFF:
        return bytes([0x4C, data_len]) + data
    elif data_len <= 0xFFFF:
        return bytes([0x4D]) + struct.pack("<H", data_len) + data
    else:
        return bytes([0x4E]) + struct.pack("<I", data_len) + data
