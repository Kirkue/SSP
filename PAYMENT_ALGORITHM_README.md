# Payment Algorithm Documentation

## Overview

The Payment Algorithm is an intelligent system that manages payment processing for the Self-Service Printing Machine, considering the limited change available in coin hoppers. It ensures that users can only make payments that the system can fulfill with available change.

## Key Features

### 1. Coin Availability Checking
- **Real-time Inventory**: Checks current coin inventory from the database
- **Minimum Thresholds**: Maintains reserve coins for future transactions
- **Maximum Change Limit**: Prevents dispensing excessive change (₱50 limit)

### 2. Payment Suggestions
- **Optimal Amounts**: Suggests payment amounts based on available change
- **Priority System**: Ranks suggestions by priority (highest, high, medium, low)
- **Multiple Options**: Provides various payment scenarios

### 3. Change Calculation
- **Optimal Distribution**: Calculates the best coin combination for change
- **Denomination Support**: Supports ₱1 and ₱5 coins
- **Validation**: Ensures change can be dispensed before processing

## Algorithm Components

### PaymentAlgorithmManager Class

The main class that handles all payment algorithm logic:

```python
class PaymentAlgorithmManager:
    def __init__(self, db_manager: DatabaseManager):
        # Initialize with database connection
        
    def get_coin_inventory(self) -> Dict[int, int]:
        # Get current coin inventory from database
        
    def calculate_change_breakdown(self, change_amount: float) -> Dict[int, int]:
        # Calculate optimal coin distribution for change
        
    def can_dispense_change(self, change_amount: float) -> Tuple[bool, str, Dict[int, int]]:
        # Check if change can be dispensed
        
    def find_optimal_payment_amounts(self, total_cost: float) -> List[Dict]:
        # Find suggested payment amounts
        
    def validate_payment(self, total_cost: float, payment_amount: float) -> Tuple[bool, str, Dict]:
        # Validate if payment can be processed
```

### Configuration Parameters

```python
# Coin denominations available
COIN_DENOMINATIONS = [1, 5]  # ₱1 and ₱5 coins

# Minimum thresholds for coin availability
MIN_COIN_THRESHOLDS = {
    1: 10,   # Minimum ₱1 coins needed
    5: 5     # Minimum ₱5 coins needed
}

# Maximum change that can be dispensed
MAX_CHANGE_LIMIT = 50.0  # ₱50 maximum change
```

## Payment Flow Integration

### 1. Payment Screen Integration

The algorithm is integrated into the payment screen through:

- **PaymentModel**: Uses the algorithm to validate payments
- **PaymentController**: Handles suggestion dialog interactions
- **PaymentSuggestionDialog**: Shows payment options to users

### 2. User Interface

- **Payment Options Button**: Opens suggestion dialog
- **Suggestion Dialog**: Shows ranked payment options
- **Status Messages**: Displays payment capabilities

### 3. Database Integration

- **Real-time Updates**: Checks coin inventory before each transaction
- **Inventory Management**: Updates coin counts after dispensing
- **Transaction Logging**: Records payment details

## Usage Examples

### Basic Usage

```python
# Initialize the algorithm
db_manager = DatabaseManager()
payment_algorithm = PaymentAlgorithmManager(db_manager)

# Get payment suggestions for ₱25.00
suggestions = payment_algorithm.find_optimal_payment_amounts(25.0)

# Validate a payment
is_valid, message, info = payment_algorithm.validate_payment(25.0, 30.0)
```

### Payment Suggestions

The algorithm provides suggestions in priority order:

1. **Exact Payment** (highest priority)
2. **Small Change** (high priority) - ₱1-5 change
3. **Medium Change** (medium priority) - ₱6-20 change
4. **Bill Denominations** (medium priority) - Round up to bills

### Example Output

```
Total Cost: ₱25.00
Status: ✅ Change available up to ₱45.00

Payment Suggestions:
1. ₱25.00 (highest priority) - Exact payment
2. ₱26.00 (high priority) - ₱1.00 change
3. ₱30.00 (high priority) - ₱5.00 change
4. ₱50.00 (medium priority) - Pay with ₱50 bill
```

## Error Handling

### Insufficient Change Scenarios

1. **No Change Available**: Suggests exact payment only
2. **Limited Change**: Shows warnings and limited options
3. **Excessive Change**: Rejects payments over ₱50 change limit

### Database Errors

- **Connection Issues**: Falls back to safe defaults
- **Inventory Errors**: Logs errors and continues operation
- **Update Failures**: Retries with error logging

## Testing

Run the test script to see the algorithm in action:

```bash
python test_payment_algorithm.py
```

The test demonstrates:
- Different payment scenarios
- Coin inventory checking
- Payment suggestion generation
- Change calculation validation

## Benefits

### For Users
- **Clear Options**: See available payment methods
- **No Failed Transactions**: Only valid payments are accepted
- **Optimal Change**: Get the best coin combination

### For Operators
- **Reduced Maintenance**: Fewer failed transactions
- **Better Inventory Management**: Maintains coin reserves
- **Transaction Reliability**: Validates payments before processing

### For System
- **Improved Uptime**: Prevents hopper failures
- **Better User Experience**: Clear payment guidance
- **Data Integrity**: Accurate transaction records

## Future Enhancements

1. **Dynamic Thresholds**: Adjust minimums based on usage patterns
2. **Bill Support**: Add support for bill denominations
3. **Machine Learning**: Optimize suggestions based on historical data
4. **Multi-Currency**: Support for different currency systems
5. **Advanced Analytics**: Detailed payment pattern analysis
