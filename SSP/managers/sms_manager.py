# sms_manager.py
import serial
import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal

class SMSManager(QObject):
    """
    Manages SMS notifications for the printing system.
    """
    sms_sent = pyqtSignal(str)  # Signal emitted when SMS is sent successfully
    sms_failed = pyqtSignal(str)  # Signal emitted when SMS fails
    
    def __init__(self, phone_number="09762912863", serial_port="/dev/serial0", baudrate=9600):
        super().__init__()
        self.phone_number = phone_number
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.ser = None
        self.is_initialized = False
        
    def initialize_modem(self):
        """Initialize the GSM modem connection."""
        try:
            print("Initializing GSM modem...")
            self.ser = serial.Serial(self.serial_port, baudrate=self.baudrate, timeout=1)
            
            # Give modem time to boot up (like your working code)
            time.sleep(5)
            
            # Basic AT check (like your working code)
            self.ser.write(b'AT\r')
            time.sleep(1)
            response = self.ser.read(100).decode(errors="ignore").strip()
            print("AT Response: " + response)
            
            if "OK" in response:
                print("GSM modem initialized successfully")
                self.is_initialized = True
                return True
            else:
                print("GSM modem initialization failed")
                self.is_initialized = False
                return False
                
        except serial.SerialException as e:
            print(f"Serial error during initialization: {e}")
            self.is_initialized = False
            return False
        except Exception as e:
            print(f"Error initializing GSM modem: {e}")
            self.is_initialized = False
            return False
    
    def send_sms(self, message):
        """
        Sends an SMS message to the configured phone number.
        """
        if not self.is_initialized:
            print("GSM modem not initialized. Attempting to initialize...")
            if not self.initialize_modem():
                error_msg = "Failed to initialize GSM modem"
                print(error_msg)
                self.sms_failed.emit(error_msg)
                return False
        
        print(f"Sending SMS: {message}")
        
        try:
            # Set SMS to text mode (like your working code)
            self.ser.write(b'AT+CMGF=1\r')
            time.sleep(1)
            response = self.ser.read(100).decode(errors="ignore").strip()
            print("CMGF Response: " + response)
            
            # Set the recipient's phone number (like your working code)
            cmd = f'AT+CMGS="{self.phone_number}"\r'
            self.ser.write(cmd.encode())
            time.sleep(1)
            response = self.ser.read(100).decode(errors="ignore").strip()
            print("CMGS Prompt: " + response)
            
            # Send the message followed immediately by Ctrl+Z (like your working code)
            self.ser.write(message.encode() + bytes([26]))
            self.ser.flush()
            print("Message sent, waiting for confirmation...")
            
            # Wait for the final response (like your working code)
            time.sleep(15)
            response = self.ser.read(500).decode(errors="ignore").strip()
            print("Final Response: " + response)
            
            if "+CMGS:" in response and "OK" in response:
                success_msg = f"SMS sent successfully to {self.phone_number}"
                print("✅ Message sent successfully!")
                self.sms_sent.emit(success_msg)
                return True
            else:
                error_msg = f"Failed to send SMS. Response: {response}"
                print("❌ Failed to send message.")
                self.sms_failed.emit(error_msg)
                return False
                
        except serial.SerialException as e:
            error_msg = f"Serial error: {e}"
            print(error_msg)
            self.sms_failed.emit(error_msg)
            return False
        except Exception as e:
            error_msg = f"Error sending SMS: {e}"
            print(error_msg)
            self.sms_failed.emit(error_msg)
            return False
    
    def send_low_paper_alert(self):
        """Send low paper alert SMS."""
        message = "Low paper, please refill."
        return self.send_sms(message)
    
    def send_paper_jam_alert(self):
        """Send paper jam alert SMS."""
        message = "Printer jam"
        return self.send_sms(message)
    
    def send_printing_error_alert(self, error_message):
        """Send printing error alert SMS."""
        message = f"Printing error: {error_message}"
        return self.send_sms(message)
    
    def send_custom_alert(self, message):
        """Send custom alert SMS."""
        return self.send_sms(message)
    
    def close(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("SMS serial port closed.")
            self.is_initialized = False
    
    def send_sms_and_close(self, message):
        """
        Sends an SMS message and closes the connection (like your working code).
        This method opens a new connection, sends the SMS, and closes it.
        """
        try:
            print("Initializing modem...")
            # Give modem time to boot up
            time.sleep(5)
            
            # Open serial connection
            ser = serial.Serial(self.serial_port, baudrate=self.baudrate, timeout=1)
            
            # Basic AT check
            ser.write(b'AT\r')
            time.sleep(1)
            print("AT Response: " + ser.read(100).decode(errors="ignore").strip())
            
            # Set SMS to text mode
            ser.write(b'AT+CMGF=1\r')
            time.sleep(1)
            print("CMGF Response: " + ser.read(100).decode(errors="ignore").strip())
            
            # Set the recipient's phone number
            cmd = f'AT+CMGS="{self.phone_number}"\r'
            ser.write(cmd.encode())
            time.sleep(1)
            print("CMGS Prompt: " + ser.read(100).decode(errors="ignore").strip())
            
            # Send the message followed immediately by Ctrl+Z (0x1A)
            ser.write(message.encode() + bytes([26]))
            ser.flush()
            print("Message sent, waiting for confirmation...")
            
            # Wait for the final response
            time.sleep(15)
            response = ser.read(500).decode(errors="ignore").strip()
            print("Final Response: " + response)
            
            if "+CMGS:" in response and "OK" in response:
                print("✅ Message sent successfully!")
                return True
            else:
                print("❌ Failed to send message.")
                return False
                
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            return False
        except Exception as e:
            print(f"An error occurred: {e}")
            return False
        finally:
            # Close the serial port
            if 'ser' in locals() and ser.is_open:
                ser.close()
                print("Serial port closed.")

# Global SMS manager instance
sms_manager = None

def get_sms_manager():
    """Get the global SMS manager instance."""
    global sms_manager
    if sms_manager is None:
        sms_manager = SMSManager()
    return sms_manager

def initialize_sms():
    """Initialize the SMS system."""
    manager = get_sms_manager()
    return manager.initialize_modem()

def send_low_paper_sms():
    """Send low paper SMS alert."""
    manager = get_sms_manager()
    return manager.send_sms_and_close("Low paper, please refill.")

def send_paper_jam_sms():
    """Send paper jam SMS alert."""
    manager = get_sms_manager()
    return manager.send_sms_and_close("Printer jam")

def send_printing_error_sms(error_message):
    """Send printing error SMS alert."""
    manager = get_sms_manager()
    return manager.send_sms_and_close(f"Printing error: {error_message}")

def cleanup_sms():
    """Clean up SMS resources."""
    global sms_manager
    if sms_manager:
        sms_manager.close()
        sms_manager = None
