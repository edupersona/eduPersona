#!/usr/bin/env python3
"""
Script to format HTML files with proper indentation and nesting.
"""

from bs4 import BeautifulSoup
import sys

def format_html_file(input_file, output_file=None):
    """
    Format an HTML file with proper indentation.

    Args:
        input_file: Path to input HTML file
        output_file: Path to output HTML file (optional, defaults to input_file)
    """
    if output_file is None:
        output_file = input_file

    # Read the HTML file
    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Format with proper indentation
    formatted_html = soup.prettify()

    # Write the formatted HTML
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(formatted_html)

    print(f"✓ Formatted HTML written to: {output_file}")
    print(f"  Original size: {len(html_content):,} bytes")
    print(f"  Formatted size: {len(formatted_html):,} bytes")

if __name__ == "__main__":
    input_file = "uva.html"
    output_file = "uva_formatted.html"

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]

    try:
        format_html_file(input_file, output_file)
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
