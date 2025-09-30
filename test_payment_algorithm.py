# test_payment_algorithm.py

"""
Test script to demonstrate the payment algorithm functionality.
This script shows how the payment algorithm works with different scenarios.
"""

import sys
import os

# Add the SSP directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'SSP'))

# Mock the config module to avoid .env file dependency
class MockConfig:
    def get(self, key, value_type=str):
        # Return default values for testing
        defaults = {
            'BLACK_AND_WHITE_PRICE': 2.0,
            'COLOR_PRICE': 5.0,
            'PRINTER_NAME': 'Test Printer',
            'PRINTER_TIMEOUT': 30,
            'PRINTER_RETRY_ATTEMPTS': 3,
            'DEFAULT_COLOR_MODE': 'Color',
            'MAX_COPIES': 10,
            'MIN_COPIES': 1,
            'PDF_ANALYSIS_DPI': 150,
            'COLOR_TOLERANCE': 10,
            'PIXEL_COUNT_THRESHOLD': 1000
        }
        return defaults.get(key, '')

# Mock the config module
sys.modules['config'] = type('MockConfigModule', (), {'config': MockConfig()})()

from database.db_manager import DatabaseManager
from managers.payment_algorithm_manager import PaymentAlgorithmManager


def test_payment_algorithm():
    """Test the payment algorithm with different scenarios."""
    
    print("=== Payment Algorithm Test ===\n")
    
    # Initialize database and algorithm manager
    db_manager = DatabaseManager()
    payment_algorithm = PaymentAlgorithmManager(db_manager)
    
    # Test scenarios
    test_cases = [
        {"total_cost": 15.0, "description": "Small amount - should have many options"},
        {"total_cost": 25.0, "description": "Medium amount - typical transaction"},
        {"total_cost": 50.0, "description": "Large amount - may have limited change options"},
        {"total_cost": 100.0, "description": "Very large amount - likely exact payment only"}
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        total_cost = test_case["total_cost"]
        description = test_case["description"]
        
        print(f"Test Case {i}: {description}")
        print(f"Total Cost: ₱{total_cost:.2f}")
        print("-" * 50)
        
        # Get current coin inventory
        coin_inventory = payment_algorithm.get_coin_inventory()
        print(f"Current Coin Inventory: ₱1={coin_inventory.get(1, 0)}, ₱5={coin_inventory.get(5, 0)}")
        
        # Get payment status message
        status_message = payment_algorithm.get_payment_status_message(total_cost)
        print(f"Status: {status_message}")
        
        # Get payment suggestions
        suggestions = payment_algorithm.find_optimal_payment_amounts(total_cost)
        print(f"Payment Suggestions ({len(suggestions)} found):")
        
        for j, suggestion in enumerate(suggestions[:3], 1):  # Show top 3
            priority = suggestion['priority']
            amount = suggestion['amount']
            change = suggestion['change']
            reason = suggestion['reason']
            
            print(f"  {j}. ₱{amount:.2f} ({priority} priority)")
            if change == 0:
                print(f"     Exact payment - {reason}")
            else:
                print(f"     ₱{change:.2f} change - {reason}")
        
        print()
        
        # Test validation for a specific payment amount
        test_payment = total_cost + 10  # Add ₱10 to test change
        is_valid, message, payment_info = payment_algorithm.validate_payment(total_cost, test_payment)
        print(f"Validation Test: ₱{test_payment:.2f} payment")
        print(f"Result: {'✓ Valid' if is_valid else '✗ Invalid'}")
        print(f"Message: {message}")
        print()
    
    # Test change calculation
    print("=== Change Calculation Test ===")
    change_amounts = [0, 1, 5, 10, 15, 23, 50]
    
    for change in change_amounts:
        breakdown = payment_algorithm.calculate_change_breakdown(change)
        coins_1 = breakdown.get(1, 0)
        coins_5 = breakdown.get(5, 0)
        print(f"₱{change:.2f} change = {coins_5}x ₱5 + {coins_1}x ₱1")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_payment_algorithm()
