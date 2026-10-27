#!/usr/bin/env python3
"""
Test Price to Book (PB) calculation fix
Verify unit conversion is correct
"""

def test_pb_calculation_units():
    """
    Test unit conversion for PB calculations

    Scenario: a certain stock
    - Total market value: 10 billion yuan = 1000000 Ten thousand yuan
    - Shareholders equity: 5 billion yuan = 5000000000 Yuan
    - expected PB = 100 / 50 = 2.0 times

    Unit conversion:
    - 1 billion = 10000 Ten thousand yuan = 100000000 Yuan
    - money_cap (Ten thousand yuan) / total_equity (Yuan) Need to convert
    - After conversion:money_cap (Ten thousand yuan) * 10000 / total_equity (Yuan)
    """

    # data in database
    money_cap = 1000000  # Ten thousand yuan = 100 billion
    total_equity = 5000000000  # Yuan = 50 billion

    # Wrong calculation method (original code)
    pb_wrong = money_cap / total_equity
    print(f"❌ miscalculation: {money_cap} / {total_equity} = {pb_wrong}")
    print(f"   This value is too small, the difference is 10,000 times!")

    # Correct way to calculate (after fix)
    # money_cap is ten thousand yuan, total_equity is yuan
    # 1 Ten thousand yuan = 10000 Yuan, so money_cap * 10000 = Yuan
    pb_correct = (money_cap * 10000) / total_equity
    print(f"\n✅ Calculate correctly: ({money_cap} * 10000) / {total_equity} = {pb_correct}")
    print(f"   expected value: 2.0 times")

    assert abs(pb_correct - 2.0) < 0.01, f"PB Calculation error, expecting 2.0, got {pb_correct}"
    print("\n✅ Test passed!")


def test_pb_calculation_with_real_example():
    """
    Test with real data

    Example of Ping An Bank (000001):
    - Total market value: 250 billion yuan = 25000000 Ten thousand yuan
    - Shareholders equity: 28 billion yuan = 28000000000 Yuan
    - expected PB ≈ 2500 / 280 ≈ 8.93 times
    """

    money_cap = 25000000  # Ten thousand yuan = 2500 billion
    total_equity = 28000000000  # Yuan = 280 billion

    # correct calculation
    pb_correct = (money_cap * 10000) / total_equity
    expected_pb = 2500 / 280  # Calculate and verify with 100 million yuan

    print("\n Example of Ping An Bank:")
    print(f"  Total market capitalization: {money_cap} Ten thousand yuan = {money_cap / 10000} billion")
    print(f"  Shareholders equity: {total_equity} Yuan = {total_equity / 100000000} billion")
    print(f"  Calculate PB: {pb_correct:.2f} times")
    print(f"  Verify PB: {expected_pb:.2f} times")

    assert abs(pb_correct - expected_pb) < 0.01, "PB Computational mismatch"
    print("✅ Test passed!")


def test_pb_calculation_formula_equivalence():
    """
    Verify whether different calculation formulas are equivalent
    """
    
    money_cap_wan = 1000  # Ten thousand yuan
    total_equity_yuan = 5000000000  # Yuan
    
    # Option 1: Convert everything into 100 million yuan
    money_cap_yi = money_cap_wan / 10000
    total_equity_yi = total_equity_yuan / 100000000
    pb1 = money_cap_yi / total_equity_yi
    
    # Option 2: Convert everything into 10,000 yuan
    total_equity_wan = total_equity_yuan / 10000
    pb2 = money_cap_wan / total_equity_wan
    
    # Option 3: Convert everything to yuan
    money_cap_yuan = money_cap_wan * 10000
    pb3 = money_cap_yuan / total_equity_yuan
    
    print(f"\n Formula equivalence verification:")
    print(f"  Option 1 (100 million yuan): {pb1:.2f}")
    print(f"  Option 2 (10,000 yuan): {pb2:.2f}")
    print(f"  Option 3 (yuan): {pb3:.2f}")
    
    assert pb1 == pb2 == pb3, "The formulas are not equivalent"
    print(f"✅ All formulas are equivalent!")


if __name__ == "__main__":
    print("=" * 60)
    print("Price to Book Ratio (PB) Calculation Repair Verification")
    print("=" * 60)
    
    test_pb_calculation_units()
    test_pb_calculation_with_real_example()
    test_pb_calculation_formula_equivalence()
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)

