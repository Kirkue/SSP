#!/usr/bin/env python3
"""
Diagnostic and fix script for pigpio connection issues.
Run this script on your Raspberry Pi to diagnose and fix pigpio connection problems.
"""

import subprocess
import sys
import time
import os

def check_pigpio_daemon():
    """Check if pigpio daemon is running."""
    try:
        result = subprocess.run(['pgrep', 'pigpiod'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ pigpio daemon is running")
            return True
        else:
            print("❌ pigpio daemon is not running")
            return False
    except Exception as e:
        print(f"Error checking pigpio daemon: {e}")
        return False

def start_pigpio_daemon():
    """Start the pigpio daemon."""
    try:
        print("Starting pigpio daemon...")
        result = subprocess.run(['sudo', 'pigpiod'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ pigpio daemon started successfully")
            time.sleep(2)  # Give it time to initialize
            return True
        else:
            print(f"❌ Failed to start pigpio daemon: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error starting pigpio daemon: {e}")
        return False

def test_pigpio_connection():
    """Test pigpio connection."""
    try:
        import pigpio
        print("Testing pigpio connection...")
        pi = pigpio.pi()
        if pi.connected:
            print("✅ pigpio connection successful")
            pi.stop()
            return True
        else:
            print("❌ pigpio connection failed")
            return False
    except ImportError:
        print("❌ pigpio library not installed")
        return False
    except Exception as e:
        print(f"❌ pigpio connection error: {e}")
        return False

def check_gpio_permissions():
    """Check GPIO permissions."""
    try:
        # Check if user is in gpio group
        result = subprocess.run(['groups'], capture_output=True, text=True)
        if 'gpio' in result.stdout:
            print("✅ User is in gpio group")
            return True
        else:
            print("❌ User is not in gpio group")
            return False
    except Exception as e:
        print(f"Error checking GPIO permissions: {e}")
        return False

def add_user_to_gpio_group():
    """Add user to gpio group."""
    try:
        print("Adding user to gpio group...")
        result = subprocess.run(['sudo', 'usermod', '-a', '-G', 'gpio', os.getenv('USER')], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ User added to gpio group")
            print("⚠️  You may need to log out and log back in for changes to take effect")
            return True
        else:
            print(f"❌ Failed to add user to gpio group: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error adding user to gpio group: {e}")
        return False

def install_pigpio():
    """Install pigpio library."""
    try:
        print("Installing pigpio library...")
        result = subprocess.run(['sudo', 'apt-get', 'update'], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Failed to update package list: {result.stderr}")
            return False
            
        result = subprocess.run(['sudo', 'apt-get', 'install', '-y', 'pigpio', 'python3-pigpio'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ pigpio library installed successfully")
            return True
        else:
            print(f"❌ Failed to install pigpio: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error installing pigpio: {e}")
        return False

def enable_pigpio_service():
    """Enable pigpio service to start automatically."""
    try:
        print("Enabling pigpio service...")
        result = subprocess.run(['sudo', 'systemctl', 'enable', 'pigpiod'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ pigpio service enabled")
            return True
        else:
            print(f"❌ Failed to enable pigpio service: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error enabling pigpio service: {e}")
        return False

def main():
    """Main diagnostic and fix function."""
    print("Pigpio Connection Diagnostic and Fix Tool")
    print("=" * 50)
    
    # Check if pigpio daemon is running
    if not check_pigpio_daemon():
        print("\n🔧 Attempting to start pigpio daemon...")
        if not start_pigpio_daemon():
            print("\n❌ Could not start pigpio daemon automatically")
            print("Try running: sudo pigpiod")
            return False
    
    # Test pigpio connection
    if not test_pigpio_connection():
        print("\n🔧 Testing pigpio connection failed")
        
        # Check if pigpio library is installed
        try:
            import pigpio
            print("✅ pigpio library is available")
        except ImportError:
            print("❌ pigpio library not found, installing...")
            if not install_pigpio():
                print("❌ Failed to install pigpio library")
                return False
        
        # Check GPIO permissions
        if not check_gpio_permissions():
            print("\n🔧 Adding user to gpio group...")
            if not add_user_to_gpio_group():
                print("❌ Failed to add user to gpio group")
                return False
        
        # Try starting daemon again
        if not start_pigpio_daemon():
            print("❌ Still cannot start pigpio daemon")
            return False
        
        # Test connection again
        if not test_pigpio_connection():
            print("❌ pigpio connection still failing")
            return False
    
    # Enable service for auto-start
    enable_pigpio_service()
    
    print("\n" + "=" * 50)
    print("✅ pigpio connection should now be working!")
    print("\nIf you're still having issues:")
    print("1. Try rebooting your Raspberry Pi")
    print("2. Check if another process is using the GPIO pins")
    print("3. Verify your hardware connections")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
