# Paper Jam Error Handling Fixes

## Problem
Paper jam errors were not showing the admin override button and PIN dialog like other printing errors. Users were stuck on the paper jam error screen without a way to dismiss it.

## Root Cause
The paper jam error handling was not integrated with the admin override system that was implemented for general printing errors. Paper jam errors were treated as regular print failures without the admin override functionality.

## Fixes Applied

### 1. Enhanced Error Detection in Thank You Screen
```python
def show_printing_error(self, message: str):
    # Check if this is a paper jam error
    is_paper_jam = "paper jam" in message.lower() or "jam" in message.lower()
    
    # Set the error type for admin override handling
    self.error_type = "paper_jam" if is_paper_jam else "printing_error"
    
    # Emit signal to show admin override button for all printing errors
    self.admin_override_requested.emit()
```

**New features:**
- ✅ Paper jam error detection
- ✅ Error type classification
- ✅ Admin override signal emission

### 2. Added Specific Paper Jam Error Method
```python
def show_paper_jam_error(self, message: str):
    """Updates the state to show a paper jam error specifically."""
    self.current_state = "error"
    self.error_type = "paper_jam"
    
    self.status_updated.emit(
        "PAPER JAM DETECTED",
        f"Paper jam detected. Please clear the paper jam and try again.\nContact an administrator if needed."
    )
    
    # Emit signal to show admin override button
    self.admin_override_requested.emit()
```

**New features:**
- ✅ Dedicated paper jam error screen
- ✅ Clear error messaging
- ✅ Admin override integration

### 3. Enhanced Main App Error Handling
```python
def on_print_failed(self, error_message):
    # Check if this is a paper jam error
    if "paper jam" in error_message.lower() or "jam" in error_message.lower():
        print("Detected paper jam error - showing paper jam error screen")
        self.thank_you_screen.show_paper_jam_error(error_message)
    else:
        print("Detected general printing error - showing printing error screen")
        self.thank_you_screen.show_printing_error(error_message)
```

**New features:**
- ✅ Paper jam error detection in main app
- ✅ Routing to appropriate error handler
- ✅ Consistent error handling flow

### 4. Added Controller Method for Paper Jam Errors
```python
def show_paper_jam_error(self, message: str):
    """Public method to show paper jam error specifically."""
    self.model.show_paper_jam_error(message)
```

**New features:**
- ✅ Public interface for paper jam errors
- ✅ Consistent with other error methods
- ✅ Proper separation of concerns

## Error Handling Flow

### 📋 **Paper Jam Error Flow**
1. **Paper jam detected** by printer manager via CUPS
2. **SMS notification sent** to admin ("Printer jam")
3. **print_failed signal emitted** with paper jam message
4. **main_app.on_print_failed()** detects paper jam
5. **thank_you_screen.show_paper_jam_error()** called
6. **Error screen shows** "PAPER JAM DETECTED" message
7. **admin_override_requested signal** emitted
8. **Admin override button** appears
9. **User clicks** admin override button
10. **PIN dialog** appears
11. **Admin enters PIN** (1234)
12. **PIN validated** successfully
13. **handle_admin_override()** called
14. **Screen shows** "ADMIN OVERRIDE" message
15. **2-second timer** starts
16. **Redirects to idle** screen

### 📋 **General Printing Error Flow**
1. **Printing error detected** by printer manager
2. **SMS notification sent** to admin ("Printing error: [details]")
3. **print_failed signal emitted** with error message
4. **main_app.on_print_failed()** detects general error
5. **thank_you_screen.show_printing_error()** called
6. **Error screen shows** "PRINTING FAILED" message
7. **admin_override_requested signal** emitted
8. **Admin override button** appears
9. **Same admin override flow** as paper jam errors

## Key Features

### 🔧 **Consistent Error Handling**
- ✅ Both paper jam and general errors show admin override button
- ✅ Both require PIN authentication to dismiss
- ✅ Both send SMS notifications
- ✅ Both prevent auto-redirect

### 📱 **User Experience**
- ✅ Clear error messages for different error types
- ✅ Consistent admin override flow
- ✅ Secure PIN authentication
- ✅ No confusion about error resolution

### 🛡️ **Admin Control**
- ✅ Admin override required for all errors
- ✅ PIN protection prevents unauthorized dismissal
- ✅ SMS notifications for immediate awareness
- ✅ Clear error classification

## Testing

### Test Script: `test_paper_jam_error_handling.py`
Run this script to verify the paper jam error handling:

```bash
python3 test_paper_jam_error_handling.py
```

**This script tests:**
1. ✅ Paper jam error detection logic
2. ✅ Error message processing
3. ✅ Admin override flow
4. ✅ Paper jam vs general error differences
5. ✅ SMS notification integration
6. ✅ User experience flow

## Files Modified

1. **`screens/thank_you/model.py`**
   - Enhanced `show_printing_error()` with paper jam detection
   - Added `show_paper_jam_error()` method
   - Added error type classification
   - Added admin override signal emission

2. **`screens/thank_you/controller.py`**
   - Added `show_paper_jam_error()` method
   - Consistent interface for error handling

3. **`main_app.py`**
   - Enhanced `on_print_failed()` with paper jam detection
   - Added routing to appropriate error handler
   - Added error type classification

4. **`test_paper_jam_error_handling.py`** (New)
   - Comprehensive paper jam error testing
   - Error detection logic testing
   - Admin override flow testing
   - User experience testing

## Verification

After applying these fixes, the system should:

1. **Detect paper jam errors correctly** via CUPS status
2. **Show appropriate error messages** for paper jams
3. **Display admin override button** for paper jam errors
4. **Require PIN authentication** to dismiss paper jam errors
5. **Send SMS notifications** for paper jam detection
6. **Behave consistently** with other error types
7. **Prevent auto-redirect** for paper jam errors
8. **Allow admin override** to return to idle screen

## Error Message Examples

### Paper Jam Error:
- **Title**: "PAPER JAM DETECTED"
- **Message**: "Paper jam detected. Please clear the paper jam and try again. Contact an administrator if needed."
- **Admin Override**: ✅ Required
- **SMS**: "Printer jam"

### General Printing Error:
- **Title**: "PRINTING FAILED"
- **Message**: "Error: [specific error message]. Please contact an administrator."
- **Admin Override**: ✅ Required
- **SMS**: "Printing error: [error details]"

The paper jam error handling now works exactly the same as other printing errors, with proper admin override functionality and SMS notifications.
