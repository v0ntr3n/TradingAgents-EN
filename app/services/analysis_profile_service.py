"""
Industry/stock analysis and allocation services

Provide CRUD operations, dimension injection formatting functions, and AI generated industry configurations
"""

import json
import logging
from typing import Optional, Dict, Any, List
from bson import ObjectId
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

# Collection name
INDUSTRY_COLLECTION = "industry_analysis_profiles"
STOCK_COLLECTION = "stock_analysis_profiles"


BUILTIN_SOURCE_DEFINITIONS = [
    {
        "key": "basic_info",
        "label": "Basic stock information/industry affiliation",
        "description": "From stock_basic_info Interface to unified stock information, supporting industry affiliation, company profile, partial valuation and basic fields.",
        "keywords": ["行业", "公司", "主营", "市值", "估值", "pe", "pb", "市盈率", "市净率", "股票基础", "基本信息"],
    },
    {
        "key": "financials",
        "label": "财务报表 / 基本面",
        "description": "Unified data capabilities from stock_financial_data, Tushare/AKShare/BaoStock, etc. can support financial indicators such as revenue, profit, cash flow, ROE, etc.",
        "keywords": [
            "营收", "收入", "净利润", "利润", "毛利率", "净利率", "现金流", "roe", "roa", "负债率", "周转", "应收", "存货",
            "资本开支", "capex", "分红", "eps", "每股收益", "经营活动现金流", "归母", "利润增长", "财务",
        ],
    },
    {
        "key": "market",
        "label": "Market/Volume and Price/Technical",
        "description": "Coming from market_quotes, historical market conditions and technical indicator capabilities, it can support price trends, trading volume, volatility, turnover rate and other volume and price indicators.",
        "keywords": [
            "股价", "价格", "成交量", "换手率", "波动率", "量价", "趋势", "技术", "均线", "macd", "rsi", "k线", "涨跌", "回撤",
        ],
    },
    {
        "key": "news",
        "label": "新闻 / 事件 / 政策",
        "description": "It comes from real-time news aggregation, announcements and public opinion capabilities, and is suitable for unstructured judgments such as policy, supervision, catalysis, and risk events.",
        "keywords": [
            "政策", "监管", "舆情", "事件", "催化", "新闻", "公告", "情绪", "风险事件", "市场预期", "行业景气", "竞争格局",
        ],
    },
]

OPERATIONAL_KEYWORDS = [
    "mau", "dau", "arpu", "付费率", "留存", "用户数", "活跃用户", "客单价", "渗透率", "复购", "订单量", "gmv", "take rate",
    "装机量", "装机", "销量", "出货量", "客流", "入住率", "产能利用率", "产销率", "客座率", "吞吐量", "日活", "月活",
]

QUALITATIVE_KEYWORDS = [
    "品牌力", "品牌势能", "生态壁垒", "用户粘性", "管理层执行力", "组织能力", "产品力", "渠道力", "技术领先性", "技术壁垒",
    "商业模式韧性", "战略定力", "护城河", "竞争优势", "定价权", "行业话语权",
]

STATUS_LABELS = {
    "directly_usable": "可直接使用",
    "partially_usable": "部分可用",
    "external_required": "需外部数据",
    "review_recommended": "建议复核",
}

ACTION_LABELS = {
    "keep": "直接保留",
    "keep_with_review": "保留但建议复核",
    "enhance_with_mcp_or_skill": "Combined with MCP/Skill reinforcement",
    "manual_import_or_external_source": "补充外部数据或手工导入",
    "remove_or_replace": "建议先删除或替换",
}


class AnalysisProfileService:
    """行业/个股分析配置服务"""

    # ==================== Industry configuration ====================

    async def get_industry_profiles(self, is_active: Optional[bool] = None) -> List[Dict]:
        """获取所有行业配置"""
        db = get_mongo_db()
        query = {}
        if is_active is not None:
            query["is_active"] = is_active
        cursor = db[INDUSTRY_COLLECTION].find(query).sort("industry", 1)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
            results.append(doc)
        return results

    async def get_industry_profile(self, profile_id: str) -> Optional[Dict]:
        """根据 ID 获取行业配置"""
        db = get_mongo_db()
        doc = await db[INDUSTRY_COLLECTION].find_one({"_id": ObjectId(profile_id)})
        if doc:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
        return doc

    async def get_industry_profile_by_name(self, industry: str) -> Optional[Dict]:
        """根据行业名称获取配置"""
        db = get_mongo_db()
        doc = await db[INDUSTRY_COLLECTION].find_one({"industry": industry, "is_active": True})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create_industry_profile(self, data: Dict) -> Dict:
        """创建行业配置"""
        db = get_mongo_db()
        now = now_tz()
        data["created_at"] = now
        data["updated_at"] = now
        data.setdefault("is_active", True)
        result = await db[INDUSTRY_COLLECTION].insert_one(data)
        data["id"] = str(result.inserted_id)
        logger.info(f"✅ 创建行业分析配置: {data.get('industry')}")
        return data

    async def update_industry_profile(self, profile_id: str, data: Dict) -> Optional[Dict]:
        """更新行业配置"""
        db = get_mongo_db()
        data["updated_at"] = now_tz()
        result = await db[INDUSTRY_COLLECTION].update_one(
            {"_id": ObjectId(profile_id)},
            {"$set": data}
        )
        if result.modified_count > 0:
            logger.info(f"✅ 更新行业分析配置: {profile_id}")
            return await self.get_industry_profile(profile_id)
        return None

    async def delete_industry_profile(self, profile_id: str) -> bool:
        """删除行业配置"""
        db = get_mongo_db()
        result = await db[INDUSTRY_COLLECTION].delete_one({"_id": ObjectId(profile_id)})
        return result.deleted_count > 0

    # ==================== Individual stock allocation ====================

    async def get_stock_profiles(self, industry: Optional[str] = None) -> List[Dict]:
        """获取个股配置列表"""
        db = get_mongo_db()
        query = {"is_active": True}
        if industry:
            query["industry"] = industry
        cursor = db[STOCK_COLLECTION].find(query).sort("stock_symbol", 1)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
            results.append(doc)
        return results

    async def get_stock_profile_by_symbol(self, stock_symbol: str) -> Optional[Dict]:
        """根据股票代码获取配置"""
        db = get_mongo_db()
        doc = await db[STOCK_COLLECTION].find_one({"stock_symbol": stock_symbol, "is_active": True})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create_stock_profile(self, data: Dict) -> Dict:
        """创建个股配置"""
        db = get_mongo_db()
        now = now_tz()
        data["created_at"] = now
        data["updated_at"] = now
        data.setdefault("is_active", True)
        result = await db[STOCK_COLLECTION].insert_one(data)
        data["id"] = str(result.inserted_id)
        logger.info(f"✅ 创建个股分析配置: {data.get('stock_symbol')}")
        return data

    async def update_stock_profile(self, profile_id: str, data: Dict) -> Optional[Dict]:
        """更新个股配置"""
        db = get_mongo_db()
        data["updated_at"] = now_tz()
        result = await db[STOCK_COLLECTION].update_one(
            {"_id": ObjectId(profile_id)},
            {"$set": data}
        )
        if result.modified_count > 0:
            return await self.get_stock_profile(profile_id)
        return None

    async def get_stock_profile(self, profile_id: str) -> Optional[Dict]:
        """根据 ID 获取个股配置"""
        db = get_mongo_db()
        doc = await db[STOCK_COLLECTION].find_one({"_id": ObjectId(profile_id)})
        if doc:
            doc["id"] = str(doc.pop("_id"))
            doc["created_at"] = str(doc.get("created_at", ""))
            doc["updated_at"] = str(doc.get("updated_at", ""))
        return doc

    async def delete_stock_profile(self, profile_id: str) -> bool:
        """删除个股配置"""
        db = get_mongo_db()
        result = await db[STOCK_COLLECTION].delete_one({"_id": ObjectId(profile_id)})
        return result.deleted_count > 0

    # ==================== Dimension injection (synchronous, for use by _prepare_system_variables) ====================

    @staticmethod
    def format_dimensions(dimensions: list) -> str:
        """Format analysis dimension list as prompt word injection text"""
        if not dimensions:
            return ""
        lines = []
        for d in dimensions:
            importance = d.get("importance", "high")
            name = d.get("name", "")
            desc = d.get("description", "")
            lines.append(f"- **{name}**（{importance}）: {desc}")
        return "\n".join(lines)

    @staticmethod
    def _contains_any(text: str, keywords: List[str]) -> bool:
        text_lower = (text or "").lower()
        return any(keyword.lower() in text_lower for keyword in keywords)

    @staticmethod
    def _source_ref(source_type: str, name: str, detail: str = "") -> Dict[str, str]:
        type_labels = {
            "builtin": "内置数据",
            "mcp": "MCP",
            "skill": "Skill",
            "manual_import": "手工导入",
        }
        return {
            "type": source_type,
            "type_label": type_labels.get(source_type, source_type),
            "name": name,
            "detail": detail,
        }

    async def _collect_capability_snapshot(self, db) -> Dict[str, Any]:
        builtin_sources = [
            {
                "key": item["key"],
                "label": item["label"],
                "description": item["description"],
            }
            for item in BUILTIN_SOURCE_DEFINITIONS
        ]

        enabled_mcp_servers: List[Dict[str, Any]] = []
        active_skills: List[Dict[str, Any]] = []

        try:
            cursor = db["mcp_server_configs"].find({"is_enabled": True})
            async for doc in cursor:
                tools = doc.get("discovered_tools", []) or []
                mappings = doc.get("data_mappings", []) or []
                summary_parts = [
                    doc.get("name", ""),
                    doc.get("description", ""),
                    doc.get("category", ""),
                ]
                summary_parts.extend(
                    [
                        tool.get("name", "") + " " + tool.get("description", "")
                        for tool in tools if isinstance(tool, dict)
                    ]
                )
                summary_parts.extend(
                    [
                        str(mapping.get("source_field", "")) + " " + str(mapping.get("target_field", ""))
                        for mapping in mappings if isinstance(mapping, dict)
                    ]
                )
                enabled_mcp_servers.append({
                    "server_id": doc.get("server_id", ""),
                    "name": doc.get("name", doc.get("server_id", "MCP")),
                    "description": doc.get("description", ""),
                    "category": doc.get("category", "function"),
                    "status": doc.get("status", "unknown"),
                    "tool_count": len(tools),
                    "mapping_count": len(mappings),
                    "summary_text": " ".join([part for part in summary_parts if part]),
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to collect MCP capability snapshot: {e}")

        try:
            cursor = db["external_skills"].find({"status": "active"})
            async for doc in cursor:
                metadata = doc.get("metadata", {}) or {}
                active_skills.append({
                    "tool_id": doc.get("tool_id", ""),
                    "name": doc.get("display_name", doc.get("tool_id", "Skill")),
                    "description": doc.get("description", ""),
                    "category": metadata.get("category") or doc.get("category", "external"),
                    "source": doc.get("source", "generated"),
                    "data_source": doc.get("data_source", ""),
                    "summary_text": " ".join(
                        [
                            doc.get("display_name", ""),
                            doc.get("description", ""),
                            str(metadata.get("category", "")),
                            str(doc.get("data_source", "")),
                        ]
                    ),
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to collect external_skills: {e}")

        try:
            cursor = db["skills"].find({"enabled": True})
            async for doc in cursor:
                active_skills.append({
                    "tool_id": doc.get("name", ""),
                    "name": doc.get("name", "Skill"),
                    "description": doc.get("description", ""),
                    "category": doc.get("category", "utility"),
                    "source": "legacy_skill",
                    "data_source": "",
                    "summary_text": " ".join(
                        [
                            str(doc.get("name", "")),
                            str(doc.get("description", "")),
                            str(doc.get("category", "")),
                        ]
                    ),
                })
        except Exception as e:
            logger.warning(f"⚠️ Failed to collect skills: {e}")

        return {
            "builtin_sources": builtin_sources,
            "enabled_mcp_servers": enabled_mcp_servers,
            "active_skills": active_skills,
            "manual_import": {
                "available": True,
                "label": "手工导入 / 本地数据",
                "description": "The current system supports supplementing indicators through batch import API or local data. The imported data source is usually marked as local / local_file.",
            },
            "counts": {
                "builtin_sources": len(builtin_sources),
                "enabled_mcp_servers": len(enabled_mcp_servers),
                "active_skills": len(active_skills),
            },
            "notes": [
                "The built-in data is more suitable for financial, market, news and announcement indicators.",
                "MCP/Skill Extended data coverage is possible, but whether it is actually available depends on the currently enabled items and field mappings.",
                "If the corresponding data cannot be found in the system, it is recommended that the user supplement external data sources or manually import them before retaining the dimension/indicator.",
            ],
        }

    def _match_mcp_sources(self, text: str, capability_snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
        matches = []
        text_lower = (text or "").lower()
        for item in capability_snapshot.get("enabled_mcp_servers", []):
            summary_text = item.get("summary_text", "").lower()
            if summary_text and any(token in summary_text for token in text_lower.split() if token):
                matches.append(self._source_ref("mcp", item.get("name", "MCP"), item.get("description", "")))
        return matches[:3]

    def _match_skill_sources(self, text: str, capability_snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
        matches = []
        text_lower = (text or "").lower()
        for item in capability_snapshot.get("active_skills", []):
            summary_text = item.get("summary_text", "").lower()
            if summary_text and any(token in summary_text for token in text_lower.split() if token):
                matches.append(self._source_ref("skill", item.get("name", "Skill"), item.get("description", "")))
        return matches[:3]

    def _evaluate_item_coverage(
        self,
        name: str,
        description: str,
        data_source: str,
        capability_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        text = " ".join([name or "", description or "", data_source or ""])
        matched_sources: List[Dict[str, str]] = []
        missing_requirements: List[str] = []

        has_financial = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[1]["keywords"])
        has_market = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[2]["keywords"])
        has_basic = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[0]["keywords"])
        has_news = self._contains_any(text, BUILTIN_SOURCE_DEFINITIONS[3]["keywords"])
        has_operational = self._contains_any(text, OPERATIONAL_KEYWORDS)
        has_qualitative = self._contains_any(text, QUALITATIVE_KEYWORDS)

        if has_basic:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[0]["label"], BUILTIN_SOURCE_DEFINITIONS[0]["description"]))
        if has_financial:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[1]["label"], BUILTIN_SOURCE_DEFINITIONS[1]["description"]))
        if has_market:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[2]["label"], BUILTIN_SOURCE_DEFINITIONS[2]["description"]))
        if has_news:
            matched_sources.append(self._source_ref("builtin", BUILTIN_SOURCE_DEFINITIONS[3]["label"], BUILTIN_SOURCE_DEFINITIONS[3]["description"]))

        mcp_matches = self._match_mcp_sources(text, capability_snapshot)
        skill_matches = self._match_skill_sources(text, capability_snapshot)
        matched_sources.extend(mcp_matches)
        matched_sources.extend(skill_matches)

        has_any_mcp = capability_snapshot.get("counts", {}).get("enabled_mcp_servers", 0) > 0
        has_any_skill = capability_snapshot.get("counts", {}).get("active_skills", 0) > 0

        if has_financial or has_market or has_basic:
            status = "directly_usable"
            action = "keep"
            user_note = "This item mainly relies on the system s current structured data capabilities. After saving, you can directly enter the analysis prompt word."
        elif has_news:
            status = "partially_usable"
            action = "keep_with_review"
            user_note = "The system can assist in judgment through news/announcement data, but most of it is unstructured information. It is recommended to manually review the analysis conclusion."
        elif has_operational:
            matched_sources.append(self._source_ref("manual_import", "手工导入 / 外部数据", capability_snapshot["manual_import"]["description"]))
            if mcp_matches or skill_matches:
                status = "partially_usable"
                action = "enhance_with_mcp_or_skill"
                user_note = "This item is more like an external indicator of operations/industry. Some MCP/Skills already in the system may be enhanced, but it is still recommended to confirm field mapping and availability."
            else:
                status = "external_required"
                action = "manual_import_or_external_source"
                user_note = "The current built-in data usually does not directly cover such operational indicators. It is recommended to access external data sources, enable matching MCP/Skill, or manually import and retain them."
                if has_any_mcp or has_any_skill:
                    missing_requirements.append("Although MCP/Skill is currently enabled, no ability description directly matching this item has been found, and manual confirmation is required.")
                else:
                    missing_requirements.append("Currently, no MCP/Skill has been found that can directly support this item, and additional external data is required.")
        elif has_qualitative:
            status = "review_recommended"
            action = "remove_or_replace"
            user_note = "This item is qualitative, abstract or difficult to verify in a structured way. It is recommended that users confirm whether there is a stable data source; if not, delete it or change it to a verifiable indicator."
            missing_requirements.append("It is recommended to replace it with verifiable financial, market, news or importable indicators.")
        else:
            matched_sources.append(self._source_ref("manual_import", "手工导入 / 外部数据", capability_snapshot["manual_import"]["description"]))
            status = "review_recommended"
            action = "keep_with_review"
            user_note = "The system has not yet identified a clear data support method. It is recommended that the user confirm the source before saving. If the data cannot be confirmed, it is recommended to delete it."
            if not matched_sources:
                missing_requirements.append("No clear data source was identified.")

        return {
            "name": name,
            "description": description,
            "requested_data_source": data_source,
            "coverage_status": status,
            "coverage_label": STATUS_LABELS[status],
            "recommended_action": action,
            "recommended_action_label": ACTION_LABELS[action],
            "matched_sources": matched_sources[:4],
            "missing_requirements": missing_requirements,
            "user_note": user_note,
        }

    @staticmethod
    def _count_status(items: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {key: 0 for key in STATUS_LABELS.keys()}
        for item in items:
            status = item.get("coverage_status")
            if status in counts:
                counts[status] += 1
        return counts

    def _build_coverage_summary(
        self,
        dimension_assessments: List[Dict[str, Any]],
        metric_assessments: List[Dict[str, Any]],
        capability_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimension_counts = self._count_status(dimension_assessments)
        metric_counts = self._count_status(metric_assessments)
        total_external = dimension_counts["external_required"] + metric_counts["external_required"]
        total_review = dimension_counts["review_recommended"] + metric_counts["review_recommended"]

        if total_external == 0 and total_review <= 1:
            overall_status = "ready"
            overall_label = "大部分内容已具备落地基础"
        elif total_external <= 2 and total_review <= 3:
            overall_status = "review_needed"
            overall_label = "建议人工复核后保存"
        else:
            overall_status = "prune_needed"
            overall_label = "建议先裁剪再保存"

        recommendations = []
        if dimension_counts["directly_usable"] or metric_counts["directly_usable"]:
            recommendations.append("Priority reservation Can be used directly dimensions and indicators, which are most easily supported stably by the current system.")
        if total_external:
            recommendations.append(f"当前有 {total_external} 项被识别为“需外部数据”，建议在保存前确认 MCP / Skill / 手工导入方案。")
        if total_review:
            recommendations.append(f"当前有 {total_review} 项为“建议复核”，若无法确认数据来源，建议先删除或改写为可验证指标。")
        if capability_snapshot.get("counts", {}).get("enabled_mcp_servers", 0) == 0:
            recommendations.append("There is currently no enabled MCP server. If you need more industry operations or alternative data, you may consider connecting to MCP first.")

        return {
            "overall_status": overall_status,
            "overall_label": overall_label,
            "dimension_counts": dimension_counts,
            "metric_counts": metric_counts,
            "recommendations": recommendations,
        }

    @staticmethod
    def get_industry_dimensions_sync(industry: str) -> Dict[str, str]:
        """
        Synchronously obtain industry analysis dimensions (for _prepare_system_variables)

        Returns:
            contains industry_dimensions, industry_focus, industry_key_metrics dictionary
        """
        result = {}
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()

            # 1. exact match
            profile = db[INDUSTRY_COLLECTION].find_one(
                {"industry": industry, "is_active": True}
            )

            # 2. Fuzzy bottom line: Contains matches (such as in stock_basic_info"bank" match configuration"bank") 
            if not profile:
                import re
                escaped = re.escape(industry)
                profile = db[INDUSTRY_COLLECTION].find_one(
                    {"industry": {"$regex": escaped, "$options": "i"}, "is_active": True}
                )
                if not profile:
                    # Reverse: The industry name in the configuration is included in the query industry name
                    all_profiles = list(db[INDUSTRY_COLLECTION].find({"is_active": True}))
                    for p in all_profiles:
                        if p.get("industry") and p["industry"] in industry:
                            profile = p
                            break

            if profile:
                dimensions = profile.get("analysis_dimensions", [])
                result["industry_dimensions"] = AnalysisProfileService.format_dimensions(dimensions)
                result["industry_focus"] = profile.get("analysis_focus", "")
                result["industry_key_metrics"] = ", ".join(profile.get("key_metrics", []))
                result["industry_comparable_companies"] = ", ".join(profile.get("comparable_companies", []))
                logger.info(f"🏭 [行业维度注入] {industry}: {len(dimensions)} 个维度")
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain industry analysis dimensions: {e}")
        return result

    @staticmethod
    def build_industry_prompt_block(industry: str) -> str:
        """
        Synchronously obtain industry analysis configuration, formatted as a text block that can be appended directly to Prompt.

        Returning an empty string indicates that the industry is not configured or the query failed.
        """
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            profile = db[INDUSTRY_COLLECTION].find_one(
                {"industry": industry, "is_active": True}
            )
            if not profile:
                return ""

            dimensions = profile.get("analysis_dimensions", [])
            if not dimensions:
                return ""

            blocks = ["\n\n## 行业分析重点\n"]

            # Analysis Dimensions
            blocks.append("### 核心分析维度\n")
            for d in dimensions:
                imp = d.get("importance", "high")
                imp_label = {"critical": "★", "high": "▲", "medium": "●", "low": "○"}.get(imp, "")
                blocks.append(f"- **{d.get('name', '')}** {imp_label}: {d.get('description', '')}")

            # Analysis focus
            focus = profile.get("analysis_focus", "")
            if focus:
                blocks.append(f"\n### 行业分析总览\n{focus}")

            # key indicators
            key_metrics = profile.get("key_metrics", [])
            if key_metrics:
                blocks.append(f"\n### 关键跟踪指标\n{', '.join(key_metrics)}")

            result = "\n".join(blocks)
            logger.info(f"🏭 [行业Prompt注入] {industry}: {len(dimensions)} 维度, 长度={len(result)}")
            return result
        except Exception as e:
            logger.warning(f"⚠️ Building industry prompt block failed: {e}")
            return ""

    @staticmethod
    def get_stock_dimensions_sync(stock_code: str) -> Dict[str, str]:
        """
        Synchronously obtain individual stock analysis dimensions (for _prepare_system_variables)

        Returns:
            contains stock_dimensions, stock_special_notes dictionary
        """
        result = {}
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            profile = db[STOCK_COLLECTION].find_one(
                {"stock_symbol": stock_code, "is_active": True}
            )
            if profile:
                dimensions = profile.get("analysis_dimensions", [])
                result["stock_dimensions"] = AnalysisProfileService.format_dimensions(dimensions)
                result["stock_special_notes"] = profile.get("special_notes", "")
                logger.info(f"📊 [个股维度注入] {stock_code}: {len(dimensions)} 个维度")
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain individual stock analysis dimensions: {e}")
        return result

    # ==================== AI Generate industry configuration ====================

    async def generate_industry_profile_with_ai(
        self,
        industry: str,
        user_request: str = "",
        existing_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Automatically generate industry analysis configurations using LLM

        Args:
            industry: Industry name, such as "bank", "New energy vehicles", "medical device"
            user_request: Users supplementary requirements or revised instructions for this round
            existing_profile: Current draft, used for multiple rounds of revisions

        Returns:
            Generated industry configuration dictionary (not saved to the database, user confirmation is required before saving)
        """
        from app.services.intelligent_assistant_service import get_reasoning_llm_config
        from core.llm import UnifiedLLMClient, Message

        db = get_mongo_db()
        config = await get_reasoning_llm_config(db)
        if not config:
            raise RuntimeError("LLM is not configured, please configure the large model in the system settings first")

        client = UnifiedLLMClient.from_config(config)

        prompt_parts = [
            f'You are a senior A-share industry research expert. please for"{industry}"The industry outputs a structured analysis dimension configuration.',
            "",
            "Requirements:",
            "1. Output the 5-8 most critical analysis_dimensions, each dimension containing:name / description / importance / data_source",
            "2. Output a section of analysis_focus (2-3 sentences)",
            "3. Output 5-8 key_metrics (names of key financial/business metrics)",
            "4. Output 3-5 comparable_companies (A-share comparable companies)",
            "5. If existing_profile exists, the task of this round is revised draft , Give priority to retaining reasonable items, and only add, delete or modify them according to user requirements, and do not make irrelevant items.",
            "6. Do not add back items that the user explicitly requests to delete.",
            "7. Please keep the output as pure JSON and do not include markdown code blocks or any additional instructions",
            "",
        ]

        if existing_profile:
            prompt_parts.extend([
                "current draft(existing_profile): ",
                json.dumps(existing_profile, ensure_ascii=False, indent=2),
                "",
            ])

        if user_request and user_request.strip():
            prompt_parts.extend([
                "User requirements for this round:",
                user_request.strip(),
                "",
            ])
        else:
            prompt_parts.extend([
                "User requirements for this round:",
                "Please provide a first draft that is suitable as an industry analysis template.",
                "",
            ])

        prompt_parts.extend([
            "Please directly output the following JSON structure:",
            "{",
            f'  "industry": "{industry}",',
            f'  "display_name": "{industry}行业",',
            '  "analysis_dimensions": [...],',
            '  "analysis_focus": "...",',
            '  "key_metrics": [...],',
            '  "comparable_companies": [...]',
            "}",
        ])

        prompt = "\n".join(prompt_parts)

        messages = [
            Message(role="system", content="You are a senior A-share industry research analyst, specializing in structured financial analysis. Please output only plain JSON, without any other text."),
            Message(role="user", content=prompt),
        ]

        response = await client.achat(messages)
        content = response.content.strip()

        # Clean up possible markdown code block tags
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            profile_data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"❌ AI 生成的行业配置 JSON 解析失败: {e}\n原文: {content[:500]}")
            raise ValueError(f"AI The generated content cannot be parsed as valid JSON: {e}")

        # Make sure required fields exist
        profile_data["industry"] = industry
        profile_data.setdefault("display_name", f"{industry}行业")
        profile_data.setdefault("is_active", True)
        profile_data.setdefault("source", "ai_generated")

        capability_snapshot = await self._collect_capability_snapshot(db)
        dimension_assessments = [
            self._evaluate_item_coverage(
                name=dimension.get("name", ""),
                description=dimension.get("description", ""),
                data_source=dimension.get("data_source", ""),
                capability_snapshot=capability_snapshot,
            )
            for dimension in profile_data.get("analysis_dimensions", [])
            if isinstance(dimension, dict)
        ]
        metric_assessments = [
            self._evaluate_item_coverage(
                name=metric,
                description="关键指标",
                data_source="metric",
                capability_snapshot=capability_snapshot,
            )
            for metric in profile_data.get("key_metrics", [])
            if isinstance(metric, str) and metric.strip()
        ]
        coverage_summary = self._build_coverage_summary(
            dimension_assessments=dimension_assessments,
            metric_assessments=metric_assessments,
            capability_snapshot=capability_snapshot,
        )

        preview = {
            "profile": profile_data,
            "coverage_summary": coverage_summary,
            "capability_snapshot": capability_snapshot,
            "dimension_assessments": dimension_assessments,
            "metric_assessments": metric_assessments,
            "next_step_guidance": [
                "Confirm first Can be used directly and Partially available of items fit your analytical framework.",
                "Yes external data required item, decide whether to access MCP/Skill, import manually, or delete it temporarily.",
                "Yes Recommend review If the data source cannot be explained, it is recommended to delete it first and then save it.",
            ],
        }

        logger.info(
            f"🤖 [AI生成] 行业配置: {industry}, 维度数: {len(profile_data.get('analysis_dimensions', []))}, "
            f"Requires external data items: {coverage_summary['dimension_counts']['external_required'] + coverage_summary['metric_counts']['external_required']}"
        )
        return preview

