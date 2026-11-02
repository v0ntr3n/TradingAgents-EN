from __future__ import annotations
import sys as _sys
import types as _types
import app.routers as _routers_pkg
_self_mod = _sys.modules[__name__]
_snapshots = {}

# === portfolio.py ===
"""
Position Research API Route
Provide position management and AI research interfaces
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel, Field
import logging
import io

from app.routers.auth_db import get_current_user
from app.services.portfolio_service import get_portfolio_service
from app.models.portfolio import (
    PositionCreate, PositionUpdate, PositionImport, PositionOperationRequest,
    PositionChangeUpdate,
    PortfolioAnalysisRequest, PositionResponse,
    PortfolioStatsResponse, PortfolioAnalysisResponse,
    PositionAnalysisRequest, PositionAnalysisByCodeRequest,
    AccountInitRequest, AccountTransactionRequest,
    AccountSettingsRequest, CapitalTransactionType, PositionChangeType,
    QMTPositionImportRequest,
    PortfolioAnalysisStatus
)
from app.core.response import ok

logger = logging.getLogger("webapi")

router = APIRouter(
    prefix="/portfolio",
    tags=["Position research"]
)


# ==================== Position management interface ====================

@router.get("/positions", response_model=dict)
async def get_positions(
    source: str = Query("all", description="Data source: all/real/paper"),
    current_user: dict = Depends(get_current_user)
):
    """Get position list"""
    try:
        service = get_portfolio_service()
        positions = await service.get_positions(
            user_id=current_user["id"],
            source=source
        )

        # Convert to list of dictionaries
        items = [pos.model_dump() for pos in positions]

        return ok(data={
            "items": items,
            "total": len(items)
        })
    except Exception as e:
        logger.error(f"Failed to obtain position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/positions/history", response_model=dict)
async def get_history_positions(
    source: str = Query("real", description="Data source: real/paper"),
    limit: int = Query(50, ge=1, le=100, description="Quantity per page"),
    skip: int = Query(0, ge=0, description="skip quantity"),
    current_user: dict = Depends(get_current_user)
):
    """Get historical positions (records of cleared positions)"""
    try:
        service = get_portfolio_service()
        result = await service.get_history_positions(
            user_id=current_user["id"],
            source=source,
            limit=limit,
            skip=skip
        )
        return ok(data=result)
    except Exception as e:
        logger.error(f"Failed to obtain historical positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions", response_model=dict)
async def add_position(
    data: PositionCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add position"""
    try:
        service = get_portfolio_service()
        position = await service.add_position(
            user_id=current_user["id"],
            data=data
        )
        return ok(data=position.model_dump(), message="Added successfully")
    except Exception as e:
        logger.error(f"Failed to add position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/positions/{position_id}", response_model=dict)
async def update_position(
    position_id: str,
    data: PositionUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update positions"""
    try:
        service = get_portfolio_service()
        position = await service.update_position(
            user_id=current_user["id"],
            position_id=position_id,
            data=data
        )
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position does not exist"
            )
        return ok(data=position.model_dump(), message="Update successful")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/positions/{position_id}", response_model=dict)
async def delete_position(
    position_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete position"""
    try:
        service = get_portfolio_service()
        success = await service.delete_position(
            user_id=current_user["id"],
            position_id=position_id
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position does not exist"
            )
        return ok(message="Delete successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/import", response_model=dict)
async def import_positions(
    data: PositionImport,
    current_user: dict = Depends(get_current_user)
):
    """Import positions in batches"""
    try:
        service = get_portfolio_service()
        result = await service.import_positions(
            user_id=current_user["id"],
            positions=data.positions
        )
        return ok(data=result, message=f"Import completed: success {result['success_count']}, failed {result['failed_count']}")
    except Exception as e:
        logger.error(f"Failed to import positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


class FileImportMapping(BaseModel):
    """File column name mapping"""
    code: str = Field("Stock code", description="Stock code listing")
    name: str = Field("Stock name", description="Stock name listing")
    quantity: str = Field("Position quantity", description="Quantity column name")
    cost_price: str = Field("cost price", description="Cost price listing")
    buy_date: str = Field("Purchase date", description="Purchase date listed")


@router.post("/positions/import/file", response_model=dict)
async def import_positions_from_file(
    file: UploadFile = File(...),
    market: str = Query("CN", description="market: CN/HK/US"),
    current_user: dict = Depends(get_current_user)
):
    """Import positions from Excel/CSV file

    Supports .xlsx / .xls / .csv formats.
    Automatically identify common brokerage export formats (Flush, Oriental Fortune, Huatai, etc.),
    Custom column name mapping is also supported.
    """
    try:
        import pandas as pd

        # read file
        content = await file.read()
        filename = file.filename or ""

        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format: {filename}, Please upload .xlsx / .xls / .csv files"
            )

        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The file content is empty"
            )

        logger.info(f"📁 File parsed successfully: {filename}, {len(df)} OK, Column: {list(df.columns)}")

        # Automatically identify column name mappings
        col_map = _auto_detect_columns(df.columns.tolist())
        logger.info(f"🔍 Automatic recognition of column mappings: {col_map}")

        # Resolves as a PositionCreate list
        positions = []
        errors = []
        for idx, row in df.iterrows():
            try:
                code = str(row.get(col_map["code"], "")).strip()
                if not code or code == "nan":
                    continue
                # Make sure the code is 6 digits
                code = code.zfill(6)

                quantity = int(float(row.get(col_map["quantity"], 0)))
                cost_price = float(row.get(col_map["cost_price"], 0))

                if quantity <= 0 or cost_price <= 0:
                    errors.append({"row": idx + 1, "code": code, "error": "Invalid quantity or cost price"})
                    continue

                name = str(row.get(col_map["name"], "")).strip()
                if name == "nan":
                    name = ""

                buy_date = None
                if col_map["buy_date"]:
                    raw_date = row.get(col_map["buy_date"], "")
                    if raw_date and str(raw_date) != "nan":
                        try:
                            from datetime import datetime as dt
                            if isinstance(raw_date, dt):
                                buy_date = raw_date
                            else:
                                # Try multiple date formats
                                for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%m/%d/%Y"]:
                                    try:
                                        buy_date = dt.strptime(str(raw_date).strip(), fmt)
                                        break
                                    except ValueError:
                                        continue
                        except Exception:
                            pass

                pos = PositionCreate(
                    code=code,
                    name=name or None,
                    quantity=quantity,
                    cost_price=cost_price,
                    market=market,
                    buy_date=buy_date,
                )
                positions.append(pos)
            except Exception as e:
                errors.append({"row": idx + 1, "error": str(e)})

        if not positions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to parse valid positions from the file. Column mapping: {col_map}, Parse error: {errors[:5]}"
            )

        # Batch import
        service = get_portfolio_service()
        result = await service.import_positions(
            user_id=current_user["id"],
            positions=positions,
            validate_input=True,
        )
        result["file_info"] = {
            "filename": filename,
            "total_rows": len(df),
            "parsed_rows": len(positions),
            "parse_errors": errors[:10],
            "column_mapping": col_map,
        }

        return ok(data=result, message=f"Import completed: success {result['success_count']}, failed {result['failed_count']}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File import position failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _auto_detect_columns(columns: List[str]) -> Dict[str, Any]:
    """Automatically recognize mapping of Excel/CSV column names to system fields

    Supports common brokerage export formats such as Flush, Oriental Fortune, Huatai, etc.
    """
    col_map = {
        "code": None,
        "name": None,
        "quantity": None,
        "cost_price": None,
        "buy_date": None,
    }

    # Stock code candidate list
    code_candidates = [
        "Stock code", "Securities code", "code", "code", "symbol",
        "stock_code", "Securities number", "securities",
    ]
    # Stock name candidate listing
    name_candidates = [
        "Stock name", "Security name", "Name", "name", "Securities abbreviation",
        "stock_name", "Security name",
    ]
    # Quantity candidate list
    quantity_candidates = [
        "Position quantity", "Number of securities", "Quantity held", "Quantity", "quantity", "Number of shares",
        "Number of shares held", "available quantity", "Position", "Open interest",
    ]
    # Cost price candidate list
    cost_price_candidates = [
        "cost price", "diluted costs", "Holding cost", "cost", "cost_price",
        "cost price", "average price", "average buying price", "buying price",
    ]
    # Purchase date candidate list
    date_candidates = [
        "Purchase date", "Opening date", "Purchase date", "Buying time",
        "buy_date", "First purchase date", "Buying day",
    ]

    def _find_column(candidates: List[str], cols: List[str]) -> Any:
        for c in candidates:
            for col in cols:
                if c in col or col in c:
                    return col
        return None

    col_map["code"] = _find_column(code_candidates, columns)
    col_map["name"] = _find_column(name_candidates, columns)
    col_map["quantity"] = _find_column(quantity_candidates, columns)
    col_map["cost_price"] = _find_column(cost_price_candidates, columns)
    col_map["buy_date"] = _find_column(date_candidates, columns)

    return col_map


@router.post("/positions/import/file/preview", response_model=dict)
async def preview_import_file(
    file: UploadFile = File(...),
    market: str = Query("CN", description="market: CN/HK/US"),
    current_user: dict = Depends(get_current_user)
):
    """Preview file import: parse the file and return the first 10 rows and column mapping results, no import is performed"""
    try:
        import pandas as pd

        content = await file.read()
        filename = file.filename or ""

        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format: {filename}"
            )

        col_map = _auto_detect_columns(df.columns.tolist())

        # Return preview data
        preview_rows = df.head(10).fillna("").to_dict("records")

        return ok(data={
            "filename": filename,
            "total_rows": len(df),
            "columns": list(df.columns),
            "column_mapping": col_map,
            "preview": preview_rows,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/import/screenshot", response_model=dict)
async def import_positions_from_screenshot(
    file: UploadFile = File(...),
    market: str = Query("CN", description="market: CN/HK/US"),
    current_user: dict = Depends(get_current_user)
):
    """Identify position information from brokerage screenshots

    Upload a screenshot of the brokerage interface (such as the position list page) and use VLM (Visual Language Model) to analyze the image.
    Automatically extract stock code, name, quantity, cost price and other information.
    The recognition results are returned for user confirmation and are not automatically imported.

    Note: The dialogue model needs to support Vision capabilities (such as Qwen-VL, GPT-4o, etc.),
    GLM-5/GLM-5.1 Text-only models do not support this feature.
    """
    try:
        import base64
        import os
        from app.services.model_capability_service import get_model_capability_service
        from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
        from tradingagents.graph.trading_graph import create_llm_by_provider

        # Disabled in JD Cloud mode (GLM-5/5.1 does not support Vision)
        if os.getenv("JDYUN_MODE", "").lower() == "true":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The current dialogue model of JD Cloud version does not support the image recognition function. Please use the file import (Excel/CSV) method to add positions in batches."
            )

        # Read pictures
        content = await file.read()
        filename = file.filename or ""

        # Check file type
        if not any(filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported image format: {filename}, Please upload PNG/JPG/BMP/WebP format"
            )

        # Base64 encoding
        img_b64 = base64.b64encode(content).decode("utf-8")
        mime_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

        # Get the conversation model (Vision capability)
        capability_service = get_model_capability_service()
        chat_model, _ = capability_service._get_default_models()
        model_name = chat_model

        # Check whether the model supports Vision (multimodal input)
        # Known models that support Vision:Qwen-VL, Qwen2-VL, GPT-4o, GPT-4V, Claude-3, gemini
        # Models known to not support Vision:GLM-5, GLM-5.1, GLM-5.2, DeepSeek-V4, DeepSeek-V3
        VISION_UNSUPPORTED_PATTERNS = ["glm-5", "glm-4", "deepseek", "qwen2.5-72b-instruct", "llama"]
        model_lower = model_name.lower()
        is_vision_supported = not any(p in model_lower for p in VISION_UNSUPPORTED_PATTERNS)

        if not is_vision_supported:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Current dialogue model {model_name} Image recognition function is not supported. Screenshot recognition requires a model that supports Vision (such as Qwen2-VL, GPT-4o, etc.). Please use the file import (Excel/CSV) method instead."
            )

        provider_info = get_provider_and_url_by_model_sync(model_name)
        backend_url = provider_info.get("backend_url")
        api_key = provider_info.get("api_key")
        provider_name = provider_info.get("provider", "dashscope")

        if not backend_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The dialogue model is not configured and the screenshot recognition function cannot be used."
            )

        # Constructing a Vision LLM request
        llm = create_llm_by_provider(
            provider=provider_name,
            model=model_name,
            backend_url=backend_url,
            temperature=0.1,
            max_tokens=4000,
        )

        # Construct multimodal messages
        system_prompt = """You are a professional brokerage position screenshot identification assistant. Please identify this screenshot of brokerage positions and extract the position information of each stock.

Please return results strictly in the following JSON format and do not include any other text:
```json
[
  {
    "code": "000001",
    "name": "Ping An Bank",
    "quantity": 1000,
    "cost_price": 12.34,
    "buy_date": "2024-01-15"
  }
]
```

Things to note:
1. Stock code must be 6 digits
2. Quantity must be an integer (number of shares)
3. Cost price to 2 decimal places
4. The purchase date format is YYYY-MM-DD, if it cannot be recognized, set it to null
5. If some fields are not recognized, set to null
6. Return only JSON array, no other content"""

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{img_b64}"
                    }
                },
                {
                    "type": "text",
                    "text": "Please identify all stock position information in this screenshot of brokerage positions."
                }
            ])
        ]

        response = await llm.ainvoke(messages)
        result_text = response.content if hasattr(response, 'content') else str(response)

        # Parse JSON results
        import json
        import re

        # Extract a JSON array (possibly wrapped in ```json ... ``` middle)
        json_match = re.search(r'\[[\s\S]*?\]', result_text)
        if not json_match:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM The returned content cannot be parsed as JSON: {result_text[:200]}"
            )

        try:
            positions_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON Parsing failed: {e}"
            )

        # Convert to PositionCreate list
        positions = []
        parse_errors = []
        for idx, item in enumerate(positions_data):
            try:
                code = str(item.get("code", "")).zfill(6)
                quantity = int(item.get("quantity", 0))
                cost_price = float(item.get("cost_price", 0))

                if not code or quantity <= 0 or cost_price <= 0:
                    parse_errors.append({"index": idx, "data": item, "error": "Required fields are missing or invalid"})
                    continue

                buy_date = None
                raw_date = item.get("buy_date")
                if raw_date and str(raw_date) != "null":
                    try:
                        from datetime import datetime as dt
                        buy_date = dt.strptime(str(raw_date), "%Y-%m-%d")
                    except ValueError:
                        pass

                pos = PositionCreate(
                    code=code,
                    name=item.get("name") or None,
                    quantity=quantity,
                    cost_price=cost_price,
                    market=market,
                    buy_date=buy_date,
                )
                positions.append(pos)
            except Exception as e:
                parse_errors.append({"index": idx, "data": item, "error": str(e)})

        logger.info(f"📸 Screenshot recognition completed: identify {len(positions_data)} Article, valid {len(positions)} bar, error {len(parse_errors)} Article")

        return ok(data={
            "filename": filename,
            "model": model_name,
            "recognized_count": len(positions_data),
            "valid_count": len(positions),
            "positions": [p.model_dump() for p in positions],
            "parse_errors": parse_errors[:10],
            "raw_response": result_text[:500],
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screenshot recognition failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/import/qmt/preview", response_model=dict)
async def preview_positions_from_qmt(
    data: QMTPositionImportRequest,
    current_user: dict = Depends(get_current_user)
):
    """Preview the impact of syncing current account positions from QMT overlay."""
    try:
        service = get_portfolio_service()
        result = await service.preview_qmt_position_import(
            user_id=current_user["id"],
            account_id=data.account_id,
            account_type=data.account_type,
        )
        return ok(data=result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"QMT Position synchronization preview failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/import/qmt", response_model=dict)
async def import_positions_from_qmt(
    data: QMTPositionImportRequest,
    current_user: dict = Depends(get_current_user)
):
    """Read-only query the current account positions from QMT and overwrite the positions synchronized to the system."""
    try:
        service = get_portfolio_service()
        result = await service.import_positions_from_qmt(
            user_id=current_user["id"],
            account_id=data.account_id,
            account_type=data.account_type,
        )
        return ok(
            data=result,
            message=(
                f"QMT Position synchronization completed: Covered {result.get('deleted_positions', 0)} Gejiu position, "
                f"success {result['success_count']}, failed {result['failed_count']}"
            )
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"QMT Position import failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/operate", response_model=dict)
async def operate_position(
    data: PositionOperationRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Execute position operations (increase positions, reduce positions, dividends, split shares, combine shares, adjust costs)

    Operation type:
    - add: Add position (need quantity, price) 
    - reduce: Reduce position (requires quantity, price) 
    - dividend: Dividend (requires dividend_amount)
    - split: split (requires ratio, e.g. "2:1") 
    - merge: partnership (requires ratio, e.g. "1:10") 
    - adjust: Adjust cost price (requires new_cost_price)
    """
    try:
        service = get_portfolio_service()
        result = await service.operate_position(
            user_id=current_user["id"],
            data=data
        )
        return ok(data=result, message=result.get("message", "Operation successful"))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Position operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== Position statistics interface ====================

@router.get("/statistics", response_model=dict)
async def get_portfolio_statistics(
    current_user: dict = Depends(get_current_user)
):
    """Get position statistics"""
    try:
        service = get_portfolio_service()
        stats = await service.get_portfolio_statistics(current_user["id"])
        return ok(data=stats.model_dump())
    except Exception as e:
        logger.error(f"Failed to obtain position statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== Position research interface ====================

@router.post("/analysis", response_model=dict)
async def analyze_portfolio(
    data: PortfolioAnalysisRequest = PortfolioAnalysisRequest(),
    current_user: dict = Depends(get_current_user)
):
    """Initiate position research"""
    try:
        service = get_portfolio_service()
        report = await service.analyze_portfolio(
            user_id=current_user["id"],
            include_paper=data.include_paper,
            research_depth=data.research_depth
        )

        # Convert to responsive format
        response_data = {
            "analysis_id": report.analysis_id,
            "status": report.status.value,
            "health_score": report.health_score,
            "risk_level": report.risk_level,
            "portfolio_snapshot": report.portfolio_snapshot.model_dump(),
            "industry_distribution": [d.model_dump() for d in report.industry_distribution],
            "concentration_analysis": report.concentration_analysis.model_dump(),
            "ai_analysis": report.ai_analysis.model_dump(),
            "execution_time": report.execution_time,
            "error_message": report.error_message,
            "created_at": report.created_at.isoformat()
        }

        return ok(data=response_data)
    except Exception as e:
        logger.error(f"Position research failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/analysis/history", response_model=dict)
async def get_analysis_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Get analysis history"""
    try:
        service = get_portfolio_service()
        result = await service.get_analysis_history(
            user_id=current_user["id"],
            page=page,
            page_size=page_size
        )

        # Convert ObjectId
        items = []
        for item in result["items"]:
            item["_id"] = str(item["_id"]) if "_id" in item else None
            items.append(item)

        return ok(data={
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"]
        })
    except Exception as e:
        logger.error(f"Failed to obtain analysis history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/analysis/{analysis_id}", response_model=dict)
async def get_analysis_detail(
    analysis_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get research report details"""
    try:
        service = get_portfolio_service()
        report = await service.get_analysis_detail(analysis_id)

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research report does not exist"
            )

        # Verify user permissions
        if report.get("user_id") != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Don t have permission to access this report"
            )

        # If the report contains ai_analysis, check and convert action_reason
        if report.get("ai_analysis") and report["ai_analysis"].get("action_reason"):
            action_reason_raw = report["ai_analysis"]["action_reason"]
            logger.info(f"📊 [Analysis details interface] Original action_reason type: {type(action_reason_raw)}, length: {len(str(action_reason_raw)) if action_reason_raw else 0}")
            
            import json
            advice_json = None
            
            if isinstance(action_reason_raw, str):
                action_reason_str = action_reason_raw.strip()
                if "```json" in action_reason_str or (action_reason_str.startswith("{") and ("analysis_summary" in action_reason_str or "neutral_operation" in action_reason_str)):
                    try:
                        if "```json" in action_reason_str:
                            json_start = action_reason_str.find("```json") + 7
                            json_end = action_reason_str.find("```", json_start)
                            if json_end > json_start:
                                json_str = action_reason_str[json_start:json_end].strip()
                                advice_json = json.loads(json_str)
                        elif action_reason_str.strip().startswith("{"):
                            advice_json = json.loads(action_reason_str)
                        
                        if advice_json:
                            logger.info("📊 [Analysis details interface] JSON Parsed successfully, converted to Markdown")
                            report["ai_analysis"]["action_reason"] = service._convert_action_advice_json_to_markdown(advice_json)
                    except Exception as e:
                        logger.warning(f"⚠️ [Analysis details interface] JSON Parsing failed: {e}")
            elif isinstance(action_reason_raw, dict):
                logger.info("📊 [Analysis details interface] action_reason is a dictionary format, converted to Markdown")
                report["ai_analysis"]["action_reason"] = service._convert_action_advice_json_to_markdown(action_reason_raw)

        # Convert ObjectId
        report["_id"] = str(report["_id"]) if "_id" in report else None

        return ok(data=report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== Single stock position research interface ====================

@router.get("/positions/{position_id}", response_model=dict)
async def get_position_detail(
    position_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get individual position details"""
    try:
        service = get_portfolio_service()
        position = await service.get_position_by_id(current_user["id"], position_id)
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position does not exist"
            )
        return ok(data=position.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to obtain position details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/{position_id}/analysis", response_model=dict)
async def analyze_position(
    position_id: str,
    data: PositionAnalysisRequest = PositionAnalysisRequest(),
    current_user: dict = Depends(get_current_user)
):
    """Initiate single stock position research"""
    try:
        service = get_portfolio_service()
        report = await service.analyze_position(
            user_id=current_user["id"],
            position_id=position_id,
            params=data
        )

        # Check if analysis failed
        if report.status == PortfolioAnalysisStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=report.error_message or "Research failed"
            )

        snapshot_dict = report.position_snapshot.model_dump() if report.position_snapshot and hasattr(report.position_snapshot, "model_dump") else {}
        ai_analysis_data = report.ai_analysis.model_dump() if report.ai_analysis and hasattr(report.ai_analysis, "model_dump") else {}
        sanitized_ai_analysis = service._sanitize_position_analysis_dict(ai_analysis_data, position_snapshot=snapshot_dict)

        # Convert to responsive format
        response_data = {
            "analysis_id": report.analysis_id,
            "position_id": report.position_id,
            "code": report.position_snapshot.code if report.position_snapshot else None,
            "name": report.position_snapshot.name if report.position_snapshot else None,
            "status": report.status.value,
            "action": sanitized_ai_analysis.get("action"),
            "action_reason": sanitized_ai_analysis.get("action_reason"),
            "confidence": sanitized_ai_analysis.get("confidence"),
            "price_targets": sanitized_ai_analysis.get("price_targets"),
            "risk_assessment": sanitized_ai_analysis.get("risk_assessment"),
            "opportunity_assessment": sanitized_ai_analysis.get("opportunity_assessment"),
            "detailed_analysis": sanitized_ai_analysis.get("detailed_analysis"),
            "user_view": sanitized_ai_analysis.get("user_view", {}),
            "appendix_sections": sanitized_ai_analysis.get("appendix_sections", []),
            "execution_time": report.execution_time,
            "error_message": report.error_message,
            "created_at": report.created_at.isoformat()
        }

        return ok(data=response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Single stock position research failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


class CheckCacheRequest(BaseModel):
    """Check cache requests"""
    code: str = Field(..., description="Stock code")
    market: str = Field("CN", description="Market type (CN/HK/US)")


@router.post("/positions/check-cache", response_model=dict)
async def check_stock_analysis_cache(
    data: CheckCacheRequest,
    current_user: dict = Depends(get_current_user)
):
    """Check Single Stock Research Report Cache Status
    
    Before starting position research, check whether a cache of individual stock research reports is available.
    If there is no cache, the front end can prompt the user to choose:
    1. Continue research (without using individual stock research reports)
    2. First go to the single stock research page to conduct research.
    
    Args:
        data: Check cached requests for ticker and market type
        
    Returns:
        Cache status information, including:
        - has_cache: Is there a cache
        - cache_age_hours: Cache time (hours)
        - cache_age_minutes: Cache time (minutes)
        - source: cache source
        - task_id: Task ID (if any)
        - created_at: Cache creation time
    """
    try:
        from app.services.portfolio_service import get_portfolio_service, convert_market_code_to_name
        
        portfolio_service = get_portfolio_service()
        
        # Convert market code to Chinese name (A shares/Hong Kong stocks/US stocks)
        market_name = convert_market_code_to_name(data.market, data.code)
        
        logger.info(f"🔍 [Check cache] Check the cache of individual stock research reports: code={data.code}, market={data.market} -> {market_name}")
        
        cache_status = await portfolio_service.check_stock_analysis_cache(
            stock_code=data.code,
            market=market_name
        )
        
        logger.info(f"✅ [Check cache] cache status: has_cache={cache_status.get('has_cache')}, "
                   f"age={cache_status.get('cache_age_minutes')}minutes")
        
        return ok(data=cache_status, message="Cache status query successful")
        
    except Exception as e:
        logger.error(f"❌ [Check cache] Query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query cache status: {str(e)}"
        )


@router.post("/positions/analyze-by-code", response_model=dict)
async def analyze_position_by_code(
    data: PositionAnalysisByCodeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Analyze positions by ticker (asynchronous mode)

    The task ID is returned immediately and analysis is performed in the background.
    The front end can pass GET /api/analysis/tasks/{task_id}/status Query analysis status and results.

    Manage with the new unified task center.
    """
    import asyncio

    try:
        logger.info(f"📥 [Position research route] Request received: code={data.code}, market={data.market}, user_id={current_user['id']}")
        
        from app.services.unified_analysis_service import get_unified_analysis_service

        unified_service = get_unified_analysis_service()
        logger.info("✅ [Position research route] Get the UnifiedAnalysisService instance")

        # Prepare task parameters
        task_params = {
            "research_depth": data.research_depth,
            "include_add_position": data.include_add_position,
            "target_profit_pct": data.target_profit_pct,
            "total_capital": data.total_capital,
            "max_position_pct": data.max_position_pct,
            "max_loss_pct": data.max_loss_pct,
            "risk_tolerance": data.risk_tolerance,
            "investment_horizon": data.investment_horizon,
            "analysis_focus": data.analysis_focus,
            "position_type": data.position_type,
        }
        logger.info(f"📋 [Position research route] Task parameters are ready: {list(task_params.keys())}")

        # Create unified research tasks
        logger.info("🔄 [Position research route] Start creating tasks...")
        result = await unified_service.create_position_analysis_task(
            user_id=current_user["id"],
            code=data.code,
            market=data.market,
            task_params=task_params
        )
        logger.info(f"✅ [Position research route] Task created successfully: task_id={result['task_id']}")
        
        # In order to be compatible with the front end, the analysis_id field (equal to task_id) is also returned.
        result["analysis_id"] = result["task_id"]

        # Backend execution research
        logger.info("🚀 [Position research route] Start background task execution...")
        asyncio.create_task(
            unified_service.execute_position_analysis(
                task_id=result["task_id"],
                user_id=current_user["id"],
                code=data.code,
                market=data.market,
                task_params=task_params
            )
        )
        logger.info("✅ [Position research route] Background task started")

        return ok(data=result, message="The position research task has been submitted and is expected to take 2-5 minutes to complete.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Position research route] Failed to create task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/positions/analysis/{task_id}", response_model=dict)
async def get_position_analysis_status(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get position research task status and results

    Note: This interface has been changed to use the unified task center, and task_id is the task ID.
    Can also be used GET /api/analysis/tasks/{task_id}/status Interface query.
    """
    try:
        from app.core.database import get_mongo_db
        from bson import ObjectId

        db = get_mongo_db()

        # Get tasks from unified task center
        task = await db.unified_analysis_tasks.find_one({
            "task_id": task_id,
            "user_id": ObjectId(current_user["id"])
        })

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The research task does not exist"
            )

        # Format return data
        task_status = task["status"]
        if hasattr(task_status, "value"):
            task_status = task_status.value
        elif isinstance(task_status, str):
            task_status = task_status
        else:
            task_status = str(task_status)
        
        # Helper function: Convert datetime or string to ISO format string
        def to_iso_string(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)
        
        result_data = {
            "task_id": task["task_id"],
            "code": task["task_params"].get("code"),
            "market": task["task_params"].get("market"),
            "status": task_status,
            "message": task.get("message"),
            "progress": task.get("progress", 0),
            "created_at": to_iso_string(task.get("created_at")),
            "started_at": to_iso_string(task.get("started_at")),
            "completed_at": to_iso_string(task.get("completed_at")),
            "error_message": task.get("error_message"),
        }
        
        # If the task is completed and there are results, flatten the fields in the result to the top level to match the data structure expected by the front end
        task_result = task.get("result")
        if task_result and isinstance(task_result, dict):
            # Extract analysis_id (if any)
            if "analysis_id" in task_result:
                result_data["analysis_id"] = task_result["analysis_id"]
            
            # Extract fields in position_snapshot
            position_snapshot = task_result.get("position_snapshot")
            if position_snapshot:
                result_data["code"] = position_snapshot.get("code") or result_data.get("code")
                result_data["name"] = position_snapshot.get("name")
                # build position_id
                if position_snapshot.get("code") and position_snapshot.get("market"):
                    result_data["position_id"] = f"{position_snapshot['code']}_{position_snapshot['market']}"
            elif result_data.get("code") and result_data.get("market"):
                # If there is no snapshot, use code and market to build position_id
                result_data["position_id"] = f"{result_data['code']}_{result_data['market']}"
            
            # Extract fields in ai_analysis and flatten to top level
            ai_analysis = task_result.get("ai_analysis")
            if ai_analysis:
                service = get_portfolio_service()
                sanitized_ai_analysis = service._sanitize_position_analysis_dict(ai_analysis, position_snapshot=position_snapshot or {})
                # action May be an enumeration type and needs to be converted to a string
                action_value = sanitized_ai_analysis.get("action")
                if hasattr(action_value, "value"):
                    action_value = action_value.value
                result_data["action"] = action_value
                result_data["action_reason"] = sanitized_ai_analysis.get("action_reason", "")
                result_data["recommendation"] = sanitized_ai_analysis.get("recommendation", "")
                result_data["confidence"] = sanitized_ai_analysis.get("confidence")
                result_data["price_targets"] = sanitized_ai_analysis.get("price_targets")
                result_data["risk_assessment"] = sanitized_ai_analysis.get("risk_assessment")
                result_data["opportunity_assessment"] = sanitized_ai_analysis.get("opportunity_assessment")
                result_data["detailed_analysis"] = sanitized_ai_analysis.get("detailed_analysis")
                result_data["user_view"] = sanitized_ai_analysis.get("user_view", {})
                result_data["appendix_sections"] = sanitized_ai_analysis.get("appendix_sections", [])
                result_data["suggested_quantity"] = sanitized_ai_analysis.get("suggested_quantity")
                result_data["suggested_amount"] = sanitized_ai_analysis.get("suggested_amount")
                result_data["risk_metrics"] = sanitized_ai_analysis.get("risk_metrics")
            
            # Keep the result field, but make sure the internal recommendation is also converted
            # Create a copy to avoid modifying the original data
            result_copy = task_result.copy() if isinstance(task_result, dict) else task_result
            if isinstance(result_copy, dict) and "ai_analysis" in result_copy:
                ai_analysis_copy = result_copy["ai_analysis"].copy() if isinstance(result_copy["ai_analysis"], dict) else result_copy["ai_analysis"]
                if isinstance(ai_analysis_copy, dict):
                    # If the top-level recommendation has been converted, synchronize it to the result.
                    if "recommendation" in result_data:
                        ai_analysis_copy["recommendation"] = result_data["recommendation"]
                        logger.info("📊 [Position research interface] Synchronize the converted recommendation to result.ai_analysis")
                    # If the top-level action_reason has been converted, it will also be synchronized to the result.
                    if "action_reason" in result_data:
                        ai_analysis_copy["action_reason"] = result_data["action_reason"]
                        logger.info("📊 [Position research interface] Synchronize the converted action_reason to result.ai_analysis")
                    if "detailed_analysis" in result_data:
                        ai_analysis_copy["detailed_analysis"] = result_data["detailed_analysis"]
                    if "user_view" in result_data:
                        ai_analysis_copy["user_view"] = result_data["user_view"]
                    if "appendix_sections" in result_data:
                        ai_analysis_copy["appendix_sections"] = result_data["appendix_sections"]
                    result_copy["ai_analysis"] = ai_analysis_copy
            result_data["result"] = result_copy
            
            # Extract execution_time
            if "execution_time" in task_result:
                result_data["execution_time"] = task_result["execution_time"]
        else:
            # If there is no result, leave it as is
            result_data["result"] = task_result

        return ok(data=result_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/positions/analysis-by-code/{code}", response_model=dict)
async def get_position_analysis_by_code(
    code: str,
    market: str = Query("CN", description="market: CN/HK/US"),
    source: str = Query("real", description="Data source: real(User positions)/paper(Simulated position)"),
    current_user: dict = Depends(get_current_user)
):
    """Get the latest research reports by ticker"""
    try:
        service = get_portfolio_service()
        # 🔥 Convert source to position_type
        position_type = "simulated" if source == "paper" else "real"
        report = await service.get_latest_position_analysis(
            user_id=current_user["id"],
            code=code,
            market=market,
            position_type=position_type
        )

        if not report:
            return ok(data=None, message="No research report yet")

        return ok(data=report)
    except Exception as e:
        logger.error(f"Failed to obtain position research report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/positions/{position_id}/analysis/history", response_model=dict)
async def get_position_analysis_history(
    position_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    source: str = Query("real", description="Data source: real(User positions)/paper(Simulated position)"),
    current_user: dict = Depends(get_current_user)
):
    """Get single stock research history"""
    try:
        service = get_portfolio_service()
        # 🔥 Convert source to position_type
        position_type = "simulated" if source == "paper" else "real"
        result = await service.get_position_analysis_history(
            user_id=current_user["id"],
            position_id=position_id,
            page=page,
            page_size=page_size,
            position_type=position_type
        )

        # Convert ObjectId
        items = []
        for item in result["items"]:
            item["_id"] = str(item["_id"]) if "_id" in item else None
            items.append(item)

        return ok(data={
            "items": items,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"]
        })
    except Exception as e:
        logger.error(f"Failed to get single stock research history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/positions/analysis/{analysis_id}", response_model=dict)
async def delete_position_analysis(
    analysis_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete position research report"""
    try:
        from app.core.database import get_mongo_db
        from bson import ObjectId
        
        db = get_mongo_db()
        
        # Find research reports
        report = await db["position_analysis_reports"].find_one({
            "analysis_id": analysis_id,
            "user_id": current_user["id"]
        })
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research report does not exist"
            )
        
        # Delete research report
        result = await db["position_analysis_reports"].delete_one({
            "analysis_id": analysis_id,
            "user_id": current_user["id"]
        })
        
        if result.deleted_count > 0:
            logger.info(f"✅ Deletion of position research report successful: {analysis_id}")
            return ok(message="Delete successfully")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Delete failed"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete position research report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== Fund account interface ====================

@router.get("/account", response_model=dict)
async def get_account(current_user: dict = Depends(get_current_user)):
    """Get fund account information"""
    try:
        service = get_portfolio_service()
        acc = await service.get_or_create_account(current_user["id"])
        # Remove _id
        acc.pop("_id", None)
        return ok(data=acc)
    except Exception as e:
        logger.error(f"Failed to obtain fund account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/account/summary", response_model=dict)
async def get_account_summary(current_user: dict = Depends(get_current_user)):
    """Get account summary (including position market value and profit calculation)"""
    try:
        service = get_portfolio_service()
        summary = await service.get_account_summary(current_user["id"])
        return ok(data=summary.model_dump())
    except Exception as e:
        logger.error(f"Failed to get account summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/account/initialize", response_model=dict)
async def initialize_account(
    request: AccountInitRequest,
    current_user: dict = Depends(get_current_user)
):
    """Initialize capital account (set initial capital)"""
    try:
        service = get_portfolio_service()
        acc = await service.initialize_account(
            user_id=current_user["id"],
            initial_capital=request.initial_capital,
            currency=request.currency
        )
        acc.pop("_id", None)
        return ok(data=acc, message=f"Initial funds have been set {request.initial_capital:,.2f} {request.currency}")
    except Exception as e:
        logger.error(f"Failed to initialize capital account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/account/deposit", response_model=dict)
async def deposit(
    request: AccountTransactionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Deposit"""
    if request.transaction_type != CapitalTransactionType.DEPOSIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction type must be deposit"
        )
    try:
        service = get_portfolio_service()
        acc = await service.deposit(
            user_id=current_user["id"],
            amount=request.amount,
            currency=request.currency,
            description=request.description
        )
        acc.pop("_id", None)
        return ok(data=acc, message=f"Deposit successful {request.amount:,.2f} {request.currency}")
    except Exception as e:
        logger.error(f"Deposit failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/account/withdraw", response_model=dict)
async def withdraw(
    request: AccountTransactionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Withdraw funds"""
    if request.transaction_type != CapitalTransactionType.WITHDRAW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction type must be withdraw"
        )
    try:
        service = get_portfolio_service()
        acc = await service.withdraw(
            user_id=current_user["id"],
            amount=request.amount,
            currency=request.currency,
            description=request.description
        )
        acc.pop("_id", None)
        return ok(data=acc, message=f"Withdraw successfully {request.amount:,.2f} {request.currency}")
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Withdrawal failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/account/settings", response_model=dict)
async def update_account_settings(
    request: AccountSettingsRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update account settings"""
    try:
        service = get_portfolio_service()
        acc = await service.update_account_settings(
            user_id=current_user["id"],
            settings=request
        )
        acc.pop("_id", None)
        return ok(data=acc, message="Account settings updated")
    except Exception as e:
        logger.error(f"Failed to update account settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/account/transactions", response_model=dict)
async def get_transactions(
    currency: str = Query(None, description="Currency type filter"),
    limit: int = Query(50, description="Return quantity limit"),
    current_user: dict = Depends(get_current_user)
):
    """Get fund transaction records"""
    try:
        service = get_portfolio_service()
        transactions = await service.get_transactions(
            user_id=current_user["id"],
            currency=currency,
            limit=limit
        )
        return ok(data={"items": transactions, "total": len(transactions)})
    except Exception as e:
        logger.error(f"Failed to obtain fund transaction records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== Position change record interface ====================

@router.get("/position-changes", response_model=dict)
async def get_position_changes(
    code: str = Query(None, description="Stock code filter"),
    market: str = Query(None, description="market filter: CN/HK/US"),
    change_type: str = Query(None, description="Change type: buy/add/reduce/sell/adjust"),
    limit: int = Query(100, description="Return quantity limit"),
    skip: int = Query(0, description="skip quantity"),
    current_user: dict = Depends(get_current_user)
):
    """Get position change records"""
    try:
        service = get_portfolio_service()
        changes = await service.get_position_changes(
            user_id=current_user["id"],
            code=code,
            market=market,
            change_type=change_type,
            limit=limit,
            skip=skip
        )
        total = await service.get_position_changes_count(
            user_id=current_user["id"],
            code=code,
            market=market,
            change_type=change_type
        )
        return ok(data={
            "items": [c.model_dump() for c in changes],
            "total": total,
            "limit": limit,
            "skip": skip
        })
    except Exception as e:
        logger.error(f"Failed to obtain position change records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/position-changes/{change_id}", response_model=dict)
async def update_position_change(
    change_id: str,
    data: PositionChangeUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Modify single transaction records (used to correct entry errors: quantity, unit price, support buying/increasing positions/reducing positions/selling)"""
    try:
        service = get_portfolio_service()
        result = await service.update_position_change(
            user_id=current_user["id"],
            change_id=change_id,
            quantity=data.quantity,
            price=data.price,
            trade_time=data.trade_time
        )
        return ok(data=result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to modify single cost: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/position-changes/{change_id}", response_model=dict)
async def delete_position_change(
    change_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a single change record and recalculate subsequent records in cascade"""
    try:
        service = get_portfolio_service()
        result = await service.delete_position_change(
            user_id=current_user["id"],
            change_id=change_id
        )
        return ok(data=result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete change record: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/reset", response_model=dict)
async def reset_position(
    code: str = Query(..., description="Stock code"),
    market: str = Query("CN", description="market: CN/HK/US"),
    current_user: dict = Depends(get_current_user)
):
    """Reset entire position: delete all change records and positions for this stock"""
    try:
        service = get_portfolio_service()
        result = await service.reset_position(
            user_id=current_user["id"],
            code=code,
            market=market
        )
        return ok(data=result)
    except Exception as e:
        logger.error(f"Failed to reset position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/positions/reset-all", response_model=dict)
async def reset_all_positions(
    current_user: dict = Depends(get_current_user)
):
    """Clear all positions: delete all positions and change records of this user"""
    try:
        service = get_portfolio_service()
        result = await service.reset_all_positions(user_id=current_user["id"])
        return ok(data=result)
    except Exception as e:
        logger.error(f"Failed to clear all positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
_snapshots['portfolio'] = dict(globals())

# === paper.py ===
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging
import re

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok
from app.services.database.serialization import serialize_document

router = APIRouter(prefix="/paper", tags=["paper"])
logger = logging.getLogger("webapi")

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


# Initial capital allocation per market
INITIAL_CASH_BY_MARKET = {
    "CNY": 1_000_000.0,   # A Shares: 1 million RMB
    "HKD": 1_000_000.0,   # Hong Kong stocks: HKD 1 million
    "USD": 100_000.0      # U.S. stocks: $100,000
}


class PlaceOrderRequest(BaseModel):
    code: str = Field(..., description="Stock code (supports A shares/ETF/Hong Kong stocks/US stocks)")
    side: Literal["buy", "sell"]
    quantity: int = Field(..., gt=0)
    market: Optional[str] = Field(None, description="market type (CN/ETF/HK/US), If not passed, it will be automatically recognized.")
    # Optional: Specify price (if not specified, current real-time price is used)
    price: Optional[float] = Field(None, description="Specify price (must be between the highest and lowest price of the day)")
    # Optional: associated analysis ID to facilitate tracking after placing an order with one click from the analysis page
    analysis_id: Optional[str] = None


def _detect_market_and_code(code: str) -> Tuple[str, str]:
    """
    Detect the market type of a ticker and standardize the ticker

    Returns:
        (market, normalized_code): Market types and standardized codes
            - CN: A Share (6 digits)
            - HK: Hong Kong stocks (4-5 digits or with .HK suffix)
            - US: US stocks (letter code)
    """
    code = code.strip().upper()

    # Hong Kong stocks: with .HK suffix
    if code.endswith('.HK'):
        return ('HK', code[:-3].zfill(5))

    # US stocks: pure letters
    if re.match(r'^[A-Z]+$', code):
        return ('US', code)

    # Hong Kong stocks: 4-5 digits
    if re.match(r'^\d{4,5}$', code):
        return ('HK', code.zfill(5))

    # A Share: 6 digits
    if re.match(r'^\d{6}$', code):
        return ('CN', code)

    # By default, it is treated as A shares, and 6 digits are added.
    return ('CN', code.zfill(6))


def _is_cn_etf_symbol(code: str) -> bool:
    code_str = str(code or "").strip().upper().zfill(6)
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _resolve_market_and_code(code: str, market: Optional[str] = None) -> Tuple[str, str, bool]:
    normalized_code = str(code or "").strip().upper()
    requested_market = str(market or "").strip().upper()

    if requested_market == "ETF":
        normalized_code = normalized_code.zfill(6)
        return "CN", normalized_code, True

    if requested_market in {"CN", "HK", "US"}:
        if requested_market == "CN":
            normalized_code = normalized_code.zfill(6)
        elif requested_market == "HK" and normalized_code.endswith('.HK'):
            normalized_code = normalized_code[:-3].zfill(5)
        return requested_market, normalized_code, requested_market == "CN" and _is_cn_etf_symbol(normalized_code)

    detected_market, normalized_code = _detect_market_and_code(code)
    is_etf = detected_market == "CN" and _is_cn_etf_symbol(normalized_code)
    return detected_market, normalized_code, is_etf


async def _get_or_create_account(user_id: str) -> Dict[str, Any]:
    """Get or create an account (multi-currency)"""
    db = get_mongo_db()
    acc = await db["paper_accounts"].find_one({"user_id": user_id})
    if not acc:
        now = datetime.utcnow().isoformat()
        acc = {
            "user_id": user_id,
            # Multi-currency cash account
            "cash": {
                "CNY": INITIAL_CASH_BY_MARKET["CNY"],
                "HKD": INITIAL_CASH_BY_MARKET["HKD"],
                "USD": INITIAL_CASH_BY_MARKET["USD"]
            },
            # Achieved profit and loss in multiple currencies
            "realized_pnl": {
                "CNY": 0.0,
                "HKD": 0.0,
                "USD": 0.0
            },
            # Account settings
            "settings": {
                "auto_currency_conversion": False,
                "default_market": "CN"
            },
            "created_at": now,
            "updated_at": now,
        }
        await db["paper_accounts"].insert_one(acc)
    else:
        # Compatible with old account structures: if cash or realized_pnl are still scalars, migrate to multi-currency objects
        updates: Dict[str, Any] = {}
        try:
            cash_val = acc.get("cash")
            if not isinstance(cash_val, dict):
                base_cash = float(cash_val or 0.0)
                updates["cash"] = {"CNY": base_cash, "HKD": 0.0, "USD": 0.0}

            pnl_val = acc.get("realized_pnl")
            if not isinstance(pnl_val, dict):
                base_pnl = float(pnl_val or 0.0)
                updates["realized_pnl"] = {"CNY": base_pnl, "HKD": 0.0, "USD": 0.0}

            if updates:
                updates["updated_at"] = datetime.utcnow().isoformat()
                await db["paper_accounts"].update_one({"user_id": user_id}, {"$set": updates})
                # Reread migrated accounts
                acc = await db["paper_accounts"].find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"❌ Account structure migration failed user_id={user_id}: {e}")

    if acc:
        acc = serialize_document(acc)

    return acc


async def _get_market_rules(market: str) -> Optional[Dict[str, Any]]:
    """Get market rule configuration"""
    db = get_mongo_db()
    rules_doc = await db["paper_market_rules"].find_one({"market": market})
    if rules_doc:
        return rules_doc.get("rules", {})
    return None


def _calculate_commission(market: str, side: str, amount: float, rules: Dict[str, Any]) -> float:
    """Calculate handling fees"""
    if not rules or "commission" not in rules:
        return 0.0

    commission_config = rules["commission"]
    commission = 0.0

    # Commission
    comm_rate = commission_config.get("rate", 0.0)
    comm_min = commission_config.get("min", 0.0)
    commission += max(amount * comm_rate, comm_min)

    # Stamp duty (sale only)
    if side == "sell" and "stamp_duty_rate" in commission_config:
        commission += amount * commission_config["stamp_duty_rate"]

    # Other expenses (Hong Kong stocks)
    if market == "HK":
        if "transaction_levy_rate" in commission_config:
            commission += amount * commission_config["transaction_levy_rate"]
        if "trading_fee_rate" in commission_config:
            commission += amount * commission_config["trading_fee_rate"]
        if "settlement_fee_rate" in commission_config:
            commission += amount * commission_config["settlement_fee_rate"]

    # SEC Fees (US stocks, sell only)
    if market == "US" and side == "sell" and "sec_fee_rate" in commission_config:
        commission += amount * commission_config["sec_fee_rate"]

    return round(commission, 2)


async def _get_available_quantity(user_id: str, code: str, market: str) -> int:
    """Get the available quantity (consider T+1 restrictions)"""
    db = get_mongo_db()
    pos = await db["paper_positions"].find_one({"user_id": user_id, "code": code})

    if not pos:
        return 0

    total_qty = pos.get("quantity", 0)

    # A shares T+1: What you bought today cannot be sold
    if market == "CN":
        # Get market rules
        rules = await _get_market_rules(market)
        if rules and rules.get("t_plus", 0) > 0:
            # Check today's buying quantity
            today = datetime.utcnow().date().isoformat()
            pipeline = [
                {"$match": {
                    "user_id": user_id,
                    "code": code,
                    "side": "buy",
                    "timestamp": {"$gte": today}
                }},
                {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
            ]
            today_buy = await db["paper_trades"].aggregate(pipeline).to_list(1)
            today_buy_qty = today_buy[0]["total"] if today_buy else 0
            return max(0, total_qty - today_buy_qty)

    # Hong Kong stocks/US stocks T+0: All available
    return total_qty


async def _get_stock_name(code: str, market: str) -> str:
    """
    Get stock name (supports multiple markets)

    - A Stock: Obtained from stock_basic_info table
    - Hong Kong stocks/US stocks: use ForeignStockService.get_quote() (name field included)

    Args:
        code: Stock code
        market: market type (CN/HK/US)

    Returns:
        Stock name
    """
    try:
        # A Stock: Obtained from stock_basic_info
        if market in {"CN", "ETF"}:
            db = get_mongo_db()
            code6 = str(code or "").strip().zfill(6)
            stock_info = await db["stock_basic_info"].find_one({
                "$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]
            })
            if stock_info and stock_info.get("name"):
                return stock_info.get("name")
            etf_info = await db["etf_basic_info"].find_one({"code": code6}, {"_id": 0, "name": 1})
            if etf_info and etf_info.get("name"):
                return etf_info.get("name")
            return f"A shares{code}"

        # Hong Kong stocks/US stocks: Use ForeignStockService (reuse the obtained market data)
        elif market in ["HK", "US"]:
            try:
                from app.services.foreign_stock_service import ForeignStockService
                db = get_mongo_db()
                service = ForeignStockService(db=db)

                # Get market information (will be read from the cache first to avoid repeated API calls)
                quote = await service.get_quote(market, code, force_refresh=False)

                if quote and quote.get("name"):
                    name = quote.get("name")
                    # Avoid returning names in default format
                    if not name.startswith("Hong Kong stocks") and not name.startswith("US stocks"):
                        return name

                return f"{'Hong Kong stocks' if market == 'HK' else 'US stocks'}{code}"
            except Exception as e:
                logger.warning(f"⚠️ {market}Failed to obtain stock name {code}: {e}")
                return f"{'Hong Kong stocks' if market == 'HK' else 'US stocks'}{code}"

        else:
            return f"stocks{code}"

    except Exception as e:
        logger.error(f"❌ Failed to get stock name {code} ({market}): {e}")
        return f"stocks{code}"


async def _get_last_price(code: str, market: str) -> Optional[float]:
    """
    Get the latest stock price (supports multiple markets)

    Args:
        code: Stock code
        market: market type (CN/HK/US)

    Returns:
        The latest price, returned if the acquisition fails None
    """
    db = get_mongo_db()

    # A Shares: obtained from database
    if market in {"CN", "ETF"}:
        code6 = str(code or "").strip().zfill(6)
        # 1. Try to get from market_quotes
        q = await db["market_quotes"].find_one(
            {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
            {"_id": 0, "close": 1}
        )
        if q and q.get("close") is not None:
            try:
                price = float(q["close"])
                if price > 0:
                    logger.debug(f"✅ Get prices from market_quotes: {code} = {price}")
                    return price
            except Exception as e:
                logger.warning(f"⚠️ market_quotes Price conversion failed {code}: {e}")

        # 2. Fallback to stock_basic_info current_price
        basic_info = await db["stock_basic_info"].find_one(
            {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
            {"_id": 0, "current_price": 1}
        )
        if basic_info and basic_info.get("current_price") is not None:
            try:
                price = float(basic_info["current_price"])
                if price > 0:
                    logger.debug(f"✅ Get prices from stock_basic_info: {code} = {price}")
                    return price
            except Exception as e:
                logger.warning(f"⚠️ stock_basic_info Price conversion failed {code}: {e}")

        etf_daily = await db["etf_daily_quotes"].find_one(
            {"code": code6},
            sort=[("trade_date", -1)],
            projection={"_id": 0, "close": 1}
        )
        if etf_daily and etf_daily.get("close") is not None:
            try:
                price = float(etf_daily["close"])
                if price > 0:
                    logger.debug(f"✅ Get prices from etf_daily_quotes: {code6} = {price}")
                    return price
            except Exception as e:
                logger.warning(f"⚠️ etf_daily_quotes Price conversion failed {code6}: {e}")

        logger.error(f"❌ Unable to obtain A-share/ETF price from database: {code}")
        return None

    # Hong Kong stocks/US stocks: use ForeignStockService
    elif market in ['HK', 'US']:
        try:
            from app.services.foreign_stock_service import ForeignStockService
            db = get_mongo_db()
            service = ForeignStockService(db=db)

            quote = await service.get_quote(market, code, force_refresh=False)

            if quote:
                # Try multiple possible price fields
                price = quote.get("price") or quote.get("current_price") or quote.get("close")
                if price and float(price) > 0:
                    logger.debug(f"✅ Get from ForeignStockService{market}price: {code} = {price}")
                    return float(price)
        except Exception as e:
            logger.error(f"❌ get{market}stock price failure {code}: {e}")
            return None

    logger.error(f"❌ Unable to get stock price: {code} (market={market})")
    return None


async def _get_today_price_range(code: str, market: str) -> Optional[Dict[str, float]]:
    """
    Get the highest and lowest price of the stock on the day (supports multiple markets)

    Args:
        code: Stock code
        market: market type (CN/HK/US)

    Returns:
        A dictionary containing high and low, returned if acquisition fails None
    """
    db = get_mongo_db()

    # A Shares: obtained from market_quotes
    if market in {"CN", "ETF"}:
        code6 = str(code or "").strip().zfill(6)
        q = await db["market_quotes"].find_one(
            {"$or": [{"code": code}, {"code": code6}, {"symbol": code}, {"symbol": code6}]},
            {"_id": 0, "high": 1, "low": 1}
        )
        if q:
            try:
                high = float(q.get("high", 0)) if q.get("high") is not None else None
                low = float(q.get("low", 0)) if q.get("low") is not None else None
                if high is not None and low is not None and high > 0 and low > 0:
                    logger.debug(f"✅ Get price range from market_quotes: {code} = high:{high}, low:{low}")
                    return {"high": high, "low": low}
            except Exception as e:
                logger.warning(f"⚠️ market_quotes Price range conversion failed {code}: {e}")

        etf_daily = await db["etf_daily_quotes"].find_one(
            {"code": code6},
            sort=[("trade_date", -1)],
            projection={"_id": 0, "high": 1, "low": 1, "open": 1, "close": 1}
        )
        if etf_daily:
            try:
                high = etf_daily.get("high")
                low = etf_daily.get("low")
                if high is None or low is None:
                    open_price = etf_daily.get("open")
                    close_price = etf_daily.get("close")
                    if open_price is not None and close_price is not None:
                        high = max(float(open_price), float(close_price))
                        low = min(float(open_price), float(close_price))
                high_val = float(high) if high is not None else None
                low_val = float(low) if low is not None else None
                if high_val is not None and low_val is not None and high_val > 0 and low_val > 0:
                    logger.debug(f"✅ Get price range from etf_daily_quotes: {code6} = high:{high_val}, low:{low_val}")
                    return {"high": high_val, "low": low_val}
            except Exception as e:
                logger.warning(f"⚠️ etf_daily_quotes Price range conversion failed {code6}: {e}")

        logger.warning(f"⚠️ Unable to obtain the A-share/ETF price range from the database: {code}")
        return None

    # Hong Kong stocks/US stocks: use ForeignStockService
    elif market in ['HK', 'US']:
        try:
            from app.services.foreign_stock_service import ForeignStockService
            service = ForeignStockService(db=db)

            quote = await service.get_quote(market, code, force_refresh=False)

            if quote:
                high = quote.get("high") or quote.get("day_high")
                low = quote.get("low") or quote.get("day_low")
                if high and low:
                    try:
                        high_val = float(high)
                        low_val = float(low)
                        if high_val > 0 and low_val > 0:
                            logger.debug(f"✅ Get from ForeignStockService{market}price range: {code} = high:{high_val}, low:{low_val}")
                            return {"high": high_val, "low": low_val}
                    except Exception as e:
                        logger.warning(f"⚠️ {market}Stock price range conversion failed {code}: {e}")
        except Exception as e:
            logger.error(f"❌ get{market}stock price range failure {code}: {e}")
            return None

    logger.warning(f"⚠️ Unable to get stock price range: {code} (market={market})")
    return None


def _zfill_code(code: str) -> str:
    s = str(code).strip()
    if len(s) == 6 and s.isdigit():
        return s
    return s.zfill(6)


@router.get("/account", response_model=dict)
async def get_account(current_user: dict = Depends(get_current_user)):
    """Obtain or create a paper account, return funds and position valuation summary (supports multiple markets)"""
    db = get_mongo_db()
    acc = await _get_or_create_account(current_user["id"])

    # Aggregated position valuation by currency
    positions = await db["paper_positions"].find({"user_id": current_user["id"]}).to_list(None)

    positions_value_by_currency = {
        "CNY": 0.0,
        "HKD": 0.0,
        "USD": 0.0
    }

    detailed_positions: List[Dict[str, Any]] = []
    for p in positions:
        code = p.get("code")
        name = p.get("name", "")  # Get stock name from database
        market = p.get("market", "CN")
        currency = p.get("currency", "CNY")
        qty = int(p.get("quantity", 0))
        avg_cost = float(p.get("avg_cost", 0.0))
        available_qty = p.get("available_qty", qty)

        # Get the latest price
        last = await _get_last_price(code, market)
        mkt_value = round((last or 0.0) * qty, 2)
        positions_value_by_currency[currency] += mkt_value

        detailed_positions.append({
            "code": code,
            "name": name,  # Add stock name to response
            "market": market,
            "currency": currency,
            "quantity": qty,
            "available_qty": available_qty,
            "avg_cost": avg_cost,
            "last_price": last,
            "market_value": mkt_value,
            "unrealized_pnl": None if last is None else round((last - avg_cost) * qty, 2)
        })

    # Calculate total assets (displayed separately by currency)
    cash = acc.get("cash", {})
    realized_pnl = acc.get("realized_pnl", {})

    # Compatible with old formats (single cash)
    if not isinstance(cash, dict):
        cash = {"CNY": float(cash), "HKD": 0.0, "USD": 0.0}
    if not isinstance(realized_pnl, dict):
        realized_pnl = {"CNY": float(realized_pnl), "HKD": 0.0, "USD": 0.0}

    summary = {
        "cash": {
            "CNY": round(float(cash.get("CNY", 0.0)), 2),
            "HKD": round(float(cash.get("HKD", 0.0)), 2),
            "USD": round(float(cash.get("USD", 0.0)), 2)
        },
        "realized_pnl": {
            "CNY": round(float(realized_pnl.get("CNY", 0.0)), 2),
            "HKD": round(float(realized_pnl.get("HKD", 0.0)), 2),
            "USD": round(float(realized_pnl.get("USD", 0.0)), 2)
        },
        "positions_value": positions_value_by_currency,
        "equity": {
            "CNY": round(float(cash.get("CNY", 0.0)) + positions_value_by_currency["CNY"], 2),
            "HKD": round(float(cash.get("HKD", 0.0)) + positions_value_by_currency["HKD"], 2),
            "USD": round(float(cash.get("USD", 0.0)) + positions_value_by_currency["USD"], 2)
        },
        "updated_at": acc.get("updated_at"),
    }

    return ok({"account": summary, "positions": detailed_positions})


@router.post("/order", response_model=dict)
async def place_order(payload: PlaceOrderRequest, current_user: dict = Depends(get_current_user)):
    """Submit a market price order and the transaction will be completed immediately at the latest price (supports multiple markets)"""
    db = get_mongo_db()

    # 1. Identify market type
    market, normalized_code, is_etf = _resolve_market_and_code(payload.code, payload.market)

    side = payload.side
    qty = int(payload.quantity)
    analysis_id = payload.analysis_id if hasattr(payload, "analysis_id") else None
    # 🔥 Fix: Get price field directly from Pydantic model (Pydantic model can access the field directly)
    specified_price = payload.price
    
    logger.info(f"📊 [Simulated trading order] Request received: code={normalized_code}, market={market}, is_etf={is_etf}, side={side}, qty={qty}, specified_price={specified_price}")

    # 2. Determine currency
    currency_map = {
        "CN": "CNY",
        "HK": "HKD",
        "US": "USD"
    }
    currency = currency_map.get(market, "CNY")

    # 3. Get an account
    acc = await _get_or_create_account(current_user["id"])

    # 4. get price
    if specified_price is not None and specified_price > 0:
        # 🔥 If a price is specified, verify whether the price is within the range of the highest and lowest prices of the day
        price_range = await _get_today_price_range(normalized_code, market)
        if not price_range:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to get stock {normalized_code} ({market}) of the day s price range, the specified price cannot be verified"
            )
        
        high = price_range.get("high", 0)
        low = price_range.get("low", 0)
        
        if specified_price < low or specified_price > high:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Specify price {specified_price:.2f} Exceeding the price range of the day [{low:.2f}, {high:.2f}], Simulated trading cannot be successful"
            )
        
        price = float(specified_price)
        logger.info(f"✅ [simulated trading] Use specified price: {normalized_code} = {price:.2f} (interval: [{low:.2f}, {high:.2f}])")
    else:
        # No price specified, current real-time price used
        price = await _get_last_price(normalized_code, market)
        if price is None or price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to get stock {normalized_code} ({market}) latest price"
            )
        logger.info(f"✅ [simulated trading] Use real-time prices: {normalized_code} = {price:.2f}")

    # 5. Calculate amount
    notional = round(price * qty, 2)

    # 6. Get market rules and calculate fees
    rules = await _get_market_rules(market)
    commission = _calculate_commission(market, side, notional, rules) if rules else 0.0
    total_cost = notional + commission

    # 7. Get a position
    pos = await db["paper_positions"].find_one({"user_id": current_user["id"], "code": normalized_code})

    now_iso = datetime.utcnow().isoformat()
    realized_pnl_delta = 0.0

    # 8. Execute buying and selling logic
    if side == "buy":
        # Funds check (account using corresponding currency)
        cash = acc.get("cash", {})
        if isinstance(cash, dict):
            available_cash = float(cash.get(currency, 0.0))
        else:
            # Compatible with older formats
            available_cash = float(cash) if currency == "CNY" else 0.0

        if available_cash < total_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Available{currency}Disadvantage: need {total_cost:.2f}, Available {available_cash:.2f}"
            )

        # Deduct funds (from corresponding currency account)
        new_cash = round(available_cash - total_cost, 2)
        await db["paper_accounts"].update_one(
            {"user_id": current_user["id"]},
            {"$set": {f"cash.{currency}": new_cash, "updated_at": now_iso}}
        )

        # Update/Create Position: Weighted Average Cost
        if not pos:
            # Get stock name (according to market type)
            stock_name = await _get_stock_name(normalized_code, market)

            new_pos = {
                "user_id": current_user["id"],
                "code": normalized_code,
                "name": stock_name,  # Add stock name
                "market": market,
                "currency": currency,
                "quantity": qty,
                "available_qty": qty if market != "CN" else 0,  # A shares T+1, Not available for buying today
                "frozen_qty": 0,
                "avg_cost": price,
                "updated_at": now_iso
            }
            await db["paper_positions"].insert_one(new_pos)
        else:
            old_qty = int(pos.get("quantity", 0))
            old_cost = float(pos.get("avg_cost", 0.0))
            new_qty = old_qty + qty
            new_avg = round((old_cost * old_qty + price * qty) / new_qty, 4) if new_qty > 0 else price

            # A shares T+1: Not available for new purchases
            if market == "CN":
                new_available = pos.get("available_qty", old_qty)  # Keep the original available quantity
            else:
                new_available = new_qty  # Hong Kong stocks/US stocks T+0, All available

            await db["paper_positions"].update_one(
                {"_id": pos["_id"]},
                {"$set": {
                    "quantity": new_qty,
                    "available_qty": new_available,
                    "avg_cost": new_avg,
                    "updated_at": now_iso
                }}
            )

    else:  # sell
        # Check available quantities (consider T+1) 
        available_qty = await _get_available_quantity(current_user["id"], normalized_code, market)
        if available_qty < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient available positions: required {qty}, Available {available_qty}"
            )

        old_qty = int(pos.get("quantity", 0))
        avg_cost = float(pos.get("avg_cost", 0.0))
        new_qty = old_qty - qty
        pnl = round((price - avg_cost) * qty, 2)
        realized_pnl_delta = pnl

        # Sales income (added to the corresponding currency account, deducting handling fees)
        net_proceeds = notional - commission
        await db["paper_accounts"].update_one(
            {"user_id": current_user["id"]},
            {
                "$inc": {
                    f"cash.{currency}": net_proceeds,
                    f"realized_pnl.{currency}": realized_pnl_delta
                },
                "$set": {"updated_at": now_iso}
            }
        )

        # Update positions
        if new_qty == 0:
            await db["paper_positions"].delete_one({"_id": pos["_id"]})
        else:
            new_available = max(0, pos.get("available_qty", old_qty) - qty)
            await db["paper_positions"].update_one(
                {"_id": pos["_id"]},
                {"$set": {
                    "quantity": new_qty,
                    "available_qty": new_available,
                    "updated_at": now_iso
                }}
            )

    # 9. Record orders and transactions (concluded)
    order_doc = {
        "user_id": current_user["id"],
        "code": normalized_code,
        "market": market,
        "currency": currency,
        "side": side,
        "quantity": qty,
        "price": price,
        "amount": notional,
        "commission": commission,
        "status": "filled",
        "created_at": now_iso,
        "filled_at": now_iso,
    }
    if analysis_id:
        order_doc["analysis_id"] = analysis_id
    await db["paper_orders"].insert_one(order_doc)

    trade_doc = {
        "user_id": current_user["id"],
        "code": normalized_code,
        "market": market,
        "currency": currency,
        "side": side,
        "quantity": qty,
        "price": price,
        "amount": notional,
        "commission": commission,
        "pnl": realized_pnl_delta if side == "sell" else 0.0,
        "timestamp": now_iso,
    }
    if analysis_id:
        trade_doc["analysis_id"] = analysis_id
    await db["paper_trades"].insert_one(trade_doc)

    return ok({"order": {k: v for k, v in order_doc.items() if k != "_id"}})


@router.get("/positions", response_model=dict)
async def list_positions(current_user: dict = Depends(get_current_user)):
    """Get the position list (supports multiple markets)"""
    db = get_mongo_db()
    items = await db["paper_positions"].find({"user_id": current_user["id"]}).to_list(None)
    enriched: List[Dict[str, Any]] = []
    for p in items:
        code = p.get("code")
        name = p.get("name", "")  # Get stock name from database
        market = p.get("market", "CN")
        currency = p.get("currency", "CNY")
        qty = int(p.get("quantity", 0))
        available_qty = p.get("available_qty", qty)
        avg_cost = float(p.get("avg_cost", 0.0))

        last = await _get_last_price(code, market)
        mkt = round((last or 0.0) * qty, 2)
        enriched.append({
            "code": code,
            "name": name,  # Add stock name to response
            "market": market,
            "currency": currency,
            "quantity": qty,
            "available_qty": available_qty,
            "avg_cost": avg_cost,
            "last_price": last,
            "market_value": mkt,
            "unrealized_pnl": None if last is None else round((last - avg_cost) * qty, 2)
        })
    return ok({"items": enriched})


@router.get("/orders", response_model=dict)
async def list_orders(limit: int = Query(50, ge=1, le=200), current_user: dict = Depends(get_current_user)):
    db = get_mongo_db()
    cursor = db["paper_orders"].find({"user_id": current_user["id"]}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(None)
    # remove _id
    cleaned = [{k: v for k, v in it.items() if k != "_id"} for it in items]
    return ok({"items": cleaned})


@router.get("/quote/{code}", response_model=dict)
async def get_quote(
    code: str,
    market: Optional[str] = Query(None, description="market type (CN/ETF/HK/US), If not passed, it will be automatically recognized."),
    current_user: dict = Depends(get_current_user)
):
    """Get stock price information (current price and today s price range)"""
    # 1. Identify market type
    market, normalized_code, is_etf = _resolve_market_and_code(code, market)
    
    # 2. Get current price
    current_price = await _get_last_price(normalized_code, market)
    
    # 3. Get the price range of the day
    price_range = await _get_today_price_range(normalized_code, market)
    
    return ok({
        "code": normalized_code,
        "market": "ETF" if is_etf else market,
        "current_price": current_price,
        "high": price_range.get("high") if price_range else None,
        "low": price_range.get("low") if price_range else None
    })


class InitializeAccountRequest(BaseModel):
    """Initialize account request (set initial amount)"""
    initial_cash: Dict[str, float] = Field(
        default_factory=lambda: {
            "CNY": INITIAL_CASH_BY_MARKET["CNY"],
            "HKD": INITIAL_CASH_BY_MARKET["HKD"],
            "USD": INITIAL_CASH_BY_MARKET["USD"]
        },
        description="Initial capital for each market (CNY/HKD/USD)"
    )


class ResetAccountRequest(BaseModel):
    """Reset account request"""
    initial_cash: Optional[Dict[str, float]] = Field(
        None,
        description="Initial funds after reset (CNY/HKD/USD), if not provided, the default value will be used"
    )


@router.post("/initialize", response_model=dict)
async def initialize_account(
    request: InitializeAccountRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Initialize account (set initial amount)
    
    If the account already exists, the initial amount will be updated (clear positions and orders, reset to the specified amount)
    If the account does not exist, a new account will be created
    """
    db = get_mongo_db()
    user_id = current_user["id"]
    
    # Verification amount
    initial_cash = request.initial_cash
    for currency, amount in initial_cash.items():
        if amount < 0:
            raise HTTPException(status_code=400, detail=f"{currency} The initial amount cannot be negative")
    
    # Check if the account exists
    existing_acc = await db["paper_accounts"].find_one({"user_id": user_id})
    
    if existing_acc:
        # The account already exists, clear positions and orders, and reset to the specified amount
        await db["paper_positions"].delete_many({"user_id": user_id})
        await db["paper_orders"].delete_many({"user_id": user_id})
        await db["paper_trades"].delete_many({"user_id": user_id})
        
        now = datetime.utcnow().isoformat()
        update_data = {
            "cash": initial_cash,
            "realized_pnl": {
                "CNY": 0.0,
                "HKD": 0.0,
                "USD": 0.0
            },
            "updated_at": now
        }
        await db["paper_accounts"].update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        logger.info(f"✅ Account has been initialized: user_id={user_id}, initial_cash={initial_cash}")
    else:
        # Account does not exist, create a new account
        now = datetime.utcnow().isoformat()
        acc = {
            "user_id": user_id,
            "cash": initial_cash,
            "realized_pnl": {
                "CNY": 0.0,
                "HKD": 0.0,
                "USD": 0.0
            },
            "settings": {
                "auto_currency_conversion": False,
                "default_market": "CN"
            },
            "created_at": now,
            "updated_at": now,
        }
        await db["paper_accounts"].insert_one(acc)
        logger.info(f"✅ Account has been created: user_id={user_id}, initial_cash={initial_cash}")
    
    # Return to updated account
    acc = await _get_or_create_account(user_id)
    return ok({
        "message": "Account has been initialized",
        "cash": acc.get("cash", {}),
        "account": acc
    })


@router.post("/reset", response_model=dict)
async def reset_account(
    confirm: bool = Query(False),
    request: Optional[ResetAccountRequest] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Reset account (supports multiple currencies and custom initial amounts)
    
    If initial_cash is provided, the specified amount is used; otherwise the default amount is used
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Please set confirm=true to confirm reset")
    
    db = get_mongo_db()
    user_id = current_user["id"]
    
    # Determine the initial amount after reset
    if request and request.initial_cash:
        initial_cash = request.initial_cash
        # Verification amount
        for currency, amount in initial_cash.items():
            if amount < 0:
                raise HTTPException(status_code=400, detail=f"{currency} The initial amount cannot be negative")
    else:
        # Use default amount
        initial_cash = INITIAL_CASH_BY_MARKET.copy()
    
    # Clear all data
    await db["paper_accounts"].delete_many({"user_id": user_id})
    await db["paper_positions"].delete_many({"user_id": user_id})
    await db["paper_orders"].delete_many({"user_id": user_id})
    await db["paper_trades"].delete_many({"user_id": user_id})
    
    # Recreate account (with specified initial amount)
    now = datetime.utcnow().isoformat()
    acc = {
        "user_id": user_id,
        "cash": initial_cash,
        "realized_pnl": {
            "CNY": 0.0,
            "HKD": 0.0,
            "USD": 0.0
        },
        "settings": {
            "auto_currency_conversion": False,
            "default_market": "CN"
        },
        "created_at": now,
        "updated_at": now,
    }
    await db["paper_accounts"].insert_one(acc)
    
    logger.info(f"✅ Account has been reset: user_id={user_id}, initial_cash={initial_cash}")
    return ok({"message": "Account has been reset", "cash": acc.get("cash", {})})


# ==================== Market rules configuration API ====================

@router.get("/market-rules")
async def get_market_rules():
    """Get trading rule configurations for all markets"""
    db = get_mongo_db()
    rules = await db["paper_market_rules"].find({}, {"_id": 0}).to_list(None)
    if not rules:
        # If there is no configuration, return to the default value (the scripts directory is deleted in the community version, and if missing, it returns empty and prompts for initialization)
        try:
            from scripts.init_paper_trading_market_rules import MARKET_RULES
            return ok(MARKET_RULES)
        except ImportError:
            return ok([])
    return ok(rules)


class CommissionUpdateRequest(BaseModel):
    rules: List[Dict[str, Any]] = Field(..., description="Commission allocation for each market")


@router.post("/market-rules/commission")
async def update_market_rules_commission(req: CommissionUpdateRequest):
    """Update commission allocation for each market"""
    db = get_mongo_db()
    updated = 0
    for item in req.rules:
        market = item.get("market")
        commission = item.get("commission", {})
        if not market:
            continue
        # Only update the commission part and keep other rules
        result = await db["paper_market_rules"].update_one(
            {"market": market},
            {"$set": {f"rules.commission.{k}": v for k, v in commission.items()}}
        )
        if result.modified_count > 0:
            updated += 1
        elif result.matched_count == 0:
            # Market rules do not exist, create basic records
            logger.warning(f"market {market} Rule does not exist, skip commission configuration update")

    logger.info(f"✅ Update commission configuration: {updated} market")
    return ok({"message": f"updated {updated} Commission allocation for each market", "updated": updated})
_snapshots['paper'] = dict(globals())

# === review.py ===
"""
Transaction review API routing
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from app.routers.auth_db import get_current_user
from app.core.permissions import get_license_info
from app.core.response import ok
from app.services.license_service import LicenseInfo, get_license_service
from app.services.trade_review_service import get_trade_review_service
from app.models.review import (
    CreateTradeReviewRequest, CreatePeriodicReviewRequest,
    SaveAsCaseRequest, ReviewType
)

router = APIRouter(
    prefix="/review",
    tags=["review"]
)
logger = logging.getLogger("webapi.review")


# ==================== Transaction review ====================

@router.post("/trade", response_model=Dict[str, Any])
async def create_trade_review(
    request: CreateTradeReviewRequest,
    current_user: dict = Depends(get_current_user),
    license_info: LicenseInfo = Depends(get_license_info)
):
    """
    Create a transaction review task (uniformly use the task center mode)

    - **trade_ids**: List of transaction IDs to be reviewed
    - **review_type**: Review type (single_trade/complete_trade)
    - **code**: Stock code (optional, if not passed, it will be inferred from transaction records)
    - **use_workflow**: Whether to use workflow engine (default True, recommended)

    Mission Center Mode Features:
    - Immediately return the task ID and perform review in the background
    - The front end can pass GET /api/v1/analysis/tasks/{task_id} Query progress
    - Supports real-time progress tracking
    - Multi-agent collaborative analysis using workflow engines

    Reference: analyze_position_by_code implementation of app/routers/portfolio.py
    """
    import asyncio

    import asyncio

    try:
        logger.info(f"📝 [Transaction review routing] Receive review request: code={request.code}, trade_ids={request.trade_ids}")
        logger.info("🔧 [Transaction review routing] Unified use of task center mode")

        if request.trading_system_id:
            license_service = get_license_service()
            if not license_service.has_feature(license_info, "trading_plan_check"):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "FEATURE_REQUIRED",
                        "message": "Trading plan consistency check is exclusive for advanced students",
                        "feature": "trading_plan_check",
                        "plan": license_info.plan,
                        "upgrade_url": "/settings/license"
                    }
                )

        # 🆕 Unified use of task center mode (supports progress query)
        logger.info("=" * 60)
        logger.info("🎯 [Transaction review routing] Enter mission center mode")
        logger.info("=" * 60)

        from app.services.unified_analysis_service import get_unified_analysis_service

        logger.info("🔄 [Transaction review routing] Get UnifiedAnalysisService instance...")
        unified_service = get_unified_analysis_service()
        logger.info("✅ [Transaction review routing] Get the UnifiedAnalysisService instance")

        # Create task (return immediately)
        logger.info("🔄 [Transaction review routing] Start creating tasks...")
        logger.info(f"   📋 user_id: {current_user['id']}")
        logger.info(f"   📋 code: {request.code}")
        logger.info(f"   📋 trade_ids: {request.trade_ids}")
        logger.info(f"   📋 review_type: {request.review_type}")

        result = await unified_service.create_trade_review_task(
            user_id=current_user["id"],
            request=request
        )
        logger.info("✅ [Transaction review routing] Task created successfully")
        logger.info(f"   📋 task_id: {result['task_id']}")
        logger.info(f"   📋 status: {result['status']}")
        logger.info(f"   📋 message: {result['message']}")

        # In order to be compatible with the front end, the review_id field (equal to task_id) is also returned.
        result["review_id"] = result["task_id"]
        logger.info(f"   📋 review_id (Compatible fields): {result['review_id']}")

        # Perform review in the background
        logger.info("🚀 [Transaction review routing] Start background task execution...")
        logger.info("   📋 This will be executed asynchronously in the background without blocking the current request")

        asyncio.create_task(
            unified_service.execute_trade_review(
                task_id=result["task_id"],
                user_id=current_user["id"],
                request=request
            )
        )
        logger.info("✅ [Transaction review routing] Background task started")
        logger.info(f"   📋 The client can pass /api/v1/analysis/tasks/{result['task_id']} Query progress")
        logger.info("=" * 60)

        return ok(data=result, message="The transaction review task has been submitted and is expected to take 1-3 minutes to complete.")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create transaction review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create a replica: {str(e)}")


@router.get("/trade/history", response_model=Dict[str, Any])
async def get_review_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    code: Optional[str] = Query(None, description="Stock code filter"),
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
    review_type: Optional[str] = Query(None, description="Review type filter"),
    source: Optional[str] = Query(None, description="Data source filtering: paper(simulated trading) or position(Position operation)"),
    current_user: dict = Depends(get_current_user)
):
    """Obtain the review history list and support filtering by stock code, time period, review type, and data source."""
    try:
        service = get_trade_review_service()
        result = await service.get_review_history(
            user_id=current_user["id"],
            page=page,
            page_size=page_size,
            code=code,
            start_date=start_date,
            end_date=end_date,
            review_type=review_type,
            source=source
        )
        return ok(result)
    except Exception as e:
        logger.error(f"Failed to obtain review history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade/{review_id}", response_model=Dict[str, Any])
async def get_review_detail(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get review details"""
    try:
        service = get_trade_review_service()
        result = await service.get_review_detail(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="The review report does not exist")
        
        return ok({
            "review_id": result.review_id,
            "review_type": result.review_type.value,
            "status": result.status.value,
            "trade_info": result.trade_info.model_dump(),
            "market_snapshot": result.market_snapshot.model_dump(),
            "ai_review": result.ai_review.model_dump(),
            "is_case_study": result.is_case_study,
            "tags": result.tags,
            "execution_time": result.execution_time,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "trading_system_id": result.trading_system_id,  # 🆕 Add trading plan ID
            "trading_system_name": result.trading_system_name  # 🆕 Add trading plan name
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to obtain review details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Review summary (for stock details page use) ====================

@router.get("/summary", response_model=Dict[str, Any])
async def get_review_summary(
    code: str = Query(..., description="Stock code (e.g. 601919)"),
    current_user: dict = Depends(get_current_user)
):
    """Get the latest review summary by stock code (for display on the stock details page)"""
    try:
        logger.info(f"[review.py] get_review_summary called: code={code}, user_id={current_user.get('id')}")
        service = get_trade_review_service()
        result = await service.get_review_summary_by_stock(
            user_id=current_user["id"],
            stock_code=code
        )
        return ok(result or {"has": False})
    except Exception as e:
        logger.error(f"Failed to obtain review summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Case library ====================

@router.post("/case", response_model=Dict[str, Any])
async def save_as_case(
    request: SaveAsCaseRequest,
    current_user: dict = Depends(get_current_user)
):
    """Save as case"""
    try:
        logger.info(f"📝 [save case] Request received: review_id={request.review_id}, user_id={current_user.get('id')}, tags={request.tags}, source={request.source}")
        service = get_trade_review_service()
        success = await service.save_as_case(
            user_id=current_user["id"],
            review_id=request.review_id,
            tags=request.tags,
            source=request.source  # Pass the source parameter
        )
        if not success:
            logger.warning(f"⚠️ [save case] The review report does not exist: review_id={request.review_id}")
            raise HTTPException(status_code=404, detail="The review report does not exist")
        logger.info(f"✅ [save case] success: review_id={request.review_id}")
        return ok({"message": "Saved as case"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [save case] failed: review_id={request.review_id}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases", response_model=Dict[str, Any])
async def get_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    source: str = Query(None, description="Data source filtering: paper(simulated trading) or position(Position operation)"),
    current_user: dict = Depends(get_current_user)
):
    """Get case library"""
    try:
        service = get_trade_review_service()
        result = await service.get_cases(
            user_id=current_user["id"],
            page=page,
            page_size=page_size,
            source=source
        )
        return ok(result)
    except Exception as e:
        logger.error(f"Failed to obtain case library: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/case/{review_id}", response_model=Dict[str, Any])
async def delete_case(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove from case library"""
    try:
        service = get_trade_review_service()
        success = await service.delete_case(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Case does not exist")
        return ok({"message": "Removed from case library"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete case failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/trade/{review_id}", response_model=Dict[str, Any])
async def delete_review(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete review record"""
    try:
        service = get_trade_review_service()
        success = await service.delete_review(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="The review record does not exist")
        return ok({"message": "The review record has been deleted"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete redo record: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Transaction statistics ====================

@router.get("/statistics", response_model=Dict[str, Any])
async def get_trading_statistics(
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user)
):
    """Get transaction statistics"""
    try:
        service = get_trade_review_service()
        stats = await service.get_trading_statistics(
            user_id=current_user["id"],
            start_date=start_date,
            end_date=end_date
        )
        return ok(stats.model_dump())
    except Exception as e:
        logger.error(f"Failed to obtain transaction statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Periodic review ====================

@router.post("/periodic", response_model=Dict[str, Any])
async def create_periodic_review(
    request: CreatePeriodicReviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a staged review

    - **period_type**: Review cycle type (week/month/quarter/year)
    - **start_date**: start date YYYY-MM-DD
    - **end_date**: end date YYYY-MM-DD
    """
    try:
        service = get_trade_review_service()
        result = await service.create_periodic_review(
            user_id=current_user["id"],
            request=request
        )
        return ok({
            "review_id": result.review_id,
            "status": result.status.value,
            "period_type": result.period_type.value,
            "period_start": result.period_start.isoformat() if result.period_start else None,
            "period_end": result.period_end.isoformat() if result.period_end else None,
            "statistics": result.statistics.model_dump() if result.statistics else None,
            "ai_review": result.ai_review.model_dump() if result.ai_review else None,
            "execution_time": result.execution_time,
            "created_at": result.created_at.isoformat() if result.created_at else None
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create staged review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create staged review: {str(e)}")


@router.get("/periodic/history", response_model=Dict[str, Any])
async def get_periodic_review_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    source: str = Query(None, description="Data source filtering: paper(simulated trading) or position(Position operation)"),
    current_user: dict = Depends(get_current_user)
):
    """Get the periodic review history list"""
    try:
        service = get_trade_review_service()
        result = await service.get_periodic_review_history(
            user_id=current_user["id"],
            page=page,
            page_size=page_size,
            source=source
        )
        return ok(result)
    except Exception as e:
        logger.error(f"Failed to obtain phased review history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodic/{review_id}", response_model=Dict[str, Any])
async def get_periodic_review_detail(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get details of periodic review"""
    try:
        service = get_trade_review_service()
        result = await service.get_periodic_review_detail(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="The periodic review report does not exist")

        return ok({
            "review_id": result.review_id,
            "period_type": result.period_type.value,
            "period_start": result.period_start.isoformat() if result.period_start else None,
            "period_end": result.period_end.isoformat() if result.period_end else None,
            "statistics": result.statistics.model_dump() if result.statistics else None,
            "trades_summary": [t.model_dump() for t in result.trades_summary],
            "ai_review": result.ai_review.model_dump() if result.ai_review else None,
            "status": result.status.value,
            "execution_time": result.execution_time,
            "created_at": result.created_at.isoformat() if result.created_at else None
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to obtain phased review details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Reviewable transaction inquiry ====================

@router.get("/reviewable-trades", response_model=Dict[str, Any])
async def get_reviewable_trades(
    code: Optional[str] = Query(None, description="Stock code filter"),
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a list of transactions that can be reviewed

    Returns the user s selling transaction record, which can be used to select a review
    Supports filtering by stock code and time period
    """
    try:
        from app.core.database import get_mongo_db
        from datetime import datetime
        db = get_mongo_db()

        # Build query conditions
        query = {"user_id": current_user["id"]}
        if code:
            query["code"] = code

        # Time period filter
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                # The end date includes today, so add one day
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query["timestamp"]["$lte"] = end_dt

        skip = (page - 1) * page_size

        # Get transaction records
        cursor = db["paper_trades"].find(query).sort("timestamp", -1).skip(skip).limit(page_size)
        trades = await cursor.to_list(None)
        total = await db["paper_trades"].count_documents(query)

        # Format results
        items = []
        for t in trades:
            items.append({
                "trade_id": str(t.get("_id")),
                "code": t.get("code"),
                "market": t.get("market", "CN"),
                "side": t.get("side"),
                "quantity": t.get("quantity"),
                "price": t.get("price"),
                "amount": t.get("amount"),
                "pnl": t.get("pnl", 0),
                "timestamp": t.get("timestamp")
            })

        # Statistics grouped by stocks (using the same filters)
        code_stats = {}
        all_trades = await db["paper_trades"].find(query).to_list(None)
        for t in all_trades:
            c = t.get("code")
            if c not in code_stats:
                code_stats[c] = {
                    "name": "",
                    "market": t.get("market", "CN"),
                    "buy_count": 0,
                    "sell_count": 0,
                    "total_pnl": 0,
                    "total_buy_amount": 0,
                    "total_sell_amount": 0,
                    "last_trade_time": None
                }
            if t.get("side") == "buy":
                code_stats[c]["buy_count"] += 1
                code_stats[c]["total_buy_amount"] += t.get("amount", 0)
            else:
                code_stats[c]["sell_count"] += 1
                code_stats[c]["total_sell_amount"] += t.get("amount", 0)
                code_stats[c]["total_pnl"] += t.get("pnl", 0)

            # Update last transaction time
            trade_time = t.get("timestamp")
            if trade_time:
                # 🔥 Handle dates of string type (MongoDB may return strings)
                if isinstance(trade_time, str):
                    trade_time = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                
                # Make sure last_trade_time is also of type datetime
                last_trade_time = code_stats[c]["last_trade_time"]
                if last_trade_time and isinstance(last_trade_time, str):
                    last_trade_time = datetime.fromisoformat(last_trade_time.replace('Z', '+00:00'))
                
                if not last_trade_time or trade_time > last_trade_time:
                    code_stats[c]["last_trade_time"] = trade_time

        # Get the stock name (first from stock_basic_info, secondly from paper_positions)
        for c in code_stats.keys():
            # 1. Get it from stock_basic_info first (most reliable)
            stock_info = await db["stock_basic_info"].find_one({"code": c})
            if stock_info and stock_info.get("name"):
                code_stats[c]["name"] = stock_info.get("name", "")
            else:
                # 2. Downgrade: obtained from paper_positions
                pos = await db["paper_positions"].find_one({"user_id": current_user["id"], "code": c})
                if pos and pos.get("name"):
                    code_stats[c]["name"] = pos.get("name", "")

        # Find stocks that have completed transactions (bought and sold)
        completed_stocks = [
            {"code": c, **stats}
            for c, stats in code_stats.items()
            if stats["buy_count"] > 0 and stats["sell_count"] > 0
        ]

        # All traded stocks (including those that have only been bought but not sold)
        # status Judgment: Only when the selling quantity >= The position is considered to be completely closed when the quantity is purchased.
        all_stocks = [
            {"code": c, "status": "completed" if stats["sell_count"] >= stats["buy_count"] and stats["sell_count"] > 0 else "holding", **stats}
            for c, stats in code_stats.items()
            if stats["buy_count"] > 0
        ]

        return ok({
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "completed_stocks": completed_stocks,
            "all_stocks": all_stocks  # New: All traded stocks
        })

    except Exception as e:
        logger.error(f"Failed to obtain resumable transactions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades-by-code/{code}", response_model=Dict[str, Any])
async def get_trades_by_code(
    code: str,
    source: str = Query("real", description="data source: real(User positions) or paper(Simulated position)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all transaction records of a certain stock

    Used to select transactions to be reviewed
    - source=real: Get user position operation records from position_changes
    - source=paper: Get simulated trading records from paper_trades
    """
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        items = []

        if source == "paper":
            # Simulated position: obtained from paper_trades
            logger.info(f"📊 Get simulated transaction records: {code}")
            cursor = db["paper_trades"].find({
                "user_id": current_user["id"],
                "code": code
            }).sort("timestamp", 1)

            trades = await cursor.to_list(None)

            for t in trades:
                items.append({
                    "trade_id": str(t.get("_id")),
                    "code": t.get("code"),
                    "market": t.get("market", "CN"),
                    "side": t.get("side"),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "amount": t.get("amount"),
                    "pnl": t.get("pnl", 0),
                    "commission": t.get("commission", 0),
                    "timestamp": t.get("timestamp")
                })
        else:
            # User positions: conversion from position_changes
            logger.info(f"📊 Obtain user position operation records: {code}")
            cursor = db["position_changes"].find({
                "user_id": current_user["id"],
                "code": code
            }).sort("created_at", 1)

            changes = await cursor.to_list(None)
            for c in changes:
                # Convert position_change to trade format
                change_type = c.get("change_type")
                side = "buy" if change_type in ["buy", "add"] else "sell"
                quantity = abs(c.get("quantity_change", 0))
                price = c.get("trade_price") or c.get("cost_price_after", 0)

                # Handle timestamp: use trade_time (actual trade time)
                trade_time = c.get("trade_time")
                if trade_time:
                    # 🔥 Handling type: trade_time may be a string or datetime object
                    if isinstance(trade_time, str):
                        try:
                            # Try to parse ISO format string
                            trade_time = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            # If parsing fails, try other formats
                            try:
                                trade_time = datetime.strptime(trade_time, "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                logger.warning(f"⚠️ Unable to parse trade_time format: {trade_time}")
                                trade_time = None
                    # If it is a datetime object, convert it to an ISO format string
                    if isinstance(trade_time, datetime):
                        timestamp_str = trade_time.isoformat()
                    else:
                        timestamp_str = None
                else:
                    timestamp_str = None

                # Handling pnl: Make sure it is a number, it cannot be None
                pnl = c.get("realized_profit")
                if pnl is None:
                    pnl = 0.0

                items.append({
                    "trade_id": str(c.get("_id")),
                    "code": c.get("code"),
                    "market": c.get("market", "CN"),
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "amount": quantity * price,
                    "pnl": float(pnl),
                    "commission": 0.0,
                    "timestamp": timestamp_str,
                    "change_type": change_type,
                    "quantity_after": c.get("quantity_after"),
                    "created_at": c.get("created_at").isoformat() if c.get("created_at") else None
                })

        # Calculate summary
        total_buy_qty = sum(t["quantity"] for t in items if t["side"] == "buy")
        total_sell_qty = sum(t["quantity"] for t in items if t["side"] == "sell")
        total_pnl = sum(t["pnl"] or 0 for t in items)  # Handling None values

        return ok({
            "code": code,
            "trades": items,
            "summary": {
                "total_trades": len(items),
                "total_buy_quantity": total_buy_qty,
                "total_sell_quantity": total_sell_qty,
                "total_pnl": round(total_pnl, 2),
                "is_closed": total_sell_qty >= total_buy_qty and total_buy_qty > 0
            }
        })

    except Exception as e:
        logger.error(f"Failed to obtain stock transaction records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
_snapshots['review'] = dict(globals())

# === favorites.py ===
"""
Stock Watchlist Management API Routing
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import logging

from app.routers.auth_db import get_current_user
from app.models.user import User, FavoriteStock
from app.services.favorites_service import favorites_service
from app.core.response import ok

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/favorites", tags=["Stock watch list management"], redirect_slashes=False)

FAVORITES_SYNC_TASKS_COLLECTION = "favorites_sync_tasks"


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


async def _create_favorites_sync_task(current_user: dict, payload: Dict[str, Any]) -> Dict[str, Any]:
    db = favorites_service.db
    task_doc = {
        "task_id": uuid4().hex,
        "task_type": "favorites_realtime",
        "status": "pending",
        "message": "Stock watch list real-time market synchronization task has been submitted",
        "payload": payload,
        "user_id": current_user["id"],
        "submitted_by": str(current_user.get("username") or current_user.get("id") or "unknown"),
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    await db[FAVORITES_SYNC_TASKS_COLLECTION].insert_one(task_doc)
    task_doc.pop("_id", None)
    return task_doc


async def _update_favorites_sync_task(task_id: str, updates: Dict[str, Any]) -> None:
    db = favorites_service.db
    await db[FAVORITES_SYNC_TASKS_COLLECTION].update_one(
        {"task_id": task_id},
        {"$set": updates},
        upsert=False,
    )


async def _get_favorites_sync_task(task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    db = favorites_service.db
    task_doc = await db[FAVORITES_SYNC_TASKS_COLLECTION].find_one({"task_id": task_id, "user_id": user_id})
    if task_doc:
        task_doc.pop("_id", None)
    return task_doc


async def _run_favorites_realtime_sync_task(task_id: str, user_id: str, data_source: str) -> None:
    try:
        await _update_favorites_sync_task(
            task_id,
            {
                "status": "running",
                "message": "Stock watch list real-time quotes are being executed simultaneously",
                "started_at": _utc_now_iso(),
                "error": None,
            },
        )

        favorites = await favorites_service.get_user_favorites(user_id)

        if not favorites:
            result = {
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "message": "No stock watchlists to sync",
                "symbols": [],
                "data_source": data_source,
            }
            await _update_favorites_sync_task(
                task_id,
                {
                    "status": "success",
                    "message": result["message"],
                    "finished_at": _utc_now_iso(),
                    "result": result,
                },
            )
            return

        symbols = [fav.get("stock_code") or fav.get("symbol") for fav in favorites]
        symbols = [s for s in symbols if s]

        if data_source == "tushare":
            from app.worker.tushare_sync_service import get_tushare_sync_service
            service = await get_tushare_sync_service()
        elif data_source == "akshare":
            from app.worker.akshare_sync_service import get_akshare_sync_service
            service = await get_akshare_sync_service()
        else:
            raise RuntimeError(f"Unsupported data source: {data_source}")

        if not service:
            raise RuntimeError(f"{data_source} Service unavailable")

        if data_source == "akshare":
            sync_result = await service.sync_realtime_quotes(
                symbols=symbols,
                force=True,
                manual_mode=True,
            )
        else:
            sync_result = await service.sync_realtime_quotes(
                symbols=symbols,
                force=True,
            )

        success_count = sync_result.get("success_count", 0)
        failed_count = sync_result.get("failed_count", 0)
        result = {
            "total": len(symbols),
            "success_count": success_count,
            "failed_count": failed_count,
            "symbols": symbols,
            "data_source": data_source,
            "message": f"Synchronization completed: success {success_count} Only, failed {failed_count} only",
        }

        await _update_favorites_sync_task(
            task_id,
            {
                "status": "success" if failed_count == 0 else "success_with_errors",
                "message": result["message"],
                "finished_at": _utc_now_iso(),
                "result": result,
            },
        )
    except Exception as e:
        logger.error(f"❌ The real-time quotation synchronization task of the stock watch list failed.: {e}", exc_info=True)
        await _update_favorites_sync_task(
            task_id,
            {
                "status": "failed",
                "message": f"Sync failed: {str(e)}",
                "finished_at": _utc_now_iso(),
                "error": str(e),
            },
        )


class AddFavoriteRequest(BaseModel):
    """Add to study list request"""
    stock_code: Optional[str] = None
    symbol: Optional[str] = None
    stock_name: str
    market: str = "A shares"
    tags: List[str] = []
    notes: str = ""
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class UpdateFavoriteRequest(BaseModel):
    """Update stock watchlist request"""
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class FavoriteStockResponse(BaseModel):
    """Stock Watchlist Response"""
    stock_code: str
    stock_name: str
    market: str
    added_at: str
    tags: List[str]
    notes: str
    alert_price_high: Optional[float]
    alert_price_low: Optional[float]
    # real time data
    current_price: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None


@router.get("", response_model=dict)
async def get_favorites(
    current_user: dict = Depends(get_current_user)
):
    """Get the user s stock watchlist list"""
    try:
        favorites = await favorites_service.get_user_favorites(current_user["id"])
        return ok(favorites)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock watchlist: {str(e)}"
        )


@router.post("", response_model=dict)
async def add_favorite(
    request: AddFavoriteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a stock to a stock watchlist"""
    import logging
    logger = logging.getLogger("webapi")

    try:
        stock_code = (request.stock_code or request.symbol or "").strip()
        if not stock_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stock code cannot be empty"
            )

        logger.info(f"📝 Add to study list request: user_id={current_user['id']}, stock_code={stock_code}, stock_name={request.stock_name}")

        # Check if it already exists
        is_fav = await favorites_service.is_favorite(current_user["id"], stock_code)
        logger.info(f"🔍 Check if it already exists: {is_fav}")

        if is_fav:
            logger.warning(f"⚠️ The stock is already in the stock watch list: {stock_code}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The stock is already on the stock watch list"
            )

        # Add to stock watchlist
        logger.info("➕ Start adding to research list...")
        success = await favorites_service.add_favorite(
            user_id=current_user["id"],
            stock_code=stock_code,
            stock_name=request.stock_name,
            market=request.market,
            tags=request.tags,
            notes=request.notes,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low
        )

        logger.info(f"✅ Add results: success={success}")

        if success:
            return ok({"stock_code": stock_code}, "Added successfully")
        else:
            logger.error("❌ Add failed: success=False")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Add failed"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Add to study list exception: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Add to study list failed: {str(e)}"
        )


@router.put("/{stock_code}", response_model=dict)
async def update_favorite(
    stock_code: str,
    request: UpdateFavoriteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update stock watchlist information"""
    try:
        success = await favorites_service.update_favorite(
            user_id=current_user["id"],
            stock_code=stock_code,
            tags=request.tags,
            notes=request.notes,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low
        )

        if success:
            return ok({"stock_code": stock_code}, "Update successful")
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock watch list does not exist"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update stock watchlist: {str(e)}"
        )


@router.delete("/{stock_code}", response_model=dict)
async def remove_favorite(
    stock_code: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove a stock from a stock watchlist"""
    try:
        success = await favorites_service.remove_favorite(current_user["id"], stock_code)

        if success:
            return ok({"stock_code": stock_code}, "Removed successfully")
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock watch list does not exist"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove stock watchlist: {str(e)}"
        )


@router.get("/check/{stock_code}", response_model=dict)
async def check_favorite(
    stock_code: str,
    current_user: dict = Depends(get_current_user)
):
    """Check if a stock is in the stock watchlist"""
    try:
        is_favorite = await favorites_service.is_favorite(current_user["id"], stock_code)
        return ok({"stock_code": stock_code, "is_favorite": is_favorite})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Checking stock watchlist status failed: {str(e)}"
        )


@router.get("/tags", response_model=dict)
async def get_user_tags(
    current_user: dict = Depends(get_current_user)
):
    """Get all tags used by the user"""
    try:
        tags = await favorites_service.get_user_tags(current_user["id"])
        return ok(tags)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tags: {str(e)}"
        )


class SyncFavoritesRequest(BaseModel):
    """Synchronize stock watch list real-time quotation request"""
    data_source: str = "tushare"  # tushare/akshare


@router.post("/sync-realtime", response_model=dict)
async def sync_favorites_realtime(
    request: SyncFavoritesRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Synchronize real-time quotes of stock watchlists

    - **data_source**: Data source (tushare/akshare)
    """
    try:
        logger.info(f"📊 Submit stock watch list real-time market synchronization task: user_id={current_user['id']}, data_source={request.data_source}")

        task_doc = await _create_favorites_sync_task(
            current_user,
            {"data_source": request.data_source},
        )
        asyncio.create_task(
            _run_favorites_realtime_sync_task(
                task_doc["task_id"],
                current_user["id"],
                request.data_source,
            )
        )

        return ok(task_doc, "Stock watch list real-time market synchronization task has been submitted")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to synchronize real-time quotes of stock watch list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.get("/sync-realtime/tasks/{task_id}", response_model=dict)
async def get_favorites_realtime_sync_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get the real-time quotation synchronization task status of the stock watch list."""
    try:
        task_doc = await _get_favorites_sync_task(task_id, current_user["id"])
        if not task_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Synchronization task does not exist"
            )
        return ok(task_doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to synchronize real-time quotes from stock watch list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain synchronization task: {str(e)}"
        )
_snapshots['favorites'] = dict(globals())

# === tags.py ===
"""
tag management API
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.response import ok
from app.services.tags_service import tags_service

router = APIRouter(prefix="/tags", tags=["tag management"], redirect_slashes=False)


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=30)
    color: Optional[str] = Field(default="#409EFF", max_length=20)
    sort_order: int = 0


class TagUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=30)
    color: Optional[str] = Field(default=None, max_length=20)
    sort_order: Optional[int] = None


class TagResponse(BaseModel):
    id: str
    name: str
    color: str
    sort_order: int
    created_at: str
    updated_at: str


@router.get("", response_model=dict)
async def list_tags(current_user: dict = Depends(get_current_user)):
    try:
        tags = await tags_service.list_tags(current_user["id"])
        return ok(tags)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get tags: {e}")


@router.post("", response_model=dict)
async def create_tag(payload: TagCreate, current_user: dict = Depends(get_current_user)):
    try:
        tag = await tags_service.create_tag(
            user_id=current_user["id"],
            name=payload.name,
            color=payload.color,
            sort_order=payload.sort_order,
        )
        return ok(tag, "Created successfully")
    except Exception as e:
        # Possible violation of unique index (same name), return 400
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create label: {e}")


@router.put("/{tag_id}", response_model=dict)
async def update_tag(tag_id: str, payload: TagUpdate, current_user: dict = Depends(get_current_user)):
    try:
        success = await tags_service.update_tag(
            user_id=current_user["id"],
            tag_id=tag_id,
            name=payload.name,
            color=payload.color,
            sort_order=payload.sort_order,
        )
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag does not exist")
        return ok({"id": tag_id}, "Update successful")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update label: {e}")


@router.delete("/{tag_id}", response_model=dict)
async def delete_tag(tag_id: str, current_user: dict = Depends(get_current_user)):
    try:
        success = await tags_service.delete_tag(current_user["id"], tag_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag does not exist")
        return ok({"id": tag_id}, "Delete successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete tag: {e}")

_snapshots['tags'] = dict(globals())

for _stem, _snap in _snapshots.items():
    _vmod = _types.ModuleType(f"app.routers.{_stem}")
    _vmod.__dict__.update(_snap)
    _sys.modules[f"app.routers.{_stem}"] = _vmod
    setattr(_routers_pkg, _stem, _vmod)
    setattr(_self_mod, _stem, _vmod)