"""
SKILL.md parser

Parse the SKILL.md file in the Agent Skills standard format:
- YAML frontmatter (--- delimited metadata)
- Markdown body (natural language instructions)

Support:
1. Standard Agent Skills format (only name + description) 
2. Extended format (increase parameters, returns, implementation etc.)
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from .models import (
    HttpImplementation,
    ImplementationType,
    McpImplementation,
    PythonImplementation,
    SkillImplementation,
    SkillMetadata,
    SkillParameter,
    SkillReturns,
)

logger = logging.getLogger(__name__)


class SkillParser:
    """SKILL.md file parser"""

    @staticmethod
    def parse_file(file_path: str) -> SkillMetadata:
        """
        Parse the SKILL.md file
        
        Args:
            file_path: SKILL.md file path
            
        Returns:
            SkillMetadata object
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"SKILL.md File does not exist: {file_path}")

        content = path.read_text(encoding="utf-8")
        skill = SkillParser.parse_content(content)
        skill.source_file = str(path.resolve())
        return skill

    @staticmethod
    def parse_content(content: str) -> SkillMetadata:
        """
        Parse SKILL.md content string
        
        Args:
            content: SKILL.md File content
            
        Returns:
            SkillMetadata object
        """
        frontmatter, body = SkillParser._split_frontmatter(content)

        if not frontmatter:
            raise ValueError("SKILL.md Must contain YAML frontmatter (separated by ---)")

        # parse YAML frontmatter
        try:
            metadata = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML frontmatter Parsing failed: {e}")

        if not isinstance(metadata, dict):
            raise ValueError("YAML frontmatter Must be a dictionary")

        # Required field verification
        if "name" not in metadata:
            raise ValueError("SKILL.md must contain 'name' Field")
        if "description" not in metadata:
            raise ValueError("SKILL.md must contain 'description' Field")

        # build SkillMetadata
        return SkillParser._build_skill_metadata(metadata, body.strip())

    @staticmethod
    def _split_frontmatter(content: str) -> Tuple[Optional[str], str]:
        """Separate YAML frontmatter and Markdown body"""
        # Match --- the beginning and end of frontmatter
        pattern = r"^---\s*\n(.*?)\n---\s*\n?(.*)"
        match = re.match(pattern, content.strip(), re.DOTALL)

        if match:
            return match.group(1), match.group(2)

        return None, content

    @staticmethod
    def _build_skill_metadata(metadata: Dict[str, Any], body: str) -> SkillMetadata:
        """Build from parsed results SkillMetadata"""
        # Basic fields
        skill_data = {
            "name": metadata["name"],
            "description": metadata["description"],
            "instructions": body,
        }

        # Agent Skills optional fields
        if "allowed-tools" in metadata or "allowed_tools" in metadata:
            skill_data["allowed_tools"] = metadata.get("allowed-tools") or metadata.get("allowed_tools")

        # Extended metadata fields
        for field in ("version", "author", "category", "tags", "icon", "color"):
            if field in metadata:
                skill_data[field] = metadata[field]

        # Function Calling extension fields
        if "when_to_use" in metadata:
            skill_data["when_to_use"] = metadata["when_to_use"]

        if "examples" in metadata:
            skill_data["examples"] = metadata["examples"]

        # Parameter definition
        if "parameters" in metadata and isinstance(metadata["parameters"], list):
            skill_data["parameters"] = [
                SkillParameter(**p) if isinstance(p, dict) else p
                for p in metadata["parameters"]
            ]

        # Return value definition
        if "returns" in metadata and isinstance(metadata["returns"], dict):
            skill_data["returns"] = SkillReturns(**metadata["returns"])

        # Implementation
        if "implementation" in metadata and isinstance(metadata["implementation"], dict):
            skill_data["implementation"] = SkillParser._parse_implementation(
                metadata["implementation"]
            )

        # status field
        for field in ("enabled", "fc_enabled"):
            if field in metadata:
                skill_data[field] = metadata[field]

        return SkillMetadata(**skill_data)

    @staticmethod
    def _parse_implementation(impl_data: Dict[str, Any]) -> Optional[SkillImplementation]:
        """Parse execution implementation configuration"""
        impl_type = impl_data.get("type", "").lower()

        if impl_type == "python":
            return PythonImplementation(**impl_data)
        elif impl_type == "http":
            return HttpImplementation(**impl_data)
        elif impl_type == "mcp":
            return McpImplementation(**impl_data)
        else:
            logger.warning(f"Unknown execution protocol type: {impl_type}, skip implementation")
            return None

