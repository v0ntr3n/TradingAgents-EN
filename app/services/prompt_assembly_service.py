"""
Hierarchical prompt word assembly service

base template + Industry portrait + individual stock portrait + ability block + Task blocks are assembled into the final prompt.

Core responsibilities:
- Merge industry portraits and individual stock portraits (inherit/overwrite/addition)
- generate analysis_context_block
- generate capability_block
- generate task_block
- Complete assembly final Prompt
"""

import logging
from typing import Optional, Dict, Any, List

from app.services.analysis_profile_service import AnalysisProfileService
from app.services.prompt_injection_policy_service import PromptInjectionPolicyService
from tradingagents.utils.template_client import get_template_client

logger = logging.getLogger(__name__)


class PromptAssemblyService:
    """
    Hierarchical prompt word assembly service
    
    Implement design documentation §5 Runtime assembly rules for:
    - Industry Analysis: Basic Template → scenario strategy → ability block → Industry portrait block → task block
    - Individual Stock Analysis: Basic Template → scenario strategy → ability block → Industry portrait summary → individual stock portrait block → task block
    """
    
    def __init__(self):
        self.profile_service = AnalysisProfileService()
        self.policy_service = PromptInjectionPolicyService()
        self.template_client = get_template_client()
    
    # ==================== public interface ====================
    
    def _get_policy_sync(
        self,
        agent_type: Optional[str],
        agent_name: Optional[str],
        scope: str,
    ):
        """Get the injection strategy synchronously and return if there is no strategy. None"""
        if not agent_type or not agent_name:
            return None
        return self.policy_service.get_policy_by_agent_scope_sync(
            agent_type=agent_type,
            agent_name=agent_name,
            scope=scope,
        )

    def build_analysis_context_block(
        self,
        analysis_type: str,
        industry: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        policy_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build analysis_context_block (analysis context block)
        
        Args:
            analysis_type: Analysis type "general" / "industry" / "stock"
            industry: Industry name
            stock_symbol: Stock code
            agent_type: Agent Type (optional, used for policy queries)
            agent_name: Agent Name (optional, used for policy queries)
        
        Returns:
            Formatted analysis context block text
        """
        if analysis_type == "general":
            return ""

        # Phase 2: policy control - injection_mode=none not injected
        policy = policy_override if policy_override is not None else self._get_policy_sync(agent_type, agent_name, analysis_type)
        if policy and policy.get("injection_mode") == "none":
            logger.info(f"📋 [策略] {agent_type}/{agent_name} scope={analysis_type} injection_mode=none，跳过上下文块")
            return ""
        
        blocks = []
        
        # 1. Get industry portraits
        industry_profile = None
        if industry:
            industry_profile = self._get_industry_profile_sync(industry)
        
        # 2. Get individual stock portraits
        stock_profile = None
        if stock_symbol and analysis_type == "stock":
            stock_profile = self._get_stock_profile_sync(stock_symbol)
        
        # 3. Merge portraits (policy control inherit_industry_for_stock, include_comparable_companies)
        inherit_industry = policy.get("inherit_industry_for_stock", True) if policy else True
        include_comparable = policy.get("include_comparable_companies", True) if policy else True
        merged = self._merge_profiles(
            industry_profile,
            stock_profile,
            inherit_industry_for_stock=inherit_industry,
            include_comparable_companies=include_comparable,
        )
        
        # 3.5 Strategy:injection_mode=summary When doing summary compression (design document §4.2) 
        injection_mode = (policy.get("injection_mode") if policy else None) or "full"
        if injection_mode == "summary":
            merged = self._summarize_merged_profile(merged)
            logger.info("📋 [analysis_context_block] Using summary mode, dimensions and text are compressed")
        
        # 4. Formatted output
        if merged.get("dimensions"):
            blocks.append("## 分析维度\n")
            for dim in merged["dimensions"]:
                importance = dim.get("importance", "high")
                name = dim.get("name", "")
                desc = dim.get("description", "")
                source = dim.get("source", "")
                source_hint = f"（来自{source}）" if source else ""
                blocks.append(f"- **{name}** [{importance}]{source_hint}: {desc}")
        
        if merged.get("key_metrics"):
            blocks.append("\n## 关键指标\n")
            blocks.append(", ".join(merged["key_metrics"]))
        
        if merged.get("analysis_focus"):
            blocks.append("\n## 分析重点\n")
            blocks.append(merged["analysis_focus"])
        
        if include_comparable and merged.get("comparable_companies"):
            blocks.append("\n## 可比公司\n")
            blocks.append(", ".join(merged["comparable_companies"]))
        
        if merged.get("special_notes"):
            blocks.append("\n## 特殊说明\n")
            blocks.append(merged["special_notes"])
        
        result = "\n".join(blocks)
        if result:
            logger.info(f"📋 [analysis_context_block] Generate length: {len(result)}")
        return result
    
    def build_capability_block(
        self,
        analysis_type: str,
        industry: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        policy_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build capability_block (capability boundary specification block)
        
        Tell the model which data can be used directly and which needs to be expressed conservatively
        
        Args:
            analysis_type: Analysis type
            industry: Industry name
            stock_symbol: Stock code
            agent_type: Agent Type (optional, used for policy queries)
            agent_name: Agent Name (optional, used for policy queries)
        
        Returns:
            Formatted capability boundary description text
        """
        # Phase 2: policy control - include_capability_block=False not injected
        policy = policy_override if policy_override is not None else self._get_policy_sync(agent_type, agent_name, analysis_type)
        if policy and policy.get("include_capability_block") is False:
            logger.info(f"🔧 [策略] {agent_type}/{agent_name} scope={analysis_type} include_capability_block=False，跳过能力块")
            return ""

        # Collection capability snapshot
        capability = self._collect_capability_snapshot_sync()
        
        blocks = []
        blocks.append("## 数据能力边界\n")
        
        # Can be used directly
        builtin = capability.get("builtin_sources", [])
        if builtin:
            blocks.append("### Ready-to-use data capabilities")
            for src in builtin[:4]:
                blocks.append(f"- {src.get('label')}: {src.get('description')[:80]}")
        
        # Can be obtained indirectly
        mcp_servers = capability.get("enabled_mcp_servers", [])
        skills = capability.get("active_skills", [])
        if mcp_servers or skills:
            blocks.append("\n### Indirectly accessible data capabilities")
            if mcp_servers:
                blocks.append("- MCP 服务:")
                for srv in mcp_servers[:3]:
                    desc = srv.get('description', '')[:60]
                    if not desc:
                        desc = f"{srv.get('tool_count', 0)} 个工具"
                    blocks.append(f"  - {srv.get('name')}: {desc}")
            if skills:
                blocks.append("- Skill 能力:")
                for sk in skills[:3]:
                    blocks.append(f"  - {sk.get('name')}: {sk.get('description', '')[:60]}")
        
        # Currently missing reminders (policy can turn off include_external_gap_notice)
        if policy is None or policy.get("include_external_gap_notice", True):
            blocks.append("\n### 数据缺口提醒")
            blocks.append("- If you need unstructured information such as operational indicators and industry external data, it is recommended to combine MCP/Skill or external data sources.")
            blocks.append("- Qualitative indicators (such as brand power, management execution ability, etc.) need to rely on professional judgment or external research reports")
        
        result = "\n".join(blocks)
        logger.info(f"🔧 [capability_block] Generate length: {len(result)}")
        return result
    
    def build_task_block(
        self,
        task_description: str,
        analysis_type: str,
    ) -> str:
        """
        Build task_block (task instruction block)
        
        Args:
            task_description: Current task description
            analysis_type: Analysis type
        
        Returns:
            Formatted task block text
        """
        if not task_description:
            return ""
        
        type_labels = {
            "general": "通用分析",
            "industry": "行业分析",
            "stock": "个股分析",
        }
        
        blocks = []
        blocks.append("## 当前分析任务\n")
        blocks.append(f"**分析类型**: {type_labels.get(analysis_type, analysis_type)}\n")
        blocks.append(f"**任务目标**:\n{task_description}")
        
        result = "\n".join(blocks)
        logger.info(f"🎯 [task_block] Generate length: {len(result)}")
        return result
    
    def assemble_prompt(
        self,
        agent_type: str,
        agent_name: str,
        analysis_type: str = "general",
        industry: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        task_description: str = "",
        include_capability: bool = True,
        variables: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        node_id: Optional[str] = None,
        template_override: Optional[Dict[str, Any]] = None,
        policy_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Complete assembly entrance: select template → Generate three blocks → variable substitution → return final Prompt
        
        Args:
            agent_type: Agent Type
            agent_name: Agent Name
            analysis_type: Analysis type "general" / "industry" / "stock"
            industry: Industry name
            stock_symbol: Stock code
            task_description: Task description
            include_capability: Whether to include ability blocks
            variables: Dictionary of extra variables
        
        Returns:
            {
                "final_prompt": str,          # finally complete Prompt
                "sections": Dict[str, str],   # Content of each paragraph
                "sources": Dict[str, str],    # Source of each paragraph
                "template_id": str,           # Template used ID
                "profile_used": Dict,         # Image information used
                "capability_gaps": List[str], # Ability gap reminder
            }
        """
        # 1. Get template
        template = template_override or self.template_client.get_effective_template(
            agent_type,
            agent_name,
            workflow_id=workflow_id,
            node_id=node_id,
        )
        if not template:
            logger.warning(f"⚠️ 未找到模板: {agent_type}/{agent_name}")
            template = {}
        
        template_id = template.get("template_id", "")
        
        # 2. Get Strategy (Phase 2)
        policy_override = (policy_overrides or {}).get(analysis_type)
        policy = policy_override if policy_override is not None else self._get_policy_sync(agent_type, agent_name, analysis_type)
        effective_include_capability = include_capability
        if policy and policy.get("include_capability_block") is False:
            effective_include_capability = False

        # 3. Generate three blocks (pass in agent information for policy control)
        context_block = self.build_analysis_context_block(
            analysis_type, industry, stock_symbol,
            agent_type=agent_type, agent_name=agent_name,
            policy_override=policy,
        )
        capability_block = self.build_capability_block(
            analysis_type, industry, stock_symbol,
            agent_type=agent_type, agent_name=agent_name,
            policy_override=policy,
        ) if effective_include_capability else ""
        task_block = self.build_task_block(task_description, analysis_type)
        
        # 4. Prepare variables (contains three new blocks)
        final_variables = variables or {}
        final_variables["analysis_context_block"] = context_block
        final_variables["capability_block"] = capability_block
        final_variables["task_block"] = task_block
        
        # 4. Format template
        formatted = self.template_client.format_template(template, final_variables)
        
        # 4.5 Strategy inject_position: If the template does not contain placeholders, append the block to the field specified by the strategy (design document §7.2) 
        inject_pos = (policy.get("inject_position") if policy else None) or "analysis_requirements"
        for key in ("system_prompt", "analysis_requirements", "constraints"):
            if key not in formatted or formatted[key] is None:
                formatted[key] = ""
        if context_block and inject_pos in formatted and context_block[:40] not in (formatted.get(inject_pos) or ""):
            formatted[inject_pos] = (formatted[inject_pos] or "").strip() + "\n\n" + context_block
        if task_block and "analysis_requirements" in formatted and task_block[:40] not in (formatted.get("analysis_requirements") or ""):
            formatted["analysis_requirements"] = (formatted["analysis_requirements"] or "").strip() + "\n\n" + task_block
        if capability_block and "constraints" in formatted and capability_block[:40] not in (formatted.get("constraints") or ""):
            formatted["constraints"] = (formatted["constraints"] or "").strip() + "\n\n" + capability_block
        
        # 5. Assembly final Prompt
        parts = []
        sections = {}
        sources = {}
        
        if formatted.get("system_prompt"):
            parts.append(formatted["system_prompt"])
            sections["system_prompt"] = formatted["system_prompt"]
            sources["system_prompt"] = "基础角色模板"
        
        if formatted.get("tool_guidance"):
            parts.append("\n\n" + formatted["tool_guidance"])
            sections["tool_guidance"] = formatted["tool_guidance"]
            sources["tool_guidance"] = "基础角色模板"
        
        # analysis_requirements bear context_block + task_block
        if formatted.get("analysis_requirements"):
            parts.append("\n\n" + formatted["analysis_requirements"])
            sections["analysis_requirements"] = formatted["analysis_requirements"]
            sources["analysis_requirements"] = "基础模板 + 上下文注入"
        
        if formatted.get("output_format"):
            parts.append("\n\n" + formatted["output_format"])
            sections["output_format"] = formatted["output_format"]
            sources["output_format"] = "基础角色模板"
        
        # constraints bear capability_block
        if formatted.get("constraints"):
            parts.append("\n\n" + formatted["constraints"])
            sections["constraints"] = formatted["constraints"]
            sources["constraints"] = "Basic template + Capability Boundary Injection"
        
        # Record three sources
        if context_block:
            sections["analysis_context_block"] = context_block
            sources["analysis_context_block"] = f"画像服务（行业={industry or 'N/A'}, 个股={stock_symbol or 'N/A'}）"
        if capability_block:
            sections["capability_block"] = capability_block
            sources["capability_block"] = "能力评估服务"
        if task_block:
            sections["task_block"] = task_block
            sources["task_block"] = "任务描述"
        
        final_prompt = "\n".join(parts)
        
        # 6. Collection capacity gap
        capability_gaps = self._collect_capability_gaps(analysis_type, industry, stock_symbol)
        
        # 7. Collect and use portrait information
        profile_used = {
            "industry": industry,
            "stock_symbol": stock_symbol,
            "industry_profile_found": bool(self._get_industry_profile_sync(industry)) if industry else False,
            "stock_profile_found": bool(self._get_stock_profile_sync(stock_symbol)) if stock_symbol else False,
        }
        
        logger.info(
            f"✅ [assemble_prompt] 组装完成: {agent_type}/{agent_name}, "
            f"Type={analysis_type}, final length={len(final_prompt)}"
        )
        
        return {
            "final_prompt": final_prompt,
            "sections": sections,
            "sources": sources,
            "template_id": template_id,
            "profile_used": profile_used,
            "capability_gaps": capability_gaps,
        }
    
    # ==================== internal tools ====================
    
    def _get_industry_profile_sync(self, industry: str) -> Optional[Dict]:
        """同步获取行业画像"""
        if not industry:
            return None
        try:
            result = AnalysisProfileService.get_industry_dimensions_sync(industry)
            if result:
                # Rebuild profile structure
                from app.core.database import get_mongo_db_sync
                db = get_mongo_db_sync()
                doc = db["industry_analysis_profiles"].find_one(
                    {"industry": industry, "is_active": True}
                )
                if doc:
                    doc["id"] = str(doc.pop("_id"))
                    return doc
        except Exception as e:
            logger.warning(f"⚠️ 获取行业画像失败: {e}")
        return None
    
    def _get_stock_profile_sync(self, stock_symbol: str) -> Optional[Dict]:
        """同步获取个股画像"""
        if not stock_symbol:
            return None
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            doc = db["stock_analysis_profiles"].find_one(
                {"stock_symbol": stock_symbol, "is_active": True}
            )
            if doc:
                doc["id"] = str(doc.pop("_id"))
                return doc
        except Exception as e:
            logger.warning(f"⚠️ 获取个股画像失败: {e}")
        return None
    
    def _merge_profiles(
        self,
        industry_profile: Optional[Dict],
        stock_profile: Optional[Dict],
        inherit_industry_for_stock: bool = True,
        include_comparable_companies: bool = True,
    ) -> Dict[str, Any]:
        """
        Merge industry portraits and individual stock portraits
        
        Rules (corresponding to design documents §6) :
        1. inherit: The analysis dimensions and key indicators in the industry portrait are inherited by default.
        2. append: Individual stocks can add exclusive dimensions
        3. override: Individual stocks can rewrite the description or importance of an industry dimension
        4. disable: Individual stocks can explicitly turn off the default dimensions of certain industries
        
        Args:
            industry_profile: Industry portrait
            stock_profile: individual stock portrait
            inherit_industry_for_stock: Whether individual stock scenarios inherit industry portraits (strategy control)
            include_comparable_companies: Whether to include comparable companies (strategic control)
        
        Returns:
            Combined structured content
        """
        result = {
            "dimensions": [],
            "key_metrics": [],
            "analysis_focus": "",
            "comparable_companies": [],
            "special_notes": "",
        }
        
        # 1. Inherited from industry portraits (individual stock scenarios and inherit_industry_for_stock=False skip when)
        if industry_profile and not (stock_profile and not inherit_industry_for_stock):
            dims = industry_profile.get("analysis_dimensions", [])
            for d in dims:
                result["dimensions"].append({
                    **d,
                    "source": "行业画像",
                })
            result["key_metrics"] = list(industry_profile.get("key_metrics", []))
            result["analysis_focus"] = industry_profile.get("analysis_focus", "")
            result["comparable_companies"] = list(industry_profile.get("comparable_companies", []))
        
        # 2. Apply stock portrait overlay
        if stock_profile:
            stock_dims = stock_profile.get("analysis_dimensions", [])
            stock_overrides = stock_profile.get("dimension_overrides", {})  # {Dimension name: {action: "override"/"disable", ...}}
            
            # Handle append/overwrite
            for sd in stock_dims:
                name = sd.get("name", "")
                existing_idx = next(
                    (i for i, d in enumerate(result["dimensions"]) if d.get("name") == name),
                    None
                )
                
                if existing_idx is not None:
                    # override: Overwrite existing dimensions
                    result["dimensions"][existing_idx] = {
                        **result["dimensions"][existing_idx],
                        **sd,
                        "source": "个股画像覆盖",
                    }
                else:
                    # append: Add new dimensions
                    result["dimensions"].append({
                        **sd,
                        "source": "个股画像追加",
                    })
            
            # Process disable
            for dim_name, override_info in stock_overrides.items():
                if override_info.get("action") == "disable":
                    result["dimensions"] = [
                        d for d in result["dimensions"]
                        if d.get("name") != dim_name
                    ]
            
            # Combine key metrics
            stock_metrics = stock_profile.get("key_metrics", [])
            for m in stock_metrics:
                if m not in result["key_metrics"]:
                    result["key_metrics"].append(m)
            
            # Special instructions
            if stock_profile.get("special_notes"):
                result["special_notes"] = stock_profile["special_notes"]

        # Policy Control: Empty when no comparable companies are included
        if not include_comparable_companies:
            result["comparable_companies"] = []
        
        return result
    
    def _summarize_merged_profile(self, merged: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summary mode: compress the merged portrait, control token (design document §4.2 injection_mode=summary) 
        - A maximum of 5 analysis dimensions are allowed, and the description is truncated to 50 words.
        - Up to 5 key indicators
        - Analysis highlights truncated to 100 words
        - Up to 3 comparable companies
        - Special instructions truncated to 80 words
        """
        out = dict(merged)
        summary_desc_len = 50
        summary_focus_len = 100
        summary_notes_len = 80
        max_dimensions = 5
        max_key_metrics = 5
        max_comparable = 3

        if out.get("dimensions"):
            out["dimensions"] = [
                {
                    **d,
                    "description": (d.get("description") or "")[:summary_desc_len]
                    + ("..." if len((d.get("description") or "")) > summary_desc_len else ""),
                }
                for d in out["dimensions"][:max_dimensions]
            ]
        if out.get("key_metrics"):
            out["key_metrics"] = list(out["key_metrics"][:max_key_metrics])
        if out.get("analysis_focus"):
            s = out["analysis_focus"]
            out["analysis_focus"] = s[:summary_focus_len] + ("..." if len(s) > summary_focus_len else "")
        if out.get("comparable_companies"):
            out["comparable_companies"] = list(out["comparable_companies"][:max_comparable])
        if out.get("special_notes"):
            s = out["special_notes"]
            out["special_notes"] = s[:summary_notes_len] + ("..." if len(s) > summary_notes_len else "")
        return out
    
    def _collect_capability_snapshot_sync(self) -> Dict[str, Any]:
        """同步收集能力快照"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            
            # Collection logic using the capabilities of AnalysisProfileService
            service = AnalysisProfileService()
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If there is an event loop, use synchronization
                    return self._collect_capability_sync_impl(db)
                else:
                    return loop.run_until_complete(service._collect_capability_snapshot(db))
            except RuntimeError:
                return self._collect_capability_sync_impl(db)
        except Exception as e:
            logger.warning(f"⚠️ 收集能力快照失败: {e}")
            return {"builtin_sources": [], "enabled_mcp_servers": [], "active_skills": []}
    
    def _collect_capability_sync_impl(self, db) -> Dict[str, Any]:
        """同步收集能力快照的实现"""
        from app.services.analysis_profile_service import BUILTIN_SOURCE_DEFINITIONS
        
        builtin_sources = [
            {"key": item["key"], "label": item["label"], "description": item["description"]}
            for item in BUILTIN_SOURCE_DEFINITIONS
        ]
        
        enabled_mcp_servers = []
        try:
            for doc in db["mcp_server_configs"].find({"is_enabled": True}):
                tools = doc.get("discovered_tools", []) or []
                enabled_mcp_servers.append({
                    "server_id": doc.get("server_id", ""),
                    "name": doc.get("name", ""),
                    "description": doc.get("description", ""),
                    "tool_count": len(tools),
                })
        except Exception:
            pass
        
        active_skills = []
        try:
            for doc in db["external_skills"].find({"status": "active"}):
                active_skills.append({
                    "tool_id": doc.get("tool_id", ""),
                    "name": doc.get("display_name", ""),
                    "description": doc.get("description", ""),
                })
        except Exception:
            pass
        
        return {
            "builtin_sources": builtin_sources,
            "enabled_mcp_servers": enabled_mcp_servers,
            "active_skills": active_skills,
        }
    
    def _collect_capability_gaps(
        self,
        analysis_type: str,
        industry: Optional[str],
        stock_symbol: Optional[str],
    ) -> List[str]:
        """收集能力缺口提醒"""
        gaps = []
        
        # Check whether the industry portrait exists
        if industry and analysis_type in ("industry", "stock"):
            profile = self._get_industry_profile_sync(industry)
            if not profile:
                gaps.append(f"行业「{industry}」暂无画像配置，建议先创建行业分析画像")
        
        # Check whether the stock image exists
        if stock_symbol and analysis_type == "stock":
            profile = self._get_stock_profile_sync(stock_symbol)
            if not profile:
                gaps.append(f"个股「{stock_symbol}」暂无画像配置，将使用行业画像作为默认框架")
        
        # Check MCP/Skill availability
        capability = self._collect_capability_snapshot_sync()
        if not capability.get("enabled_mcp_servers"):
            gaps.append("No MCP servers are currently enabled, and some data capabilities may be limited.")
        
        return gaps


# ==================== Global singleton ====================

_assembly_service: Optional[PromptAssemblyService] = None


def get_prompt_assembly_service() -> PromptAssemblyService:
    """Get the PromptAssemblyService global singleton"""
    global _assembly_service
    if _assembly_service is None:
        _assembly_service = PromptAssemblyService()
    return _assembly_service