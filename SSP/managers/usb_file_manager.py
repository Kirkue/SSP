# usb_file_manager.py

import os
import shutil
import psutil
import tempfile
import platform
from datetime import datetime

class USBFileManager:
    """Handles USB detection and PDF file filtering"""
    
    def __init__(self):
        # FIX: Create a unique session ID and a session-specific temp directory
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_base_dir = os.path.join(tempfile.gettempdir(), "PrintingSystem")
        self.destination_dir = os.path.join(temp_base_dir, f"Session_{self.session_id}")
        
        os.makedirs(self.destination_dir, exist_ok=True)
        print(f"✅ Temp directory created for session {self.session_id}: {self.destination_dir}")

        self.supported_extensions = ['.pdf']
        self.last_known_drives = set()
        
        # Disk safety tracking
        self.current_usb_drive = None
        self.files_in_use = set()  # Track files currently being processed
        self.operation_in_progress = False
    
    def get_usb_drives(self):
        """Detect ONLY actual USB/removable drives - exclude all internal drives"""
        usb_drives = []
        system = platform.system()
        
        try:
            if system == "Windows":
                usb_drives = self._get_windows_usb_drives()
            elif system == "Linux":
                usb_drives = self._get_linux_usb_drives()
            else:
                print(f"OS not found: {system}")
                
        except Exception as e:
            print(f"Error detecting USB drives: {e}")
        
        print(f"Detected {len(usb_drives)} actual USB drives: {usb_drives}")
        return usb_drives
    
    def _get_windows_usb_drives(self):
        """Windows-specific USB drive detection"""
        usb_drives = []
        
        try:
            import win32file
            import win32api
            
            # Get all logical drives
            drives = win32api.GetLogicalDriveStrings()
            drives = drives.split('\000')[:-1]
            
            print(f"Checking {len(drives)} drives: {drives}")
            
            for drive in drives:
                try:
                    # Check if it's a removable drive
                    drive_type = win32file.GetDriveType(drive)
                    print(f"Drive {drive} type: {drive_type}")
                    
                    # DRIVE_REMOVABLE = 2 (floppy, USB, etc.)
                    if drive_type == 2:
                        # Additional check to ensure it's accessible
                        if os.path.exists(drive) and os.path.isdir(drive):
                            try:
                                # Try to access the drive to make sure it's ready
                                os.listdir(drive)
                                usb_drives.append(drive)
                                print(f"✅ Found removable USB drive: {drive}")
                            except (OSError, PermissionError) as e:
                                print(f"❌ USB drive {drive} not ready or accessible: {e}")
                    else:
                        print(f"Drive {drive} is not removable (type: {drive_type})")
                                
                except Exception as e:
                    print(f"Error checking drive {drive}: {e}")
                    continue
                    
        except ImportError:
            print("❌ pywin32 not available, using fallback method")
            # Fallback method using psutil
            usb_drives = self._get_usb_drives_fallback()
        except Exception as e:
            print(f"❌ Error in Windows USB detection: {e}")
            # Try fallback method
            usb_drives = self._get_usb_drives_fallback()
            
        return usb_drives
    
    def _get_linux_usb_drives(self):
        """Linux-specific USB drive detection"""
        usb_drives = []
        
        try:
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                # Check for typical USB mount points
                usb_mount_patterns = [
                    '/media/',
                    '/mnt/',
                    '/run/media/',
                    '/Volumes/'  # Sometimes used on Linux too
                ]
                
                is_usb_mount = any(partition.mountpoint.startswith(pattern) 
                                 for pattern in usb_mount_patterns)
                
                # Also check if explicitly marked as removable
                is_removable = 'removable' in partition.opts
                
                if is_usb_mount or is_removable:
                    try:
                        if os.path.exists(partition.mountpoint) and os.path.isdir(partition.mountpoint):
                            # Try to access to ensure it's ready
                            os.listdir(partition.mountpoint)
                            usb_drives.append(partition.mountpoint)
                            print(f"Found USB drive: {partition.mountpoint} ({partition.fstype})")
                    except (OSError, PermissionError):
                        print(f"USB drive {partition.mountpoint} not accessible")
                        
        except Exception as e:
            print(f"Error in Linux USB detection: {e}")
            
        return usb_drives
    
    def _get_macos_usb_drives(self):
        """macOS-specific USB drive detection"""
        usb_drives = []
        
        try:
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                # On macOS, USB drives are typically mounted under /Volumes/
                if partition.mountpoint.startswith('/Volumes/'):
                    # Skip the main system volume
                    if partition.mountpoint != '/Volumes/Macintosh HD':
                        try:
                            if os.path.exists(partition.mountpoint) and os.path.isdir(partition.mountpoint):
                                os.listdir(partition.mountpoint)
                                usb_drives.append(partition.mountpoint)
                                print(f"Found USB drive: {partition.mountpoint}")
                        except (OSError, PermissionError):
                            print(f"USB drive {partition.mountpoint} not accessible")
                            
        except Exception as e:
            print(f"Error in macOS USB detection: {e}")
            
        return usb_drives
    
    def _get_usb_drives_fallback(self):
        """Fallback method for USB detection"""
        usb_drives = []
        
        try:
            partitions = psutil.disk_partitions()
            print(f"Fallback method: Checking {len(partitions)} partitions")
            
            for partition in partitions:
                print(f"Partition: {partition.device} -> {partition.mountpoint} (opts: {partition.opts})")
                
                # Check for removable drives
                is_removable = 'removable' in partition.opts
                
                # Also check for common USB drive characteristics
                is_likely_usb = (
                    'removable' in partition.opts or
                    partition.fstype in ['FAT32', 'FAT', 'exFAT', 'NTFS'] and
                    partition.mountpoint and
                    len(partition.mountpoint) == 3 and  # Drive letter like "C:\"
                    partition.mountpoint.endswith('\\')
                )
                
                if is_removable or is_likely_usb:
                    try:
                        if os.path.exists(partition.mountpoint):
                            usage = psutil.disk_usage(partition.mountpoint)
                            if usage.total > 0:
                                # Additional size check - USB drives are typically smaller
                                total_gb = usage.total / (1024**3)
                                if total_gb < 2048:  # Less than 2TB
                                    usb_drives.append(partition.mountpoint)
                                    print(f"✅ Found removable drive: {partition.mountpoint} ({total_gb:.1f}GB)")
                                else:
                                    print(f"Drive {partition.mountpoint} too large ({total_gb:.1f}GB) - likely not USB")
                    except (PermissionError, OSError) as e:
                        print(f"❌ Cannot access {partition.mountpoint}: {e}")
                        continue
                        
        except Exception as e:
            print(f"❌ Error in fallback USB detection: {e}")
            
        return usb_drives
    
    def check_for_new_drives(self):
        """Check if new USB drives have been inserted"""
        current_drives = set(self.get_usb_drives())
        new_drives = current_drives - self.last_known_drives
        removed_drives = self.last_known_drives - current_drives
        
        self.last_known_drives = current_drives
        
        return list(new_drives), list(removed_drives)
    
    def scan_and_copy_pdf_files(self, source_dir):
        """Scan for and copy PDF files from USB drive with safety checks"""
        print(f"\n🔍 Starting scan_and_copy_pdf_files for {source_dir}")
        copied_files = []

        try:
            # Create a new session directory for each USB drive
            self._create_new_session()
            
            # Set current drive and mark operation as in progress
            self.set_current_drive(source_dir)
            self.set_operation_in_progress(True)
            
            print(f"📂 Scanning and copying PDF files from {source_dir} to {self.destination_dir}")
            
            for root, _, files in os.walk(source_dir):
                for filename in files:
                    if filename.lower().endswith('.pdf'):
                        source_path = os.path.join(root, filename)
                        dest_path = os.path.join(self.destination_dir, filename)
                        
                        try:
                            # Mark file as in use
                            self.mark_file_in_use(source_path)
                            
                            # Copy file and verify
                            shutil.copy2(source_path, dest_path)
                            if os.path.exists(dest_path):
                                file_size = os.path.getsize(dest_path)
                                print(f"✅ Copied {filename} ({file_size/1024:.1f} KB)")
                                
                                # Get PDF page count
                                try:
                                    import fitz  # PyMuPDF
                                    doc = fitz.open(dest_path)
                                    page_count = len(doc)
                                    doc.close()
                                except Exception:
                                    page_count = 1
                                    print(f"⚠️ Could not get page count for {filename}")
                                
                                copied_files.append({
                                    'filename': filename,
                                    'path': dest_path,
                                    'size': file_size,
                                    'pages': page_count,
                                    'type': '.pdf'
                                })
                            
                            # Mark file as complete
                            self.mark_file_complete(source_path)
                            
                        except Exception as e:
                            print(f"❌ Error copying {filename}: {str(e)}")
                            # Mark file as complete even if error occurred
                            self.mark_file_complete(source_path)
                            
            # Mark operation as complete
            self.set_operation_in_progress(False)
            
            # After all files are processed, automatically "eject" the USB drive
            if copied_files:
                print(f"✅ Successfully copied {len(copied_files)} PDF files:")
                for f in copied_files:
                    print(f"   📄 {f['filename']} ({f['size']/1024:.1f} KB, {f['pages']} pages)")
                
                # Automatically eject USB drive after successful copy
                self._auto_eject_usb_drive(source_dir)
            else:
                print("❌ No PDF files found to copy")
                
            return copied_files

        except Exception as e:
            print(f"❌ Error in scan_and_copy_pdf_files: {str(e)}")
            # Ensure operation is marked as complete even on error
            self.set_operation_in_progress(False)
            import traceback
            traceback.print_exc()
            return []
        
    def cleanup_temp_files(self):
        """Delete all files in the temporary directory after printing"""
        try:
            if os.path.exists(self.destination_dir):
                print(f"Cleaning up temporary files in {self.destination_dir}")
                
                # Remove all files in the directory
                for filename in os.listdir(self.destination_dir):
                    file_path = os.path.join(self.destination_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            print(f"Deleted: {filename}")
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                            print(f"Deleted directory: {filename}")
                    except Exception as e:
                        print(f"Error deleting {filename}: {e}")
                
                print("Temporary files cleanup completed")
            else:
                print("Temporary directory does not exist")
                
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def cleanup_all_temp_folders(self):
        """Clean up all old temporary folders from previous sessions"""
        try:
            # FIX: Use the correct base directory
            temp_base_dir = os.path.join(tempfile.gettempdir(), "PrintingSystem")
            if os.path.exists(temp_base_dir):
                print(f"Cleaning up old session folders in {temp_base_dir}")
            
                current_session_folder = f"Session_{self.session_id}"
            
                for folder_name in os.listdir(temp_base_dir):
                    if folder_name.startswith("Session_") and folder_name != current_session_folder:
                        folder_path = os.path.join(temp_base_dir, folder_name)
                        try:
                            if os.path.isdir(folder_path):
                                shutil.rmtree(folder_path)
                                print(f"Deleted old session folder: {folder_name}")
                        except Exception as e:
                            print(f"Error deleting old session folder {folder_name}: {e}")
                        
        except Exception as e:
            print(f"Error cleaning up old session folders: {e}")
    
    def get_temp_folder_info(self):
        """Get information about the current temporary folder"""
        try:
            if os.path.exists(self.destination_dir):
                files = os.listdir(self.destination_dir)
                total_size = 0
                for filename in files:
                    file_path = os.path.join(self.destination_dir, filename)
                    if os.path.isfile(file_path):
                        total_size += os.path.getsize(file_path)
                
                return {
                    'folder_path': self.destination_dir,
                    'file_count': len(files),
                    'total_size': total_size,
                    'session_id': self.session_id # This will now work
                }
            else:
                return None
        except Exception as e:
            print(f"Error getting temp folder info: {e}")
            return None
    
    def estimate_pdf_pages_fast(self, file_size):
        """Fast estimate of PDF pages based on file size"""
        # Rough estimate: 1 page per 50KB for PDF
        estimated_pages = max(1, file_size // 51200)
        return min(estimated_pages, 100)
    
    def estimate_pdf_pages(self, file_path):
        """Estimate number of pages in PDF based on file size"""
        try:
            file_size = os.path.getsize(file_path)
            return self.estimate_pdf_pages_fast(file_size)
        except:
            return 1

    def get_drive_info(self, drive_path):
        """Get detailed information about a drive"""
        try:
            usage = psutil.disk_usage(drive_path)
            total_gb = usage.total / (1024**3)
            free_gb = usage.free / (1024**3)
            used_gb = usage.used / (1024**3)
        
            # Try to get filesystem type
            fs_type = "Unknown"
            partitions = psutil.disk_partitions()
            for partition in partitions:
                if partition.mountpoint == drive_path:
                    fs_type = partition.fstype
                    break
        
            return {
                'path': drive_path,
                'total_gb': total_gb,
                'free_gb': free_gb,
                'used_gb': used_gb,
                'filesystem': fs_type,
                'is_removable': True  # All drives returned by get_usb_drives are removable
            }
        except Exception as e:
            print(f"Error getting drive info for {drive_path}: {e}")
            return None
    
    def set_current_drive(self, drive_path):
        """Set the current USB drive being used."""
        self.current_usb_drive = drive_path
        print(f"🔒 Set current USB drive: {drive_path}")
    
    def is_drive_safe_to_remove(self):
        """Check if the current USB drive is safe to remove."""
        if not self.current_usb_drive:
            return True, "No USB drive currently in use"
        
        if self.operation_in_progress:
            return False, "File operations are currently in progress"
        
        if self.files_in_use:
            return False, f"Files are currently being processed: {list(self.files_in_use)}"
        
        # Check if drive is still accessible
        try:
            if not os.path.exists(self.current_usb_drive):
                return False, "USB drive is no longer accessible"
            
            # Try to access the drive
            os.listdir(self.current_usb_drive)
            return True, "USB drive is safe to remove"
        except Exception as e:
            return False, f"USB drive access error: {e}"
    
    def mark_file_in_use(self, file_path):
        """Mark a file as being processed."""
        self.files_in_use.add(file_path)
        print(f"🔒 Marked file as in use: {file_path}")
    
    def mark_file_complete(self, file_path):
        """Mark a file as no longer being processed."""
        self.files_in_use.discard(file_path)
        print(f"🔓 Marked file as complete: {file_path}")
    
    def set_operation_in_progress(self, in_progress):
        """Set the operation in progress flag."""
        self.operation_in_progress = in_progress
        status = "started" if in_progress else "completed"
        print(f"🔄 File operation {status}")
    
    def get_safety_warning(self):
        """Get a safety warning message for the user."""
        if not self.current_usb_drive:
            return None
        
        is_safe, message = self.is_drive_safe_to_remove()
        if is_safe:
            return None
        
        return f"⚠️ DO NOT REMOVE USB DRIVE: {message}"
    
    def force_safe_eject(self):
        """Force safe ejection by clearing all operations."""
        print("🛑 Force safe ejection requested")
        self.files_in_use.clear()
        self.operation_in_progress = False
        self.current_usb_drive = None
        print("✅ USB drive marked as safe to remove")
    
    def _create_new_session(self):
        """Create a new session directory for each USB drive."""
        # Generate new session ID with current timestamp
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_base_dir = os.path.join(tempfile.gettempdir(), "PrintingSystem")
        self.destination_dir = os.path.join(temp_base_dir, f"Session_{self.session_id}")
        
        # Create the new directory
        os.makedirs(self.destination_dir, exist_ok=True)
        print(f"✅ New session directory created: {self.destination_dir}")
        
        # Clear any previous session data
        self.files_in_use.clear()
        self.operation_in_progress = False
        self.current_usb_drive = None
    
    def _auto_eject_usb_drive(self, usb_path):
        """Automatically eject USB drive after files are copied."""
        try:
            print(f"🔄 Auto-ejecting USB drive: {usb_path}")
            
            # Clear all safety tracking
            self.files_in_use.clear()
            self.operation_in_progress = False
            self.current_usb_drive = None
            
            # Try to unmount the drive (Linux/macOS)
            if platform.system() == "Linux":
                try:
                    import subprocess
                    # Find the device path for the mount point
                    result = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', usb_path], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        device = result.stdout.strip()
                        print(f"🔌 Unmounting device: {device}")
                        subprocess.run(['umount', usb_path], timeout=10)
                        print(f"✅ USB drive unmounted successfully")
                    else:
                        print("⚠️ Could not find device for unmounting")
                except Exception as e:
                    print(f"⚠️ Could not unmount USB drive: {e}")
            
            print("✅ USB drive is now safe to remove at any time")
            
        except Exception as e:
            print(f"⚠️ Error during auto-eject: {e}")
            # Still clear the safety tracking even if unmount fails
            self.files_in_use.clear()
            self.operation_in_progress = False
            self.current_usb_drive = None