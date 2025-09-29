# managers/ink_analysis_manager.py

import cv2
import numpy as np
from pdf2image import convert_from_path
import os
import sys
from datetime import datetime

class InkAnalysisManager:
    """Manages ink usage analysis for PDF files and updates database accordingly."""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        
    def analyze_pdf_ink_usage(self, pdf_path, selected_pages=None, dpi=150):
        """
        Analyze ink usage for a PDF file.
        
        Args:
            pdf_path (str): Path to the PDF file
            selected_pages (list): List of page numbers to analyze (1-indexed)
            dpi (int): DPI for rendering PDF pages
            
        Returns:
            dict: Analysis results with CMYK percentages and usage
        """
        try:
            print(f"DEBUG: analyze_pdf_ink_usage called")
            print(f"DEBUG: PDF path: {pdf_path}")
            print(f"DEBUG: Selected pages: {selected_pages}")
            print(f"DEBUG: DPI: {dpi}")
            
            print(f"Analyzing ink usage for PDF: {pdf_path}")
            
            # Convert PDF to images
            print("DEBUG: Converting PDF to images...")
            pages = convert_from_path(pdf_path, dpi=dpi)
            total_pages = len(pages)
            print(f"DEBUG: Total pages: {total_pages}")
            
            if total_pages == 0:
                print("DEBUG: No pages found, returning empty result")
                return self._create_empty_result()
            
            # Filter to selected pages if specified
            if selected_pages:
                print(f"DEBUG: Filtering to selected pages: {selected_pages}")
                # Convert to 0-indexed and filter
                pages_to_analyze = [pages[i-1] for i in selected_pages if 1 <= i <= total_pages]
            else:
                print("DEBUG: Analyzing all pages")
                pages_to_analyze = pages
            
            print(f"DEBUG: Pages to analyze: {len(pages_to_analyze)}")
            
            if not pages_to_analyze:
                print("DEBUG: No pages to analyze, returning empty result")
                return self._create_empty_result()
            
            # Analyze each page
            total_c, total_m, total_y, total_k = 0, 0, 0, 0
            analyzed_pages = 0
            
            for page_image in pages_to_analyze:
                print(f"DEBUG: Analyzing page {analyzed_pages + 1}")
                # Convert to OpenCV format (BGR)
                opencv_image = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)
                
                # Analyze ink usage for this page
                c, m, y, k = self._analyze_ink_usage(opencv_image)
                
                total_c += c
                total_m += m
                total_y += y
                total_k += k
                analyzed_pages += 1
                
                print(f"Page {analyzed_pages}: C:{c:.2f}% M:{m:.2f}% Y:{y:.2f}% K:{k:.2f}%")
            
            # Calculate averages
            avg_c = total_c / analyzed_pages
            avg_m = total_m / analyzed_pages
            avg_y = total_y / analyzed_pages
            avg_k = total_k / analyzed_pages
            
            print(f"DEBUG: Averages calculated: C:{avg_c:.2f}% M:{avg_m:.2f}% Y:{avg_y:.2f}% K:{avg_k:.2f}%")
            
            # Calculate job costs (percentage of cartridge used)
            black_cost, color_cost = self._calculate_job_costs(
                avg_k, avg_c, avg_m, avg_y, analyzed_pages
            )
            
            print(f"DEBUG: Job costs calculated: Black {black_cost:.2f}%, Color {color_cost:.2f}%")
            
            result = {
                'success': True,
                'total_pages': total_pages,
                'analyzed_pages': analyzed_pages,
                'selected_pages': selected_pages,
                'averages': {
                    'cyan': avg_c,
                    'magenta': avg_m,
                    'yellow': avg_y,
                    'black': avg_k
                },
                'totals': {
                    'cyan': total_c,
                    'magenta': total_m,
                    'yellow': total_y,
                    'black': total_k
                },
                'job_costs': {
                    'black_cartridge_percent': black_cost,
                    'color_cartridge_percent': color_cost
                },
                'timestamp': datetime.now()
            }
            
            print(f"Analysis complete: C:{avg_c:.2f}% M:{avg_m:.2f}% Y:{avg_y:.2f}% K:{avg_k:.2f}%")
            print(f"Job costs: Black {black_cost:.2f}%, Color {color_cost:.2f}%")
            
            return result
            
        except Exception as e:
            print(f"Error analyzing PDF ink usage: {e}")
            import traceback
            traceback.print_exc()
            return self._create_error_result(str(e))
    
    def _analyze_ink_usage(self, image_data, ignore_white=True):
        """
        Analyzes a single image and returns its CMYK ink coverage percentages.
        Based on the original ink.py analyze_ink_usage function.
        """
        if ignore_white:
            white_mask = np.all(image_data == [255, 255, 255], axis=-1)
            pixels_to_analyze = image_data[~white_mask]
            if pixels_to_analyze.size == 0:
                return (0, 0, 0, 0)
            num_pixels = pixels_to_analyze.shape[0]
            analysis_target = pixels_to_analyze
        else:
            height, width, _ = image_data.shape
            num_pixels = height * width
            analysis_target = image_data.reshape((num_pixels, 3))

        bgr_normalized = analysis_target.astype(np.float32) / 255.0
        b, g, r = bgr_normalized[:, 0], bgr_normalized[:, 1], bgr_normalized[:, 2]

        epsilon = 1e-9
        k = 1 - np.maximum.reduce([r, g, b])
        c = (1 - r - k) / (1 - k + epsilon)
        m = (1 - g - k) / (1 - k + epsilon)
        y = (1 - b - k) / (1 - k + epsilon)

        cyan_coverage = (np.sum(c) / num_pixels) * 100
        magenta_coverage = (np.sum(m) / num_pixels) * 100
        yellow_coverage = (np.sum(y) / num_pixels) * 100
        black_coverage = (np.sum(k) / num_pixels) * 100
        
        return (cyan_coverage, magenta_coverage, yellow_coverage, black_coverage)
    
    def _calculate_job_costs(self, avg_k, avg_c, avg_m, avg_y, total_pages, 
                           yield_black=17000, yield_color=17000, standard_coverage=5.0):
        """
        Calculate percentage of cartridge the print job will use.
        Based on the original ink.py calculate_job_costs function.
        """
        job_cost_black_percent = 0.0
        job_cost_color_percent = 0.0

        if yield_black and avg_k > 0:
            realistic_yield_black = (yield_black * standard_coverage) / avg_k
            if realistic_yield_black > 0:
                job_cost_black_percent = (1 / realistic_yield_black) * total_pages * 100

        avg_total_color = avg_c + avg_m + avg_y
        if yield_color and avg_total_color > 0:
            realistic_yield_color = (yield_color * standard_coverage) / avg_total_color
            if realistic_yield_color > 0:
                job_cost_color_percent = (1 / realistic_yield_color) * total_pages * 100
                
        return job_cost_black_percent, job_cost_color_percent
    
    def _create_empty_result(self):
        """Create an empty result for when no pages are analyzed."""
        return {
            'success': True,
            'total_pages': 0,
            'analyzed_pages': 0,
            'selected_pages': None,
            'averages': {'cyan': 0, 'magenta': 0, 'yellow': 0, 'black': 0},
            'totals': {'cyan': 0, 'magenta': 0, 'yellow': 0, 'black': 0},
            'job_costs': {'black_cartridge_percent': 0, 'color_cartridge_percent': 0},
            'timestamp': datetime.now()
        }
    
    def _create_error_result(self, error_message):
        """Create an error result."""
        return {
            'success': False,
            'error': error_message,
            'total_pages': 0,
            'analyzed_pages': 0,
            'selected_pages': None,
            'averages': {'cyan': 0, 'magenta': 0, 'yellow': 0, 'black': 0},
            'totals': {'cyan': 0, 'magenta': 0, 'yellow': 0, 'black': 0},
            'job_costs': {'black_cartridge_percent': 0, 'color_cartridge_percent': 0},
            'timestamp': datetime.now()
        }
    
    def update_database_after_print(self, analysis_result, copies=1):
        """
        Update the CMYK ink levels in the database after printing.
        
        Args:
            analysis_result (dict): Result from analyze_pdf_ink_usage
            copies (int): Number of copies printed
        """
        print(f"DEBUG: update_database_after_print called with copies={copies}")
        print(f"DEBUG: analysis_result={analysis_result}")
        
        if not self.db_manager:
            print("Warning: No database manager provided, cannot update ink levels")
            return False
        
        print(f"DEBUG: Using database manager: {self.db_manager}")
        print(f"DEBUG: Database manager type: {type(self.db_manager)}")
        
        if not analysis_result.get('success', False):
            print("Warning: Analysis failed, cannot update ink levels")
            return False
        
        try:
            # Get current ink levels
            print("DEBUG: Getting current ink levels from database...")
            current_levels = self.db_manager.get_cmyk_ink_levels()
            print(f"DEBUG: Current levels: {current_levels}")
            
            if not current_levels:
                print("Warning: No current ink levels found, cannot update")
                return False
            
            # Calculate ink usage for all copies
            job_costs = analysis_result['job_costs']
            copies_factor = copies
            
            print(f"DEBUG: Job costs: {job_costs}")
            print(f"DEBUG: Copies factor: {copies_factor}")
            
            # Calculate new levels (subtract usage from current levels)
            new_cyan = max(0, current_levels['cyan'] - (job_costs['color_cartridge_percent'] * copies_factor))
            new_magenta = max(0, current_levels['magenta'] - (job_costs['color_cartridge_percent'] * copies_factor))
            new_yellow = max(0, current_levels['yellow'] - (job_costs['color_cartridge_percent'] * copies_factor))
            new_black = max(0, current_levels['black'] - (job_costs['black_cartridge_percent'] * copies_factor))
            
            print(f"DEBUG: New levels calculated:")
            print(f"  Cyan: {current_levels['cyan']:.1f}% -> {new_cyan:.1f}%")
            print(f"  Magenta: {current_levels['magenta']:.1f}% -> {new_magenta:.1f}%")
            print(f"  Yellow: {current_levels['yellow']:.1f}% -> {new_yellow:.1f}%")
            print(f"  Black: {current_levels['black']:.1f}% -> {new_black:.1f}%")
            
            # Update database
            print("DEBUG: Updating database...")
            success = self.db_manager.update_cmyk_ink_levels(
                new_cyan, new_magenta, new_yellow, new_black
            )
            
            if success:
                print(f"Ink levels updated after printing:")
                print(f"  Cyan: {current_levels['cyan']:.1f}% -> {new_cyan:.1f}%")
                print(f"  Magenta: {current_levels['magenta']:.1f}% -> {new_magenta:.1f}%")
                print(f"  Yellow: {current_levels['yellow']:.1f}% -> {new_yellow:.1f}%")
                print(f"  Black: {current_levels['black']:.1f}% -> {new_black:.1f}%")
                return True
            else:
                print("Error: Failed to update ink levels in database")
                return False
                
        except Exception as e:
            print(f"Error updating ink levels after printing: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def analyze_and_update_after_print(self, pdf_path, selected_pages=None, copies=1, dpi=150):
        """
        Complete workflow: analyze PDF ink usage and update database.
        
        Args:
            pdf_path (str): Path to the PDF file
            selected_pages (list): List of page numbers to analyze
            copies (int): Number of copies printed
            dpi (int): DPI for rendering PDF pages
            
        Returns:
            dict: Analysis result with success status
        """
        print(f"Starting ink analysis and database update for {copies} copies")
        
        # Analyze the PDF
        analysis_result = self.analyze_pdf_ink_usage(pdf_path, selected_pages, dpi)
        
        if not analysis_result.get('success', False):
            return analysis_result
        
        # Update database
        update_success = self.update_database_after_print(analysis_result, copies)
        
        analysis_result['database_updated'] = update_success
        
        if update_success:
            print("Ink analysis and database update completed successfully")
        else:
            print("Ink analysis completed but database update failed")
        
        return analysis_result
