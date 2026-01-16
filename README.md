-# Self-Service Printing Kiosk (SSP) System

A robust, touch-optimized Python application designed to power standalone self-service printing kiosks. This system manages the entire printing workflow—from USB file detection and PDF previewing to coin-based payment processing and driverless printing via CUPS.

## 📝 Description

The SSP System is a purpose-built solution for automated document printing services. Built with **Python** and **PyQt5**, it provides a user-friendly graphical interface that guides customers through the printing process. The system integrates directly with hardware components for payment (coin hoppers) and utilizes **CUPS (Common Unix Printing System)** to ensure reliable, driverless compatibility with a wide range of printer hardware.

Key capabilities include dynamic cost calculation, real-time ink coverage analysis for resource management, and automated SMS alerts for hardware status monitoring.

## ✨ Key Features

* **Touch-First Interface**: A complete GUI built with PyQt5 featuring intuitive screens for file browsing, print settings, and payments.
* **Plug-and-Play USB Printing**: Automatically detects USB devices and allows users to browse and preview PDF files directly on the kiosk screen.
* **Driverless Printing (CUPS)**: Leverages the CUPS printing system to handle jobs natively, eliminating the need for vendor-specific drivers and ensuring PDF compatibility.
* **Intelligent Payment Handling**:
    * Calculates costs based on page count, copies, and color mode.
    * Integrates with coin hoppers to accept payment and dispense change via a custom algorithm.
* **Ink Analysis Engine**: Analyzes PDF content before printing to estimate ink usage and ensure accurate resource tracking.
* **Admin Dashboard**: A secured backend for owners to view transaction logs, monitor database records, and manage system configuration.
* **Smart Alerts**: Sends SMS notifications to administrators for critical events like paper jams, low paper, or printer errors.

## 🛠️ Technical Stack

* **Language**: Python 3
* **GUI Framework**: PyQt5
* **Printing Backend**: CUPS (Common Unix Printing System) via `subprocess`
* **PDF Processing**: PyMuPDF (`fitz`)
* **Database**: SQLite
* **Configuration**: Environment-based (`.env`)

## ⚙️ System Requirements

### Hardware
* Computer/Raspberry Pi (Linux recommended)
* Touchscreen Display
* Printer (CUPS-compatible)
* Coin Acceptor & Hopper (Serial/Pulse integration)

### Software
* **OS**: Linux (Ubuntu/Debian/Raspbian recommended for full CUPS support)
* **Python**: 3.x
* **Dependencies**: CUPS (Daemon must be running)

## 🚀 Installation & Setup

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/yourusername/SSP.git](https://github.com/yourusername/SSP.git)
    cd SSP
    ```

2.  **Install System Dependencies (Linux)**
    Ensure CUPS and Python development headers are installed:
    ```bash
    sudo apt-get update
    sudo apt-get install cups libcups2-dev python3-dev
    ```

3.  **Install Python Dependencies**
    ```bash
    pip install PyQt5 PyMuPDF python-dotenv
    ```

4.  **Configure the Environment**
    Create a `.env` file in the root directory (or rename `env.example` if provided) and configure your hardware settings:
    ```env
    PRINTER_NAME=Your_Printer_Name_In_CUPS
    BLACK_AND_WHITE_PRICE=5.00
    COLOR_PRICE=10.00
    # Add other configuration keys as needed
    ```

5.  **Run the Application**
    ```bash
    python main_app.py
    ```
