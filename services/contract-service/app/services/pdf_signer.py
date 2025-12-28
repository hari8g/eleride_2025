"""
Service to add signatures to PDF contracts.
"""
from pathlib import Path
from typing import Optional
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import letter
from PIL import Image
import io


class PDFSigner:
    """Handles adding signatures to PDF contracts."""
    
    def add_signature(self, pdf_path: Path, signature_bytes: bytes, output_filename: Optional[str] = None) -> Optional[Path]:
        """
        Add signature to an existing PDF contract.
        
        Args:
            pdf_path: Path to the original PDF contract
            signature_bytes: Signature image as bytes (PNG)
            output_filename: Optional output filename (without extension)
        
        Returns:
            Path to signed PDF, or None if signing fails
        """
        try:
            from PyPDF2 import PdfReader, PdfWriter
            import tempfile
            
            # Load signature image
            signature_img = Image.open(io.BytesIO(signature_bytes))
            
            # Resize signature to reasonable size (max 200px width)
            max_width = 200
            if signature_img.width > max_width:
                ratio = max_width / signature_img.width
                new_height = int(signature_img.height * ratio)
                signature_img = signature_img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert signature to bytes for reportlab
            signature_buffer = io.BytesIO()
            signature_img.save(signature_buffer, format="PNG")
            signature_buffer.seek(0)
            
            # Create a PDF overlay with the signature
            # Signature position: bottom right of the page
            overlay_buffer = io.BytesIO()
            c = canvas.Canvas(overlay_buffer, pagesize=letter)
            width, height = letter
            
            # Position signature at bottom right (adjust coordinates as needed)
            # X: right side with some margin, Y: bottom with margin for signature line
            sig_x = width - signature_img.width - 100  # 100px from right
            sig_y = 100  # 100px from bottom
            
            c.drawImage(ImageReader(signature_buffer), sig_x, sig_y, 
                       width=signature_img.width, height=signature_img.height)
            c.save()
            
            # Read the original PDF
            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            
            # Read overlay PDF
            overlay_buffer.seek(0)
            overlay_reader = PdfReader(overlay_buffer)
            
            # Merge overlay with original PDF
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                if page_num < len(overlay_reader.pages):
                    overlay_page = overlay_reader.pages[0]
                    page.merge_page(overlay_page)
                writer.add_page(page)
            
            # Generate output filename
            if not output_filename:
                base_name = pdf_path.stem
                output_filename = f"{base_name}_signed"
            
            output_path = pdf_path.parent / f"{output_filename}.pdf"
            
            # Write signed PDF
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            
            return output_path
            
        except Exception as e:
            print(f"Error adding signature to PDF: {str(e)}")
            return None

