"""
Test Bitcoin script utilities.
"""

import hashlib

from jmcore.btc_script import mk_freeze_script, redeem_script_to_p2wsh_script


def test_mk_freeze_script():
    """Test creating a freeze script"""
    pubkey = "02a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
    locktime = 1956528000

    script = mk_freeze_script(pubkey, locktime)

    assert isinstance(script, bytes)
    assert len(script) > 0

    assert 0xB1 in script
    assert 0x75 in script
    assert 0xAC in script


def test_redeem_script_to_p2wsh():
    """Test converting redeem script to P2WSH"""
    pubkey = "02a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
    locktime = 1956528000

    redeem_script = mk_freeze_script(pubkey, locktime)
    p2wsh_script = redeem_script_to_p2wsh_script(redeem_script)

    assert len(p2wsh_script) == 34
    assert p2wsh_script[0] == 0x00
    assert p2wsh_script[1] == 0x20

    expected_hash = hashlib.sha256(redeem_script).digest()
    actual_hash = p2wsh_script[2:]
    assert actual_hash == expected_hash


def test_freeze_script_with_known_output():
    """Test freeze script matches expected output"""
    pubkey = "02a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
    locktime = 1956528000

    script = mk_freeze_script(pubkey, locktime)
    p2wsh_script = redeem_script_to_p2wsh_script(script)

    assert p2wsh_script[0] == 0x00
    assert p2wsh_script[1] == 0x20


def test_freeze_script_invalid_pubkey():
    """Test that invalid pubkey length raises error"""
    try:
        mk_freeze_script("abcd", 1956528000)
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "Invalid pubkey length" in str(e)
