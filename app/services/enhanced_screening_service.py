"""
Enhanced stock screening service
Combining database optimization and traditional screening methods to provide efficient stock screening functions
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.models.screening import ScreeningCondition, FieldType, BASIC_FIELDS_INFO
from app.services.factor_registry_service import get_factor_registry_service
from app.services.database_screening_service import get_database_screening_service
from app.services.screening_service import ScreeningService, ScreeningParams

logger = logging.getLogger(__name__)

from app.services.enhanced_screening.utils import (
    analyze_conditions as _analyze_conditions_util,
    convert_conditions_to_traditional_format as _convert_to_traditional_util,
)
from app.core.database import get_mongo_db


class EnhancedScreeningService:
    """增强的股票筛选服务"""

    def __init__(self):
        self.db_service = get_database_screening_service()
        self.traditional_service = ScreeningService()
        self.factor_registry_service = get_factor_registry_service()

        # Fields that support database optimization
        self.db_supported_fields = set(BASIC_FIELDS_INFO.keys())

    async def screen_stocks(
        self,
        conditions: List[ScreeningCondition],
        market: str = "CN",
        date: Optional[str] = None,
        adj: str = "qfq",
        limit: int = 50,
        offset: int = 0,
        order_by: Optional[List[Dict[str, str]]] = None,
        use_database_optimization: bool = True
    ) -> Dict[str, Any]:
        """
        Smart Stock Screening

        Args:
            conditions: filter list
            market: market
            date: transaction date
            adj: Restoration method
            limit: Return quantity limit
            offset: offset
            order_by: Sorting conditions
            use_database_optimization: Whether to use database optimization

        Returns:
            Dict: Filter results
        """
        start_time = time.time()

        try:
            # Analyze filters
            analysis = self._analyze_conditions(conditions)
            database_can_handle = await self.db_service.can_handle_conditions(conditions)

            # Decide which filter to use
            if (use_database_optimization and
                analysis["can_use_database"] and
                database_can_handle):

                # Use database optimization filtering
                result = await self._screen_with_database(
                    conditions, limit, offset, order_by
                )
                optimization_used = "database"
                source = "mongodb"

            else:
                # Use traditional filtering
                result = await self._screen_with_traditional_method(
                    conditions, market, date, adj, limit, offset, order_by
                )
                optimization_used = "traditional"
                source = "api"

            # Extract items/total
            items = result[0] if isinstance(result, tuple) else result.get("items", [])
            total = result[1] if isinstance(result, tuple) else result.get("total", 0)

            # If the database optimization path is used, enrichment is performed from the database quotation table (to avoid external calls during requests)
            if source == "mongodb" and items:
                try:
                    db = get_mongo_db()
                    coll = db["market_quotes"]
                    codes = [str(it.get("code")).zfill(6) for it in items if it.get("code")]
                    if codes:
                        cursor = coll.find(
                            {"code": {"$in": codes}},
                            projection={"_id": 0, "code": 1, "close": 1, "pct_chg": 1, "amount": 1},
                        )
                        quotes_list = await cursor.to_list(length=len(codes))
                        quotes_map = {str(d.get("code")).zfill(6): d for d in quotes_list}
                        for it in items:
                            key = str(it.get("code")).zfill(6)
                            q = quotes_map.get(key)
                            if not q:
                                continue
                            if q.get("close") is not None:
                                it["close"] = q.get("close")
                            if q.get("pct_chg") is not None:
                                it["pct_chg"] = q.get("pct_chg")
                            if q.get("amount") is not None:
                                it["amount"] = q.get("amount")
                except Exception as enrich_err:
                    logger.warning(f"Real-time market information enrichment failed (ignored): {enrich_err}")

            # Add real-time to filter results PE/PB
            if items:
                try:
                    items = await self._enrich_results_with_realtime_metrics(items)
                except Exception as enrich_err:
                    logger.warning(f"Real-time PE/PB enrichment failed (ignored): {enrich_err}")

            # Calculation time
            took_ms = int((time.time() - start_time) * 1000)

            # Return results
            return {
                "total": total,
                "items": items,
                "took_ms": took_ms,
                "optimization_used": optimization_used,
                "source": source,
                "analysis": {
                    **analysis,
                    "database_can_handle": database_can_handle,
                }
            }

        except Exception as e:
            logger.error(f"❌ 股票筛选失败: {e}")
            took_ms = int((time.time() - start_time) * 1000)

            return {
                "total": 0,
                "items": [],
                "took_ms": took_ms,
                "optimization_used": "none",
                "source": "error",
                "error": str(e)
            }

    def _analyze_conditions(self, conditions: List[ScreeningCondition]) -> Dict[str, Any]:
        """Delegate condition analysis to utils."""
        analysis = _analyze_conditions_util(conditions)
        logger.info(f"📊 筛选条件分析: {analysis}")
        return analysis

    async def _screen_with_database(
        self,
        conditions: List[ScreeningCondition],
        limit: int,
        offset: int,
        order_by: Optional[List[Dict[str, str]]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """使用数据库优化筛选"""
        logger.info("🚀 使用数据库优化筛选")

        return await self.db_service.screen_stocks(
            conditions=conditions,
            limit=limit,
            offset=offset,
            order_by=order_by
        )

    async def _screen_with_traditional_method(
        self,
        conditions: List[ScreeningCondition],
        market: str,
        date: Optional[str],
        adj: str,
        limit: int,
        offset: int,
        order_by: Optional[List[Dict[str, str]]]
    ) -> Dict[str, Any]:
        """使用传统筛选方法"""
        logger.info("🔄 使用传统筛选方法")

        # Convert conditional formats to formats supported by legacy services
        traditional_conditions = self._convert_conditions_to_traditional_format(conditions)

        # Create filter parameters
        params = ScreeningParams(
            market=market,
            date=date,
            adj=adj,
            limit=limit,
            offset=offset,
            order_by=order_by
        )

        # Perform traditional screening
        result = self.traditional_service.run(traditional_conditions, params)

        return result

    def _convert_conditions_to_traditional_format(
        self,
        conditions: List[ScreeningCondition]
    ) -> Dict[str, Any]:
        """Delegate condition conversion to utils."""
        return _convert_to_traditional_util(conditions)

    async def _enrich_results_with_realtime_metrics(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add PE/PB for filtering results (use static data to avoid performance issues)

        Args:
            items: Filter the results list

        Returns:
            List[Dict]: List of results after enrichment
        """
        # 🔥 Stock screening scenario: directly use the static data in stock_basic_info PE/PB
        # Reason: Computing dynamic PE in batches can cause serious performance issues (multiple collections are queried for each stock)
        # Static PE is based on the closing price of the latest trading day, which is accurate enough for screening scenarios.

        logger.info(f"📊 [筛选结果富集] 使用静态PE/PB（避免性能问题），共 {len(items)} 只股票")

        # Note: PE/PB in items already comes from stock_basic_info, no additional processing is required here.
        # If real-time PE is needed in the future, it can be calculated separately on the individual stock details page.

        return items

    async def get_field_info(self, field: str) -> Optional[Dict[str, Any]]:
        """
        Get field information

        Args:
            field: Field name

        Returns:
            Dict: Field information
        """
        field_info = self.factor_registry_service.get_screening_field_info(field)
        if field_info is None:
            return None

        stats = await self.db_service.get_field_statistics(field)

        available_values = None
        if field_info.get("data_type") == "string":
            available_values = await self.db_service.get_available_values(field)

        return {
            **field_info,
            "statistics": stats,
            "available_values": available_values,
        }

    async def get_all_supported_fields(self) -> List[Dict[str, Any]]:
        """获取所有支持的字段信息"""
        fields = []

        for field_name in self.factor_registry_service.get_legacy_screening_field_config()["fields"].keys():
            field_info = await self.get_field_info(field_name)
            if field_info:
                fields.append(field_info)

        return fields

    async def validate_conditions(self, conditions: List[ScreeningCondition]) -> Dict[str, Any]:
        """
        Validate filters

        Args:
            conditions: filter list

        Returns:
            Dict: Verification results
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        for i, condition in enumerate(conditions):
            field = condition.field
            operator = condition.operator
            value = condition.value

            # Check if the field supports
            if field not in BASIC_FIELDS_INFO:
                validation_result["errors"].append(
                    f"条件 {i+1}: 不支持的字段 '{field}'"
                )
                validation_result["valid"] = False
                continue

            field_info = BASIC_FIELDS_INFO[field]

            # Check if the operator is supported
            if operator not in [op.value for op in field_info.supported_operators]:
                validation_result["errors"].append(
                    f"条件 {i+1}: 字段 '{field}' 不支持操作符 '{operator}'"
                )
                validation_result["valid"] = False

            # Check value type and range
            if field_info.data_type == "number":
                if operator == "between":
                    if not isinstance(value, list) or len(value) != 2:
                        validation_result["errors"].append(
                            f"条件 {i+1}: between操作符需要两个数值"
                        )
                        validation_result["valid"] = False
                    elif not all(isinstance(v, (int, float)) for v in value):
                        validation_result["errors"].append(
                            f"条件 {i+1}: between操作符的值必须是数字"
                        )
                        validation_result["valid"] = False
                elif not isinstance(value, (int, float)):
                    validation_result["errors"].append(
                        f"条件 {i+1}: 数值字段 '{field}' 的值必须是数字"
                    )
                    validation_result["valid"] = False

        return validation_result


# Global service instance
_enhanced_screening_service: Optional[EnhancedScreeningService] = None


def get_enhanced_screening_service() -> EnhancedScreeningService:
    """获取增强筛选服务实例"""
    global _enhanced_screening_service
    if _enhanced_screening_service is None:
        _enhanced_screening_service = EnhancedScreeningService()
    return _enhanced_screening_service
