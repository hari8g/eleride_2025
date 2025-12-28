"""
FastAPI application for contract generation service.
"""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, status, APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import ContractRenderRequest, ContractRenderResponse
from app.services.contract_renderer import ContractRenderer
from app.services.pdf_converter import PDFConverter

# Create main app
app = FastAPI(
    title=settings.app_name,
    description="Contract generation microservice for rider agreements",
    version="1.0.0"
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
)

# Initialize services
renderer = ContractRenderer()
pdf_converter = PDFConverter(settings.libreoffice_path) if settings.enable_pdf else None


@app.get("/health")
async def health_check():
    """Liveness probe (for ALB health checks - direct target access)."""
    return {"status": "healthy", "service": settings.app_name}

@app.get("/contracts/health")
async def health_check_contracts():
    """Liveness probe (for CloudFront/ALB routing with /contracts prefix)."""
    return {"status": "healthy", "service": settings.app_name}


@app.get("/template/inspect")
async def inspect_template():
    """
    Scan template and return all placeholders found.
    Used by ops to verify template integrity.
    """
    try:
        placeholders = renderer.get_template_placeholders()
        return {
            "template_path": str(renderer.template_path),
            "template_exists": renderer.template_path.exists(),
            "placeholders_found": placeholders,
            "placeholder_count": len(placeholders)
        }
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inspecting template: {str(e)}"
        )


@app.post("/contracts/render", response_model=ContractRenderResponse)
async def render_contract(request: ContractRenderRequest):
    """
    Render contract from template with provided data.
    Returns generated DOCX file.
    """
    try:
        # Render contract
        filename, file_path = renderer.render_contract(request)
        
        # Get file size
        file_size = file_path.stat().st_size if file_path.exists() else None
        
        return ContractRenderResponse(
            success=True,
            filename=f"{filename}.docx",
            message="Contract generated successfully",
            file_size_bytes=file_size
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rendering contract: {str(e)}"
        )


@app.get("/contracts/download/{filename}")
async def download_contract(filename: str):
    """
    Download or view generated contract file (DOCX or PDF).
    Supports inline viewing in iframes for PDFs.
    """
    file_path = Path(settings.generated_dir) / filename
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract file not found"
        )
    
    # Determine media type and disposition based on extension
    if filename.lower().endswith(".pdf"):
        media_type = "application/pdf"
        # Use 'inline' for PDFs so they can be displayed in iframes
        headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    else:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
        headers=headers
    )


@app.post("/contracts/render/pdf")
async def render_contract_pdf(request: ContractRenderRequest):
    """
    Render contract and convert to PDF.
    Returns PDF file and saves it for later download.
    """
    try:
        # Render DOCX first (use output_filename if provided to ensure consistency)
        # Get output_filename from request (may be None if not provided)
        output_filename = request.output_filename if hasattr(request, 'output_filename') else None
        # Debug logging (can be removed later)
        if output_filename:
            print(f"[DEBUG] Using provided output_filename: {output_filename}")
        filename, docx_path = renderer.render_contract(request, output_filename=output_filename)
        
        # Try PDF conversion if available
        pdf_path = None
        if pdf_converter and pdf_converter.is_available():
            success, pdf_path = pdf_converter.convert_docx_to_pdf(docx_path)
            
            if success and pdf_path and pdf_path.exists():
                return FileResponse(
                    path=str(pdf_path),
                    filename=f"{filename}.pdf",
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}.pdf"'}
                )
        
        # Fallback to DOCX if PDF conversion not available or fails
        return FileResponse(
            path=str(docx_path),
            filename=f"{filename}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


@app.post("/contracts/sign")
async def sign_contract(request: dict):
    """
    Add signature to an existing contract PDF.
    Returns signed PDF file.
    """
    try:
        from app.services.pdf_signer import PDFSigner
        import base64
        from pathlib import Path
        
        # Handle both dict and Pydantic model
        if hasattr(request, "dict"):
            request_dict = request.dict()
        else:
            request_dict = request
        
        contract_filename = request_dict.get("contract_filename")
        signature_image = request_dict.get("signature_image")  # Base64 data URL
        
        if not contract_filename or not signature_image:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="contract_filename and signature_image are required"
            )
        
        # Extract base64 data from data URL if present
        if "," in signature_image:
            signature_image = signature_image.split(",")[-1]
        
        # Decode signature image
        try:
            signature_bytes = base64.b64decode(signature_image)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid signature image: {str(e)}"
            )
        
        # Get contract file path
        contract_path = Path(settings.generated_dir) / contract_filename
        if not contract_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract file not found: {contract_filename}"
            )
        
        # Sign the PDF
        pdf_signer = PDFSigner()
        signed_path = pdf_signer.add_signature(contract_path, signature_bytes)
        
        if signed_path and signed_path.exists():
            signed_filename = signed_path.name
            return FileResponse(
                path=str(signed_path),
                filename=signed_filename,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{signed_filename}"'}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to sign contract"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error signing contract: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

