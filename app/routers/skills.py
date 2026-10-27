"""
Skill management API

Based on Agent Skills standard + Skill CRUD interface for extension fields.
Support: import SKILL.md, import from URL, list query, update, delete, enable/disable, register to ToolRegistry
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, File
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db
from app.services.capability_index_service import CapabilityIndexService
from app.services.clawhub_skill_service import ClawHubSkillService, SKILLS_DIR
from app.services.skillhub_service import SkillHubService
from app.services.skill_credential_service import (
    SkillCredentialService,
    CredentialDeclaration,
    CREDENTIALS_COLLECTION,
)
from core.skills.models import SkillMetadata, SkillParameter, SkillReturns, ImplementationType
from core.skills.parser import SkillParser
from core.skills.converter import SkillConverter
from core.skills.executor import SkillExecutor
from core.skills.script_executor import ScriptSkillExecutor
from core.tools.registry import get_tool_registry

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/api/skills", tags=["skills"])

COLLECTION = "skills"


# =============================================================================
# request/response model
# =============================================================================

class SkillResponse(BaseModel):
    """Skill response model"""
    id: str = ""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: str = "general"
    tags: List[str] = []
    icon: str = "🔧"
    color: str = "#95a5a6"
    when_to_use: str = ""
    parameters: List[Dict[str, Any]] = []
    returns: Optional[Dict[str, Any]] = None
    implementation: Optional[Dict[str, Any]] = None
    instructions: str = ""
    enabled: bool = True
    fc_enabled: bool = True
    is_builtin: bool = False
    skill_type: str = "knowledge"
    is_executable: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillCreateRequest(BaseModel):
    """Create Skill Request"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: str = "general"
    tags: List[str] = []
    icon: str = "🔧"
    color: str = "#95a5a6"
    when_to_use: str = ""
    parameters: List[Dict[str, Any]] = []
    returns: Optional[Dict[str, Any]] = None
    implementation: Optional[Dict[str, Any]] = None
    instructions: str = ""
    enabled: bool = True
    fc_enabled: bool = True


class SkillImportRequest(BaseModel):
    """Import SKILL.md request"""
    content: str = Field(..., description="SKILL.md File content")


class SkillImportUrlRequest(BaseModel):
    """Import requests from URL"""
    url: str = Field(..., description="SKILL.md Direct link URL, such as GitHub raw address")


class SkillToggleRequest(BaseModel):
    """Enable/disable requests"""
    enabled: bool


# =============================================================================
# Helper function
# =============================================================================

def _doc_to_response(doc: Dict[str, Any]) -> SkillResponse:
    """Convert MongoDB documents to SkillResponse"""
    doc.pop("_id", None)
    impl = doc.get("implementation")
    has_impl = impl is not None
    params = doc.get("parameters", [])
    skill_type = "knowledge"
    if has_impl:
        skill_type = impl.get("type", "unknown") if isinstance(impl, dict) else "unknown"
    return SkillResponse(
        id=doc.get("name", ""),
        name=doc.get("name", ""),
        description=doc.get("description", ""),
        version=doc.get("version", "1.0.0"),
        author=doc.get("author", ""),
        category=doc.get("category", "general"),
        tags=doc.get("tags", []),
        icon=doc.get("icon", "🔧"),
        color=doc.get("color", "#95a5a6"),
        when_to_use=doc.get("when_to_use", ""),
        parameters=params,
        returns=doc.get("returns"),
        implementation=impl,
        instructions=doc.get("instructions", ""),
        enabled=doc.get("enabled", True),
        fc_enabled=doc.get("fc_enabled", True),
        is_builtin=doc.get("is_builtin", False),
        skill_type=skill_type,
        is_executable=has_impl,
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", ""),
    )


def _skill_to_doc(skill: SkillMetadata) -> Dict[str, Any]:
    """Convert SkillMetadata to MongoDB document"""
    doc = skill.model_dump(exclude_none=True)
    # Make sure the timestamp is a string
    now = datetime.utcnow().isoformat()
    if "created_at" not in doc or not doc["created_at"]:
        doc["created_at"] = now
    doc["updated_at"] = now
    return doc


def _request_to_doc(req: SkillCreateRequest) -> Dict[str, Any]:
    """Convert create requests into MongoDB documents"""
    doc = req.model_dump(exclude_none=True)
    now = datetime.utcnow().isoformat()
    doc["created_at"] = now
    doc["updated_at"] = now
    doc["is_builtin"] = False
    return doc


def _kwargs_to_cli_args(kwargs: Dict[str, Any]) -> List[str]:
    """Convert keyword arguments to command line argument list

    Agreement:
    - priority use `cli_args` Array directly as argv (LLM has complete control over parameters)
    - named `query`, `question`, `q`, `input` The parameters are treated as positional parameters (the first argv of the script)
    - Other parameters are converted to `--name value` Form (underscore to hyphen)
    - Boolean True only adds flag (no value)
    - None skip
    """
    # Prefer using the cli_args array (LLM has full control over command line arguments)
    if "cli_args" in kwargs and kwargs["cli_args"] is not None:
        raw = kwargs["cli_args"]
        if isinstance(raw, list):
            return [str(x) for x in raw]
        if isinstance(raw, str):
            # Simply split by spaces (support LLM splicing with a single string)
            import shlex
            try:
                return shlex.split(raw)
            except ValueError:
                return raw.split()

    cli_args: List[str] = []
    positional_keys = ("query", "question", "q", "input", "keyword", "text")
    positional_value = None
    extras: List[tuple] = []

    for key, value in kwargs.items():
        if value is None or key == "cli_args":
            continue
        if key in positional_keys and positional_value is None:
            positional_value = str(value)
        else:
            extras.append((key, value))

    if positional_value is not None:
        cli_args.append(positional_value)

    for key, value in extras:
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                cli_args.append(flag)
        else:
            cli_args.extend([flag, str(value)])

    return cli_args


def _create_script_skill_wrapper(doc: Dict[str, Any]):
    """Create a synchronous wrapper function for a local scripted skill

    This wrapper will, when called:
    1. Read skill_dir and script_path
    2. Decrypt load credentials from MongoDB
    3. Convert kwargs to command line arguments (positional arguments + --flag value) 
    4. Call ScriptSkillExecutor.execute_cli to execute the script
    """
    import inspect

    impl = doc.get("implementation") or {}
    skill_name = doc.get("name", "")
    skill_dir = impl.get("skill_dir") or doc.get("skill_dir")
    script_path = impl.get("script_path")
    timeout = impl.get("timeout", 60)

    def wrapper(**kwargs):
        credentials = {}
        try:
            from app.core.database import get_mongo_db_sync
            from app.services.skill_credential_service import _decrypt_value
            db = get_mongo_db_sync()
            if db is not None:
                cred_doc = db[CREDENTIALS_COLLECTION].find_one({"skill_name": skill_name})
                if cred_doc:
                    credentials = {
                        key: _decrypt_value(value)
                        for key, value in (cred_doc.get("credentials") or {}).items()
                    }
        except Exception as e:
            logger.warning(f"⚠️ Load Skill '{skill_name}' Credentials failed: {e}")

        # Allow LLM to specify which script to call via the script parameter (multi-script Skill scenario)
        actual_script_path = script_path
        if kwargs.get("script"):
            requested = str(kwargs.pop("script"))
            # Find matching scripts in skill_dir
            sk_path = Path(skill_dir) if skill_dir else None
            if sk_path and sk_path.exists():
                # Supports relative paths, plain file names, with/without .py suffix
                candidates = []
                if not requested.endswith(".py"):
                    requested_py = requested + ".py"
                else:
                    requested_py = requested
                # Look in scripts/ and root directories
                for base in [sk_path / "scripts", sk_path]:
                    if base.is_dir():
                        for p in base.iterdir():
                            if p.is_file() and p.name == requested_py:
                                candidates.append(p)
                if candidates:
                    chosen = candidates[0]
                    # relative path
                    actual_script_path = str(chosen.relative_to(sk_path)).replace("\\", "/")
                    logger.info(f"🎯 Skill '{skill_name}' Select script: {actual_script_path}")
                else:
                    logger.warning(f"⚠️ Skill '{skill_name}' The specified script cannot be found '{requested}', Use default: {script_path}")

        cli_args = _kwargs_to_cli_args(kwargs)
        logger.info(f"🔧 call script type Skill: {skill_name} script={actual_script_path} args={cli_args}")

        result = ScriptSkillExecutor.execute_cli(
            skill_dir=skill_dir,
            script_path=actual_script_path,
            args=cli_args,
            credentials=credentials,
            timeout=timeout,
        )
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "Script execution failed")
        return result.get("result")

    wrapper.__name__ = skill_name.replace("-", "_")
    wrapper.__doc__ = doc.get("description", "")

    # Build function signature - if SKILL.md does not declare parameters, give a default `query` Parameters let LLM know
    params = []
    declared_params = doc.get("parameters") or []
    if declared_params:
        for p in declared_params:
            default = inspect.Parameter.empty if p.get("required", True) else p.get("default")
            params.append(inspect.Parameter(
                name=p.get("name"),
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default,
            ))
    else:
        # SKILL.md no statement parameters
        # Three parameters are provided by default:
        # - query: Positional parameters (string) for simple scenes
        # - cli_args: Full array of command line arguments for complex scripts (e.g. dcf_calculator.py --fcf 100 --shares 50)
        # - script: Specify which script to call in a multi-script Skill scenario (such as 'dcf_calculator' or 'valuation_snapshot.py') 
        params.append(inspect.Parameter(
            name="query",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[str],
        ))
        params.append(inspect.Parameter(
            name="cli_args",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[List[str]],
        ))
        params.append(inspect.Parameter(
            name="script",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=Optional[str],
        ))

    if params:
        wrapper.__signature__ = inspect.Signature(parameters=params)
        # Also set __annotations__ to let LangChain/Pydantic infer schema
        wrapper.__annotations__ = {p.name: (p.annotation if p.annotation != inspect.Parameter.empty else str) for p in params}

    return wrapper


async def _register_skill_to_registry(doc: Dict[str, Any]):
    """Register the Skill to ToolRegistry (if it is an executable Skill)

    Rules:
    - knowledge Type (no implementation): Not registered as a callable tool, injected as a prompt word context
    - python/http/mcp Type: Register as a callable tool
    - Executable Skill without parameters: registered as a parameterless function
    - Local scripted skills (yes skill_dir + script_path) : Register as a callable tool and pass it when executing {baseDir} replace
    """
    impl = doc.get("implementation")
    logger.info(
        f"🔧 _register_skill_to_registry: name={doc.get('name')}, "
        f"impl_type={impl.get('type') if isinstance(impl, dict) else None}, "
        f"has_code={bool(impl.get('code')) if isinstance(impl, dict) else False}, "
        f"has_script_path={bool(impl.get('script_path')) if isinstance(impl, dict) else False}, "
        f"has_skill_dir_in_impl={bool(impl.get('skill_dir')) if isinstance(impl, dict) else False}, "
        f"has_skill_dir_in_doc={bool(doc.get('skill_dir'))}"
    )

    # knowledge Type: Not registered as a tool, prompt words are injected by the Agent base class
    if not impl:
        logger.info(f"📚 Skill '{doc.get('name')}' It is knowledge-based and is not registered as a callable tool (will be injected through prompt words)")
        return

    try:
        # Filter out extension fields not recognized by SkillMetadata (e.g. skill_dir, has_scripts, source_type) 
        _META_KNOWN_FIELDS = {
            "name", "description", "allowed_tools", "version", "author", "category",
            "tags", "icon", "color", "when_to_use", "parameters", "returns", "examples",
            "implementation", "instructions", "enabled", "fc_enabled", "is_builtin",
            "source_file", "created_at", "updated_at",
        }
        skill_kwargs = {k: v for k, v in doc.items() if k != "_id" and k in _META_KNOWN_FIELDS}
        skill = SkillMetadata(**skill_kwargs)

        # If code is provided, uses the sandbox wrapper
        if impl.get("code"):
            from core.tools.external_skill_loader import register_single_external_skill
            from core.tools.fc_converter import sanitize_function_name
            tool_id = sanitize_function_name(skill.name.replace("-", "_"))
            register_single_external_skill(
                None,
                get_tool_registry(),
                {
                    **doc,
                    "tool_id": tool_id,
                    "code": impl.get("code"),
                    "display_name": skill.description[:50] if skill.description else skill.name,
                    "parameters": doc.get("parameters", []),
                },
            )
        else:
            registry = get_tool_registry()
            from core.tools.fc_converter import sanitize_function_name
            tool_id = sanitize_function_name(skill.name.replace("-", "_"))

            # ⚠️ Naming conflict check:Skill name → tool_id Cannot have the same name as impl.function
            #    Otherwise, the wrapper in ToolRegistry will conflict with the original function key.
            #    This causes an infinite loop to form when SkillExecutor is called.
            impl_type_str = impl.get("type") if isinstance(impl, dict) else getattr(impl, "type", None)
            impl_func = impl.get("function") if isinstance(impl, dict) else getattr(impl, "function", None)
            if impl_type_str == "python" and impl_func and impl_func == tool_id:
                suggested_name = f"{doc.get('name', 'unnamed')}-tool"
                logger.warning(
                    f"⚠️ Skill naming conflict: tool_id '{tool_id}' with impl.function '{impl_func}' Same name!"
                    f" This results in infinite recursion during execution. It is recommended to change the Skill name to '{suggested_name}' to avoid conflicts."
                )
                logger.warning(
                    f"   conflict Skill: name={doc.get('name')}, function={impl_func}, module={impl.get('module')}"
                )

            # Compatible: If there is no skill_dir in impl, fill it in from the top level of doc
            if isinstance(impl, dict) and impl.get("script_path") and not impl.get("skill_dir"):
                if doc.get("skill_dir"):
                    impl["skill_dir"] = doc["skill_dir"]
                    logger.info(f"   → Automatic completion from doc.skill_dir impl.skill_dir: {doc['skill_dir']}")

            if isinstance(impl, dict) and impl.get("script_path") and (impl.get("skill_dir") or doc.get("skill_dir")):
                wrapper = _create_script_skill_wrapper(doc)
                logger.info(f"   → Using scripted Skill wrappers (execute_cli mode)")
            else:
                wrapper = SkillExecutor.create_sync_wrapper(skill)
                logger.info(f"   → Using the generic SkillExecutor synchronization wrapper")

            # 🔥 category Must be a ToolCategory enumeration value, otherwise mapped to external
            from core.tools.config import ToolCategory
            valid_categories = {c.value for c in ToolCategory}
            raw_category = doc.get("category", "external")
            if raw_category not in valid_categories:
                logger.info(f"   → category '{raw_category}' Not in the enumeration scope, mapped to 'external'")
                raw_category = "external"

            registry.register_function(
                tool_id=tool_id,
                func=wrapper,
                name=skill.description[:50] if skill.description else skill.name,
                category=raw_category,
                description=skill.description,
                is_online=True,
                override=True,
            )
        logger.info(f"✅ Skill '{skill.name}' Already registered to ToolRegistry (tool_id={tool_id}, type={impl.get('type', 'unknown')})")
    except Exception as e:
        logger.warning(f"⚠️ Skill Registration to ToolRegistry failed: {e}", exc_info=True)


async def _sync_capability_index(db: AsyncIOMotorDatabase):
    try:
        await CapabilityIndexService(db).ensure_index()
    except Exception as e:
        logger.warning(f"⚠️ CapabilityIndex Sync failed: {e}")


# =============================================================================
# API endpoint
# =============================================================================

@router.get("", response_model=List[SkillResponse])
async def list_skills(
    category: Optional[str] = Query(None, description="Filter by category"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    skill_type: Optional[str] = Query(None, description="Filter by type: knowledge, python, http, mcp"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get a list of all Skills"""
    query = {}
    if category:
        query["category"] = category
    if enabled is not None:
        query["enabled"] = enabled

    skills = []
    async for doc in db[COLLECTION].find(query).sort("created_at", -1):
        resp = _doc_to_response(doc)
        if skill_type:
            if resp.skill_type != skill_type:
                continue
        skills.append(resp)
    return skills


@router.get("/categories")
async def list_skill_categories(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get all Skill categories"""
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    categories = []
    async for doc in db[COLLECTION].aggregate(pipeline):
        categories.append({"id": doc["_id"], "name": doc["_id"], "count": doc["count"]})
    return categories


@router.post("", response_model=SkillResponse)
async def create_skill(
    req: SkillCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """create new Skill"""
    # Check if it already exists
    existing = await db[COLLECTION].find_one({"name": req.name})
    if existing:
        raise HTTPException(status_code=400, detail=f"Skill '{req.name}' Already exists")

    doc = _request_to_doc(req)
    await db[COLLECTION].insert_one(doc)

    # Register to ToolRegistry
    await _register_skill_to_registry(doc)
    await _sync_capability_index(db)

    doc.pop("_id", None)
    return _doc_to_response(doc)


@router.post("/import", response_model=SkillResponse)
async def import_skill(
    req: SkillImportRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Import from SKILL.md content Skill"""
    try:
        skill = SkillParser.parse_content(req.content)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=f"SKILL.md Parsing failed: {e}")

    # Check if it already exists
    existing = await db[COLLECTION].find_one({"name": skill.name})
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{skill.name}' Exists, please use the update interface",
        )

    doc = _skill_to_doc(skill)
    await db[COLLECTION].insert_one(doc)

    # Register to ToolRegistry
    await _register_skill_to_registry(doc)
    await _sync_capability_index(db)

    doc.pop("_id", None)
    return _doc_to_response(doc)


@router.post("/import-file", response_model=SkillResponse)
async def import_skill_file(
    file: UploadFile = File(..., description="SKILL.md File"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Upload and import the SKILL.md file"""
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="The file encoding must be UTF-8")

    try:
        skill = SkillParser.parse_content(text)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=f"SKILL.md Parsing failed: {e}")

    existing = await db[COLLECTION].find_one({"name": skill.name})
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{skill.name}' Exists, please use the update interface",
        )

    doc = _skill_to_doc(skill)
    doc["source_file"] = file.filename
    await db[COLLECTION].insert_one(doc)

    await _register_skill_to_registry(doc)
    await _sync_capability_index(db)

    doc.pop("_id", None)
    return _doc_to_response(doc)


# =============================================================================
# Test response model (shared by multiple import endpoints, needs to be defined in advance)
# =============================================================================

class SkillTestResponse(BaseModel):
    """Test Skill Response"""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: int = 0


class ImportWithTestResponse(BaseModel):
    """Import and test the response"""
    skill: SkillResponse
    test_result: Optional[SkillTestResponse] = None
    message: str


# =============================================================================
# Tencent SkillHub docking (skillhub.cloud.tencent.com)
# =============================================================================

class SkillHubSkillResponse(BaseModel):
    """SkillHub Skill response"""
    skill_id: str = Field(..., description="Skill ID, such as tencent-docs")
    display_name: str = Field("", description="display name")
    description: str = Field("", description="Description")
    category: str = Field("", description="Classification")
    author: str = Field("", description="Author/Source")
    downloads: str = Field("", description="Number of downloads, such as 15.691 million")
    version: str = Field("", description="version number")
    needs_api_key: bool = Field(False, description="Is it necessary API Key")
    ai_score: str = Field("", description="AI Rating")
    url: str = Field("", description="SkillHub Details page URL")
    install_command: str = Field("", description="Installation command")


class SkillHubListResponse(BaseModel):
    """SkillHub list response"""
    total: str = Field("7.1 million", description="Total quantity description")
    skills: List[SkillHubSkillResponse] = []
    featured: List[SkillHubSkillResponse] = Field(default_factory=list, description="Featured recommendations")


# SkillHub Selected skills (popular skills crawled from the website, updated regularly)
SKILLHUB_FEATURED = [
    SkillHubSkillResponse(
        skill_id="web-tools-guide",
        display_name="Web Tools Guide",
        description="Essential pre-requisite skills for searching/online/checking information, including error handling processes for web_search, web_fetch, browser and other tools",
        category="knowledge management",
        author="SkillHub",
        downloads="6215.8 million",
        version="latest",
        needs_api_key=False,
        ai_score="4.7",
        url="https://skillhub.cloud.tencent.com/skills/web-tools-guide",
        install_command="skillhub install web-tools-guide",
    ),
    SkillHubSkillResponse(
        skill_id="tencent-docs",
        display_name="Tencent Documents TENCENT DOCS",
        description="Online cloud document platform, the first choice for creating/editing/managing documents, supporting documents/Excel/PPT/mind maps, etc.",
        category="Office efficiency",
        author="Tencent Documentation Team",
        downloads="1569.1 million",
        version="v1.0.37",
        needs_api_key=True,
        ai_score="4.7",
        url="https://skillhub.cloud.tencent.com/skills/tencent-docs",
        install_command="skillhub install tencent-docs",
    ),
    SkillHubSkillResponse(
        skill_id="self-improving-agent",
        display_name="Self-Improving Agent",
        description="Capture lessons learned, errors and corrections for continuous improvement. Suitable for scenarios such as operation failure, user correction, discovery of better methods, etc.",
        category="Agent Enhance",
        author="SkillHub",
        downloads="81.3 million",
        version="latest",
        needs_api_key=False,
        ai_score="4.1",
        url="https://skillhub.cloud.tencent.com/skills/self-improving-agent",
        install_command="skillhub install self-improving-agent",
    ),
    SkillHubSkillResponse(
        skill_id="skill-vetter",
        display_name="Skill Vetter",
        description="AI Agent skills security pre-review tool, check risk signals, permission scope and suspicious patterns before installing skills from ClawdHub, GitHub and other sources",
        category="safe",
        author="SkillHub",
        downloads="26.8 million",
        version="latest",
        needs_api_key=False,
        ai_score="4.5",
        url="https://skillhub.cloud.tencent.com/skills/skill-vetter",
        install_command="skillhub install skill-vetter",
    ),
    SkillHubSkillResponse(
        skill_id="customer-hunter",
        display_name="Customer Hunter",
        description="Tencent Cloud Sales Customer Acquisition Skill, directly recruit target customers from Qichacha/Baidu Encyclopedia/BOSS, and generate HTML reports with three-dimensional scores",
        category="Sales and customer acquisition",
        author="SkillHub",
        downloads="470",
        version="v1.0.15",
        needs_api_key=True,
        ai_score="4.7",
        url="https://skillhub.cloud.tencent.com/skills/customer-hunter",
        install_command="skillhub install customer-hunter",
    ),
    SkillHubSkillResponse(
        skill_id="wxa-skills-generate",
        display_name="WeChat applet AI development model generation",
        description="Generate atomic interfaces and atomic components based on original business code, supporting CodeBuddy, Claude Code, etc. Coding Agent",
        category="WeChat applet",
        author="WeChat Mini Program Team",
        downloads="",
        version="latest",
        needs_api_key=False,
        ai_score="",
        url="https://skillhub.cloud.tencent.com/skills/wxa-skills-generate",
        install_command="skillhub install wxa-skills-generate",
    ),
    SkillHubSkillResponse(
        skill_id="agently-mail",
        display_name="Agently Mail",
        description="QQ The exclusive email service created by the email team for Agent supports WeChat login authorization, sending and receiving emails, search, attachment management, etc.",
        category="Office efficiency",
        author="QQ Email team",
        downloads="",
        version="latest",
        needs_api_key=True,
        ai_score="",
        url="https://skillhub.cloud.tencent.com/skills/agently-mail",
        install_command="skillhub install agently-mail",
    ),
    SkillHubSkillResponse(
        skill_id="tcop-api",
        display_name="Tencent Cloud Observability Platform",
        description="Use natural language to drive all API capabilities of Tencent Cloud Observability Platform, without the need to flip through documents or manually spell parameters.",
        category="Operation and maintenance monitoring",
        author="Tencent Cloud Observability Team",
        downloads="",
        version="latest",
        needs_api_key=True,
        ai_score="",
        url="https://skillhub.cloud.tencent.com/skills/tcop-api",
        install_command="skillhub install tcop-api",
    ),
]


@router.get("/skillhub/skills", response_model=SkillHubListResponse)
async def list_skillhub_skills(
    keyword: str = Query("", description="Search keywords"),
):
    """Browse Tencent SkillHub (skillhub.cloud.tencent.com) skills on"""
    if keyword:
        # Keyword Search: Filter in Featured List
        kw = keyword.lower()
        filtered = [
            s for s in SKILLHUB_FEATURED
            if kw in s.display_name.lower() or kw in s.description.lower() or kw in s.category.lower()
        ]
        return SkillHubListResponse(
            total=f"{len(filtered)} matches",
            skills=filtered,
            featured=SKILLHUB_FEATURED[:4],
        )

    return SkillHubListResponse(
        total="7.1 million",
        skills=SKILLHUB_FEATURED,
        featured=SKILLHUB_FEATURED[:4],
    )


class ImportFromSkillHubRequest(BaseModel):
    """Import requests from SkillHub"""
    skill_id: str = Field(..., description="SkillHub Skill ID, such as tencent-docs")
    test_args: Optional[Dict[str, Any]] = Field(default=None, description="Test parameters")


@router.post("/import-skillhub", response_model=ImportWithTestResponse)
async def import_from_skillhub(
    req: ImportFromSkillHubRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Import Skill from Tencent SkillHub (get SKILL.md and parse the registration)"""
    try:
        skill_content = ""

        # Try getting it from the SkillHub website SKILL.md
        skillhub_url = f"https://skillhub.cloud.tencent.com/skills/{req.skill_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(skillhub_url)
                if resp.status_code == 200:
                    # Extract SKILL.md content from HTML
                    text = resp.text
                    # Try to find the SKILL.md content block in the page
                    import re
                    # Find <pre> or the contents of the code block
                    skill_md_match = re.search(r'<pre[^>]*class="[^"]*skill[^"]*"[^>]*>(.*?)</pre>', text, re.DOTALL)
                    if skill_md_match:
                        from html import unescape
                        skill_content = unescape(skill_md_match.group(1).strip())
        except Exception as e:
            logger.warning(f"Failed to get content from SkillHub website: {e}")

        # If not available from website, generate base SKILL.md
        if not skill_content:
            # Find skill information from a curated list
            skill_info = next((s for s in SKILLHUB_FEATURED if s.skill_id == req.skill_id), None)
            if not skill_info:
                skill_info = SkillHubSkillResponse(
                    skill_id=req.skill_id,
                    display_name=req.skill_id,
                    description=f"Skills imported from SkillHub: {req.skill_id}",
                )

            skill_content = f"""---
name: {req.skill_id}
version: "1.0.0"
description: {skill_info.description}
author: {skill_info.author or "SkillHub"}
category: {skill_info.category or "imported"}
tags: [skillhub, {skill_info.category.lower() if skill_info.category else "imported"}]
parameters: []
implementation:
  type: python
  code: |
    import json, sys
    args = json.loads(sys.stdin.read()) if sys.stdin else {{}}
    print("__SANDBOX_OUTPUT_START__")
    print(json.dumps({{"info": "Skill imported from SkillHub", "skill_id": "{req.skill_id}", "name": "{skill_info.display_name}"}}, ensure_ascii=False))
    print("__SANDBOX_OUTPUT_END__")
when_to_use: |
  When a user mentions {skill_info.display_name} or {req.skill_id} This Skill is triggered when the relevant function occurs.
---

{skill_info.description}

Installation command: {skill_info.install_command}
Details: {skill_info.url}
"""

        # Parse and import
        skill = SkillParser.parse_content(skill_content)
        doc = _skill_to_doc(skill)
        doc["source_type"] = "skillhub"
        doc["source_url"] = f"https://skillhub.cloud.tencent.com/skills/{req.skill_id}"

        existing = await db[COLLECTION].find_one({"name": doc["name"]})
        if existing:
            await db[COLLECTION].update_one({"name": doc["name"]}, {"$set": doc})
            doc["_id"] = existing["_id"]
        else:
            await db[COLLECTION].insert_one(doc)

        await _register_skill_to_registry(doc)
        await _sync_capability_index(db)

        # test
        test_result = None
        if req.test_args:
            impl = doc.get("implementation", {})
            if impl.get("type") == "python" and impl.get("code"):
                sandbox_result = _execute_python_sandbox(impl["code"], req.test_args, 30)
                test_result = SkillTestResponse(
                    success=sandbox_result["success"],
                    result=sandbox_result.get("result"),
                    error=sandbox_result.get("error"),
                    execution_time_ms=sandbox_result.get("execution_time_ms", 0),
                )

        skill_resp = _doc_to_response(doc)
        return ImportWithTestResponse(
            skill=skill_resp,
            test_result=test_result,
            message=f"Imported from SkillHub Skill: {skill_resp.name}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import from SkillHub failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


# =============================================================================
# Test and platform docking interface
# =============================================================================

class SkillTestRequest(BaseModel):
    """Test Skill Request"""
    skill_name: str
    args: Dict[str, Any] = Field(default_factory=dict, description="Test parameters (passed directly to the script)")
    question: str = Field(default="", description="Natural language test questions, automatically converted into script parameters by LLM")
    timeout: int = Field(default=30, description="Timeout (seconds)")


def _execute_python_sandbox(code: str, args: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """Execute Python code in a sandbox"""
    import subprocess
    import tempfile
    import json
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        # Prepare input parameters
        input_data = json.dumps(args, ensure_ascii=False)

        # Execute code
        proc = subprocess.run(
            ["python", temp_path],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent.parent.parent),
        )

        if proc.returncode != 0:
            return {"success": False, "error": proc.stderr or "Execution failed", "execution_time_ms": 0}

        # parse output
        stdout = proc.stdout.strip()
        if "__SANDBOX_OUTPUT_START__" in stdout:
            start = stdout.index("__SANDBOX_OUTPUT_START__") + len("__SANDBOX_OUTPUT_START__")
            end = stdout.index("__SANDBOX_OUTPUT_END__")
            result_str = stdout[start:end].strip()
            try:
                result = json.loads(result_str)
            except:
                result = result_str
            return {"success": True, "result": result, "execution_time_ms": 0}
        else:
            return {"success": True, "result": {"stdout": stdout}, "execution_time_ms": 0}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Execution timeout ({timeout}s) ", "execution_time_ms": timeout * 1000}
    except Exception as e:
        return {"success": False, "error": str(e), "execution_time_ms": 0}
    finally:
        Path(temp_path).unlink(missing_ok=True)


@router.post("/test", response_model=SkillTestResponse)
async def test_skill(
    req: SkillTestRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Test Skill (distinguish between knowledge and executable types)"""
    try:
        # Try to get from skills collection
        doc = await db[COLLECTION].find_one({"name": req.skill_name})
        if doc:
            return await _test_skill_doc(doc, req, db)

        # Try to get from external_skills
        ext_doc = await db["external_skills"].find_one({"tool_id": req.skill_name})
        if ext_doc:
            code = ext_doc.get("code", "")
            if code:
                # Detect whether it is a placeholder code (only info field)
                is_placeholder = _is_placeholder_code(code)
                if is_placeholder:
                    return SkillTestResponse(
                        success=False,
                        error="This Skill is knowledge-based, with only document descriptions and no executable code."
                              "It provides contextual information to the Agent through ToolRegistry and does not require independent execution of tests.",
                        result={
                            "skill_type": "knowledge",
                            "name": ext_doc.get("display_name") or ext_doc.get("tool_id"),
                            "description": ext_doc.get("description", ""),
                            "registered_in_registry": _check_tool_registry(ext_doc.get("tool_id", "")),
                        },
                        execution_time_ms=0
                    )

                # Determine test parameters: priority question(LLM Transfer parameters) > args > test_input > empty
                test_args = dict(req.args) if req.args else {}
                llm_conversion_note = None

                if req.question:
                    # If there is a natural language problem: go to LLM first to transfer parameters
                    conversion = await _convert_question_to_args_for_external_skill(ext_doc, req.question)
                    if conversion.get("success"):
                        test_args = conversion.get("args", {})
                        llm_conversion_note = conversion.get("note", "")
                        logger.info(
                            f"💬 external_skill test: question='{req.question[:50]}...' → args={test_args}"
                        )
                    else:
                        # LLM Conversion fails, use test_input to find out
                        fallback_input = ext_doc.get("test_input") or {}
                        if fallback_input:
                            test_args = fallback_input
                            llm_conversion_note = f"LLM Conversion failed, use test_input to find out: {conversion.get('error', '')}"
                            logger.warning(
                                f"⚠️ external_skill Test LLM parameter transfer failed, use test_input to find out: {conversion.get('error')}"
                            )
                elif not test_args:
                    # There are no questions or args, automatically tested with test_input
                    fallback_input = ext_doc.get("test_input") or {}
                    if fallback_input:
                        test_args = fallback_input
                        llm_conversion_note = "Automatically use test_input as test parameter"
                        logger.info(f"🔄 external_skill test: No questions/parameters, automatically used test_input={test_args}")

                # Execute using SandboxRunner (correct handling of purely functional code)
                result = _run_external_skill_sandbox(code, ext_doc, test_args, req.timeout)
                resp_result = result.get("result")
                if isinstance(resp_result, dict) and llm_conversion_note:
                    resp_result = dict(resp_result)
                    resp_result["_llm_conversion_note"] = llm_conversion_note
                    resp_result["_test_args"] = test_args
                return SkillTestResponse(
                    success=result["success"],
                    result=resp_result,
                    error=result.get("error"),
                    execution_time_ms=result.get("execution_time_ms", 0)
                )
            else:
                return SkillTestResponse(
                    success=False,
                    error="This Skill has no executable code",
                    result={"skill_type": "unknown"}
                )

        raise HTTPException(status_code=404, detail=f"Skill '{req.skill_name}' does not exist")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test Skill failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"test failed: {str(e)}")


def _is_placeholder_code(code: str) -> bool:
    """Detect whether it is a placeholder code (only info metadata is returned)"""
    import re
    # match pattern: print(json.dumps({"info": "Skill imported from...
    placeholder_patterns = [
        r'"info".*?"Skill imported',
        r'"info".*?"Skill imported from SkillHub"',
        r'__SANDBOX_OUTPUT',
    ]
    for pattern in placeholder_patterns:
        if re.search(pattern, code):
            return True
    return False


def _run_external_skill_sandbox(
    code: str,
    ext_doc: Dict[str, Any],
    test_args: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    """Use SandboxRunner to execute the pure function code of external_skill.

    _execute_python_sandbox Parameters are passed through stdin and are not suitable for pure function code.
    SandboxRunner A layer of main entry will be automatically wrapped to call the function.

    Args:
        code: Skill Python function code
        ext_doc: external_skills Document (used to get tool_id)
        test_args: Test parameter dictionary
        timeout: Timeout seconds

    Returns:
        {"success": bool, "result": Any, "error": str, "execution_time_ms": int}
    """
    try:
        from core.tools.external.sandbox_runner import SandboxRunner
        from core.tools.external.skill_spec import SkillSpec

        # Construct a minimal SkillSpec (requires only tool_id and test_input)
        tool_id = ext_doc.get("tool_id", "")
        spec = SkillSpec(
            tool_id=tool_id,
            display_name=ext_doc.get("display_name", tool_id),
            description=ext_doc.get("description", ""),
            category=ext_doc.get("category", "utility"),
            test_input=test_args,
        )

        runner = SandboxRunner(timeout=timeout)
        sandbox_result = runner.run(code, spec, test_input=test_args)

        # Write the stdout/stderr of the child process to the webapi log to facilitate troubleshooting issues such as data source selection.
        if sandbox_result.stdout:
            for line in sandbox_result.stdout.split("\n"):
                line = line.strip()
                if line:
                    logger.info(f"📦 [sandbox stdout] {line}")
        if sandbox_result.stderr:
            for line in sandbox_result.stderr.split("\n"):
                line = line.strip()
                if line:
                    logger.warning(f"📦 [sandbox stderr] {line}")

        return {
            "success": sandbox_result.success,
            "result": sandbox_result.output,
            "error": sandbox_result.error,
            "execution_time_ms": int((sandbox_result.execution_time or 0) * 1000),
        }
    except Exception as e:
        logger.error(f"external_skill Sandbox execution exception: {e}", exc_info=True)
        return {"success": False, "result": None, "error": str(e), "execution_time_ms": 0}


async def _convert_question_to_args_for_external_skill(
    ext_doc: Dict[str, Any],
    question: str,
) -> Dict[str, Any]:
    """Use LLM to convert natural language questions into function parameters of external_skill.

    Args:
        ext_doc: external_skills Documents in the collection, including parameters, description, display_name, etc.
        question: User s natural language testing questions

    Returns:
        {"success": True, "args": {...}, "note": "..."} or {"success": False, "error": "..."}
    """
    import os
    import json as _json

    parameters = ext_doc.get("parameters") or []
    display_name = ext_doc.get("display_name") or ext_doc.get("tool_id", "")
    description = ext_doc.get("description") or ""
    test_input = ext_doc.get("test_input") or {}

    if not parameters:
        # If there is no parameter definition, empty parameters will be returned directly.
        return {"success": True, "args": {}, "note": "No parameter definition"}

    try:
        from core.llm.unified_client import UnifiedLLMClient
        from core.llm.models import Message
    except Exception as e:
        return {"success": False, "error": f"Unable to import LLM client: {e}"}

    llm_client = None
    last_err = None
    for provider, env_key in [
        ("dashscope", "DASHSCOPE_API_KEY"),
        ("deepseek", "DEEPSEEK_API_KEY"),
    ]:
        if not os.getenv(env_key):
            continue
        try:
            llm_client = UnifiedLLMClient.from_provider(provider)
            break
        except Exception as e:
            last_err = e
            continue

    if llm_client is None:
        return {"success": False, "error": f"No available LLM configuration found: {last_err}"}

    # JSON description of construction parameter definitions
    param_schema = []
    for p in parameters:
        param_schema.append({
            "name": p.get("name", ""),
            "type": p.get("param_type") or p.get("type", "string"),
            "required": p.get("required", False),
            "default": p.get("default"),
            "description": p.get("description", ""),
        })

    system_prompt = f"""You are a parameter extraction assistant. Your task is to extract the parameters required to call the Skill function from the user s natural language question.

## Skill information
- Name: {display_name}
- Description: {description[:500]}

## Function parameter definition
```json
{_json.dumps(param_schema, ensure_ascii=False, indent=2)}
```

## Reference test input (parameter format reference)
```json
{_json.dumps(test_input, ensure_ascii=False, indent=2)}
```

## Task
Extract parameter values from user questions and output them in strict JSON format:
```json
{{
  "args": {{
    "param1": "value1",
    "param2": 123
  }}
}}
```

## rules
1. Only output JSON, do not output any other text, explanations, markdown code blocks
2. For parameters not mentioned in the user s question, if there is a default value, you don t need to fill it in; if it is a required parameter but is not given in the question, use the value in the reference test input or a reasonable default value.
3. The stock code is a 6-digit pure number (such as 000002, 600519), without the .SH/.SZ suffix
4. Parameters of numeric type must be numbers without quotation marks"""

    try:
        response = llm_client.chat(
            [
                Message(role="system", content=system_prompt),
                Message(role="user", content=f"User questions:{question}\n\n Please extract the parameters."),
            ],
            max_tokens=512,
        )
        # Record token usage
        try:
            from app.services.usage_statistics_service import usage_statistics_service
            await usage_statistics_service.record_llm_usage(
                response=response,
                session_id="skill_test",
                analysis_type="skill_test",
            )
        except Exception as e:
            logger.warning(f"Record token usage failure: {e}")
        raw = (response.content or "").strip()

        # Try to extract from possible markdown code blocks JSON
        if "```" in raw:
            import re as _re
            m = _re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, _re.DOTALL)
            if m:
                raw = m.group(1).strip()

        # Remove possible prefixes/suffixes
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        parsed = _json.loads(raw)
        args = parsed.get("args", {}) if isinstance(parsed, dict) else {}

        # Type correction: Convert the value to the correct type according to the parameter definition
        for p in parameters:
            name = p.get("name", "")
            ptype = (p.get("param_type") or p.get("type", "")).lower()
            if name in args:
                try:
                    if ptype in ("int", "integer", "number"):
                        args[name] = int(args[name])
                    elif ptype in ("float", "double"):
                        args[name] = float(args[name])
                    elif ptype == "boolean":
                        if isinstance(args[name], str):
                            args[name] = args[name].lower() in ("true", "1", "yes")
                except (ValueError, TypeError):
                    pass

        return {
            "success": True,
            "args": args,
            "note": f"LLM Extracted from question: {question[:60]}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _check_tool_registry(tool_id: str) -> bool:
    """Check if the tool is registered to ToolRegistry"""
    try:
        registry = get_tool_registry()
        tool = registry.get_tool(tool_id.replace("-", "_"))
        return tool is not None
    except Exception:
        return False


def _collect_script_help_info(doc: Dict[str, Any]) -> str:
    """Scan all .py scripts in the Skill package and run --help to get parameter descriptions

    Return the spliced string for LLM to refer to in the system prompt word.
    """
    import subprocess as _sp

    impl = doc.get("implementation") or {}
    skill_dir = impl.get("skill_dir") or doc.get("skill_dir")
    if not skill_dir:
        return " (No script directory information)"

    skill_path = Path(skill_dir)
    if not skill_path.exists():
        return f" (Script directory does not exist: {skill_dir}) "

    # Find all .py scripts (scripts/ takes precedence, otherwise root directory)
    scripts_dir = skill_path / "scripts"
    candidates = []
    if scripts_dir.is_dir():
        candidates = sorted([p for p in scripts_dir.iterdir() if p.is_file() and p.suffix == ".py"])
    else:
        candidates = sorted([p for p in skill_path.iterdir()
                             if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"])

    if not candidates:
        return " (Executable script not found)"

    sections = []
    for script in candidates[:8]:  # Take a maximum of 8 to avoid too long prompt words
        rel_path = script.relative_to(skill_path)
        try:
            proc = _sp.run(
                ["python", str(script), "--help"],
                cwd=str(skill_path),
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            help_text = (proc.stdout or proc.stderr or "").strip()
            if help_text:
                # Truncate the help output of a single script to avoid being too long
                if len(help_text) > 800:
                    help_text = help_text[:800] + "\n... (Truncated)"
                sections.append(f"### `{rel_path}`\n```\n{help_text}\n```")
            else:
                sections.append(f"### `{rel_path}`\n (No --help output, it may be a script without parameters, just execute it directly)")
        except Exception as e:
            sections.append(f"### `{rel_path}`\n (Failed to get --help: {e}) ")

    return "\n\n".join(sections) if sections else " (No script help information)"


async def _test_skill_via_agent(
    doc: Dict[str, Any],
    question: str,
    timeout: int,
    db: AsyncIOMotorDatabase,
) -> Dict[str, Any]:
    """Pass LLM Function Calling test Skill

    The actual Agent calling Skill in the project uses the same technology stack:
    1. Obtain registered Skill tools from ToolRegistry (including credential injection logic)
    2. Create an LLM client using UnifiedLLMClient
    3. Register Skill as a callable tool
    4. Put SKILL.md description + instructions as system prompt word
    5. Let LLM call tools autonomously
    6. Returns the complete execution trace (LLM inference + Tool call + tool results)

    Args:
        doc: MongoDB Skill documentation in
        question: User testing questions (natural language)
        timeout: Timeout seconds
        db: MongoDB database

    Returns:
        {success, result, error, execution_time_ms, tool_calls, final_answer}
    """
    import time as _time
    start = _time.time()

    skill_name = doc.get("name", "")
    tool_id = skill_name.replace("-", "_")

    # 1. Get the registered tool from ToolRegistry, if not, register it immediately (lazy registration)
    try:
        registry = get_tool_registry()
        tool_func = registry.get_function(tool_id)
        if tool_func is None:
            logger.info(f"🔁 Skill '{skill_name}' Not in ToolRegistry, try to register now...")
            try:
                await _register_skill_to_registry(doc)
                tool_func = registry.get_function(tool_id)
            except Exception as reg_err:
                return {
                    "success": False,
                    "error": f"Instant registration failed: {reg_err}",
                    "execution_time_ms": int((_time.time() - start) * 1000),
                }
        tool_metadata = registry.get_tool(tool_id)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get tool: {e}",
            "execution_time_ms": int((_time.time() - start) * 1000),
        }

    if tool_func is None:
        # If registration is still not successful, give a clear diagnosis
        impl = doc.get("implementation") or {}
        diag = {
            "has_implementation": bool(impl),
            "impl_type": impl.get("type") if isinstance(impl, dict) else None,
            "has_script_path": bool(impl.get("script_path") if isinstance(impl, dict) else None),
            "has_skill_dir": bool((impl.get("skill_dir") if isinstance(impl, dict) else None) or doc.get("skill_dir")),
        }
        return {
            "success": False,
            "error": (
                f"Skill '{skill_name}' (tool_id={tool_id}) Not registered with ToolRegistry,"
                f"Instant registration also failed. diagnostic information: {diag}. "
                f"Please confirm that the Skill s implementation.script_path and skill_dir have been correctly written to the database."
            ),
            "execution_time_ms": int((_time.time() - start) * 1000),
        }

    # 2. Create LLM client (per system configuration)
    try:
        import os
        from core.llm.unified_client import UnifiedLLMClient
        from core.llm.models import Message

        llm_client = None
        last_err = None
        for provider, env_key in [
            ("dashscope", "DASHSCOPE_API_KEY"),
            ("deepseek", "DEEPSEEK_API_KEY"),
        ]:
            if not os.getenv(env_key):
                continue
            try:
                llm_client = UnifiedLLMClient.from_provider(provider)
                logger.info(f"💡 Test Skill usage LLM provider={provider}")
                break
            except Exception as e:
                last_err = e
                continue

        if llm_client is None:
            return {
                "success": False,
                "error": f"No available LLM configuration found (tried DASHSCOPE/DEEPSEEK): {last_err}",
                "execution_time_ms": int((_time.time() - start) * 1000),
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to initialize LLM client: {e}",
            "execution_time_ms": int((_time.time() - start) * 1000),
        }

    # 3. Register Skill as LLM Tool
    try:
        tool_def = llm_client.register_tool(
            tool_func,
            name=tool_id,
            description=doc.get("description") or skill_name,
        )
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to register Skill tool: {e}",
            "execution_time_ms": int((_time.time() - start) * 1000),
        }

    # 4. Construct prompt words: use SKILL.md instructions as the system prompt word
    instructions = doc.get("instructions") or ""
    description = doc.get("description") or ""
    when_to_use = doc.get("when_to_use") or ""

    # 4.1 Scan the script directory for --help output of all .py scripts to let LLM know what parameters each script supports
    script_help_info = _collect_script_help_info(doc)

    system_prompt = f"""You are a Skill Test Assistant. Your task is to based on the user s question, call the `{tool_id}` tools to get real results.

## Skill Description
{description}

## When to use
{when_to_use}

## Skill Detailed instructions (from SKILL.md)
{instructions[:6000]}

## Description of script command line parameters (from script --help output)
{script_help_info}

## Tool calling method
The tool accepts three parameters:
- `query` (string): Simple scenario, will be used as the first positional parameter of the script
- `cli_args` (string[]): the complete array of command line parameters,**Used for complex scripts that require the --flag value form**
- `script` (string): When Skill contains**multiple scripts**When , specify which one to call (such as `"dcf_calculator"` or `"valuation_snapshot.py"`) 

For example, to call `dcf_calculator.py --fcf 100 --shares 50 --growth 0.1`, Should pass:
```json
{{"script": "dcf_calculator", "cli_args": ["--fcf", "100", "--shares", "50", "--growth", "0.1"]}}
```

## key rules
1. **Must be called `{tool_id}` Tools to answer questions**, Don t answer out of thin air
2. **Read the above carefully"Script command line parameter description"**, from all available scripts**Choose the most suitable one** (use `script` parameter specification)
3. **Prefer scripts with the simplest parameters/reasonable default values**do tests (e.g. `valuation_snapshot`, `watchlist_manager` etc.), avoid choosing those that require a large number of required parameters (such as `dcf_calculator` Requires --fcf --shares)
4. **If the script requires a number/specific parameter that is not given in the user s question, you should generate reasonable test values yourself** (For example, testing the DCF estimator can be done with fcf=100, shares=50 and other typical figures)
5. **Don t reject calls due to lack of real data**——This is a test to verify that the tool can perform properly
6. After getting the results returned by the tool, briefly summarize the key information
7. If the tool fails, clearly communicate the reason for the failure"""

    user_question = question.strip() or "Please call the tool with reasonable test parameters to verify that it works properly. If the script requires specific parameters such as --fcf, --shares, etc., please generate the test values yourself."

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_question),
    ]

    # 5. Let LLM call tools autonomously
    tool_calls_trace = []
    try:
        response = await llm_client.achat(
            messages=messages,
            tools=[tool_def],
            auto_execute_tools=True,
            max_tool_rounds=3,
            tools_used=tool_calls_trace,
        )
    except Exception as e:
        logger.error(f"❌ LLM call failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"LLM call failed: {e}",
            "execution_time_ms": int((_time.time() - start) * 1000),
        }

    # Record token usage
    try:
        from app.services.usage_statistics_service import usage_statistics_service
        await usage_statistics_service.record_llm_usage(
            response=response,
            session_id="skill_test",
            analysis_type="skill_test",
        )
    except Exception as e:
        logger.warning(f"Record token usage failure: {e}")

    elapsed_ms = int((_time.time() - start) * 1000)

    # 6. Organize results
    return {
        "success": True,
        "result": {
            "skill_name": skill_name,
            "question": user_question,
            "tool_calls": tool_calls_trace,
            "tool_calls_count": len(tool_calls_trace),
            "final_answer": response.content or "",
            "model": response.model,
            "provider": response.provider,
        },
        "execution_time_ms": elapsed_ms,
    }


async def _test_skill_doc(doc: Dict[str, Any], req: SkillTestRequest, db: AsyncIOMotorDatabase) -> SkillTestResponse:
    """Test Skill documents in the skills collection"""
    impl = doc.get("implementation", {}) if isinstance(doc.get("implementation"), dict) else {}

    # Determine skill type
    skill_type = impl.get("type") if impl else "knowledge"
    logger.info(f"🔬 _test_skill_doc: name={doc.get('name')}, skill_type={skill_type}, "
                f"has_script_path={bool(impl.get('script_path'))}, has_code={bool(impl.get('code'))}, "
                f"has_skill_dir={bool(impl.get('skill_dir') or doc.get('skill_dir'))}")

    if skill_type == "python" and impl.get("code"):
        # Embed Python code
        code = impl["code"]
        # Detect placeholder code
        if _is_placeholder_code(code):
            return SkillTestResponse(
                success=True,
                result={
                    "skill_type": "knowledge",
                    "name": doc.get("display_name") or doc.get("name"),
                    "description": doc.get("description", ""),
                    "registered_in_registry": _check_tool_registry(doc.get("name", "")),
                    "note": "This Skill is knowledge-based and provides Agent context information without the need for independent execution."
                },
                execution_time_ms=0
            )
        # real executable code
        result = _execute_python_sandbox(code, req.args, req.timeout)
        return SkillTestResponse(
            success=result["success"],
            result=result.get("result"),
            error=result.get("error"),
            execution_time_ms=result.get("execution_time_ms", 0)
        )

    # Local Script Skill: Passed Agent + Function Calling real execution
    # Uses the same technology stack as the project analysis process (LLM + ToolRegistry + UnifiedLLMClient) 
    script_path = impl.get("script_path") if isinstance(impl, dict) else None
    skill_dir_val = (impl.get("skill_dir") if isinstance(impl, dict) else None) or doc.get("skill_dir")
    if script_path and skill_dir_val:
        agent_result = await _test_skill_via_agent(
            doc=doc,
            question=req.question or "",
            timeout=req.timeout or 60,
            db=db,
        )
        return SkillTestResponse(
            success=agent_result.get("success", False),
            result=agent_result.get("result"),
            error=agent_result.get("error"),
            execution_time_ms=agent_result.get("execution_time_ms", 0),
        )

    # knowledge type or other type
    return SkillTestResponse(
        success=True,
        result={
            "skill_type": skill_type,
            "name": doc.get("display_name") or doc.get("name"),
            "description": doc.get("description", ""),
            "category": doc.get("category", ""),
            "parameters_count": len(doc.get("parameters", [])),
            "registered_in_registry": _check_tool_registry(doc.get("name", "")),
            "has_implementation": bool(impl),
            "note": f"This Skill is {skill_type} type,{'Executable but no execution entry is currently configured' if skill_type == 'python' else 'Provide support for Agent as knowledge base/prompt words'}"
        },
        execution_time_ms=0
    )


class GitHubRepoSkill(BaseModel):
    """GitHub in warehouse Skill"""
    path: str
    name: str
    url: str
    raw_url: str
    size: int


class GitHubRepoResponse(BaseModel):
    """GitHub warehouse response"""
    owner: str
    repo: str
    skills: List[GitHubRepoSkill]
    readme: Optional[str] = None


@router.get("/github/repo/{owner}/{repo}", response_model=GitHubRepoResponse)
async def list_github_repo_skills(owner: str, repo: str):
    """List Skill files in GitHub repository"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get a list of warehouse contents
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
            resp = await client.get(api_url)
            resp.raise_for_status()
            contents = resp.json()

            skills = []
            readme = None

            for item in contents:
                if item["type"] == "file":
                    name = item["name"]
                    # Find SKILL.md or *.skill.md File
                    if name == "SKILL.md" or name.endswith(".skill.md"):
                        skills.append(GitHubRepoSkill(
                            path=item["path"],
                            name=name.replace(".md", ""),
                            url=item["html_url"],
                            raw_url=item["download_url"],
                            size=item["size"]
                        ))
                    elif name.lower() == "readme.md":
                        # get README
                        readme_resp = await client.get(item["download_url"])
                        if readme_resp.status_code == 200:
                            readme = readme_resp.text

        return GitHubRepoResponse(
            owner=owner,
            repo=repo,
            skills=skills,
            readme=readme
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"warehouse {owner}/{repo} does not exist")
        raise HTTPException(status_code=400, detail=f"GitHub API Error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Failed to get GitHub repository: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to obtain warehouse: {str(e)}")


class ImportFromGitHubRequest(BaseModel):
    """Import requests from GitHub"""
    owner: str
    repo: str
    path: str
    test_args: Dict[str, Any] = Field(default_factory=dict, description="Test parameters")


@router.post("/import-github", response_model=ImportWithTestResponse)
async def import_skill_from_github(
    req: ImportFromGitHubRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Import Skill from GitHub repository and test"""
    try:
        # Get raw content
        raw_url = f"https://raw.githubusercontent.com/{req.owner}/{req.repo}/main/{req.path}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(raw_url)
            if resp.status_code == 404:
                # Try the master branch
                raw_url = f"https://raw.githubusercontent.com/{req.owner}/{req.repo}/master/{req.path}"
                resp = await client.get(raw_url)
            resp.raise_for_status()
            content = resp.text

        # Parse and import
        skill = SkillParser.parse_content(content)
        existing = await db[COLLECTION].find_one({"name": skill.name})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Skill '{skill.name}' Already exists, please use the update interface or delete it first and then import it.",
            )

        doc = _skill_to_doc(skill)
        doc["source_url"] = raw_url
        doc["source_type"] = "github"
        await db[COLLECTION].insert_one(doc)
        await _register_skill_to_registry(doc)
        await _sync_capability_index(db)

        doc.pop("_id", None)
        skill_resp = _doc_to_response(doc)

        # If it is an executable type, automatically test
        test_result = None
        if skill_resp.is_executable and skill_resp.implementation:
            test_req = SkillTestRequest(
                skill_name=skill_resp.name,
                args=req.test_args,
                timeout=30
            )
            try:
                test_result = await test_skill(test_req, db)
            except Exception as e:
                test_result = SkillTestResponse(success=False, error=f"test failed: {str(e)}")

        message = "Import successful" + (", Test passed" if test_result and test_result.success else "")
        return ImportWithTestResponse(
            skill=skill_resp,
            test_result=test_result,
            message=message
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import from GitHub failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


class SmitheryServerResponse(BaseModel):
    """Smithery MCP Server response"""
    id: str
    name: str
    description: str
    tools: List[Dict[str, Any]]
    install_command: str


@router.get("/smithery/servers", response_model=List[SmitheryServerResponse])
async def list_smithery_servers():
    """List on Smithery MCP Server"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://smithery.ai/api/servers")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for server in data.get("servers", [])[:50]:
            servers.append(SmitheryServerResponse(
                id=server.get("id", ""),
                name=server.get("name", ""),
                description=server.get("description", ""),
                tools=server.get("tools", []),
                install_command=f"npx -y @smithery/cli install {server.get('id', '')}"
            ))

        return servers
    except Exception as e:
        logger.error(f"Failed to get Smithery server list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get list: {str(e)}")


# =============================================================================
# MCP Hub China (mcp-cn.com)
# =============================================================================


class MCPHubServerResponse(BaseModel):
    """MCP Hub Chinese server response"""
    server_id: int
    qualified_name: str
    display_name: str
    description: str
    creator: str
    use_count: int
    tag: str
    is_domestic: bool
    connections: str
    package_url: str

class MCPHubListResponse(BaseModel):
    """MCP Hub list response"""
    total: int
    page: int
    page_size: int
    servers: List[MCPHubServerResponse]


@router.get("/mcphub/servers", response_model=MCPHubListResponse)
async def list_mcphub_servers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=50, description="Quantity per page"),
    keyword: str = Query("", description="Search keywords"),
):
    """Browse MCP Hub China (mcp-cn.com) on MCP Server"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {"page": page, "pageSize": page_size}
            if keyword:
                params["keyword"] = keyword
            resp = await client.get("https://www.mcp-cn.com/api/servers", params=params)
            resp.raise_for_status()
            data = resp.json()

        servers = []
        for item in data.get("data", []):
            servers.append(MCPHubServerResponse(
                server_id=item.get("server_id", 0),
                qualified_name=item.get("qualified_name", ""),
                display_name=item.get("display_name", ""),
                description=item.get("description", ""),
                creator=item.get("creator", ""),
                use_count=item.get("use_count", 0),
                tag=item.get("tag", ""),
                is_domestic=item.get("is_domestic", False),
                connections=item.get("connections", ""),
                package_url=item.get("package_url", ""),
            ))

        pagination = data.get("pagination", {})
        return MCPHubListResponse(
            total=pagination.get("total", 0),
            page=page,
            page_size=page_size,
            servers=servers,
        )
    except Exception as e:
        logger.error(f"Failed to get MCP Hub server list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get list: {str(e)}")


# =============================================================================
# AgentHub / ClawHub (agent.xjtool.top)
# =============================================================================


class AgentHubItemResponse(BaseModel):
    """AgentHub resource response"""
    id: int
    pkg_id: str
    type: str
    display_name: str
    description: str
    version: str
    origin: str
    source_url: str
    stars: int
    downloads: int
    installs: int
    icon_url: str = ""

class AgentHubSearchResponse(BaseModel):
    """AgentHub search response"""
    total: int
    items: List[AgentHubItemResponse]


@router.get("/agenthub/search", response_model=AgentHubSearchResponse)
async def search_agenthub(
    q: str = Query("", description="Search keywords"),
    type_filter: str = Query("", description="Type filtering: skill | mcp-server"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """Search AgentHub (agent.xjtool.top) Skill and MCP Server"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params: Dict[str, Any] = {"q": q or "stock", "page": page, "size": page_size}
            if type_filter:
                params["type"] = type_filter
            resp = await client.get("https://agent.xjtool.top/api/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        items = []
        for item in data.get("items", []):
            items.append(AgentHubItemResponse(
                id=item.get("id", 0),
                pkg_id=item.get("pkgId", ""),
                type=item.get("type", ""),
                display_name=item.get("displayName", ""),
                description=item.get("description", ""),
                version=item.get("version", ""),
                origin=item.get("origin", ""),
                source_url=item.get("sourceUrl", ""),
                stars=item.get("stars", 0),
                downloads=item.get("downloads", 0),
                installs=item.get("installs", 0),
                icon_url=item.get("iconUrl", ""),
            ))

        return AgentHubSearchResponse(
            total=data.get("total", 0),
            items=items,
        )
    except Exception as e:
        logger.error(f"Search AgentHub failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# =============================================================================
# Import from AgentHub
# =============================================================================


class ImportFromAgentHubRequest(BaseModel):
    """Import requests from AgentHub"""
    pkg_id: str = Field(..., description="AgentHub Package ID, such as io.clawhub.mbpz/akshare-stock")
    test_args: Optional[Dict[str, Any]] = Field(default=None, description="Test parameters")


@router.post("/import-agenthub", response_model=ImportWithTestResponse)
async def import_from_agenthub(
    req: ImportFromAgentHubRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Import Skill from AgentHub (get the source code and parse it into SKILL.md format)"""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Get Skill details and source code
            resp = await client.get(f"https://agent.xjtool.top/api/items/{req.pkg_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"not found Skill: {req.pkg_id}")
            resp.raise_for_status()
            item_data = resp.json()

        # Try to get the source code content
        source_url = item_data.get("sourceUrl", "")
        skill_content = ""

        if source_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    src_resp = await client.get(source_url)
                    if src_resp.status_code == 200:
                        skill_content = src_resp.text
            except Exception:
                pass

        if not skill_content:
            # If source code cannot be obtained, generate a base SKILL.md
            skill_content = f"""---
name: {item_data.get("displayName", req.pkg_id.split("/")[-1]).lower().replace(" ", "-")}
version: "{item_data.get("version", "1.0.0")}"
description: {item_data.get("description", "")}
author: {item_data.get("origin", "agenthub")}
category: imported
tags: [agenthub, {item_data.get("type", "skill")}]
parameters: []
implementation:
  type: python
  code: |
    import json, sys
    args = json.loads(sys.stdin.read()) if sys.stdin else {{}}
    print("__SANDBOX_OUTPUT_START__")
    print(json.dumps({{"info": "Skill imported from AgentHub", "name": "{item_data.get("displayName", "")}", "pkg_id": "{req.pkg_id}"}}, ensure_ascii=False))
    print("__SANDBOX_OUTPUT_END__")
---

{item_data.get("description", "Imported from AgentHub Skill")}
"""

        # Parse and import
        skill = SkillParser.parse_content(skill_content)
        doc = _skill_to_doc(skill)
        doc["source_type"] = "agenthub"
        doc["source_url"] = source_url or f"https://agent.xjtool.top/api/items/{req.pkg_id}"

        existing = await db[COLLECTION].find_one({"name": doc["name"]})
        if existing:
            # update
            await db[COLLECTION].update_one({"name": doc["name"]}, {"$set": doc})
            doc["_id"] = existing["_id"]
        else:
            await db[COLLECTION].insert_one(doc)

        await _register_skill_to_registry(doc)
        await _sync_capability_index(db)

        # test
        test_result = None
        if req.test_args:
            impl = doc.get("implementation", {})
            if impl.get("type") == "python" and impl.get("code"):
                sandbox_result = _execute_python_sandbox(impl["code"], req.test_args, 30)
                test_result = SkillTestResponse(
                    success=sandbox_result["success"],
                    result=sandbox_result.get("result"),
                    error=sandbox_result.get("error"),
                    execution_time_ms=sandbox_result.get("execution_time_ms", 0),
                )

        skill_resp = _doc_to_response(doc)
        return ImportWithTestResponse(
            skill=skill_resp,
            test_result=test_result,
            message=f"Imported from AgentHub Skill: {skill_resp.name}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import from AgentHub failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


# =============================================================================
# ClawHub (clawhub.ai) - Local Skill Package Management
# Supports openclaw skills install similar installation method, download the complete Skill package to the local
# =============================================================================


class ClawHubSearchResult(BaseModel):
    """ClawHub Search result items"""
    slug: str
    display_name: str
    summary: str = ""
    version: Optional[str] = Field(default="", description="Version number, which may be None")
    owner_handle: str = ""
    owner_display_name: str = ""
    canonical_url: str = ""
    score: float = 0.0
    updated_at: Optional[int] = None


class ClawHubSearchResponse(BaseModel):
    """ClawHub search response"""
    query: str
    total: int
    results: List[ClawHubSearchResult]


@router.get("/clawhub/search", response_model=ClawHubSearchResponse)
async def search_clawhub(
    q: str = Query(..., description="Search keywords"),
    limit: int = Query(20, ge=1, le=50, description="Return maximum quantity"),
):
    """Search ClawHub (clawhub.ai) on Skill

    Call ClawHub public API: GET /api/v1/search?q=...
    No authentication required, rate limiting 3000/min per IP
    """
    try:
        results = await ClawHubSkillService.search_skills(q, limit=limit)
        logger.info(f"🔍 ClawHub Search q='{q}': Return {len(results) if results else 0} results")
        parsed = [ClawHubSearchResult(**r) for r in (results or [])]
        return ClawHubSearchResponse(query=q, total=len(parsed), results=parsed)
    except Exception as e:
        logger.error(f"❌ ClawHub Search exception: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ClawHub Search failed: {str(e)}")


class ClawHubInstallRequest(BaseModel):
    """ClawHub Skill Installation request"""
    slug: str = Field(..., description="Skill logo, such as 'ifind-repilot-finance-data-search' or '@wenzisay/ifind-repilot-finance-data-search'")
    version: Optional[str] = Field(default=None, description="Specify version (optional)")
    tag: Optional[str] = Field(default=None, description="Version label, such as 'latest' (optional)")


class ClawHubInstallResponse(BaseModel):
    """ClawHub Skill Installation response"""
    success: bool
    skill_name: str = ""
    skill_dir: str = ""
    version: str = ""
    has_scripts: bool = False
    scripts_count: int = 0
    extracted_files_count: int = 0
    skill_type: str = ""
    message: str


@router.post("/install-clawhub", response_model=ClawHubInstallResponse)
async def install_from_clawhub(
    req: ClawHubInstallRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Install Skill package from ClawHub to local directory

    Process:
    1. Call ClawHub API to download the complete Skill package (including scripts/)
    2. Unzip to skills/<slug>/ Directory
    3. Verify whether it is a script-based Skill (including scripts/ directory), reject knowledge-based Skills
    4. Parse SKILL.md and register to MongoDB
    5. Register to ToolRegistry

    Similar to `openclaw skills install <slug>` Effect of command
    """
    try:
        # 1. Download and unzip the Skill package
        install_result = await ClawHubSkillService.install_skill(
            slug=req.slug, version=req.version, tag=req.tag
        )

        if not install_result.get("success"):
            return ClawHubInstallResponse(
                success=False,
                skill_name=req.slug,
                message=install_result.get("message", "Installation failed"),
                skill_type=install_result.get("skill_type", ""),
            )

        # 2. Parse SKILL.md and register to MongoDB
        skill_name = install_result["skill_name"]
        skill_dir = install_result["skill_dir"]

        try:
            doc = await _import_local_skill_to_db(skill_dir, db, source_type="clawhub")
        except Exception as e:
            logger.warning(f"Skill Package downloaded but registration to MongoDB failed: {e}", exc_info=True)
            return ClawHubInstallResponse(
                success=True,
                skill_name=skill_name,
                skill_dir=skill_dir,
                version=install_result.get("version", ""),
                has_scripts=True,
                scripts_count=install_result.get("scripts_count", 0),
                extracted_files_count=install_result.get("extracted_files_count", 0),
                message=f"Skill The package has been downloaded to {skill_dir}, But registration to the database failed: {e}. You can try again using the import-local interface.",
            )

        return ClawHubInstallResponse(
            success=True,
            skill_name=skill_name,
            skill_dir=skill_dir,
            version=install_result.get("version", ""),
            has_scripts=True,
            scripts_count=install_result.get("scripts_count", 0),
            extracted_files_count=install_result.get("extracted_files_count", 0),
            message=f"Skill '{skill_name}' Installation and registration successful",
        )
    except Exception as e:
        logger.error(f"Installing Skill from ClawHub failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Installation failed: {str(e)}")


class LocalSkillImportRequest(BaseModel):
    """Local Skill Import Request"""
    skill_dir: str = Field(..., description="Local Skill package directory path, such as 'skills/ifind-finance-search' or absolute path")


class LocalSkillImportResponse(BaseModel):
    """Local Skill import response"""
    success: bool
    skill_name: str = ""
    skill_dir: str = ""
    has_scripts: bool = False
    scripts_count: int = 0
    message: str


@router.post("/import-local", response_model=LocalSkillImportResponse)
async def import_local_skill(
    req: LocalSkillImportRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Import Skill package from local directory to MongoDB

    Applies to:
    - Passed `openclaw skills install` or `clawhub install` Installed into the skills/ directory Skill
    - Manually downloaded Skill package

    Requirements:
    - The directory must contain the SKILL.md file
    - The directory must contain the scripts/ subdirectory (knowledge-based Skills are rejected)
    """
    try:
        # Parse directory path
        skill_dir_path = Path(req.skill_dir)
        if not skill_dir_path.is_absolute():
            skill_dir_path = (SKILLS_DIR / req.skill_dir).resolve()

        if not skill_dir_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Skill Directory does not exist: {skill_dir_path}. Please use install-clawhub to install the Skill package first.",
            )

        # Verification SKILL.md
        skill_md_path = skill_dir_path / "SKILL.md"
        if not skill_md_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"not found in directory SKILL.md: {skill_md_path}",
            )

        # Verify scripts/ directory (reject knowledge-based Skills)
        scripts_dir = skill_dir_path / "scripts"
        if not scripts_dir.is_dir():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Knowledge-based Skills (without scripts/ directory) do not support import."
                    f"This project only supports Python script skills that contain executable scripts."
                ),
            )
        script_files = [f for f in scripts_dir.iterdir() if f.is_file() and f.suffix == ".py"]
        if not script_files:
            raise HTTPException(
                status_code=400,
                detail=f"scripts/ There is no Python script file in the directory and cannot be imported.",
            )

        doc = await _import_local_skill_to_db(str(skill_dir_path), db, source_type="local")

        return LocalSkillImportResponse(
            success=True,
            skill_name=doc.get("name", ""),
            skill_dir=str(skill_dir_path),
            has_scripts=True,
            scripts_count=len(script_files),
            message=f"Skill '{doc.get('name', '')}' Import successful",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Local Skill import failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


class LocalSkillItem(BaseModel):
    """Local Skill Package Items"""
    name: str
    skill_dir: str
    has_scripts: bool
    has_skill_md: bool
    source: str = "local"
    version: str = ""
    installed_at: str = ""
    canonical_url: str = ""
    imported_to_db: bool = False


@router.get("/local", response_model=List[LocalSkillItem])
async def list_local_skills(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """List locally installed Skill packages

    Scan the skills/ directory and return all subdirectories containing SKILL.md.
    Also check if it has been imported to MongoDB.
    """
    local_skills = ClawHubSkillService.list_local_skills()

    # Query the imported data in MongoDB Skill
    imported_names = set()
    async for doc in db[COLLECTION].find({"source_type": {"$in": ["clawhub_local", "local", "clawhub"]}}, {"name": 1}):
        if doc.get("name"):
            imported_names.add(doc["name"])

    result = []
    for item in local_skills:
        item["imported_to_db"] = item["name"] in imported_names
        result.append(LocalSkillItem(**item))
    return result


class LocalSkillUninstallResponse(BaseModel):
    """Local Skill uninstall response"""
    success: bool
    message: str


@router.delete("/local/{slug}", response_model=LocalSkillUninstallResponse)
async def uninstall_local_skill(
    slug: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Uninstall local skill package

    1. Delete skills/<slug>/ Directory
    2. Delete corresponding records from MongoDB
    3. Log out from ToolRegistry (naturally invalid after restart)
    """
    try:
        # 1. Delete local directory
        result = ClawHubSkillService.uninstall_local_skill(slug)
        if not result.get("success"):
            return LocalSkillUninstallResponse(
                success=False,
                message=result.get("message", "Uninstall failed"),
            )

        # 2. Delete records from MongoDB
        delete_result = await db[COLLECTION].delete_many({
            "$or": [
                {"name": slug},
                {"name": slug.replace("-", "_")},
            ]
        })
        deleted_count = delete_result.deleted_count

        message = result.get("message", "Uninstalled successfully")
        if deleted_count > 0:
            message += f", Deleted {deleted_count} database record"

        return LocalSkillUninstallResponse(success=True, message=message)
    except Exception as e:
        logger.error(f"Failed to uninstall local Skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Uninstall failed: {str(e)}")


# =============================================================
# SkillHub (Tencent) Skill Search and install
# Called through the skillhub CLI subprocess, the skill is actually stored in GitHub
# =============================================================


class SkillHubSearchResult(BaseModel):
    """SkillHub Search result items"""
    slug: str = ""
    skill_id: str = ""
    display_name: str = ""
    summary: str = ""
    version: str = ""
    owner_handle: str = ""
    github_owner: str = ""
    github_repo: str = ""
    github_stars: int = 0
    download_count: int = 0
    security_score: int = 0
    security_status: str = ""
    ai_score: Optional[float] = None
    rating: float = 0
    is_verified: bool = False
    canonical_url: str = ""


class SkillHubSearchResponse(BaseModel):
    """SkillHub search response"""
    query: str
    total: int
    results: List[SkillHubSearchResult]


class SkillHubInstallRequest(BaseModel):
    """SkillHub Installation request"""
    skill_id: str = Field(..., description="Skill slug, Such as 'stock-info-explorer'")


class SkillHubInstallResponse(BaseModel):
    """SkillHub Installation response"""
    success: bool
    skill_name: str = ""
    skill_dir: str = ""
    version: str = ""
    has_scripts: bool = False
    scripts_count: int = 0
    message: str


# =============================================================
# ZIP File upload/URL import (replaces SkillHub CLI)
# =============================================================

class ImportZipResponse(BaseModel):
    """ZIP Import response"""
    success: bool
    skill_name: str = ""
    skill_dir: str = ""
    has_scripts: bool = False
    scripts_count: int = 0
    dependencies_installed: bool = False
    dependencies_log: str = ""
    message: str


def _install_skill_dependencies(skill_dir: str) -> Dict[str, Any]:
    """If there is requirements.txt in the Skill package, dependencies will be installed automatically.

    Returns:
        {success: bool, installed: bool, log: str}
        - installed=False Indicates that there is no requirements.txt (not considered a failure)
        - installed=True success=True Indicates successful installation
    """
    import subprocess as _sp
    import sys

    req_file = Path(skill_dir) / "requirements.txt"
    if not req_file.exists():
        return {"success": True, "installed": False, "log": "No requirements.txt, skip dependency installation"}

    try:
        # Read the content and filter comments and blank lines
        lines = [
            l.strip() for l in req_file.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        if not lines:
            return {"success": True, "installed": False, "log": "requirements.txt is empty"}

        logger.info(f"📦 Requirements.txt is detected and dependencies are installed.: {lines}")

        proc = _sp.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--disable-pip-version-check"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            encoding="utf-8",
            errors="replace",
        )

        log_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        # Truncate logs to avoid being too long
        if len(log_output) > 2000:
            log_output = log_output[:1000] + "\n... (Omit the middle) ...\n" + log_output[-1000:]

        if proc.returncode == 0:
            logger.info(f"✅ Skill Dependencies installed successfully: {skill_dir}")
            return {"success": True, "installed": True, "log": log_output}
        else:
            logger.error(f"❌ Skill Dependency installation failed (returncode={proc.returncode})")
            return {"success": False, "installed": True, "log": log_output}
    except Exception as e:
        logger.error(f"❌ Dependency installation exception: {e}", exc_info=True)
        return {"success": False, "installed": True, "log": f"Installation exception: {e}"}


@router.post("/{skill_name}/install-deps")
async def install_skill_deps(
    skill_name: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Manually trigger requirements.txt dependency installation for installed Skills

    Usage scenarios: Dependency installation fails during import, the user later manually changes requirements.txt, etc.
    """
    existing = await db[COLLECTION].find_one({
        "$or": [
            {"name": skill_name},
            {"display_name": skill_name},
        ]
    })
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    skill_dir = existing.get("skill_dir")
    if not skill_dir or not Path(skill_dir).exists():
        raise HTTPException(status_code=400, detail=f"Skill Directory does not exist: {skill_dir}")

    result = _install_skill_dependencies(skill_dir)
    return {
        "success": result["success"],
        "installed": result["installed"],
        "log": result["log"],
        "message": (
            "Dependencies installed successfully" if result["installed"] and result["success"]
            else ("No requirements.txt to install" if not result["installed"] else "Dependency installation failed")
        ),
    }


def _resolve_skill_name(skill_root: Path, fallback: str) -> str:
    """Parse the real name field from SKILL.md frontmatter and convert it to a legal directory name

    Processing logic:
    1. Priority is given to extracting English slugs in brackets (such as "Stock Value Investment Analysis (valuation-analysis)" → "valuation-analysis") 
    2. If the entire name is already a legal slug (English/number/hyphen/underscore), use it directly
    3. Otherwise replace spaces with hyphens and strip non-ASCII characters
    4. Returned when parsing fails or the result is empty fallback
    """
    import re

    skill_md = skill_root / "SKILL.md"
    if not skill_md.exists():
        return fallback
    try:
        content = skill_md.read_text(encoding="utf-8")
        skill = SkillParser.parse_content(content)
        name = skill.metadata.name if skill and skill.metadata else None
        if not name or not name.strip():
            return fallback

        name = name.strip()

        # 1. Extract slugs within parentheses first:xxx (yyy) → yyy
        m = re.search(r'\(([a-zA-Z0-9][\w\-]*)\)', name)
        if m:
            slug = m.group(1).strip()
            if slug:
                logger.info(f"📝 Extract from name brackets slug: '{name}' → '{slug}'")
                return slug

        # 2. Already legal slug
        if re.match(r'^[a-zA-Z0-9][\w\-]*$', name):
            return name

        # 3. slugify: space→hyphen, strip non ASCII
        slug = re.sub(r'[^\w\-]', '-', name).strip('-')
        slug = re.sub(r'-+', '-', slug)
        # Remove non-ASCII (Chinese, etc.)
        slug = ''.join(c for c in slug if c.isascii())
        slug = slug.strip('-')

        if slug:
            logger.info(f"📝 name slugify: '{name}' → '{slug}'")
            return slug
    except Exception as e:
        logger.warning(f"Parsing name from SKILL.md failed, using fallback={fallback}: {e}")

    return fallback


@router.post("/import-zip", response_model=ImportZipResponse)
async def import_skill_from_zip(
    file: UploadFile = File(..., description="Skill Package ZIP file"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Upload ZIP file to import Skill package

    Process:
    1. Receive ZIP file, verify format and size (50MB limit)
    2. Unzip to the temporary directory and locate the SKILL.md root directory
    3. move to skills/<name>/
    4. Parse SKILL.md and register to MongoDB + ToolRegistry
    """
    import tempfile

    # 1. Verify file type
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a file in .zip format")

    try:
        zip_bytes = await file.read()
        if len(zip_bytes) > 50 * 1024 * 1024:  # 50MB Limit
            raise HTTPException(status_code=400, detail="ZIP File size cannot exceed 50MB")

        # 2. Unzip to temporary directory
        with tempfile.TemporaryDirectory(prefix="skill_import_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            ClawHubSkillService._extract_zip(zip_bytes, tmp_path)

            # 3. Locate the SKILL.md root directory
            skill_root = ClawHubSkillService._locate_skill_root(tmp_path)
            if not skill_root:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP The SKILL.md file was not found in the package. Please confirm that it is a valid Skill package.",
                )

            # Prioritize parsing the real name field from SKILL.md (avoid using temporary directory names)
            skill_name = _resolve_skill_name(skill_root, fallback=skill_root.name)
            target_dir = SKILLS_DIR / skill_name

            # 4. If the target already exists, delete the old directory first
            if target_dir.exists():
                import shutil
                shutil.rmtree(target_dir)
                logger.info(f"🔄 Replaced existing skill package: {skill_name}")

            # 5. Move to skills/ directory
            import shutil
            shutil.move(str(skill_root), str(target_dir))
            logger.info(f"📦 ZIP Import successful: {skill_name} → {target_dir}")

            # 6. Parse SKILL.md and register to MongoDB + ToolRegistry
            doc = await _import_local_skill_to_db(str(target_dir), db, source_type="zip_upload")
            await _register_skill_to_registry(doc)

            script_count = len(doc.get("script_files", []))

            # 7. Automatically install requirements.txt dependencies
            dep_result = _install_skill_dependencies(str(target_dir))

            msg = f"Skill '{skill_name}' Import successful"
            if dep_result["installed"]:
                if dep_result["success"]:
                    msg += ", Dependencies are installed"
                else:
                    msg += ", But the dependency installation failed (please manually pip install -r requirements.txt)"

            return ImportZipResponse(
                success=True,
                skill_name=skill_name,
                skill_dir=str(target_dir),
                has_scripts=doc.get("has_scripts", False),
                scripts_count=script_count,
                dependencies_installed=dep_result["installed"] and dep_result["success"],
                dependencies_log=dep_result["log"],
                message=msg,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ ZIP Import failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


class ImportUrlRequest(BaseModel):
    """URL import request"""
    url: str = Field(..., description="Skill Package ZIP download link")
    name: Optional[str] = Field(None, description="Custom skill name (optional)")


@router.post("/import-url", response_model=ImportZipResponse)
async def import_skill_from_url(
    req: ImportUrlRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Import Skill package via download link

    Process:
    1. Download ZIP file from URL
    2. Unzip to the temporary directory and locate SKILL.md
    3. move to skills/<name>/
    4. Parse SKILL.md and register to MongoDB + ToolRegistry
    """
    import tempfile

    try:
        url = req.url.strip()

        # 1. Download ZIP
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            zip_bytes = resp.content

        if len(zip_bytes) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 50MB")

        # 2. Unzip to temporary directory
        with tempfile.TemporaryDirectory(prefix="skill_url_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            ClawHubSkillService._extract_zip(zip_bytes, tmp_path)

            # 3. Locate the SKILL.md root directory
            skill_root = ClawHubSkillService._locate_skill_root(tmp_path)
            if not skill_root:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP The SKILL.md file was not found in the package. Please confirm that it is a valid Skill package.",
                )

            # 4. Determine the name (first resolve the real name from SKILL.md)
            skill_name = req.name or _resolve_skill_name(skill_root, fallback=skill_root.name)
            target_dir = SKILLS_DIR / skill_name

            if target_dir.exists():
                import shutil
                shutil.rmtree(target_dir)

            # 5. Move to skills/ directory
            import shutil
            shutil.move(str(skill_root), str(target_dir))
            logger.info(f"📦 URL Import successful: {skill_name} ← {url[:80]}...")

            # 6. Parse and register
            doc = await _import_local_skill_to_db(str(target_dir), db, source_type="url_import")
            await _register_skill_to_registry(doc)

            script_count = len(doc.get("script_files", []))

            # 7. Automatically install requirements.txt dependencies
            dep_result = _install_skill_dependencies(str(target_dir))

            msg = f"Skill '{skill_name}' Import from URL successful"
            if dep_result["installed"]:
                if dep_result["success"]:
                    msg += ", Dependencies are installed"
                else:
                    msg += ", But the dependency installation failed (please manually pip install -r requirements.txt)"

            return ImportZipResponse(
                success=True,
                skill_name=skill_name,
                skill_dir=str(target_dir),
                has_scripts=doc.get("has_scripts", False),
                scripts_count=script_count,
                dependencies_installed=dep_result["installed"] and dep_result["success"],
                dependencies_log=dep_result["log"],
                message=msg,
            )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Download failed (HTTP {e.response.status_code})")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ URL Import failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


# =============================================================
# Internal helper function: import local Skill package MongoDB
# =============================================================

async def _import_local_skill_to_db(
    skill_dir: str,
    db: AsyncIOMotorDatabase,
    source_type: str = "local",
) -> Dict[str, Any]:
    """Import local Skill package MongoDB

    Args:
        skill_dir: Skill Package directory absolute path
        db: MongoDB database
        source_type: Source type (clawhub/local)

    Returns:
        imported Skill doc

    Raises:
        HTTPException: If parsing of SKILL.md fails
    """
    skill_dir_path = Path(skill_dir)
    skill_md_path = skill_dir_path / "SKILL.md"

    # parse SKILL.md
    content = skill_md_path.read_text(encoding="utf-8")
    skill = SkillParser.parse_content(content)

    # build doc
    doc = _skill_to_doc(skill)
    doc["skill_dir"] = str(skill_dir_path.resolve())
    doc["source_type"] = source_type
    doc["has_scripts"] = True

    # List Python scripts (compatible with both package structures)
    #   A) scripts/*.py (ClawHub standard)
    #   B) root directory *.py (SkillHub Partial package structure, such as stock-monitor/monitor.py)
    scripts_dir = skill_dir_path / "scripts"
    script_files = []
    if scripts_dir.is_dir():
        script_files = [f.name for f in scripts_dir.iterdir() if f.is_file() and f.suffix == ".py"]
    else:
        # Check the root directory .py file
        script_files = [f.name for f in skill_dir_path.iterdir()
                        if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"]
        if script_files:
            logger.info(f"📦 Skill '{doc.get('name', '?')}' Use root script: {script_files}")
    doc["script_files"] = script_files

    # If implementation is not declared in SKILL.md, one will be automatically built
    # Priority is given to using the entry script in the scripts/ directory, otherwise the first .py file in the root directory is used.
    if not doc.get("implementation"):
        if script_files:
            if (skill_dir_path / "scripts").is_dir():
                script_path = f"scripts/{script_files[0]}"
            else:
                script_path = script_files[0]
            doc["implementation"] = {
                "type": "python",
                "script_path": script_path,
                "skill_dir": str(skill_dir_path.resolve()),
                "note": "Auto-detected",
            }
    else:
        # If there is an implementation, add the skill_dir field
        impl = doc["implementation"]
        if isinstance(impl, dict):
            impl.setdefault("skill_dir", str(skill_dir_path.resolve()))
            # If there is no code/module/function but there is a script file, add script_path
            if not impl.get("code") and not impl.get("module") and not impl.get("script_path"):
                if script_files:
                    if (skill_dir_path / "scripts").is_dir():
                        impl["script_path"] = f"scripts/{script_files[0]}"
                    else:
                        impl["script_path"] = script_files[0]

    # Parse the credential statement and save to doc
    credential_decls = SkillCredentialService.parse_credentials_from_skill_md(str(skill_dir_path))
    if credential_decls:
        doc["required_credentials"] = [d.to_dict() for d in credential_decls]

    # Write to MongoDB (upsert)
    existing = await db[COLLECTION].find_one({"name": doc["name"]})
    if existing:
        await db[COLLECTION].update_one({"name": doc["name"]}, {"$set": doc})
        doc["_id"] = existing["_id"]
    else:
        await db[COLLECTION].insert_one(doc)

    # Register to ToolRegistry
    await _register_skill_to_registry(doc)
    await _sync_capability_index(db)

    logger.info(f"✅ local Skill '{doc['name']}' Imported MongoDB (skill_dir={skill_dir_path})")
    return doc


# =============================================================================
# Skill Credential management
# Two credential configuration methods are supported:
# 1. frontmatter env Declaration (environment variable injection)
# 2. Command line parameter configuration (such as --set-token)
# =============================================================================


class CredentialRequirementResponse(BaseModel):
    """Credential assertion response"""
    name: str
    description: str = ""
    required: bool = False
    config_type: str = "env"  # env | script_arg
    config_command: str = ""
    configured: bool = False
    masked_value: str = ""


class CredentialStatusResponse(BaseModel):
    """Credential status response"""
    skill_name: str
    required: List[CredentialRequirementResponse] = []
    extra: List[Dict[str, str]] = []
    all_configured: bool = False
    missing_required: List[str] = []


class SaveCredentialsRequest(BaseModel):
    """Save credential request"""
    credentials: Dict[str, str] = Field(..., description="Credential key-value pair (plain text, will be stored encrypted)")


class ConfigureViaScriptRequest(BaseModel):
    """Configure credential requests via script commands"""
    config_command: str = Field(..., description="Configuration commands such as '--set-token'")
    credential_value: str = Field(..., description="Voucher value")
    script_path: Optional[str] = Field(default=None, description="Script path (obtained from implementation.script_path by default)")
    timeout: int = Field(default=30, description="Timeout seconds")


@router.get("/{skill_name}/credentials/required", response_model=CredentialStatusResponse)
async def get_skill_credentials_status(
    skill_name: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get Skill credential configuration status

    Returns a list of required credentials and their configuration status (no clear text is returned).
    The credential statement is parsed from SKILL.md and supports two methods:
    1. frontmatter metadata.openclaw.env Statement
    2. instructions Configuration commands such as --set-token in
    """
    # Get Skill Documentation
    doc = await db[COLLECTION].find_one({"name": skill_name})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    # Get credential statement
    declarations: List[CredentialDeclaration] = []
    skill_dir = doc.get("skill_dir")
    if skill_dir:
        declarations = SkillCredentialService.parse_credentials_from_skill_md(skill_dir)
    else:
        # Read a saved declaration from doc
        for decl_dict in doc.get("required_credentials", []):
            declarations.append(CredentialDeclaration(
                name=decl_dict.get("name", ""),
                description=decl_dict.get("description", ""),
                required=decl_dict.get("required", False),
                config_type=decl_dict.get("config_type", "env"),
                config_command=decl_dict.get("config_command", ""),
            ))

    # Get voucher status
    status = await SkillCredentialService.get_credentials_status(db, skill_name, declarations)

    return CredentialStatusResponse(
        skill_name=status["skill_name"],
        required=[CredentialRequirementResponse(**r) for r in status["required"]],
        extra=status["extra"],
        all_configured=status["all_configured"],
        missing_required=status["missing_required"],
    )


@router.post("/{skill_name}/credentials")
async def save_skill_credentials(
    skill_name: str,
    req: SaveCredentialsRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Save Skill Credentials (encrypted storage)

    Encrypt the credential values and store them in the MongoDB skill_credentials collection.
    It will be automatically injected as an environment variable when executing the script.

    For skills configured using commands such as --set-token,
    Please use the /credentials/configure-script endpoint.
    """
    # Verify that Skill exists
    doc = await db[COLLECTION].find_one({"name": skill_name})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    result = await SkillCredentialService.save_credentials(db, skill_name, req.credentials)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Save failed"))

    return {
        "success": True,
        "skill_name": skill_name,
        "saved_count": result["saved_count"],
        "message": f"Credentials saved ({result['saved_count']} items)",
    }


@router.get("/{skill_name}/credentials", response_model=CredentialStatusResponse)
async def get_skill_credentials(
    skill_name: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get Skill credential status (alias, same as /credentials/required)"""
    return await get_skill_credentials_status(skill_name, db)


@router.delete("/{skill_name}/credentials")
async def delete_skill_credentials(
    skill_name: str,
    keys: Optional[str] = Query(None, description="Certificate key names to be deleted (comma separated), if not passed, all will be deleted."),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete Skill Credentials"""
    key_list = keys.split(",") if keys else None
    result = await SkillCredentialService.delete_credentials(db, skill_name, key_list)
    return {
        "success": result["success"],
        "deleted_count": result["deleted_count"],
        "message": f"Deleted {result['deleted_count']} item voucher",
    }


@router.post("/{skill_name}/credentials/configure-script")
async def configure_credential_via_script(
    skill_name: str,
    req: ConfigureViaScriptRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Configure credentials via script s configure command

    Applies to Skills that use commands such as --set-token to configure credentials.
    For example:python scripts/fetch_data.py --set-token <token>

    After execution, the credentials are stored by the script itself (e.g. writing ~/.config/xxx/config.json) . 
    At the same time, the credential value will be encrypted and saved to MongoDB to facilitate the injection of environment variables during subsequent execution.
    """
    # Verify that Skill exists
    doc = await db[COLLECTION].find_one({"name": skill_name})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    skill_dir = doc.get("skill_dir")
    if not skill_dir:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{skill_name}' There is no local package directory (skill_dir) and the configuration command cannot be executed.",
        )

    # Get script path
    script_path = req.script_path
    if not script_path:
        impl = doc.get("implementation") or {}
        script_path = impl.get("script_path")
    if not script_path:
        raise HTTPException(
            status_code=400,
            detail="script_path is not specified and there is no script_path field in Skill implementation",
        )

    # Execute configuration command
    result = await SkillCredentialService.configure_via_script(
        skill_dir=skill_dir,
        script_path=script_path,
        config_command=req.config_command,
        credential_value=req.credential_value,
        timeout=req.timeout,
    )

    if not result.get("success"):
        return {
            "success": False,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "message": result.get("message", "Configuration failed"),
        }

    # At the same time, the credential value is encrypted and saved to MongoDB
    # Deduced credential name:--set-token -> AUTH_TOKEN
    var_name = SkillCredentialService._derive_var_name(
        req.config_command.lstrip("-").replace("set-", "").replace("config-", "")
    )
    await SkillCredentialService.save_credentials(
        db, skill_name, {var_name: req.credential_value}
    )

    return {
        "success": True,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": f"Credential configuration is successful and executed {req.config_command} command and save to database",
        "saved_credential_name": var_name,
    }


# =============================================================================
# Dynamic path routing (must be placed after fixed path routing to avoid path parameter matching conflicts)
# =============================================================================

@router.get("/{skill_name}", response_model=SkillResponse)
async def get_skill(
    skill_name: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get Skill details"""
    doc = await db[COLLECTION].find_one({"name": skill_name})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")
    return _doc_to_response(doc)


@router.put("/{skill_name}", response_model=SkillResponse)
async def update_skill(
    skill_name: str,
    req: SkillCreateRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """update Skill"""
    existing = await db[COLLECTION].find_one({"name": skill_name})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    if existing.get("is_builtin", False):
        raise HTTPException(status_code=400, detail="Built-in skills cannot be modified")

    update_doc = req.model_dump(exclude_none=True)
    update_doc["updated_at"] = datetime.utcnow().isoformat()
    update_doc["name"] = req.name

    await db[COLLECTION].update_one({"name": skill_name}, {"$set": update_doc})

    updated = await db[COLLECTION].find_one({"name": req.name})
    if updated:
        await _register_skill_to_registry(updated)
        await _sync_capability_index(db)

    return _doc_to_response(updated or update_doc)


@router.delete("/{skill_name}")
async def delete_skill(
    skill_name: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Remove Skill (Uninstall)

    1. Delete Skill records in MongoDB
    2. Logout from ToolRegistry
    3. Delete Agent binding relationship
    4. delete local skills/<skill_name>/ Directory (if it exists)
    5. Delete the credentials for this Skill

    Supports name or display_name matching.
    """
    # Compatible: support name / display_name / skill_id(Underline) Multiple format matching
    existing = await db[COLLECTION].find_one({
        "$or": [
            {"name": skill_name},
            {"display_name": skill_name},
            {"name": skill_name.replace("_", "-")},
            {"skill_id": skill_name},
            {"skill_id": skill_name.replace("-", "_")},
        ]
    })

    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    real_name = existing["name"]

    if existing.get("is_builtin", False):
        raise HTTPException(status_code=400, detail="Built-in skills cannot be deleted")

    # 1. Delete MongoDB records
    await db[COLLECTION].delete_one({"name": real_name})

    # 2. Logout from ToolRegistry
    tool_id = real_name.replace("-", "_")
    registry = get_tool_registry()
    registry.unregister(tool_id)

    # 3. Delete Agent binding relationship
    await db.tool_agent_bindings.delete_many({"tool_id": tool_id})

    # 4. Delete the local skills/ directory (trying multiple name matches at the same time)
    deleted_dir = False
    # try to match directly name / display_name / skill_id
    candidates = [
        real_name,
        skill_name,
        existing.get("display_name", ""),
        existing.get("skill_id", ""),
    ]
    # Remove duplicates
    seen = set()
    unique_candidates = []
    for c in candidates:
        c = str(c or "").strip()
        if c and c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    for name_to_try in unique_candidates:
        try:
            result = ClawHubSkillService.uninstall_local_skill(name_to_try)
            if result.get("success"):
                deleted_dir = True
                break
        except Exception:
            pass

    # If direct matching fails, scan skill_import_* Directory, matched by skill_id in SKILL.md
    if not deleted_dir:
        try:
            import re
            skills_dir = Path(__file__).resolve().parents[2] / "skills"
            for child in skills_dir.iterdir():
                if not child.is_dir():
                    continue
                if not child.name.startswith("skill_import_"):
                    continue
                skill_md = child / "SKILL.md"
                if not skill_md.exists():
                    continue
                content = skill_md.read_text(encoding="utf-8", errors="ignore")
                # Check if the skill_id contains the skill or name
                doc_skill_id = str(existing.get("skill_id", "")).strip()
                doc_name = str(existing.get("name", "")).strip()
                if doc_skill_id and doc_skill_id in content:
                    import shutil
                    shutil.rmtree(child)
                    deleted_dir = True
                    logger.info(f"✅ Removed import directory via SKILL.md matching: {child.name} (skill_id={doc_skill_id})")
                    break
                if doc_name and doc_name in content:
                    import shutil
                    shutil.rmtree(child)
                    deleted_dir = True
                    logger.info(f"✅ Removed import directory via SKILL.md matching: {child.name} (name={doc_name})")
                    break
        except Exception:
            pass

    # 5. Delete credentials
    try:
        await SkillCredentialService.delete_credentials(db, real_name, keys=None)
    except Exception as e:
        logger.warning(f"Deleting Skill Credentials failed: {e}")

    await _sync_capability_index(db)

    msg = f"Skill '{real_name}' Uninstalled"
    if deleted_dir:
        msg += " (including local directory and credentials)"
    return {"success": True, "message": msg, "deleted_dir": deleted_dir}


@router.post("/{skill_name}/toggle")
async def toggle_skill(
    skill_name: str,
    req: SkillToggleRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """enable/disable Skill"""
    existing = await db[COLLECTION].find_one({"name": skill_name})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    await db[COLLECTION].update_one(
        {"name": skill_name},
        {"$set": {"enabled": req.enabled, "updated_at": datetime.utcnow().isoformat()}},
    )

    tool_id = skill_name.replace("-", "_")
    registry = get_tool_registry()
    if req.enabled:
        updated = await db[COLLECTION].find_one({"name": skill_name})
        if updated:
            await _register_skill_to_registry(updated)
    else:
        registry.unregister(tool_id)
    await _sync_capability_index(db)

    status = "enable" if req.enabled else "Disable"
    return {"success": True, "message": f"Skill '{skill_name}' Already{status}"}


@router.get("/{skill_name}/export")
async def export_skill(
    skill_name: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Export Skill to SKILL.md format"""
    doc = await db[COLLECTION].find_one({"name": skill_name})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' does not exist")

    doc.pop("_id", None)

    import yaml
    frontmatter_fields = {}
    for key in ("name", "description", "version", "author", "category", "tags",
                "when_to_use", "parameters", "returns", "implementation",
                "enabled", "fc_enabled"):
        val = doc.get(key)
        if val is not None and val != "" and val != []:
            frontmatter_fields[key] = val

    yaml_str = yaml.dump(frontmatter_fields, allow_unicode=True, default_flow_style=False, sort_keys=False)
    instructions = doc.get("instructions", "")

    skill_md = f"---\n{yaml_str}---\n\n{instructions}\n"

    return {"content": skill_md, "filename": f"{skill_name}.SKILL.md"}

