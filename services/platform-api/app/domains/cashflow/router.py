from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.domains.cashflow.schemas import DataFilesOut, PayslipOut, RidersOut, RiderOut
from app.domains.cashflow.service import (
    build_payslip_row,
    get_data_dir,
    get_riders_from_file,
    list_xlsx_files,
    load_excel,
)

router = APIRouter(prefix="/api")


@router.get("/data-files", response_model=DataFilesOut)
def get_data_files() -> DataFilesOut:
    """List all available Excel payout files."""
    try:
        files = list_xlsx_files()
        data_dir = str(get_data_dir())
        return DataFilesOut(data_dir=data_dir, files=files)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}",
        )


@router.get("/riders", response_model=RidersOut)
def get_riders(file: str = Query(..., description="Excel filename")) -> RidersOut:
    """Get list of riders from an Excel file."""
    try:
        riders_data = get_riders_from_file(file)
        riders = [RiderOut(**r) for r in riders_data]
        return RidersOut(file=file, count=len(riders), riders=riders)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load riders: {str(e)}",
        )


@router.get("/payslip", response_model=PayslipOut)
def get_payslip(
    file: str = Query(..., description="Excel filename"),
    cee_id: str = Query(..., description="Rider cee_id"),
) -> PayslipOut:
    """Get payslip data for a rider from an Excel file."""
    try:
        df = load_excel(file)
        payslip_data = build_payslip_row(df, cee_id)
        return PayslipOut(**payslip_data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate payslip: {str(e)}",
        )


@router.get("/payslip.pdf")
def get_payslip_pdf(
    file: str = Query(..., description="Excel filename"),
    cee_id: str = Query(..., description="Rider cee_id"),
) -> Response:
    """Generate and download PDF payslip for a rider."""
    try:
        # Import here to avoid loading reportlab if not needed
        from app.domains.cashflow.pdf import render_pdf
        
        df = load_excel(file)
        payslip_data = build_payslip_row(df, cee_id)
        pdf_bytes = render_pdf(payslip_data)
        
        from pathlib import Path
        fn = f"payslip_{Path(file).stem}_{cee_id}.pdf".replace(" ", "_")
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fn}"'},
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}",
        )

