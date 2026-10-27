"""
Data models related to stock screening
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from core.skill_runtime.factor_schema import P0_PUBLIC_SCREENING_FIELDS, get_factor_field_schema


class OperatorType(str, Enum):
    """filter operator type"""
    GT = ">"           # greater than
    LT = "<"           # less than
    GTE = ">="         # Greater than or equal to
    LTE = "<="         # less than or equal to
    EQ = "=="          # equal to
    NE = "!="          # not equal to
    BETWEEN = "between"  # interval
    IN = "in"          # included in
    NOT_IN = "not_in"  # not included in
    CONTAINS = "contains"  # string contains
    CROSS_UP = "cross_up"    # Technical Indicators: Crossing Up
    CROSS_DOWN = "cross_down"  # Technical Indicators: Crossing Down


class FieldType(str, Enum):
    """Field type"""
    BASIC = "basic"        # Basic information fields
    TECHNICAL = "technical"  # Technical indicator field
    FUNDAMENTAL = "fundamental"  # fundamental fields


class ScreeningCondition(BaseModel):
    """single filter"""
    field: str = Field(..., description="Field name")
    operator: OperatorType = Field(..., description="Operator")
    value: Union[float, int, str, List[Union[float, int, str]]] = Field(..., description="filter value")
    field_type: Optional[FieldType] = Field(None, description="Field type")
    
    class Config:
        use_enum_values = True


class ScreeningRequest(BaseModel):
    """Filter requests"""
    market: str = Field("CN", description="Market:CN/HK/US")
    date: Optional[str] = Field(None, description="Trading date YYYY-MM-DD, the default is the latest")
    adj: str = Field("qfq", description="Restoration caliber:qfq/hfq/none")
    
    # Filter criteria
    conditions: List[ScreeningCondition] = Field(default_factory=list, description="filter list")
    
    # Sorting and paging
    order_by: Optional[List[Dict[str, str]]] = Field(None, description="Sorting conditions")
    limit: int = Field(50, ge=1, le=500, description="Return quantity limit")
    offset: int = Field(0, ge=0, description="offset")
    
    # Optimization options
    use_database_optimization: bool = Field(True, description="Whether to use database optimization")


class ScreeningResponse(BaseModel):
    """Filter responses"""
    total: int = Field(..., description="total quantity")
    items: List[Dict[str, Any]] = Field(..., description="Filter results")
    took_ms: Optional[int] = Field(None, description="Time consuming(milliseconds)")
    optimization_used: Optional[str] = Field(None, description="Optimization methods used")
    source: Optional[str] = Field(None, description="data source")


class FieldInfo(BaseModel):
    """Field information"""
    name: str = Field(..., description="Field name")
    display_name: str = Field(..., description="display name")
    field_type: FieldType = Field(..., description="Field type")
    data_type: str = Field(..., description="data type: number/string/date")
    description: str = Field("", description="Field description")
    unit: Optional[str] = Field(None, description="unit")
    
    # Statistics for numeric fields
    min_value: Optional[float] = Field(None, description="minimum value")
    max_value: Optional[float] = Field(None, description="maximum value")
    avg_value: Optional[float] = Field(None, description="average")
    
    # Optional values for enumeration fields
    available_values: Optional[List[str]] = Field(None, description="list of optional values")
    
    # Supported operators
    supported_operators: List[OperatorType] = Field(default_factory=list, description="Supported operators")


class FieldStatistics(BaseModel):
    """Field statistics"""
    field: str = Field(..., description="Field name")
    count: int = Field(..., description="Valid data quantity")
    min_value: Optional[float] = Field(None, description="minimum value")
    max_value: Optional[float] = Field(None, description="maximum value")
    avg_value: Optional[float] = Field(None, description="average")
    median_value: Optional[float] = Field(None, description="median")
    std_value: Optional[float] = Field(None, description="standard deviation")


_NUMERIC_OPERATORS = [
    OperatorType.GT,
    OperatorType.LT,
    OperatorType.GTE,
    OperatorType.LTE,
    OperatorType.BETWEEN,
]
_STRING_OPERATORS = [
    OperatorType.EQ,
    OperatorType.NE,
    OperatorType.IN,
    OperatorType.NOT_IN,
    OperatorType.CONTAINS,
]
_BOOLEAN_OPERATORS = [OperatorType.EQ, OperatorType.NE]


def _get_supported_operators(data_type: str) -> List[OperatorType]:
    if data_type == "number":
        return list(_NUMERIC_OPERATORS)
    if data_type == "boolean":
        return list(_BOOLEAN_OPERATORS)
    return list(_STRING_OPERATORS)


def _build_p0_screening_field_info() -> Dict[str, "FieldInfo"]:
    field_info_map: Dict[str, FieldInfo] = {}
    for field_name in P0_PUBLIC_SCREENING_FIELDS:
        schema = get_factor_field_schema(field_name)
        if schema is None:
            continue
        field_info_map[field_name] = FieldInfo(
            name=schema.field_name,
            display_name=schema.display_name,
            field_type=FieldType.FUNDAMENTAL,
            data_type=schema.data_type,
            description=schema.description,
            unit=schema.screening_unit or schema.unit or None,
            supported_operators=_get_supported_operators(schema.data_type),
        )
    return field_info_map


def _dedupe_fields(fields: List[str]) -> List[str]:
    return list(dict.fromkeys(fields))


# Predefined field information
BASIC_FIELDS_INFO = {
    "keyword": FieldInfo(
        name="keyword",
        display_name="keywords",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Stock code or name",
        supported_operators=[OperatorType.CONTAINS]
    ),
    "symbol": FieldInfo(
        name="symbol",
        display_name="Stock code",
        field_type=FieldType.BASIC,
        data_type="string",
        description="6 stock code",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN, OperatorType.CONTAINS]
    ),
    "code": FieldInfo(  # Compatible with old fields
        name="code",
        display_name="Stock code(Deprecated)",
        field_type=FieldType.BASIC,
        data_type="string",
        description="6 stock code(Deprecated,Use symbol)",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN, OperatorType.CONTAINS]
    ),
    "name": FieldInfo(
        name="name",
        display_name="Stock name",
        field_type=FieldType.BASIC,
        data_type="string",
        description="stock abbreviation",
        supported_operators=[OperatorType.CONTAINS, OperatorType.EQ, OperatorType.NE]
    ),
    "industry": FieldInfo(
        name="industry",
        display_name="Industry",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Shenwan Industry Classification",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN, OperatorType.CONTAINS]
    ),
    "area": FieldInfo(
        name="area",
        display_name="Region",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Company registration area",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN]
    ),
    "market": FieldInfo(
        name="market",
        display_name="Market",
        field_type=FieldType.BASIC,
        data_type="string",
        description="trading market",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN]
    ),
    "total_mv": FieldInfo(
        name="total_mv",
        display_name="Total market capitalization",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Total market capitalization",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "circ_mv": FieldInfo(
        name="circ_mv",
        display_name="Circulation market value",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Circulation market value",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pe": FieldInfo(
        name="pe",
        display_name="P/E ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="P/E ratio(PE)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pb": FieldInfo(
        name="pb",
        display_name="price to book ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="price to book ratio(PB)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pe_ttm": FieldInfo(
        name="pe_ttm",
        display_name="rolling price to earnings ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="rolling price to earnings ratio(PE TTM)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "ps_ttm": FieldInfo(
        name="ps_ttm",
        display_name="rolling price-to-sales ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="rolling price-to-sales ratio(PS TTM)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pb_mrq": FieldInfo(
        name="pb_mrq",
        display_name="Latest price-to-book ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Latest price-to-book ratio(PB MRQ)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "roe": FieldInfo(
        name="roe",
        display_name="ROE",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="ROE(The latest issue,%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "roa": FieldInfo(
        name="roa",
        display_name="return on total assets",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="return on total assets(ROA, %)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "gross_margin": FieldInfo(
        name="gross_margin",
        display_name="Gross profit margin",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="gross sales profit margin(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "netprofit_margin": FieldInfo(
        name="netprofit_margin",
        display_name="net profit margin",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="net sales profit margin(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "debt_to_assets": FieldInfo(
        name="debt_to_assets",
        display_name="Asset-liability ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Asset-liability ratio(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "assets_to_eqt": FieldInfo(
        name="assets_to_eqt",
        display_name="equity multiplier",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="equity multiplier(Total assets/shareholders equity)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "current_ratio": FieldInfo(
        name="current_ratio",
        display_name="current ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="current ratio(Current assets/current liabilities)",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "quick_ratio": FieldInfo(
        name="quick_ratio",
        display_name="quick ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="quick ratio",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "cash_ratio": FieldInfo(
        name="cash_ratio",
        display_name="cash ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="cash ratio",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "dividend_yield": FieldInfo(
        name="dividend_yield",
        display_name="dividend yield",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Dividend rate in the last 12 months(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "peg": FieldInfo(
        name="peg",
        display_name="PEG",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="PEG=PE TTM/Net profit year-on-year growth rate",
        unit="times/%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "roic": FieldInfo(
        name="roic",
        display_name="return on invested capital",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="ROIC(Conservative agency caliber,%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "cash_conversion": FieldInfo(
        name="cash_conversion",
        display_name="Profit to cash conversion rate",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Operating cash flow/net profit",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "accrual_ratio": FieldInfo(
        name="accrual_ratio",
        display_name="accruals ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="(Net Profit - Operating Cash Flow)/Total assets, percentage output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "asset_turnover": FieldInfo(
        name="asset_turnover",
        display_name="asset turnover rate",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Revenue/total assets, currently using the latest conservative proxy for total assets",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "gross_profit_to_assets": FieldInfo(
        name="gross_profit_to_assets",
        display_name="gross profit to assets ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Gross profit/total assets, percentage output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "interest_coverage": FieldInfo(
        name="interest_coverage",
        display_name="interest coverage ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="oper_profit/fin_exp conservative agency caliber",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "inventory_turnover": FieldInfo(
        name="inventory_turnover",
        display_name="Inventory turnover",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Operating costs/inventory, current conservative proxy using latest inventory balance",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "receivable_turnover": FieldInfo(
        name="receivable_turnover",
        display_name="Accounts receivable turnover ratio",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Revenue/Accounts Receivable, currently using the latest accounts receivable balance conservative proxy",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "net_cash_position": FieldInfo(
        name="net_cash_position",
        display_name="net cash position",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="(money_cap-total_ncl)/total_assets Conservative proxy for , percent output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "piotroski_f_score": FieldInfo(
        name="piotroski_f_score",
        display_name="Piotroski F-Score",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="9-point quality score based on financial signals from the last two periods",
        unit="points",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "altman_z_score": FieldInfo(
        name="altman_z_score",
        display_name="Altman Z-Score",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Financial distress risk score, currently using retained earnings and EBIT calibers in raw_data",
        unit="points",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "beneish_m_score": FieldInfo(
        name="beneish_m_score",
        display_name="Beneish M-Score",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Earnings manipulation risk score, based on the 8-index model of the last two periods",
        unit="points",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "revenue_ttm": FieldInfo(
        name="revenue_ttm",
        display_name="rolling revenue",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Rolling 12-month operating income",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "revenue_yoy": FieldInfo(
        name="revenue_yoy",
        display_name="Year-on-year revenue",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Year-on-year revenue growth rate for the latest reporting period compared to the same quarter last year",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "revenue_cagr_3y": FieldInfo(
        name="revenue_cagr_3y",
        display_name="Three-year compound growth rate of revenue",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Three-year revenue compared with three years ago in the same quarter CAGR",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "net_profit_ttm": FieldInfo(
        name="net_profit_ttm",
        display_name="rolling net profit",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Rolling 12-month net profit",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "net_profit_yoy": FieldInfo(
        name="net_profit_yoy",
        display_name="Net profit year-on-year",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="The year-on-year growth rate of net profit in the latest reporting period compared to the same quarter last year",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "profit_cagr_3y": FieldInfo(
        name="profit_cagr_3y",
        display_name="Three-year compound growth rate of net profit",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Three-year net profit compared to three years ago in the same quarter CAGR",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "oper_profit_yoy": FieldInfo(
        name="oper_profit_yoy",
        display_name="Operating profit year-on-year",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="The year-on-year growth rate of operating profit in the latest reporting period compared with the same quarter last year",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "n_cashflow_act": FieldInfo(
        name="n_cashflow_act",
        display_name="operating cash flow",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Net cash flow from operating activities",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "fcf": FieldInfo(
        name="fcf",
        display_name="free cash flow",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="free cash flow(Conservative agency caliber)=operating cash flow+investment cash flow",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "fcf_yield": FieldInfo(
        name="fcf_yield",
        display_name="free cash flow yield",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="free cash flow yield(%)",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "fcf_margin": FieldInfo(
        name="fcf_margin",
        display_name="free cash flow rate",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Free cash flow/revenue, % output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "ocf_yield": FieldInfo(
        name="ocf_yield",
        display_name="operating cash flow yield",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Operating cash flow/total market capitalization, percentage output",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "report_period": FieldInfo(
        name="report_period",
        display_name="financial reporting period",
        field_type=FieldType.FUNDAMENTAL,
        data_type="string",
        description="The latest financial report reporting period, such as 20250930",
        supported_operators=[OperatorType.EQ, OperatorType.NE, OperatorType.IN, OperatorType.NOT_IN]
    ),
    "net_working_capital": FieldInfo(
        name="net_working_capital",
        display_name="net working capital",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="net working capital(billion)=Current assets - current liabilities",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "working_capital_change": FieldInfo(
        name="working_capital_change",
        display_name="working capital changes",
        field_type=FieldType.FUNDAMENTAL,
        data_type="number",
        description="Changes in net working capital in the last two periods",
        unit="billion",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "is_st": FieldInfo(
        name="is_st",
        display_name="ST Status",
        field_type=FieldType.BASIC,
        data_type="string",
        description="Whether it is ST or*ST stocks",
        supported_operators=[OperatorType.EQ, OperatorType.NE]
    ),
    "turnover_rate": FieldInfo(
        name="turnover_rate",
        display_name="turnover rate",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="turnover rate",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "volume_ratio": FieldInfo(
        name="volume_ratio",
        display_name="Quantity ratio",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="Quantity ratio",
        unit="times",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),

    # Price data field (now in the view and can be queried directly from the database)
    "close": FieldInfo(
        name="close",
        display_name="closing price",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="latest closing price",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "pct_chg": FieldInfo(
        name="pct_chg",
        display_name="Increase or decrease",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="Increase or decrease",
        unit="%",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "amount": FieldInfo(
        name="amount",
        display_name="Turnover",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="Turnover",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "volume": FieldInfo(
        name="volume",
        display_name="Volume",
        field_type=FieldType.FUNDAMENTAL,  # Changed to FUNDAMENTAL because it is now possible to query directly in the view
        data_type="number",
        description="Volume",
        unit="hand",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),

    # Technical indicator field
    "ma20": FieldInfo(
        name="ma20",
        display_name="20 daily moving average",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="20 daily moving average",
        unit="Yuan",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "rsi14": FieldInfo(
        name="rsi14",
        display_name="RSI indicator",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="14 Daily Relative Strength Index",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "kdj_k": FieldInfo(
        name="kdj_k",
        display_name="KDJ-K",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="KDJ Index K value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "kdj_d": FieldInfo(
        name="kdj_d",
        display_name="KDJ-D",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="KDJ Index D value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "kdj_j": FieldInfo(
        name="kdj_j",
        display_name="KDJ-J",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="KDJ Index J value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "dif": FieldInfo(
        name="dif",
        display_name="MACD-DIF",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="MACD Indicator DIF value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "dea": FieldInfo(
        name="dea",
        display_name="MACD-DEA",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="MACD Indicator DEA value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
    "macd_hist": FieldInfo(
        name="macd_hist",
        display_name="MACD bar chart",
        field_type=FieldType.TECHNICAL,
        data_type="number",
        description="MACD Histogram value",
        unit="",
        supported_operators=[OperatorType.GT, OperatorType.LT, OperatorType.GTE, OperatorType.LTE, OperatorType.BETWEEN]
    ),
}


# P0 Public fundamental fields are uniformly derived from factor_schema to avoid drift with runtime/schema.
BASIC_FIELDS_INFO.update(_build_p0_screening_field_info())


SCREENING_FINANCIAL_CATEGORY_FIELDS = _dedupe_fields(
    ["total_mv", "circ_mv", *P0_PUBLIC_SCREENING_FIELDS, "report_period", "is_st"]
)

