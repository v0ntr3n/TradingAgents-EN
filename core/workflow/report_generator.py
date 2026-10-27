"""
Universal report generator

Generate structured reports based on report templates and Agent output.
Supports LLM-assisted generation and rule extraction modes.

Usage process:
1. The workflow execution is completed and all Agent outputs are collected
2. Get the associated report template based on workflow_id
3. Call the report generator to generate a structured report
4. Save reports to analysis_reports collection
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Universal report generator
    
    Two generation modes are supported:
    1. LLM Generation: Use the generator_prompt of the report template to call LLM to generate the report
    2. Rule Extraction: Extract fields by rules from Agent output
    """
    
    def __init__(self, db=None):
        """
        Initialize report generator
        
        Args:
            db: MongoDB Database connection (optional, used to obtain report templates)
        """
        self.db = db
        self._templates_cache: Dict[str, Any] = {}
    
    async def get_template(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the report template associated with the workflow
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            Dictionary of report templates, returned if none None
        """
        # Check cache
        if workflow_id in self._templates_cache:
            return self._templates_cache[workflow_id]
        
        if not self.db:
            logger.warning("Database connection not set up, unable to get report template")
            return None
        
        try:
            template = await self.db.report_templates.find_one({
                "workflow_id": workflow_id,
                "status": "active"
            })
            
            if template:
                self._templates_cache[workflow_id] = template
                logger.info(f"✅ Get report template: {template.get('name')} (workflow_id={workflow_id})")
            else:
                logger.info(f"📝 Workflow {workflow_id} There is no associated report template, the default format will be used")
            
            return template
        except Exception as e:
            logger.error(f"❌ Failed to obtain report template: {e}")
            return None
    
    async def generate_report(
        self,
        workflow_id: str,
        agent_outputs: Dict[str, Any],
        workflow_state: Optional[Dict[str, Any]] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Generate report
        
        Args:
            workflow_id: Workflow ID
            agent_outputs: Output dictionary of each Agent
            workflow_state: Workflow status (including ticker, context, etc.)
            use_llm: Whether to use LLM to generate reports
            
        Returns:
            Structured reporting dictionary
        """
        template = await self.get_template(workflow_id)
        
        if not template:
            # Without template, return raw Agent output
            return self._generate_default_report(agent_outputs, workflow_state)
        
        if use_llm and template.get("generator_prompt"):
            return await self._generate_with_llm(template, agent_outputs, workflow_state)
        else:
            return self._generate_with_rules(template, agent_outputs, workflow_state)
    
    def _generate_default_report(
        self,
        agent_outputs: Dict[str, Any],
        workflow_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate default format report (used when no template is available)"""
        return {
            "report_type": "default",
            "generated_at": datetime.utcnow().isoformat(),
            "workflow_id": workflow_state.get("workflow_id") if workflow_state else None,
            "ticker": workflow_state.get("ticker") if workflow_state else None,
            "agent_outputs": agent_outputs,
            "summary": self._extract_summary_from_outputs(agent_outputs)
        }
    
    def _extract_summary_from_outputs(self, agent_outputs: Dict[str, Any]) -> str:
        """Extract summaries from Agent output"""
        summaries = []
        for agent_name, output in agent_outputs.items():
            if isinstance(output, dict):
                if "summary" in output:
                    summaries.append(f"【{agent_name}】{output['summary']}")
                elif "conclusion" in output:
                    summaries.append(f"【{agent_name}】{output['conclusion']}")
        return "\n".join(summaries) if summaries else "No abstract yet"
    
    def _generate_with_rules(
        self,
        template: Dict[str, Any],
        agent_outputs: Dict[str, Any],
        workflow_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Use rules to extract fields from Agent output"""
        output_schema = template.get("output_schema", [])
        result = {
            "report_type": template.get("template_id"),
            "template_name": template.get("name"),
            "generated_at": datetime.utcnow().isoformat(),
            "workflow_id": template.get("workflow_id"),
            "ticker": workflow_state.get("ticker") if workflow_state else None,
        }
        
        # Extract fields by output_schema
        for field_def in output_schema:
            field_name = field_def.get("name")
            field_type = field_def.get("type", "string")
            default = field_def.get("default")
            
            # Try to extract from agent_outputs
            value = self._extract_field_value(field_name, agent_outputs, field_type)
            result[field_name] = value if value is not None else default
        
        # Add raw agent_outputs (optional, for debugging)
        result["agent_outputs"] = agent_outputs

        return result

    def _extract_field_value(
        self,
        field_name: str,
        agent_outputs: Dict[str, Any],
        field_type: str
    ) -> Any:
        """Extract field values from Agent output"""
        # Iterate through all Agent output, looking for matching fields
        for agent_name, output in agent_outputs.items():
            if isinstance(output, dict):
                if field_name in output:
                    return self._convert_type(output[field_name], field_type)
                # Try nested search
                for key, value in output.items():
                    if isinstance(value, dict) and field_name in value:
                        return self._convert_type(value[field_name], field_type)
        return None

    def _convert_type(self, value: Any, target_type: str) -> Any:
        """type conversion"""
        try:
            if target_type == "string":
                return str(value) if value is not None else None
            elif target_type == "number":
                return float(value) if value is not None else None
            elif target_type == "boolean":
                return bool(value) if value is not None else None
            elif target_type == "array":
                if isinstance(value, list):
                    return value
                return [value] if value is not None else []
            elif target_type == "object":
                return value if isinstance(value, dict) else {}
            return value
        except (ValueError, TypeError):
            return None

    async def _generate_with_llm(
        self,
        template: Dict[str, Any],
        agent_outputs: Dict[str, Any],
        workflow_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate reports using LLM"""
        try:
            from core.llm.unified_client import UnifiedLLMClient

            llm_client = UnifiedLLMClient()

            # Build prompt words
            generator_prompt = template.get("generator_prompt", "")
            output_schema = template.get("output_schema", [])

            # Format output_schema as JSON Schema description
            schema_description = self._format_output_schema(output_schema)

            # Build a complete prompt word
            prompt = f"""You are a professional financial analysis report generator.

## Task
Generate a structured analysis report based on the following analysts analysis results.

## Analyze results
{json.dumps(agent_outputs, ensure_ascii=False, indent=2)}

## reporting requirements
{generator_prompt}

## Output format
Please output the report in the following JSON format:
{schema_description}

## Things to note
1. Only output JSON format, do not include other text
2. Make sure all required fields have values
3. Please use numbers instead of strings for numerical fields.
4. Remain objective and neutral and draw conclusions based on analysis results

Please generate a report:"""

            # call LLM
            response = await llm_client.chat_async(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            # Parse LLM response
            result = self._parse_llm_response(response, template)

            # Add metadata
            result["report_type"] = template.get("template_id")
            result["template_name"] = template.get("name")
            result["generated_at"] = datetime.utcnow().isoformat()
            result["workflow_id"] = template.get("workflow_id")
            result["ticker"] = workflow_state.get("ticker") if workflow_state else None
            result["generation_method"] = "llm"

            return result

        except Exception as e:
            logger.error(f"❌ LLM Report generation failed: {e}, Downgrade to rule extraction")
            return self._generate_with_rules(template, agent_outputs, workflow_state)

    def _format_output_schema(self, output_schema: List[Dict[str, Any]]) -> str:
        """Format output_schema into a human-readable description"""
        lines = ["{"]
        for field in output_schema:
            name = field.get("name")
            field_type = field.get("type", "string")
            desc = field.get("description", "")
            required = field.get("required", True)
            enum_values = field.get("enum")

            type_hint = field_type
            if enum_values:
                type_hint = f"string, Optional value: {enum_values}"

            req_mark = "*Required*" if required else "Optional"
            lines.append(f'  "{name}": {type_hint},  // {desc} ({req_mark})')

        lines.append("}")
        return "\n".join(lines)

    def _parse_llm_response(
        self,
        response: str,
        template: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse LLM response"""
        try:
            # Try to extract JSON
            content = response.strip()

            # Processing markdown code blocks
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ LLM Response JSON parsing failed: {e}")
            return {"raw_response": response, "parse_error": str(e)}

