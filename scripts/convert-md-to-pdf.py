#!/usr/bin/env python3
"""
Convert Markdown to PDF using markdown2 and weasyprint
"""

import sys
import os

def convert_md_to_pdf(md_file, pdf_file):
    """Convert markdown file to PDF."""
    try:
        # Try using weasyprint + markdown2
        import markdown2
        from weasyprint import HTML, CSS
        
        # Read markdown file
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Convert markdown to HTML
        html_content = markdown2.markdown(
            md_content,
            extras=['fenced-code-blocks', 'tables', 'header-ids', 'toc']
        )
        
        # Add CSS styling
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    max-width: 900px;
                    margin: 40px auto;
                    padding: 0 20px;
                    color: #333;
                }}
                h1 {{
                    color: #2c3e50;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #2980b9;
                    border-bottom: 2px solid #bdc3c7;
                    padding-bottom: 8px;
                    margin-top: 30px;
                }}
                h3 {{
                    color: #16a085;
                    margin-top: 25px;
                }}
                code {{
                    background-color: #f4f4f4;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                    font-size: 0.9em;
                }}
                pre {{
                    background-color: #f8f8f8;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    padding: 15px;
                    overflow-x: auto;
                }}
                pre code {{
                    background-color: transparent;
                    padding: 0;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 20px 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #3498db;
                    color: white;
                }}
                tr:nth-child(even) {{
                    background-color: #f2f2f2;
                }}
                blockquote {{
                    border-left: 4px solid #3498db;
                    padding-left: 20px;
                    margin-left: 0;
                    color: #555;
                }}
                a {{
                    color: #3498db;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                .page-break {{
                    page-break-after: always;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Convert HTML to PDF
        HTML(string=styled_html).write_pdf(pdf_file)
        print(f"✓ Successfully created PDF: {pdf_file}")
        return True
        
    except ImportError as e:
        print(f"✗ Missing required packages: {e}")
        print("\nTo convert Markdown to PDF, install:")
        print("  pip3 install markdown2 weasyprint")
        print("\nOr use pandoc:")
        print("  brew install pandoc basictex")
        print("  pandoc input.md -o output.pdf")
        return False
    
    except Exception as e:
        print(f"✗ Error converting to PDF: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 convert-md-to-pdf.py <input.md> <output.pdf>")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2]
    
    if not os.path.exists(md_file):
        print(f"✗ Error: File not found: {md_file}")
        sys.exit(1)
    
    success = convert_md_to_pdf(md_file, pdf_file)
    sys.exit(0 if success else 1)
