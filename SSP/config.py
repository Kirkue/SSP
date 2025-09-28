"""
Configuration loader for SSP (Self-Service Printer) application.
Loads configuration from .env file. Application will exit if .env file is not found.
"""

import os
import sys
from typing import Union, Optional


class Config:
    """Configuration class that loads settings from .env file."""
    
    def __init__(self, env_file: str = ".env"):
        """Initialize configuration from .env file."""
        self.env_file = env_file
        self._check_env_file_exists()
        self._load_env_file()
    
    def _check_env_file_exists(self):
        """Check if .env file exists and exit if not found."""
        if not os.path.exists(self.env_file):
            print(f"ERROR: Configuration file '{self.env_file}' not found!")
            print("Please create a .env file with your configuration settings.")
            print("You can copy .env.example to .env and modify the values as needed.")
            sys.exit(1)
    
    def _load_env_file(self):
        """Load environment variables from .env file."""
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
        """Get black and white page price."""
        return self.get('BLACK_AND_WHITE_PRICE', float)
    
    @property
    def color_price(self) -> float:
        """Get color page price."""
        return self.get('COLOR_PRICE', float)
    
    # Printer configuration
    @property
    def printer_name(self) -> str:
        """Get printer name."""
        return self.get('PRINTER_NAME', str)
    
    @property
    def printer_timeout(self) -> int:
        """Get printer timeout in seconds."""
        return self.get('PRINTER_TIMEOUT', int)
    
    @property
    def printer_retry_attempts(self) -> int:
        """Get number of printer retry attempts."""
        return self.get('PRINTER_RETRY_ATTEMPTS', int)
    
    # System settings
    @property
    def default_color_mode(self) -> str:
        """Get default color mode."""
        return self.get('DEFAULT_COLOR_MODE', str)
    
    @property
    def max_copies(self) -> int:
        """Get maximum number of copies."""
        return self.get('MAX_COPIES', int)
    
    @property
    def min_copies(self) -> int:
        """Get minimum number of copies."""
        return self.get('MIN_COPIES', int)
    
    # Analysis settings
    @property
    def pdf_analysis_dpi(self) -> int:
        """Get PDF analysis DPI."""
        return self.get('PDF_ANALYSIS_DPI', int)
    
    @property
    def color_tolerance(self) -> int:
        """Get color tolerance for analysis."""
        return self.get('COLOR_TOLERANCE', int)
    
    @property
    def pixel_count_threshold(self) -> int:
        """Get pixel count threshold for analysis."""
        return self.get('PIXEL_COUNT_THRESHOLD', int)


# Global configuration instance
config = Config()


def get_config() -> Config:
    """Get the global configuration instance."""
    return config
