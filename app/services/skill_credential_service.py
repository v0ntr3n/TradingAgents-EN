"""
Skill Credential Management Services

Responsible for managing ClawHub Skill s credentials (API Key, Auth Token, etc.).

Two credential configuration methods are supported:
1. **frontmatter env Statement** - Declare the required environment variables in the YAML frontmatter of SKILL.md
   ```yaml
   metadata:
     openclaw:
       env:
         - name: IFIND_AUTH_TOKEN
           description: "Certification token"
           required: true
   ```
   When the script is executed, the credential values ​​are injected as environment variables.

2. **Command line parameter configuration** - Through the configuration commands of the script itself (such as `--set-token`) Configuration
   For example ifind-repilot-finance-data-search Skill:
   ```bash
   python3 <skill_dir>/scripts/fetch_data.py --set-token <your_auth_token>
   ```
   Credentials are stored in a location specified by the script (e.g. ~/.config/ifind-repilot/config.json) . 

Credentials encrypted storage:
- Use Fernet encryption (AES-128-CBC + HMAC-SHA256) 
- The key is derived from JWT_SECRET (reuse project s existing mechanism)
- Stored in the MongoDB skill_credentials collection
"""

import base64
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("webapi")

# Credential storage collection
CREDENTIALS_COLLECTION = "skill_credentials"


def _get_encryption_key() -> bytes:
    """Get the encryption key (derived based on JWT_SECRET)

    Reuse the encryption mechanism in mcp.py to maintain consistency.
    """
    secret = os.getenv("JWT_SECRET", "trading-agents-default-secret")
    return hashlib.sha256(secret.encode()).digest()


def _get_fernet():
    """获取 Fernet 实例"""
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(_get_encryption_key())
    return Fernet(key)


def _encrypt_value(plain: str) -> str:
    """Encrypted credential value

    Output format:v2:<fernet_token>
    """
    f = _get_fernet()
    token = f.encrypt(plain.encode("utf-8")).decode("ascii")
    return f"v2:{token}"


def _decrypt_value(cipher: str) -> str:
    """Decrypt credential value

    Two formats are supported:
    - v2:<fernet_token>: New format, Fernet decryption
    - <base64>: old format,XOR + base64 Decryption (backwards compatible)
    """
    if cipher.startswith("v2:"):
        f = _get_fernet()
        token = cipher[3:].encode("ascii")
        return f.decrypt(token).decode("utf-8")
    else:
        # Old format compatible
        key = _get_encryption_key()
        data = base64.b64decode(cipher)
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return decrypted.decode("utf-8")


def _mask_value(value: str) -> str:
    """Masked display: only the first 4 digits and the last 4 digits are displayed"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


class CredentialDeclaration:
    """Credential declaration (parsed from SKILL.md)"""

    def __init__(
        self,
        name: str,
        description: str = "",
        required: bool = False,
        config_type: str = "env",  # env | script_arg
        config_command: str = "",  # Only script_arg types like "--set-token"
        config_position: int = 0,  # The location of the configuration command in instructions
    ):
        self.name = name
        self.description = description
        self.required = required
        self.config_type = config_type  # env: Environment variable injection;script_arg: Script command configuration
        self.config_command = config_command
        self.config_position = config_position

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "config_type": self.config_type,
            "config_command": self.config_command,
        }


class SkillCredentialService:
    """Skill 凭证管理服务"""

    # =============================================================
    # Credential claim parsing
    # =============================================================

    @staticmethod
    def parse_credentials_from_skill_md(skill_dir: str) -> List[CredentialDeclaration]:
        """Parse required credential declarations from SKILL.md

        Parsing order:
        1. Parse from frontmatter metadata.openclaw.env (standard way)
        2. Parse configuration commands such as --set-token (command line parameter type) from instructions

        Args:
            skill_dir: Skill package directory path

        Returns:
            Credential declaration list
        """
        skill_md_path = Path(skill_dir) / "SKILL.md"
        if not skill_md_path.exists():
            return []

        content = skill_md_path.read_text(encoding="utf-8")
        return SkillCredentialService._parse_credentials_from_content(content)

    @staticmethod
    def _parse_credentials_from_content(content: str) -> List[CredentialDeclaration]:
        """Parse credential claims from SKILL.md content"""
        declarations: List[CredentialDeclaration] = []

        # 1. parse frontmatter
        frontmatter, body = SkillCredentialService._split_frontmatter(content)
        if frontmatter:
            try:
                metadata = yaml.safe_load(frontmatter)
                if isinstance(metadata, dict):
                    declarations.extend(
                        SkillCredentialService._parse_env_from_frontmatter(metadata)
                    )
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse SKILL.md frontmatter: {e}")

        # 2. Parse configuration commands such as --set-token from instructions
        if body:
            declarations.extend(
                SkillCredentialService._parse_config_commands_from_body(body)
            )

        # Remove duplicates (by name)
        seen_names = set()
        unique: List[CredentialDeclaration] = []
        for decl in declarations:
            if decl.name not in seen_names:
                seen_names.add(decl.name)
                unique.append(decl)

        return unique

    @staticmethod
    def _split_frontmatter(content: str):
        """Separate YAML frontmatter and body"""
        pattern = r"^---\s*\n(.*?)\n---\s*\n?(.*)"
        match = re.match(pattern, content.strip(), re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return None, content

    @staticmethod
    def _parse_env_from_frontmatter(metadata: Dict[str, Any]) -> List[CredentialDeclaration]:
        """Parse credential claims from frontmatter metadata.openclaw.env"""
        declarations: List[CredentialDeclaration] = []

        # support metadata.openclaw.env
        meta = metadata.get("metadata") or {}
        if isinstance(meta, str):
            # Some SKILL.md metadata are JSON strings
            try:
                import json
                meta = json.loads(meta)
            except (json.JSONDecodeError, ValueError):
                meta = {}

        if not isinstance(meta, dict):
            return declarations

        openclaw_meta = meta.get("openclaw") or {}
        if not isinstance(openclaw_meta, dict):
            return declarations

        env_decls = openclaw_meta.get("env") or []
        if not isinstance(env_decls, list):
            return declarations

        for env_decl in env_decls:
            if isinstance(env_decl, dict):
                declarations.append(CredentialDeclaration(
                    name=env_decl.get("name", ""),
                    description=env_decl.get("description", ""),
                    required=env_decl.get("required", False),
                    config_type="env",
                ))
            elif isinstance(env_decl, str):
                declarations.append(CredentialDeclaration(
                    name=env_decl,
                    description="",
                    required=True,
                    config_type="env",
                ))

        return declarations

    @staticmethod
    def _parse_config_commands_from_body(body: str) -> List[CredentialDeclaration]:
        """Parse configuration commands such as --set-token from instructions

        Match pattern:
        - `--set-token <your_auth_token>`
        - `--set-api-key <your_api_key>`
        - `--config-token <token>`
        - `--set-key <key>`

        Extract variable names:set-token -> AUTH_TOKEN, set-api-key -> API_KEY
        """
        declarations: List[CredentialDeclaration] = []

        # Matches --set-xxx or --config-xxx followed by placeholder
        patterns = [
            (r"--set-(\w[\w-]*)\s+<([^>]+)>", "set"),
            (r"--config-(\w[\w-]*)\s+<([^>]+)>", "config"),
            (r"--set-(\w[\w-]*)\s+(\w+)", "set"),
        ]

        seen_commands = set()
        for pattern, prefix in patterns:
            for match in re.finditer(pattern, body):
                cmd_name = match.group(1).lower()
                placeholder = match.group(2)
                full_command = f"--{prefix}-{cmd_name}"

                if full_command in seen_commands:
                    continue
                seen_commands.add(full_command)

                # Deducing environment variable names from command names
                # set-token -> AUTH_TOKEN
                # set-api-key -> API_KEY
                # set-auth-token -> AUTH_TOKEN
                var_name = SkillCredentialService._derive_var_name(cmd_name)

                # Deriving descriptions from placeholders
                description = f"通过 `{full_command}` 命令配置"

                declarations.append(CredentialDeclaration(
                    name=var_name,
                    description=description,
                    required=True,
                    config_type="script_arg",
                    config_command=full_command,
                ))

        return declarations

    @staticmethod
    def _derive_var_name(cmd_name: str) -> str:
        """Deducing environment variable names from command names

        set-token -> AUTH_TOKEN
        set-api-key -> API_KEY
        set-auth-token -> AUTH_TOKEN
        """
        # Remove common prefixes
        parts = cmd_name.split("-")
        # Filter out prefix words such as set/config/auth
        filtered = [p for p in parts if p not in ("set", "config", "auth", "the", "your")]
        if not filtered:
            filtered = parts
        return "_".join(p.upper() for p in filtered)

    # =============================================================
    # Credential Storage (MongoDB + Fernet encryption)
    # =============================================================

    @staticmethod
    async def save_credentials(
        db: AsyncIOMotorDatabase,
        skill_name: str,
        credentials: Dict[str, str],
    ) -> Dict[str, Any]:
        """Save Skill Credentials (encrypted storage)

        Args:
            db: MongoDB database
            skill_name: Skill Name
            credentials: Credential key-value pair (plain text)

        Returns:
            {success, skill_name, saved_count}
        """
        if not credentials:
            return {"success": False, "message": "凭证不能为空"}

        # Encrypt all credential values
        encrypted = {
            key: _encrypt_value(str(value))
            for key, value in credentials.items()
            if value is not None and str(value) != ""
        }

        if not encrypted:
            return {"success": False, "message": "没有有效的凭证值"}

        # Write to MongoDB (upsert)
        await db[CREDENTIALS_COLLECTION].update_one(
            {"skill_name": skill_name},
            {
                "$set": {
                    "skill_name": skill_name,
                    "credentials": encrypted,
                    "updated_at": SkillCredentialService._now_iso(),
                },
                "$setOnInsert": {
                    "created_at": SkillCredentialService._now_iso(),
                },
            },
            upsert=True,
        )

        logger.info(f"✅ Skill '{skill_name}' 凭证已保存（{len(encrypted)} 项）")
        return {
            "success": True,
            "skill_name": skill_name,
            "saved_count": len(encrypted),
        }

    @staticmethod
    async def get_credentials_decrypted(
        db: AsyncIOMotorDatabase,
        skill_name: str,
    ) -> Dict[str, str]:
        """Get Skill credentials (decrypted plain text)

        Note: This method returns plain text and is only used to inject environment variables when executing scripts.
        Do not use for API responses.

        Args:
            db: MongoDB database
            skill_name: Skill Name

        Returns:
            Credential key-value pair (plain text)
        """
        doc = await db[CREDENTIALS_COLLECTION].find_one({"skill_name": skill_name})
        if not doc:
            return {}

        decrypted = {}
        for key, encrypted_value in doc.get("credentials", {}).items():
            try:
                decrypted[key] = _decrypt_value(encrypted_value)
            except Exception as e:
                logger.warning(f"⚠️ 解密凭证 '{key}' 失败: {e}")
                decrypted[key] = ""

        return decrypted

    @staticmethod
    async def get_credentials_status(
        db: AsyncIOMotorDatabase,
        skill_name: str,
        required_declarations: List[CredentialDeclaration] = None,
    ) -> Dict[str, Any]:
        """Get the credential configuration status (do not return clear text)

        Used in API responses to show configured/unconfigured status and masking values.

        Args:
            db: MongoDB database
            skill_name: Skill Name
            required_declarations: List of required credential claims (optional)

        Returns:
            {
                "skill_name": str,
                "required": [{name, description, required, config_type, config_command, configured, masked_value}],
                "extra": [{name, masked_value}],  # Configured but undeclared credentials
                "all_configured": bool,
                "missing_required": [name]
            }
        """
        doc = await db[CREDENTIALS_COLLECTION].find_one({"skill_name": skill_name})
        stored_credentials = doc.get("credentials", {}) if doc else {}

        # Decrypt to generate masked values
        decrypted = {}
        for key, encrypted_value in stored_credentials.items():
            try:
                decrypted[key] = _decrypt_value(encrypted_value)
            except Exception:
                decrypted[key] = ""

        required_list = []
        missing_required = []
        configured_names = set(stored_credentials.keys())

        if required_declarations:
            for decl in required_declarations:
                is_configured = decl.name in decrypted and bool(decrypted[decl.name])
                masked_value = _mask_value(decrypted[decl.name]) if is_configured else ""
                required_list.append({
                    "name": decl.name,
                    "description": decl.description,
                    "required": decl.required,
                    "config_type": decl.config_type,
                    "config_command": decl.config_command,
                    "configured": is_configured,
                    "masked_value": masked_value,
                })
                if decl.required and not is_configured:
                    missing_required.append(decl.name)

        # Configured but undeclared credentials
        declared_names = {d.name for d in required_declarations} if required_declarations else set()
        extra_list = []
        for key, value in decrypted.items():
            if key not in declared_names:
                extra_list.append({
                    "name": key,
                    "masked_value": _mask_value(value),
                })

        return {
            "skill_name": skill_name,
            "required": required_list,
            "extra": extra_list,
            "all_configured": len(missing_required) == 0,
            "missing_required": missing_required,
        }

    @staticmethod
    async def delete_credentials(
        db: AsyncIOMotorDatabase,
        skill_name: str,
        keys: List[str] = None,
    ) -> Dict[str, Any]:
        """Delete Skill Credentials

        Args:
            db: MongoDB database
            skill_name: Skill Name
            keys: List of credential keys to delete (None means delete all)

        Returns:
            {success, deleted_count}
        """
        if keys is None:
            # Delete all
            result = await db[CREDENTIALS_COLLECTION].delete_many({"skill_name": skill_name})
            deleted = result.deleted_count
        else:
            # Delete specified key
            doc = await db[CREDENTIALS_COLLECTION].find_one({"skill_name": skill_name})
            if not doc:
                return {"success": True, "deleted_count": 0}

            existing = doc.get("credentials", {})
            deleted = 0
            for key in keys:
                if key in existing:
                    del existing[key]
                    deleted += 1

            if not existing:
                await db[CREDENTIALS_COLLECTION].delete_one({"skill_name": skill_name})
            else:
                await db[CREDENTIALS_COLLECTION].update_one(
                    {"skill_name": skill_name},
                    {"$set": {"credentials": existing, "updated_at": SkillCredentialService._now_iso()}},
                )

        logger.info(f"✅ Skill '{skill_name}' 凭证已删除（{deleted} 项）")
        return {"success": True, "deleted_count": deleted}

    # =============================================================
    # Command line parameter-based credential configuration
    # =============================================================

    @staticmethod
    async def configure_via_script(
        skill_dir: str,
        script_path: str,
        config_command: str,
        credential_value: str,
        timeout: int = 30,
        python_executable: str = "python",
    ) -> Dict[str, Any]:
        """Configure credentials via script s configure command

        Applies to Skills that use commands such as --set-token to configure credentials.
        For example:python scripts/fetch_data.py --set-token <token>

        Args:
            skill_dir: Skill package directory
            script_path: Script relative paths (e.g. "scripts/fetch_data.py") 
            config_command: Configuration commands (such as "--set-token") 
            credential_value: Voucher value
            timeout: Timeout seconds
            python_executable: Python interpreter

        Returns:
            {success, stdout, stderr, message}
        """
        import subprocess

        skill_dir_path = Path(skill_dir).resolve()
        full_script_path = skill_dir_path / script_path

        if not full_script_path.exists():
            return {
                "success": False,
                "message": f"脚本文件不存在: {full_script_path}",
            }

        # Build command:python scripts/fetch_data.py --set-token <token>
        cmd = [python_executable, str(full_script_path), config_command, credential_value]

        try:
            logger.info(f"🔧 执行凭证配置命令: {config_command}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(skill_dir_path),
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "message": "凭证配置成功",
                }
            else:
                return {
                    "success": False,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "message": f"配置失败: {result.stderr or result.stdout or '未知错误'}",
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": f"配置命令执行超时（{timeout}秒）",
            }
        except Exception as e:
            logger.error(f"❌ Credential configuration command execution exception: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e),
            }

    # =============================================================
    # Helper methods
    # =============================================================

    @staticmethod
    def _now_iso() -> str:
        """Get the ISO format string of the current time"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
