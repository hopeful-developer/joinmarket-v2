"""
Test fidelity bond value calculations.
"""

from jmcore.bond_calc import calculate_timelocked_fidelity_bond_value


def test_bond_value_basic() -> None:
    """Test basic bond value calculation"""
    utxo_value = 100_000_000
    confirmation_time = 1577836800
    locktime = 1893456000
    current_time = 1704067200

    value = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime, current_time
    )

    assert value > 0
    assert isinstance(value, int)


def test_bond_value_zero_locktime() -> None:
    """Test bond value with zero effective locktime"""
    utxo_value = 100_000_000
    current_time = 1704067200
    confirmation_time = current_time
    locktime = current_time

    value = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime, current_time
    )

    assert value == 0


def test_bond_value_expired() -> None:
    """Test bond value after locktime expires"""
    utxo_value = 100_000_000
    confirmation_time = 1577836800
    locktime = 1893456000
    current_time = 1956528001

    value = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime, current_time
    )

    assert value >= 0


def test_bond_value_increases_with_amount() -> None:
    """Test that bond value increases with UTXO amount"""
    confirmation_time = 1577836800
    locktime = 1893456000
    current_time = 1704067200

    value1 = calculate_timelocked_fidelity_bond_value(
        50_000_000, confirmation_time, locktime, current_time
    )
    value2 = calculate_timelocked_fidelity_bond_value(
        100_000_000, confirmation_time, locktime, current_time
    )

    assert value2 > value1


def test_bond_value_increases_with_locktime() -> None:
    """Test that bond value increases with longer locktime"""
    utxo_value = 100_000_000
    confirmation_time = 1577836800
    current_time = 1704067200

    locktime1 = 1893456000
    locktime2 = 1956528000

    value1 = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime1, current_time
    )
    value2 = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime2, current_time
    )

    assert value2 > value1


def test_bond_value_with_custom_params() -> None:
    """Test bond value with custom interest rate and exponent"""
    utxo_value = 100_000_000
    confirmation_time = 1577836800
    locktime = 1893456000
    current_time = 1704067200

    value_default = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime, current_time
    )

    value_higher_interest = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime, current_time, interest_rate=0.03
    )

    value_higher_exponent = calculate_timelocked_fidelity_bond_value(
        utxo_value, confirmation_time, locktime, current_time, exponent=2.0
    )

    assert value_higher_interest > value_default
    assert value_higher_exponent > value_default
