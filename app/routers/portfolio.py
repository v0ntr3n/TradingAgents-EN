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
                            logger.info(f"📊 [Analysis details interface] JSON Parsed successfully, converted to Markdown")
                            report["ai_analysis"]["action_reason"] = service._convert_action_advice_json_to_markdown(advice_json)
                    except Exception as e:
                        logger.warning(f"⚠️ [Analysis details interface] JSON Parsing failed: {e}")
            elif isinstance(action_reason_raw, dict):
                logger.info(f"📊 [Analysis details interface] action_reason is a dictionary format, converted to Markdown")
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
        logger.info(f"✅ [Position research route] Get the UnifiedAnalysisService instance")

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
        logger.info(f"🔄 [Position research route] Start creating tasks...")
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
        logger.info(f"🚀 [Position research route] Start background task execution...")
        asyncio.create_task(
            unified_service.execute_position_analysis(
                task_id=result["task_id"],
                user_id=current_user["id"],
                code=data.code,
                market=data.market,
                task_params=task_params
            )
        )
        logger.info(f"✅ [Position research route] Background task started")

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
                        logger.info(f"📊 [Position research interface] Synchronize the converted recommendation to result.ai_analysis")
                    # If the top-level action_reason has been converted, it will also be synchronized to the result.
                    if "action_reason" in result_data:
                        ai_analysis_copy["action_reason"] = result_data["action_reason"]
                        logger.info(f"📊 [Position research interface] Synchronize the converted action_reason to result.ai_analysis")
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
