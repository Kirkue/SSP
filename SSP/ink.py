import cv2
import numpy as np
import argparse
from pdf2image import convert_from_path
import sys

# Analyzes a single image and returns its CMYK ink coverage percentages.
def analyze_ink_usage(image_data, ignore_white=True):
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

# Percentage of a new cartridge the print job will use.
def calculate_job_costs(avg_k, avg_c, avg_m, avg_y, total_pages, yield_black, yield_color, standard_coverage=5.0):
  
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

# This section handles the user's command line inputs (the PDF path and DPI).
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Estimate printer ink usage for a PDF document.")
    parser.add_argument("pdf_path", type=str, help="The path to the PDF document.")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for rendering PDF pages.") #150 is good, 200 is better but slower
    args = parser.parse_args()

# Open the PDF file and convert it into a list of images.
    try:
        pages = convert_from_path(args.pdf_path, dpi=args.dpi)
    except Exception as e:
        sys.exit(f"Error processing PDF: {e}")

    total_pages = len(pages)

    if total_pages == 0:
        sys.exit(0)
        
# Init ink vars
    total_c, total_m, total_y, total_k = 0, 0, 0, 0

    for page_image in pages:
        opencv_image = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)  # Convert the page to OpenCV format (BGR).

        c, m, y, k = analyze_ink_usage(opencv_image)

        total_c += c
        total_m += m
        total_y += y
        total_k += k

    avg_c = total_c / total_pages
    avg_m = total_m / total_pages
    avg_y = total_y / total_pages
    avg_k = total_k / total_pages
    
    # 6000-page ink cartridge basis.
    black_cost, color_cost = calculate_job_costs(
        avg_k, avg_c, avg_m, avg_y, total_pages, yield_black=17000, yield_color=17000
    )

    # Display the final calculated results to the user.
    print(f"C: {avg_c:.2f} %")
    print(f"M: {avg_m:.2f} %")
    print(f"Y: {avg_y:.2f} %")
    print(f"K: {avg_k:.2f} %")
    print(f"Black Cartridge Used %: {black_cost:.2f}")
    print(f"Color Cartridge Used %: {color_cost:.2f}")