"""
Configuration Module for SSP (Self-Service Printer) Application

Loads application configuration from a .env file and provides type-safe access
to configuration values. Application will exit if .env file is not found.

Configuration Categories:
- Page Pricing: Prices for black & white and color printing
- Printer Settings: Printer name, timeout, and retry attempts
- System Settings: Color mode, copy limits
- Analysis Settings: PDF analysis DPI, color tolerance, thresholds
"""

import os
import sys
from typing import Union


class Config:
    """
    Configuration class that loads and provides access to settings from .env file.
    
    All configuration values are loaded from environment variables and are
    accessible via properties with automatic type conversion.
    """
    
    def __init__(self, env_file: str = ".env"):
        """
        Initialize configuration from .env file.
        
        Args:
            env_file: Path to .env configuration file (default: ".env")
            
        Raises:
            SystemExit: If .env file is not found
        """
        self.env_file = env_file
        self._check_env_file_exists()
        self._load_env_file()
    
    def _check_env_file_exists(self):
        """
        Verify that .env file exists.
        
        Exits application with error message if file is not found.
        """
        if not os.path.exists(self.env_file):
            print(f"❌ Configuration file '{self.env_file}' not found!")
            print("Please create a .env file with your configuration settings.")
            sys.exit(1)
    
    def _load_env_file(self):
        """
        Load environment variables from .env file.
        
        Parses key=value pairs and sets them as environment variables.
        Supports comments (lines starting with #) and quoted values.
        """
        with open(self.env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Set environment variable
                    os.environ[key] = value
    
    def get(self, key: str, value_type: type = str) -> Union[str, int, float, bool]:
        """
        Get configuration value with type conversion.
        
        Args:
            key: Configuration key
            value_type: Type to convert the value to (str, int, float, bool)
        
        Returns:
            Configuration value converted to specified type
        
        Raises:
            KeyError: If the configuration key is not found
            ValueError: If the value cannot be converted to the specified type
        """
        if key not in os.environ:
            raise KeyError(f"Configuration key '{key}' not found in .env file")
        
        value = os.environ[key]
        
        try:
            if value_type == bool:
                return value.lower() in ('true', '1', 'yes', 'on')
            elif value_type == int:
                return int(value)
            elif value_type == float:
                return float(value)
            else:
                return str(value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Could not convert '{key}={value}' to {value_type.__name__}: {e}")
    
    # Page pricing configuration
    
    @property
    def black_and_white_price(self) -> float:
        """Get price per page for black and white printing."""
        return self.get('BLACK_AND_WHITE_PRICE', float)
    
    @property
    def color_price(self) -> float:
        """Get price per page for color printing."""
        return self.get('COLOR_PRICE', float)
    
    # Printer configuration
    
    @property
    def printer_name(self) -> str:
        """Get CUPS printer name."""
        return self.get('PRINTER_NAME', str)
    
    @property
    def printer_timeout(self) -> int:
        """Get printer command timeout in seconds."""
        return self.get('PRINTER_TIMEOUT', int)
    
    @property
    def printer_retry_attempts(self) -> int:
        """Get number of printer retry attempts."""
        return self.get('PRINTER_RETRY_ATTEMPTS', int)
    
    # System settings
    
    @property
    def default_color_mode(self) -> str:
        """Get default color mode ('Color' or 'Black and White')."""
        return self.get('DEFAULT_COLOR_MODE', str)
    
    @property
    def max_copies(self) -> int:
        """Get maximum number of copies allowed per print job."""
        return self.get('MAX_COPIES', int)
    
    @property
    def min_copies(self) -> int:
        """Get minimum number of copies required per print job."""
        return self.get('MIN_COPIES', int)
    
    # Analysis settings
    
    @property
    def pdf_analysis_dpi(self) -> int:
        """Get DPI used for PDF analysis (higher = more accurate but slower)."""
        return self.get('PDF_ANALYSIS_DPI', int)
    
    @property
    def color_tolerance(self) -> int:
        """Get color tolerance for distinguishing color vs grayscale (0-255)."""
        return self.get('COLOR_TOLERANCE', int)
    
    @property
    def pixel_count_threshold(self) -> int:
        """Get minimum pixel count threshold for color detection."""
        return self.get('PIXEL_COUNT_THRESHOLD', int)
    
    # Display settings
    
    @property
    def force_fullscreen(self) -> bool:
        """Force fullscreen mode regardless of screen size."""
        return self.get('FORCE_FULLSCREEN', bool)
    
    @property
    def window_width(self) -> int:
        """Get preferred window width for windowed mode."""
        return self.get('WINDOW_WIDTH', int)
    
    @property
    def window_height(self) -> int:
        """Get preferred window height for windowed mode."""
        return self.get('WINDOW_HEIGHT', int)
    
    @property
    def fullscreen_threshold_width(self) -> int:
        """Get screen width threshold below which fullscreen is used."""
        return self.get('FULLSCREEN_THRESHOLD_WIDTH', int)
    
    @property
    def fullscreen_threshold_height(self) -> int:
        """Get screen height threshold below which fullscreen is used."""
        return self.get('FULLSCREEN_THRESHOLD_HEIGHT', int)


# Global configuration instance
config = Config()


def get_config() -> Config:
    """
    Get the global configuration instance.
    
    Returns:
        Global Config object with loaded settings
    """
    return config
