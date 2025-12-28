"""
PDF conversion service using LibreOffice headless.
Falls back gracefully if LibreOffice is not available.
"""
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple


class PDFConverter:
    """Handles DOCX to PDF conversion."""
    
    def __init__(self, libreoffice_path: str = "/usr/bin/libreoffice"):
        self.libreoffice_path = libreoffice_path
        self._available = self._check_libreoffice()
    
    def _check_libreoffice(self) -> bool:
        """Check if LibreOffice is available."""
        try:
            result = subprocess.run(
                [self.libreoffice_path, "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def is_available(self) -> bool:
        """Check if PDF conversion is available."""
        return self._available
    
    def convert_docx_to_pdf(
        self, 
        docx_path: Path, 
        output_dir: Optional[Path] = None
    ) -> Tuple[bool, Optional[Path]]:
        """
        Convert DOCX to PDF using LibreOffice headless.
        
        Args:
            docx_path: Path to DOCX file
            output_dir: Optional output directory (defaults to same as DOCX)
        
        Returns:
            Tuple of (success, pdf_path)
        """
        if not self._available:
            return False, None
        
        if not docx_path.exists():
            return False, None
        
        # Use same directory as DOCX if output_dir not specified
        if output_dir is None:
            output_dir = docx_path.parent
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # LibreOffice headless conversion
            # --headless: run without GUI
            # --convert-to pdf: convert to PDF
            # --outdir: output directory
            result = subprocess.run(
                [
                    self.libreoffice_path,
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(output_dir),
                    str(docx_path)
                ],
                capture_output=True,
                timeout=30,
                check=True
            )
            
            # LibreOffice creates PDF with same name as DOCX
            pdf_path = output_dir / f"{docx_path.stem}.pdf"
            
            if pdf_path.exists():
                return True, pdf_path
            else:
                return False, None
                
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            return False, None

