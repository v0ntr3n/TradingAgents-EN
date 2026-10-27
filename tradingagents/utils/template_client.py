"""
Prompt word template client - used by Agent to obtain prompt words from the template system

Directly connect to MongoDB to obtain the template, and it does not pass HTTP API
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Optional, Dict, Any
from pymongo import MongoClient
from bson import ObjectId
from tradingagents.utils.logging_init import get_logger

if TYPE_CHECKING:
    # Only type annotations are used; the top-level import triggers the initialization of the tradingagents.agents package.
    # with agents/* Module reverse import This module (get_agent_prompt) forms a circular import
    from tradingagents.agents.utils.agent_context import AgentContext

logger = get_logger("template_client")


class TemplateClient:
    """Prompt word template client - direct connection MongoDB"""

    def __init__(self, mongo_uri: Optional[str] = None, db_name: Optional[str] = None):
        """
        Initialize template client

        Args:
            mongo_uri: MongoDB Connection string, built from environment variables by default
            db_name: Database name, read from environment variables by default
        """
        from tradingagents.config.mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name

        self.mongo_uri = mongo_uri or build_mongodb_connection_string()
        self.db_name = db_name or get_mongodb_database_name()

        # Create MongoDB connection
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.db_name]
        self.templates_collection = self.db.prompt_templates
        self.configs_collection = self.db.user_template_configs

        logger.info(f"✅ Template client initialization successful: {self.db_name}")

    def get_effective_template(
        self,
        agent_type: str,
        agent_name: str,
        user_id: Optional[str] = None,
        preference_id: Optional[str] = None,
        context: Optional[AgentContext] = None,
        workflow_id: Optional[str] = None,  # 🆕 Process-specific prompt word support
        node_id: Optional[str] = None        # 🆕 Node-specific prompt word support
    ) -> Optional[Dict[str, Any]]:
        """
        Get a valid template (supports process-specific prompt words + Node-specific prompt words)

        Priority order:
        1. Debug Template (is_debug_mode=True and debug_template_id has a value)
        2. Node-specific templates (workflow_id + node_id + agent_name, The same agent has different prompt words at different nodes)
        2.5. Process-specific templates (workflow_id + agent_name, Downgrade without node_id)
        3. User configuration template (template configured by user_id)
        4. User preference system template (system template corresponding to preference_type)
        5. Default system template (workflow_id=None system template)

        Args:
            agent_type: Agent type(analysts, researchers, debators, managers, trader) 
            agent_name: Agent Name
            user_id: User ID (optional)
            preference_id: Preference ID (optional, default is neutral)
            context: AgentContext Object containing debug mode information and workflow_id
            workflow_id: 🆕 Workflow ID (optional, used to load process-specific prompt words)
            node_id: 🆕 Node ID (optional, used when the same agent has different prompt words on different nodes)

        Returns:
            Template content dictionary, including system_prompt, tool_guidance, analysis_requirements and other fields
            If the acquisition fails, return None
        """
        try:
            # Compatible context is dict or AgentContext object
            ctx_user = None
            ctx_pref = None
            ctx_workflow_id = None  # 🆕 Extract from context workflow_id
            ctx_node_id = None      # 🆕 Extract from context node_id
            is_debug_mode = False
            debug_template_id = None

            if context:
                if isinstance(context, dict):
                    ctx_user = context.get('user_id')
                    ctx_pref = context.get('preference_id')
                    ctx_workflow_id = context.get('workflow_id')  # 🆕
                    ctx_node_id = context.get('node_id')          # 🆕
                    is_debug_mode = context.get('is_debug_mode', False)
                    debug_template_id = context.get('debug_template_id') if is_debug_mode else None
                else:
                    ctx_user = getattr(context, 'user_id', None)
                    ctx_pref = getattr(context, 'preference_id', None)
                    ctx_workflow_id = getattr(context, 'workflow_id', None)  # 🆕
                    ctx_node_id = getattr(context, 'node_id', None)          # 🆕
                    is_debug_mode = getattr(context, 'is_debug_mode', False)
                    # 🔥 Fix: should extract regardless of whether is_debug_mode is True debug_template_id
                    debug_template_id = getattr(context, 'debug_template_id', None)

            # 🆕 Merge workflow_id and node_id: parameters first, context second
            effective_workflow_id = workflow_id or ctx_workflow_id
            effective_node_id = node_id or ctx_node_id

            # 🔥 Debug log: record context parsing results
            logger.info(f"🔍 [get_effective_template] Context Parse results:")
            logger.info(f"   - context Type: {type(context)}")
            logger.info(f"   - is_debug_mode: {is_debug_mode}")
            logger.info(f"   - debug_template_id: {debug_template_id}")
            logger.info(f"   - user_id: {ctx_user}")
            logger.info(f"   - preference_id: {ctx_pref}")
            logger.info(f"   - workflow_id (parameters): {workflow_id}")
            logger.info(f"   - workflow_id (context): {ctx_workflow_id}")
            logger.info(f"   - workflow_id (valid): {effective_workflow_id}")
            logger.info(f"   - node_id (parameters): {node_id}")
            logger.info(f"   - node_id (context): {ctx_node_id}")
            logger.info(f"   - node_id (valid): {effective_node_id}")

            logger.info(
                f"[diagnose] input agent_type={agent_type} agent_name={agent_name} "
                f"user_id={user_id} pref={preference_id} ctx_user={ctx_user} ctx_pref={ctx_pref}"
            )

            # 🔥 The debug template has the highest priority: if debug_template_id is provided, use the debug template directly (highest priority)
            # Note: In debugging mode, it does not check whether agent_type and agent_name match, allowing cross-type debugging.
            # 🔥 Fix: debug template should be used even if is_debug_mode is False as long as debug_template_id is provided
            if debug_template_id:
                logger.info(f"🔍 [debug mode] Use debug templates ID: {debug_template_id} (highest priority)")
                try:
                    template_oid = debug_template_id if isinstance(debug_template_id, ObjectId) else ObjectId(str(debug_template_id))
                    debug_template = self.templates_collection.find_one({"_id": template_oid})

                    if debug_template:
                        # 🔥 Validate agent_type and agent_name of template (only for logging, does not prevent use)
                        template_agent_type = debug_template.get("agent_type")
                        template_agent_name = debug_template.get("agent_name")
                        
                        if template_agent_type != agent_type or template_agent_name != agent_name:
                            logger.warning(
                                f"⚠️ [debug mode] Debug template s agent_type/agent_name mismatch: "
                                f"Template({template_agent_type}/{template_agent_name}) vs "
                                f"Request({agent_type}/{agent_name}), but still uses debug templates (debug mode allows cross-types)"
                            )
                        
                        logger.info(
                            f"✅ [debug mode] Successfully obtained debugging template: {agent_type}/{agent_name} "
                            f"(template_id={debug_template_id}, template type={template_agent_type}/{template_agent_name})"
                        )
                        content = debug_template.get("content") or {}
                        
                        # 🔥 Debugging: Print details of template content
                        logger.info(f"🔍 [debug mode] Template content fields: {list(content.keys())}")
                        if "user_prompt" in content:
                            user_prompt_preview = str(content["user_prompt"])[:200] if content["user_prompt"] else ""
                            logger.info(f"🔍 [debug mode] user_prompt length: {len(str(content.get('user_prompt', '')))}, first 200 characters: {user_prompt_preview}")
                        if "system_prompt" in content:
                            system_prompt_preview = str(content["system_prompt"])[:200] if content["system_prompt"] else ""
                            logger.info(f"🔍 [debug mode] system_prompt length: {len(str(content.get('system_prompt', '')))}, first 200 characters: {system_prompt_preview}")
                        
                        content["source"] = "debug"
                        content["template_id"] = str(debug_template.get("_id"))
                        content["version"] = debug_template.get("version", 1)
                        content["is_debug"] = True
                        logger.info(f"🔍 [debug mode] The debugging template has the highest priority and will be returned directly, skipping subsequent agent configuration checks.")
                        return content
                    else:
                        logger.warning(f"⚠️ [debug mode] Debug template does not exist: {debug_template_id}, Downgrade to normal process")
                except Exception as e:
                    logger.error(f"❌ [debug mode] Failed to obtain debugging template: {e}, Downgrade to normal process")
            
            # 🔥 If debug mode is enabled but there is no debug template ID, log a warning but do not prevent continuing
            if is_debug_mode and not debug_template_id:
                logger.warning(f"⚠️ [debug mode] Debug mode is enabled but debug_template_id is not provided, normal process will be used")

            # The default preference is neutral
            # Compatible context is dict or AgentContext object
            if context:
                if isinstance(context, dict):
                    # context is a dictionary
                    preference_id = context.get("preference_id") or preference_id
                    user_id = context.get("user_id") or user_id
                else:
                    # context is an AgentContext object
                    preference_id = context.preference_id if context.preference_id else preference_id
                    user_id = context.user_id if context.user_id else user_id
            preference_id = preference_id or "neutral"

            # 🆕 Priority 1.5: Node-specific templates/process-specific templates
            # Query strategy:
            #   1) Yes node_id → Exact match first workflow_id + node_id, Then downgrade to workflow_id (no node_id)
            #   2) None node_id → Match workflow_id directly (old behavior)
            if effective_workflow_id:
                def _find_workflow_template(extra_filter: dict) -> Optional[dict]:
                    """Auxiliary: Check the process template according to the given additional conditions, first try matching preferences, and then try without preferences"""
                    base_query = {
                        "agent_type": agent_type,
                        "agent_name": agent_name,
                        "workflow_id": effective_workflow_id,
                        "status": "active",
                        **extra_filter,
                    }
                    if preference_id:
                        q = {**base_query, "preference_type": preference_id}
                        tpl = self.templates_collection.find_one(q)
                        if tpl:
                            return tpl
                        # Downgrade: No preferred process template
                        q_no_pref = {**base_query, "preference_type": None}
                        return self.templates_collection.find_one(q_no_pref)
                    return self.templates_collection.find_one(base_query)

                workflow_template = None
                template_source_label = "workflow_specific"

                # Step 1: If there is node_id, check the node-specific template first
                if effective_node_id:
                    workflow_template = _find_workflow_template({"node_id": effective_node_id})
                    if workflow_template:
                        template_source_label = "node_specific"
                        logger.info(
                            f"✅ [priority 1.5a] Get node-specific templates: {agent_type}/{agent_name} "
                            f"(workflow_id={effective_workflow_id}, node_id={effective_node_id})"
                        )

                # Step 2: If there is no node-specific template, downgrade to a process template without node_id (compatible with old data)
                # Only match documents whose node_id is empty/non-existent to avoid mismatching node-specific templates
                if not workflow_template:
                    workflow_template = _find_workflow_template({
                        "$or": [
                            {"node_id": {"$exists": False}},
                            {"node_id": None},
                            {"node_id": ""}
                        ]
                    })
                    if workflow_template:
                        logger.info(
                            f"✅ [priority 1.5b] Get process-specific templates: {agent_type}/{agent_name} "
                            f"(workflow_id={effective_workflow_id}, node_id={effective_node_id or 'N/A'})"
                        )

                if workflow_template:
                    content = workflow_template.get("content") or {}
                    content["source"] = template_source_label
                    content["template_id"] = str(workflow_template.get("_id"))
                    content["version"] = workflow_template.get("version", 1)
                    content["workflow_id"] = effective_workflow_id
                    content["node_id"] = effective_node_id or ""
                    content["selected_preference"] = preference_id
                    return content
                else:
                    logger.info(
                        f"📝 [priority 1.5] Process/node specific template not found: {agent_type}/{agent_name} "
                        f"(workflow_id={effective_workflow_id}, node_id={effective_node_id or 'N/A'}), Continue to find the default template"
                    )

            # 1. Priority 1: If user_id is specified, first check whether the user has set a template in the agent configuration.
            if user_id:
                user_oid = None
                try:
                    user_oid = user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))
                except Exception:
                    user_oid = None

                if user_oid:
                    config_query = {
                        "user_id": user_oid,
                        "agent_type": agent_type,
                        "agent_name": agent_name,
                        "is_active": True
                    }
                    logger.info(f"[diagnose] config_query={config_query}")
                    config = self.configs_collection.find_one(config_query)

                    if config and config.get("template_id"):
                        template_oid = None
                        try:
                            tid = config["template_id"]
                            template_oid = tid if isinstance(tid, ObjectId) else ObjectId(str(tid))
                        except Exception:
                            template_oid = None
                            logger.info(f"[diagnose] template_id_convert_failed raw={config.get('template_id')}")

                        # 🔥 Only use templates in the published state
                        template = self.templates_collection.find_one({
                            "_id": template_oid,
                            "status": "active"
                        }) if template_oid else None

                        if template:
                            logger.info(
                                f"[diagnose] path=user_active_config config_id={config.get('_id')} "
                                f"template_id={template.get('_id')} version={template.get('version')} pref={config.get('preference_id')}"
                            )
                            logger.info(
                                f"✅ [priority 1] Get the template set by the user in the agent configuration: {agent_type}/{agent_name} "
                                f"(user_id={user_id}, template_id={template_oid})"
                            )
                            content = template.get("content") or {}
                            content["source"] = "user_config"
                            content["template_id"] = str(template.get("_id"))
                            content["version"] = template.get("version", 1)
                            content["selected_preference"] = config.get("preference_id") or preference_id
                            return content
                        else:
                            # If the user-configured template is in draft status, log a warning and skip it
                            logger.warning(
                                f"⚠️ User configured templates {template_oid} Not in published status or does not exist, downgraded to user preference template"
                            )
                            logger.info("[diagnose] user_config_found_but_template_lookup_failed_or_not_active")

            # 2. Priority 2: Find the [default] system template corresponding to user preferences
            # 🔥 Backward compatibility: only matches if workflow_id is empty or does not exist (old default template), excludes process-specific templates
            system_query = {
                "agent_type": agent_type,
                "agent_name": agent_name,
                "preference_type": preference_id,
                "is_system": True,
                "status": "active",
                "$or": [{"workflow_id": {"$exists": False}}, {"workflow_id": None}]
            }

            system_template = self.templates_collection.find_one(system_query)

            if system_template:
                logger.info(
                    f"✅ [priority 2] Get the system template corresponding to user preferences: {agent_type}/{agent_name} (preference={preference_id})"
                )
                logger.info(f"[diagnose] path=system_fallback system_query={system_query}")
                content = system_template.get("content") or {}
                content["source"] = "system"
                content["template_id"] = str(system_template.get("_id"))
                content["version"] = system_template.get("version", 1)
                content["selected_preference"] = preference_id
                return content

            # 3. Priority 3: If no template corresponding to user preference is found, downgrade to the default neutral template.
            # 🔥 Backward compatibility: only matches the default template (workflow_id is empty or does not exist)
            if preference_id != "neutral":
                logger.info(
                    f"⚠️ Preference not found {preference_id} system template, downgrade to the default neutral template: {agent_type}/{agent_name}"
                )
                neutral_query = {
                    "agent_type": agent_type,
                    "agent_name": agent_name,
                    "preference_type": "neutral",
                    "is_system": True,
                    "status": "active",
                    "$or": [{"workflow_id": {"$exists": False}}, {"workflow_id": None}]
                }
                neutral_template = self.templates_collection.find_one(neutral_query)
                if neutral_template:
                    logger.info(f"✅ [priority 3] Get the default neutral system template: {agent_type}/{agent_name}")
                    content = neutral_template.get("content") or {}
                    content["source"] = "system"
                    content["template_id"] = str(neutral_template.get("_id"))
                    content["version"] = neutral_template.get("version", 1)
                    content["selected_preference"] = "neutral"
                    return content

            logger.error(
                f"❌ No available templates found: {agent_type}/{agent_name} (preference={preference_id})"
            )
            return None

        except Exception as e:
            logger.error(f"❌ Get template exception: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def format_template(
        self,
        template_content: Dict[str, Any],
        variables: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Format template, replace variables

        Two syntaxes are supported:
        1. Single level braces:{variable_name}
        2. Double curly braces (Jinja2 style):{{variable.nested_key}}

        Args:
            template_content: Template content dictionary (returned from get_effective_template)
            variables: Variable dictionary, supports nesting, such as {"trade": {"code": "300274"}}

        Returns:
            Formatted template content dictionary
        """
        try:
            # Three variables for hierarchical prompt words: empty by default when not passed in, to prevent template placeholders from being rendered as None (design document §5.3) 
            if variables is not None:
                variables = dict(variables)
                variables.setdefault("analysis_context_block", "")
                variables.setdefault("capability_block", "")
                variables.setdefault("task_block", "")
            else:
                variables = {
                    "analysis_context_block": "",
                    "capability_block": "",
                    "task_block": "",
                }

            # Print input variables (for debugging)
            logger.info(f"🔧 [format_template] input variables (total {len(variables)} a):")
            if not variables:
                logger.warning(f"⚠️ [format_template] The variable dictionary is empty!")
            else:
                for k, v in variables.items():
                    if isinstance(v, str) and len(v) > 100:
                        logger.info(f"  - {k}: {v[:100]}...")
                    else:
                        logger.info(f"  - {k}: {v}")

            def get_nested_value(data: Dict[str, Any], path: str) -> Any:
                """Get the value of the nested dictionary, supporting dotted paths such as 'trade.code'"""
                keys = path.split('.')
                value = data
                for key in keys:
                    if isinstance(value, dict):
                        value = value.get(key, '')
                    else:
                        return ''
                return value

            def replace_variable(match):
                """Replace variable placeholder"""
                var_path = match.group(1).strip()
                value = get_nested_value(variables, var_path)
                # logger.info(f"  replace {{{{{var_path}}}}} -> {value}")  # Too many, comment them out
                return str(value) if value is not None else ''

            formatted = {}

            # 🔧 Two syntaxes are supported:
            # 1. double curly braces {{variable.path}} (Jinja2 style, high priority)
            # 2. Single level braces {variable} (Simple variables to avoid conflicts with content)
            # Process double-level curly braces first, then single-level curly braces (to avoid conflicts)
            double_brace_pattern = re.compile(r'\{\{([^}]+)\}\}')
            # Single level curly braces: match only {variable name}, Variable names can only be a combination of letters, numbers, and underscores
            single_brace_pattern = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')

            for key, value in template_content.items():
                if isinstance(value, str):
                    formatted_value = value
                    
                    # Step 1: Replace double-curly brace variables {{variable.path}}
                    def replacer_double(match):
                        var_path = match.group(1).strip()
                        val = get_nested_value(variables, var_path)
                        return str(val) if val is not None else ''
                    
                    formatted_value = double_brace_pattern.sub(replacer_double, formatted_value)
                    
                    # Step 2: Replace single-level curly brace variables {variable} (Matches only simple variable names)
                    def replacer_single(match):
                        var_name = match.group(1).strip()
                        # Get directly from the variables dictionary (nested paths are not supported)
                        val = variables.get(var_name)
                        return str(val) if val is not None else ''
                    
                    formatted_value = single_brace_pattern.sub(replacer_single, formatted_value)
                    formatted[key] = formatted_value

                    # Check if there are any unreplaced variables (only for system_prompt and user_prompt)
                    if key in ['system_prompt', 'user_prompt']:
                        # Check for double curly braces
                        unmatched_double = re.findall(r'\{\{([^}]+)\}\}', formatted_value)
                        # Check for single-level curly braces (simple variable names)
                        unmatched_single = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', formatted_value)
                        if unmatched_double or unmatched_single:
                            total_unmatched = len(unmatched_double) + len(unmatched_single)
                            logger.warning(f"⚠️ [template rendering] {key} There may be {total_unmatched} Unrendered variables")
                            # Show first 200 characters
                            logger.warning(f"⚠️ [template rendering] {key} first 200 characters: {formatted_value[:200]}")
                            if unmatched_double:
                                for var_name in unmatched_double:
                                    logger.warning(f"  - not replaced(Double layer): {var_name}")
                            if unmatched_single:
                                for var_name in unmatched_single:
                                    logger.warning(f"  - not replaced(single layer): {var_name}")
                else:
                    formatted[key] = value

            return formatted

        except Exception as e:
            logger.error(f"[TemplateClient] Formatting template exception: {e}")
            import traceback
            traceback.print_exc()
            return {}


# Global singleton
_template_client = None


def get_template_client() -> TemplateClient:
    """Get the global template client singleton"""
    global _template_client
    if _template_client is None:
        _template_client = TemplateClient()
    return _template_client


def get_agent_prompt(
    agent_type: str,
    agent_name: str,
    variables: Dict[str, str],
    user_id: Optional[str] = None,
    preference_id: Optional[str] = None,
    fallback_prompt: Optional[str] = None,
    context: Optional[AgentContext] = None,
    workflow_id: Optional[str] = None,  # 🆕 Process-specific prompt word support
    node_id: Optional[str] = None        # 🆕 Node-specific prompt word support
) -> str:
    """
    Get Agent prompt words (convenient function)

    Args:
        agent_type: Agent Type
        agent_name: Agent Name
        variables: Template variable dictionary (such as ticker, company_name, current_date, etc.)
        user_id: User ID (optional)
        preference_id: Preference ID (optional)
        fallback_prompt: Downgrade prompt word (used when the API is unavailable)
        context: AgentContext object
        workflow_id: 🆕 Workflow ID (optional, used to load process-specific prompt words)
        node_id: 🆕 Node ID (optional, the same agent loads different prompt words on different nodes)

    Returns:
        Complete prompt word string
    """
    try:
        client = get_template_client()

        # Get templates from MongoDB (supports process-specific prompt words + Node-specific prompt words)
        template_content = client.get_effective_template(
            agent_type, agent_name, user_id, preference_id, context, workflow_id, node_id
        )

        if template_content:
            logger.info(f"📝 [template rendering] Start formatting template, number of variables: {len(variables)}")
            logger.info(f"📝 [template rendering] template fields: {list(template_content.keys())}")

            # Format template
            formatted = client.format_template(template_content, variables)

            logger.info(f"📝 [template rendering] Formatting completed, check rendering results...")
            # Check if there are any unrendered variables
            for key, value in formatted.items():
                if isinstance(value, str) and ('{{' in value or '{' in value):
                    # Check for double curly braces
                    unmatched_double = re.findall(r'\{\{([^}]+)\}\}', value)
                    # Check for single-level curly braces (simple variable names)
                    unmatched_single = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', value)

                    if unmatched_double or unmatched_single:
                        total_unmatched = len(unmatched_double) + len(unmatched_single)
                        logger.warning(f"⚠️ [template rendering] {key} There may be {total_unmatched} Unrendered variables")
                        # Show first 200 characters
                        logger.warning(f"⚠️ [template rendering] {key} first 200 characters: {value[:200]}")
                        # Print specific uncrendered variable names
                        if unmatched_double:
                            logger.warning(f"  📌 Unrendered variables(double curly braces): {', '.join(unmatched_double)}")
                        if unmatched_single:
                            logger.warning(f"  📌 Unrendered variables(Single level braces): {', '.join(unmatched_single)}")

            # Combine complete prompt words
            parts = []
            if formatted.get("system_prompt"):
                parts.append(formatted["system_prompt"])
            if formatted.get("tool_guidance"):
                parts.append("\n\n" + formatted["tool_guidance"])
            if formatted.get("analysis_requirements"):
                parts.append("\n\n" + formatted["analysis_requirements"])
            if formatted.get("output_format"):
                parts.append("\n\n" + formatted["output_format"])
            if formatted.get("constraints"):
                parts.append("\n\n" + formatted["constraints"])

            prompt = "\n".join(parts)
            logger.info(f"✅ Successfully generated prompt word: {agent_type}/{agent_name} (length: {len(prompt)})")
            logger.info(f"📝 [template rendering] prompt word: {prompt}")
            return prompt
        else:
            # Downgrade: Use hardcoded prompt words
            logger.warning(
                f"⚠️ Unable to obtain template, use downgrade prompt word: {agent_type}/{agent_name}"
            )
            return fallback_prompt or "Please analyze."

    except Exception as e:
        logger.error(f"❌ Get prompt word exception: {e}")
        return fallback_prompt or "Please analyze."


def get_user_prompt(
    agent_type: str,
    agent_name: str,
    variables: Dict[str, Any],
    user_id: Optional[str] = None,
    preference_id: Optional[str] = None,
    fallback_prompt: Optional[str] = None,
    context: Optional[AgentContext] = None,
    workflow_id: Optional[str] = None,  # 🆕 Process-specific prompt word support
    node_id: Optional[str] = None        # 🆕 Node-specific prompt word support
) -> str:
    """
    Get Agent user prompt words (convenient function)

    Args:
        agent_type: Agent Type
        agent_name: Agent Name
        variables: Template variable dictionary (contains all data that needs to be replaced)
        user_id: User ID (optional)
        preference_id: Preference ID (optional)
        fallback_prompt: Downgrade prompt word (used when the API is unavailable)
        context: AgentContext object
        workflow_id: 🆕 Workflow ID (optional, used to load process-specific prompt words)
        node_id: 🆕 Node ID (optional, the same agent loads different prompt words on different nodes)

    Returns:
        Rendered user prompt word string
    """
    try:
        # 🔍 Debugging: Print received variables
        logger.info(f"🔍 [get_user_prompt] received variable (total {len(variables)} a):")
        if not variables:
            logger.warning(f"⚠️ [get_user_prompt] The variable dictionary is empty!")
        else:
            for k, v in variables.items():
                if isinstance(v, str) and len(v) > 100:
                    logger.info(f"  - {k}: {v[:100]}...")
                else:
                    logger.info(f"  - {k}: {v}")

        client = get_template_client()

        # Get templates from MongoDB (supports process-specific prompt words + Node-specific prompt words)
        template_content = client.get_effective_template(
            agent_type, agent_name, user_id, preference_id, context, workflow_id, node_id
        )

        if template_content:
            # Format template
            formatted = client.format_template(template_content, variables)

            # Return user prompt word
            user_prompt = formatted.get("user_prompt", "")
            if user_prompt:
                # Check if there are any unrendered variables
                unmatched_double = re.findall(r'\{\{([^}]+)\}\}', user_prompt)
                unmatched_single = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', user_prompt)

                if unmatched_double or unmatched_single:
                    total_unmatched = len(unmatched_double) + len(unmatched_single)
                    logger.warning(f"⚠️ [get_user_prompt] user_prompt There may be {total_unmatched} Unrendered variables")
                    logger.warning(f"⚠️ [get_user_prompt] user_prompt first 200 characters: {user_prompt[:200]}")
                    if unmatched_double:
                        logger.warning(f"  📌 Unrendered variables(double curly braces): {', '.join(unmatched_double)}")
                    if unmatched_single:
                        logger.warning(f"  📌 Unrendered variables(Single level braces): {', '.join(unmatched_single)}")

                logger.info(f"✅ Successfully generated user prompt words: {agent_type}/{agent_name} (length: {len(user_prompt)})")
                logger.info(f"📝 [get_user_prompt] User prompt words: {user_prompt}")
                return user_prompt
            else:
                logger.warning(f"⚠️ There is no user_prompt field in the template, use the downgrade prompt word: {agent_type}/{agent_name}")
                return fallback_prompt or "Please analyze."
        else:
            # Downgrade: Use hardcoded prompt words
            logger.warning(
                f"⚠️ Unable to obtain template, use downgrade prompt word: {agent_type}/{agent_name}"
            )
            return fallback_prompt or "Please analyze."

    except Exception as e:
        logger.error(f"❌ Obtain user prompt word exception: {e}")
        import traceback
        traceback.print_exc()
        return fallback_prompt or "Please analyze."


def close_template_client():
    """Close global template client connection"""
    global _template_client
    if _template_client is not None:
        _template_client.client.close()
        _template_client = None
        logger.info("✅ Template client connection closed")

