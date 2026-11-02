from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['skillhub_service', 'clawhub_skill_service', 'skill_credential_service', 'skill_gap_service', 'skill_generation_service', 'capability_index_service']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === skillhub_service.py ===
"""
SkillHub Skill Search and installation services

Pass skillhub CLI (npm package) Search and install skills.
Skill The actual storage is in the GitHub repository, and the CLI is responsible for downloading and decompressing it from GitHub.
Some skills are specific to SkillHub and are not on ClawHub, so you need to use the CLI.

Automatically detect and install on first use skillhub CLI (npm install -g skillhub). 

CLI Command:
- skillhub search "<query>" --json --limit <n>
- skillhub install <skill-id> --project --force

After installation the Skill is located in .claude/skills/<name>/, need to move to skills/<name>/
Then reuse _import_local_skill_to_db to import into MongoDB.
"""

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("webapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
CLAUDE_SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"

# CLI Automatic installation lock (prevents concurrent requests for repeated installations)
_cli_install_lock = asyncio.Lock()
_cli_checked = False  # Process Level Cache: CLI confirmed to be available


class SkillHubService:
    """SkillHub Skill Search and install services (via CLI child process)"""

    CLI_TIMEOUT = 60  # Search/install timeout seconds
    INSTALL_TIMEOUT = 120  # Install Skill package timeout seconds

    # =============================================================
    # CLI Automatic installation
    # =============================================================

    @classmethod
    async def _ensure_cli(cls) -> bool:
        """Make sure skillhub CLI is available, if not it will be installed automatically

        Returns:
            True False if the CLI is available, False if the installation fails
        """
        global _cli_checked
        if _cli_checked:
            return True

        async with _cli_install_lock:
            # double-check
            if _cli_checked:
                return True

            # 1. Check if it is installed
            if await cls._is_cli_available():
                _cli_checked = True
                return True

            # 2. Automatic installation
            logger.info("📦 skillhub CLI Not installed, installing automatically (npm install -g skillhub)...")
            ok = await cls._install_cli()
            if ok:
                _cli_checked = True
                logger.info("✅ skillhub CLI Installation successful")
            else:
                logger.error("❌ skillhub CLI Automatic installation failed")
            return ok

    @staticmethod
    async def _is_cli_available() -> bool:
        """Check if skillhub CLI is available"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "skillhub --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            return False
        except Exception:
            return False

    @staticmethod
    async def _install_cli() -> bool:
        """Install globally via npm skillhub CLI"""
        try:
            proc = await asyncio.create_subprocess_shell(
                "npm install -g skillhub",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
                return True
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            logger.error(f"npm install -g skillhub failed: {err[:300]}")
            return False
        except Exception as e:
            logger.error(f"npm install -g skillhub Abnormal: {e}")
            return False

    # =============================================================
    # public method
    # =============================================================

    @classmethod
    async def search_skills(cls, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search on SkillHub Skill

        call: skillhub search "<query>" --json --limit <n>
        """
        if not query.strip():
            return []

        # Make sure the CLI is available
        if not await cls._ensure_cli():
            logger.error("skillhub CLI Unavailable, unable to search")
            return []

        try:
            # Called in shell mode (skillhub on Windows is a .cmd file)
            cmd = f'skillhub search "{query}" --json --limit {limit}'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=cls.CLI_TIMEOUT)

            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace") if stderr else ""
                logger.warning(f"skillhub search failed (exit={proc.returncode}): {err[:200]}")
                return []

            data = json.loads(stdout.decode("utf-8"))
            raw_skills = data.get("skills", []) if isinstance(data, dict) else []

            # Standardized fields
            normalized = []
            for item in raw_skills:
                if not isinstance(item, dict):
                    continue
                skill_id = item.get("id", "")
                parts = skill_id.split("/")
                slug = parts[-1] if parts else skill_id
                owner = parts[0] if len(parts) >= 1 else ""

                normalized.append({
                    "slug": slug,
                    "skill_id": skill_id,
                    "display_name": item.get("name") or slug,
                    "summary": item.get("description") or "",
                    "version": "",
                    "owner_handle": owner,
                    "github_owner": item.get("githubOwner", ""),
                    "github_repo": item.get("githubRepo", ""),
                    "github_stars": item.get("githubStars", 0),
                    "download_count": item.get("downloadCount", 0),
                    "security_score": item.get("securityScore", 0),
                    "security_status": item.get("securityStatus") or "",
                    "ai_score": item.get("aiScore"),
                    "rating": item.get("rating", 0),
                    "is_verified": item.get("isVerified", False),
                    "canonical_url": f"https://skillhub.cn/skills/{slug}",
                })

            # Sort by download volume in descending order (CLI does not support --sort parameter, sort on Python side)
            normalized.sort(key=lambda x: x.get("download_count", 0), reverse=True)
            logger.info(f"📊 SkillHub Search results have been sorted in descending order by download volume (top: {normalized[0]['download_count'] if normalized else 0})")

            return normalized

        except asyncio.TimeoutError:
            logger.warning("skillhub search timeout")
            return []
        except Exception as e:
            logger.warning(f"skillhub search Abnormal: {e}")
            return []

    @classmethod
    async def install_skill(cls, skill_id: str) -> Dict[str, Any]:
        """Install Skill from SkillHub to local directory

        Process:
        1. call skillhub install <id> --project --force
        2. install to .claude/skills/<name>/
        3. move to skills/<name>/
        4. Verify that SKILL.md and scripts/ exist
        """
        skill_id = skill_id.strip()
        if not skill_id:
            return {"success": False, "message": "skill_id cannot be empty"}

        # Make sure the CLI is available
        if not await cls._ensure_cli():
            return {"success": False, "message": "skillhub CLI Automatic installation failed, please run manually: npm install -g skillhub"}

        # skill_id Format: "owner/repo/skill-name", Take the last paragraph as slug
        parts = skill_id.split("/")
        slug = parts[-1] if parts else skill_id

        # 1. Invoke CLI installation
        try:
            cmd = f'skillhub install "{skill_id}" --project --force'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=cls.INSTALL_TIMEOUT)

            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace") if stderr else ""
                return {"success": False, "message": f"skillhub install failed: {err[:300]}"}

            logger.info(f"✅ skillhub install success: {skill_id}")
        except asyncio.TimeoutError:
            return {"success": False, "message": f"安装超时（{cls.INSTALL_TIMEOUT}s）"}
        except Exception as e:
            return {"success": False, "message": f"安装异常: {e}"}

        # 2. Locate the installation directory (.claude/skills/<slug>/) 
        installed_dir = CLAUDE_SKILLS_DIR / slug
        if not installed_dir.exists():
            installed_dir = cls._find_installed_skill(slug)
            if installed_dir is None:
                return {
                    "success": False,
                    "message": f"CLI 安装完成但未在 {CLAUDE_SKILLS_DIR} 找到 Skill 目录",
                }

        # 3. move to skills/<slug>/
        target_dir = SKILLS_DIR / slug
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(installed_dir), str(target_dir))
        except Exception as e:
            return {"success": False, "message": f"Failed to move skill directory: {e}"}

        # 4. Verification SKILL.md
        if not (target_dir / "SKILL.md").exists():
            shutil.rmtree(target_dir, ignore_errors=True)
            return {"success": False, "message": "Skill Not found in package SKILL.md"}

        # 5. Verify scripts/ or root directory .py file
        # SkillHub There are two possible package structures:
        #   A) scripts/*.py (ClawHub standard)
        #   B) root directory *.py (Such as stock-monitor/data_source.py, monitor.py etc.)
        scripts_dir = target_dir / "scripts"
        has_scripts = False
        script_count = 0

        if scripts_dir.is_dir() and any(scripts_dir.iterdir()):
            has_scripts = True
            script_count = len([f for f in scripts_dir.iterdir() if f.suffix == ".py"])
        else:
            # Check if there is a .py file in the root directory
            root_py_files = [f for f in target_dir.iterdir()
                             if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"]
            if root_py_files:
                has_scripts = True
                script_count = len(root_py_files)
                logger.info(f"📦 Skill '{slug}' Root Python script detected: {[f.name for f in root_py_files]}")

        if not has_scripts:
            logger.info(f"📚 Skill '{slug}' is knowledge-based (no Python scripts), remains but marked as knowledge-based")

        # 6. Write source information
        origin_dir = target_dir / ".skillhub"
        origin_dir.mkdir(exist_ok=True)
        origin_info = {
            "source": "skillhub",
            "skill_id": skill_id,
            "slug": slug,
            "installed_at": cls._now_iso(),
        }
        (origin_dir / "origin.json").write_text(
            json.dumps(origin_info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        script_count = len([f for f in scripts_dir.iterdir() if f.suffix == ".py"]) if has_scripts else 0

        return {
            "success": True,
            "skill_name": slug,
            "skill_dir": str(target_dir),
            "version": "",
            "has_scripts": has_scripts,
            "scripts_count": script_count,
            "message": f"Skill '{slug}' 安装成功",
        }

    # =============================================================
    # internal method
    # =============================================================

    @staticmethod
    def _find_installed_skill(slug: str) -> Optional[Path]:
        """Find the installed Skill directory under .claude/skills/"""
        if not CLAUDE_SKILLS_DIR.exists():
            return None
        for item in CLAUDE_SKILLS_DIR.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                if item.name == slug or slug in item.name or item.name in slug:
                    return item
        # If no exact match is found, return to the first directory with SKILL.md
        for item in CLAUDE_SKILLS_DIR.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                return item
        return None

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

# === clawhub_skill_service.py ===
"""
ClawHub Skill Download and management services

Responsible for ClawHub (clawhub.ai) Download the complete Skill package (including scripts/) to the local directory,
And parse SKILL.md registered to MongoDB.

ClawHub API Documentation: https://docs.openclaw.ai/clawhub/api
- GET /api/v1/skills/{slug}          Get skill metadata
- GET /api/v1/search?q=...           Search Skill
- GET /api/v1/download?slug=&version=&tag=  Download the Skill ZIP package
- GET /api/v1/skills?limit=&cursor=&sort=   list Skill

slug Format: The unique identifier of the Skill, such as "ifind-repilot-finance-data-search"
"""

import io
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("webapi")

# ClawHub API Basics URL
CLAWHUB_BASE_URL = "https://clawhub.ai"

# Local Skill package storage root directory (skills/ under the project root directory)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"


class ClawHubSkillService:
    """ClawHub Skill Download and management services"""

    # Download timeout (seconds), Skill package may be larger
    DOWNLOAD_TIMEOUT = 60.0
    # API Request timeout
    API_TIMEOUT = 15.0
    # HTTP Client default headers
    DEFAULT_HEADERS = {
        "User-Agent": "TradingAgentsCN/3.0 (Skill Installer)",
        "Accept": "application/json",
    }

    # =============================================================
    # public method
    # =============================================================

    @classmethod
    async def search_skills(cls, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search on ClawHub Skill

        Args:
            query: Search keywords
            limit: Return maximum number (1-200)

        Returns:
            Skill List, each item contains slug/displayName/summary/version/ownerHandle, etc.
        """
        if not query.strip():
            return []
        limit = max(1, min(200, limit))
        url = f"{CLAWHUB_BASE_URL}/api/v1/search"
        params = {"q": query, "limit": limit, "nonSuspiciousOnly": "true"}

        try:
            async with httpx.AsyncClient(timeout=cls.API_TIMEOUT, headers=cls.DEFAULT_HEADERS) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(f"ClawHub Search failed: HTTP {resp.status_code}, {resp.text[:200]}")
                    return []
                data = resp.json()
                results = data.get("results", []) if isinstance(data, dict) else []
                # Standardized fields
                normalized = []
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    owner = item.get("owner") or {}
                    normalized.append({
                        "slug": item.get("slug", ""),
            "display_name": item.get("displayName") or item.get("slug", ""),
            "summary": item.get("summary") or "",
            "version": item.get("version") or "",
            "updated_at": item.get("updatedAt"),
                        "owner_handle": owner.get("handle", "") if isinstance(owner, dict) else "",
                        "owner_display_name": owner.get("displayName", "") if isinstance(owner, dict) else "",
                        "canonical_url": f"{CLAWHUB_BASE_URL}/{owner.get('handle', '')}/{item.get('slug', '')}"
                                         if isinstance(owner, dict) and owner.get("handle") else "",
                        "score": item.get("score", 0),
                    })
                return normalized
        except httpx.TimeoutException:
            logger.warning("ClawHub 搜索超时")
            return []
        except Exception as e:
            logger.warning(f"ClawHub Search exception: {e}")
            return []

    @classmethod
    async def get_skill_info(cls, slug: str) -> Optional[Dict[str, Any]]:
        """Get ClawHub Skill metadata

        Args:
            slug: Skill logo, such as "ifind-repilot-finance-data-search"

        Returns:
            Skill Metadata dictionary, returned on failure None
        """
        url = f"{CLAWHUB_BASE_URL}/api/v1/skills/{slug}"
        try:
            async with httpx.AsyncClient(timeout=cls.API_TIMEOUT, headers=cls.DEFAULT_HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 404:
                    logger.info(f"ClawHub Skill does not exist: {slug}")
                    return None
                if resp.status_code != 200:
                    logger.warning(f"ClawHub Failed to obtain skill metadata: HTTP {resp.status_code}")
                    return None
                return resp.json()
        except Exception as e:
            logger.warning(f"ClawHub Get Skill metadata exception: {e}")
            return None

    @classmethod
    async def install_skill(
        cls,
        slug: str,
        version: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Install Skill from ClawHub to local directory

        Process:
        1. Call /api/v1/download to download the ZIP package
        2. Unzip to skills/<slug>/ Directory
        3. Verify that SKILL.md exists
        4. Verify whether it is a script-type Skill (including scripts/ directory)
        5. Write .clawhub/origin.json to record source information

        Args:
            slug: Skill logo
            version: Specify version (optional, latest by default)
            tag: version label (optional, e.g. "latest") 

        Returns:
            {
                "success": bool,
                "skill_name": str,
                "skill_dir": str,
                "version": str,
                "has_scripts": bool,
                "message": str
            }
        """
        slug = slug.strip().lstrip("@")
        # Support owner/slug format, take the last paragraph as slug
        if "/" in slug:
            slug = slug.split("/")[-1]

        if not slug:
            return {"success": False, "message": "slug 不能为空"}

        # 1. Download ZIP package
        zip_bytes, resolved_version = await cls._download_zip(slug, version=version, tag=tag)
        if zip_bytes is None:
            return {
                "success": False,
                "message": f"下载 Skill '{slug}' 失败，请检查 slug 是否正确或网络连接",
            }

        # 2. Unzip to skills/<slug>/ Directory
        skill_dir = SKILLS_DIR / slug
        # If it already exists, clear it first (reinstall)
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)
        skill_dir.mkdir(parents=True, exist_ok=True)

        try:
            extracted_files = cls._extract_zip(zip_bytes, skill_dir)
        except Exception as e:
            logger.error(f"Failed to decompress Skill ZIP: {e}", exc_info=True)
            return {"success": False, "message": f"解压失败: {e}"}

        # 3. Verify that SKILL.md exists
        # ZIP It may contain a layer of root directories, and you need to locate the actual Skill root directory.
        skill_root = cls._locate_skill_root(skill_dir)
        if skill_root is None:
            return {
                "success": False,
                "message": "Skill SKILL.md file not found in package",
                "skill_dir": str(skill_dir),
            }

        # If the Skill root directory is not skill_dir itself, rename
        if skill_root != skill_dir:
            # Move the skill_root content to skill_dir
            import shutil
            temp_name = skill_dir.parent / f"{slug}.tmp_{Path(__file__).stem}"
            if temp_name.exists():
                shutil.rmtree(temp_name, ignore_errors=True)
            shutil.move(str(skill_root), str(temp_name))
            shutil.rmtree(str(skill_dir), ignore_errors=True)
            shutil.move(str(temp_name), str(skill_dir))

        # 4. Verify whether it is a script-type Skill (including scripts/ directory or root directory .py file)
        scripts_dir = skill_dir / "scripts"
        has_scripts = False
        if scripts_dir.is_dir() and any(scripts_dir.iterdir()):
            has_scripts = True
        else:
            # Compatible with SkillHub package structure: put .py files directly in the root directory (such as stock-monitor/monitor.py)
            root_py_files = [f for f in skill_dir.iterdir()
                             if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"]
            if root_py_files:
                has_scripts = True
                logger.info(f"📦 Skill '{slug}' Root Python script detected: {[f.name for f in root_py_files]}")

        if not has_scripts:
            # Knowledge-based Skill, reject import based on user decision
            logger.info(f"📚 Skill '{slug}' It is knowledge type (no scripts/ directory) and refuses to be imported.")
            # Clean downloaded directory
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)
            return {
                "success": False,
                "message": (
                    f"Skill '{slug}' It is a knowledge-based Skill (no scripts/ directory), and this project does not support import."
                    "This project only supports Python script skills that contain executable scripts."
                ),
                "skill_type": "knowledge",
            }

        # 5. Write .clawhub/origin.json to record source information
        origin_dir = skill_dir / ".clawhub"
        origin_dir.mkdir(exist_ok=True)
        import json
        origin_info = {
            "source": "clawhub",
            "slug": slug,
            "version": resolved_version or "",
            "installed_at": cls._now_iso(),
            "canonical_url": f"{CLAWHUB_BASE_URL}/skills/{slug}",
        }
        (origin_dir / "origin.json").write_text(
            json.dumps(origin_info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(f"✅ ClawHub Skill '{slug}' Installation successful, directory: {skill_dir}")

        # Count the number of scripts (compatible with both package structures)
        if scripts_dir.is_dir():
            script_count = len([f for f in scripts_dir.iterdir() if f.suffix == ".py"])
        else:
            script_count = len([f for f in skill_dir.iterdir()
                                if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"])

        return {
            "success": True,
            "skill_name": slug,
            "skill_dir": str(skill_dir),
            "version": resolved_version or "",
            "has_scripts": True,
            "scripts_count": script_count,
            "extracted_files_count": len(extracted_files),
            "message": f"Skill '{slug}' 安装成功",
        }

    @classmethod
    def list_local_skills(cls) -> List[Dict[str, Any]]:
        """List locally installed ClawHub Skill packages

        Returns:
            Local Skill list, each item includes name/dir/has_scripts/origin, etc.
        """
        if not SKILLS_DIR.exists():
            return []

        skills = []
        for item in SKILLS_DIR.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith(".") or item.name == ".gitkeep":
                continue
            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                continue

            scripts_dir = item / "scripts"
            has_scripts = scripts_dir.is_dir() and any(scripts_dir.iterdir()) if scripts_dir.exists() else False

            # read origin.json
            origin = {}
            origin_path = item / ".clawhub" / "origin.json"
            if origin_path.exists():
                try:
                    import json
                    origin = json.loads(origin_path.read_text(encoding="utf-8"))
                except Exception:
                    origin = {}

            skills.append({
                "name": item.name,
                "skill_dir": str(item),
                "has_scripts": has_scripts,
                "has_skill_md": True,
                "source": origin.get("source", "local"),
                "version": origin.get("version", ""),
                "installed_at": origin.get("installed_at", ""),
                "canonical_url": origin.get("canonical_url", ""),
            })
        return skills

    @classmethod
    def uninstall_local_skill(cls, slug: str) -> Dict[str, Any]:
        """Uninstall the local Skill package (delete the directory)

        Args:
            slug: Skill logo

        Returns:
            {success, message}
        """
        slug = slug.strip().lstrip("@")
        if "/" in slug:
            slug = slug.split("/")[-1]

        skill_dir = SKILLS_DIR / slug
        if not skill_dir.exists():
            return {"success": False, "message": f"本地 Skill '{slug}' 不存在"}

        try:
            import shutil
            shutil.rmtree(skill_dir)
            logger.info(f"✅ Uninstalled local Skill: {slug}")
            return {"success": True, "message": f"Skill '{slug}' 已卸载"}
        except Exception as e:
            return {"success": False, "message": f"卸载失败: {e}"}

    # =============================================================
    # internal method
    # =============================================================

    @classmethod
    async def _download_zip(
        cls,
        slug: str,
        version: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> tuple[Optional[bytes], Optional[str]]:
        """Download the Skill ZIP package from ClawHub

        API: GET /api/v1/download?slug=&version=&tag=
        Anonymous access, rate limiting 1200/min per IP

        Returns:
            (zip_bytes, resolved_version), Return on failure (None, None)
        """
        url = f"{CLAWHUB_BASE_URL}/api/v1/download"
        params = {"slug": slug}
        if version:
            params["version"] = version
        if tag:
            params["tag"] = tag

        try:
            async with httpx.AsyncClient(
                timeout=cls.DOWNLOAD_TIMEOUT,
                headers={**cls.DEFAULT_HEADERS, "Accept": "application/zip"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 404:
                    logger.warning(f"ClawHub Skill '{slug}' 不存在或不可下载")
                    return None, None
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "?")
                    logger.warning(f"ClawHub 下载被限流，请等待 {retry_after} 秒后重试")
                    return None, None
                if resp.status_code != 200:
                    logger.warning(f"ClawHub Download failed: HTTP {resp.status_code}, {resp.text[:200]}")
                    return None, None

                # Parse the version from the response (if any)
                resolved_version = (
                    resp.headers.get("X-Skill-Version")
                    or resp.headers.get("x-skill-version")
                    or version
                    or ""
                )

                content_type = resp.headers.get("content-type", "")
                if "zip" not in content_type and not resp.content[:4] == b"PK\x03\x04":
                    logger.warning(f"ClawHub What is returned is not a ZIP file: content-type={content_type}")
                    return None, None

                return resp.content, resolved_version
        except httpx.TimeoutException:
            logger.warning(f"ClawHub Download timeout: {slug}")
            return None, None
        except Exception as e:
            logger.warning(f"ClawHub Download exception: {e}")
            return None, None

    @staticmethod
    def _extract_zip(zip_bytes: bytes, target_dir: Path) -> List[str]:
        """Unzip the ZIP to the target directory

        Args:
            zip_bytes: ZIP file byte data
            target_dir: target directory

        Returns:
            Extracted file list
        """
        extracted = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # Security check: deny entries containing .. or absolute paths
            for member in zf.namelist():
                if member.startswith("/") or ".." in Path(member).parts:
                    raise ValueError(f"ZIP Contains unsafe paths: {member}")

            zf.extractall(target_dir)
            extracted = zf.namelist()
        return extracted

    @staticmethod
    def _locate_skill_root(base_dir: Path) -> Optional[Path]:
        """Locate the actual directory containing SKILL.md

        ZIP Packages may:
        1. Directly include SKILL.md (the root directory is the Skill root)
        2. Contains a layer of subdirectories, and in the subdirectory there are SKILL.md

        Returns:
            Skill Root directory path, return if not found None
        """
        # Case 1:base_dir/SKILL.md
        if (base_dir / "SKILL.md").exists():
            return base_dir

        # Case 2:base_dir/<subdir>/SKILL.md
        for item in base_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                return item

        return None

    @staticmethod
    def _now_iso() -> str:
        """Get the ISO format string of the current time"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

# === skill_credential_service.py ===
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
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

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

# === skill_gap_service.py ===
"""
Skill Gap Management Services

Responsible for:
- Persist tool gap reports to the MongoDB skill_gap_reports collection
- push WebSocket + Notification center notification
- Provide list/details/ignore/resolve CRUD
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.database import get_mongo_db
from app.models.notification import NotificationCreate
from app.utils.timezone import now_tz

logger = logging.getLogger("skill_gap_service")

COLLECTION = "skill_gap_reports"


class SkillGapService:
    """Skill 缺口管理服务"""

    # ------------------------------------------------------------------
    # write operation
    # ------------------------------------------------------------------

    async def create_report(
        self,
        gap_type: str,
        tool_name: str,
        agent_id: str,
        error: str = "",
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "admin",
    ) -> str:
        """创建缺口报告并推送通知"""
        db = get_mongo_db()
        report_id = f"gap_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now = now_tz()

        # Extract workflow/task information from context
        workflow_id = context.get("workflow_id", "") if context else ""
        workflow_name = context.get("workflow_name", "") if context else ""
        task_id = context.get("task_id", "") if context else ""
        node_id = context.get("node_id", "") if context else ""

        doc = {
            "report_id": report_id,
            "user_id": user_id,
            "status": "pending",
            "source": {
                "agent_id": agent_id,
                "agent_name": context.get("agent_name", agent_id) if context else agent_id,
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "task_id": task_id,
                "node_id": node_id,
            },
            "gap": {
                "type": gap_type,
                "tool_name": tool_name,
                "error_message": error,
                "tool_call_args": context.get("tool_call_args", {}) if context else {},
                "context_summary": context.get("context_summary", "") if context else "",
            },
            "analysis": None,
            "created_at": now,
            "updated_at": now,
            "resolved_at": None,
            "expires_at": now + timedelta(days=7),
        }

        await db[COLLECTION].insert_one(doc)
        logger.info(f"[SkillGapService] Gap report saved: {report_id}")

        # push notification
        await self._send_notification(user_id, report_id, tool_name, agent_id, gap_type)
        return report_id

    async def _send_notification(
        self, user_id: str, report_id: str, tool_name: str, agent_id: str, gap_type: str
    ) -> None:
        """Push notifications via NotificationsService"""
        try:
            from app.services.notifications_service import get_notifications_service
            svc = get_notifications_service()
            gap_label = "工具未找到" if gap_type == "tool_not_found" else "工具执行失败"
            await svc.create_and_publish(
                payload=NotificationCreate(
                    user_id=user_id,
                    type="alert",
                    title=f"🔧 发现工具缺口 [{gap_label}]",
                    content=f"Agent {agent_id} 需要工具 `{tool_name}`，但该工具{gap_label}。点击查看详情并决定是否创建 Skill。",
                    link=f"/workflow/skill-gaps/{report_id}",
                    source="skill_gap_detector",
                    severity="warning",
                    metadata={"report_id": report_id, "tool_name": tool_name},
                )
            )
        except Exception as e:
            logger.warning(f"[SkillGapService] Push notification failed (ignored): {e}")

    # ------------------------------------------------------------------
    # Read operation
    # ------------------------------------------------------------------

    async def list_gaps(
        self, user_id: str, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> Dict[str, Any]:
        db = get_mongo_db()
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status
        total = await db[COLLECTION].count_documents(query)
        items = []
        async for doc in (
            db[COLLECTION].find(query).sort("created_at", -1)
            .skip((page - 1) * page_size).limit(page_size)
        ):
            doc["_id"] = str(doc["_id"])
            items.append(doc)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def get_gap(self, report_id: str) -> Optional[Dict[str, Any]]:
        db = get_mongo_db()
        doc = await db[COLLECTION].find_one({"report_id": report_id})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def dismiss_gap(self, report_id: str, user_id: str) -> bool:
        db = get_mongo_db()
        now = now_tz()
        res = await db[COLLECTION].find_one_and_update(
            {"report_id": report_id, "user_id": user_id},
            {"$set": {"status": "dismissed", "updated_at": now}},
        )
        if res:
            # Notification detector records ignored
            tool_name = res.get("gap", {}).get("tool_name", "")
            if tool_name:
                from core.tools.external.skill_gap_detector import SkillGapDetector
                SkillGapDetector.mark_dismissed(tool_name)
        return res is not None

    async def resolve_gap(self, report_id: str, user_id: str, skill_id: str = "") -> bool:
        db = get_mongo_db()
        now = now_tz()
        update = {"$set": {"status": "resolved", "updated_at": now, "resolved_at": now}}
        if skill_id:
            update["$set"]["analysis.resolved_skill_id"] = skill_id
        res = await db[COLLECTION].update_one(
            {"report_id": report_id, "user_id": user_id}, update
        )
        return res.modified_count > 0

    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        db = get_mongo_db()
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        status_counts: Dict[str, int] = {}
        async for doc in db[COLLECTION].aggregate(pipeline):
            status_counts[doc["_id"]] = doc["count"]

        pipeline2 = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$gap.type", "count": {"$sum": 1}}},
        ]
        type_counts: Dict[str, int] = {}
        async for doc in db[COLLECTION].aggregate(pipeline2):
            type_counts[doc["_id"]] = doc["count"]

        return {
            "by_status": status_counts,
            "by_type": type_counts,
            "total": sum(status_counts.values()),
        }


_skill_gap_service: Optional[SkillGapService] = None


def get_skill_gap_service() -> SkillGapService:
    global _skill_gap_service
    if _skill_gap_service is None:
        _skill_gap_service = SkillGapService()
    return _skill_gap_service


# === skill_generation_service.py ===
"""
Skill Build service — business logic layer

Encapsulates each module in core/tools/external/ to handle MongoDB persistence and asynchronous orchestration.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.llm import Message
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

from core.tools.external import (
    ConversationRound,
    DefaultReconnaissanceController,
    ExpectedOutput,
    ImplementationFactReport,
    IterationController,
    RequirementAnalyzer,
    SkillCreationSession,
    SkillHandoffContext,
    SkillParameter,
    SkillSpec,
    SessionStatus,
    PipelineResult,
)
from core.tools.external.requirement_analyzer import classify_requirement_mode

logger = logging.getLogger("webapi")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_CODE_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "code" / "skill"

# MongoDB Collection name
SESSION_COLLECTION = "skill_creation_sessions"
SKILL_COLLECTION = "external_skills"
# Consistent with iteration_controller.MAX_ITERATIONS; if you need to adjust it, please modify it simultaneously.
SKILL_PIPELINE_MAX_ITERATIONS = 10
SKILL_GENERATION_AGENTIC_ENABLED = os.getenv("SKILL_GENERATION_AGENTIC_ENABLED", "true").lower() not in {"0", "false", "no", "off"}


class SkillGenerationService:
    """
    Skill Build service

    Provides complete business logic for demand communication, code generation, and skill management.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        reasoning_llm_client=None,
        coding_llm_client=None,
        quick_llm_client=None,
        provider: str = "deepseek",
        model: Optional[str] = None,
    ):
        """
        Args:
            db: MongoDB database
            reasoning_llm_client: For requirements analysis (large model for deep reasoning), specification generation and other heavy reasoning steps
            coding_llm_client: For code generation (large programming model), code generation and Judge scoring
            quick_llm_client: Used for demand dialogue (quick model), clarity/boundary/multi-round reply and other low-latency links
            provider, model: Used for fallback, used when all the above clients are empty.
        """
        self._db = db
        self._provider = provider
        self._model = model
        self._analyzer = RequirementAnalyzer(
            llm_client=reasoning_llm_client,
            provider=provider,
            model=model,
            quick_llm_client=quick_llm_client,
        )
        self._reconnaissance = DefaultReconnaissanceController(
            llm_client=coding_llm_client, provider=provider, model=model,
            analyzer=self._analyzer,
        )
        self._controller = IterationController(
            llm_client=coding_llm_client,
            provider=provider,
            model=model,
            max_iterations=SKILL_PIPELINE_MAX_ITERATIONS,
            reconnaissance_controller=self._reconnaissance,
            quick_llm_client=quick_llm_client,
        )

    def _build_session_recommendations(
        self,
        *,
        spec: Optional[SkillSpec] = None,
        session: Optional[SkillCreationSession] = None,
        fact_report: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if spec is not None:
            return self._analyzer.build_recommendations(spec=spec, fact_report=fact_report)
        conversation = ""
        if session is not None:
            conversation = self._analyzer._collect_conversation(session)
        return self._analyzer.build_recommendations(conversation=conversation, fact_report=fact_report)

    @staticmethod
    def _dedupe_text_list(items: Any) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        if not isinstance(items, list):
            return result
        for item in items:
            value = str(item or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    async def _search_capability_index(self, spec: SkillSpec) -> list:
        """Search the capabilities index (Qdrant vector library) for tools related to spec semantics.

        using spec display_name + description Construct query, recall top_k=12 related tools.
        If the capability index service is unavailable, an empty list is returned (does not block the process).
        """
        try:
            # Construct semantic query text
            query_parts = [
                spec.display_name or "",
                spec.description or "",
                spec.category or "",
            ]
            # Add parameter description to make the search more accurate
            for param in (spec.parameters or []):
                desc = getattr(param, "description", None) or (param.get("description") if isinstance(param, dict) else None)
                if desc:
                    query_parts.append(desc)
            query = " ".join(p for p in query_parts if p).strip()
            if not query:
                return []

            svc = CapabilityIndexService(self._db)
            hits = await svc.search_capabilities(
                query=query,
                top_k=12,
                bindable_only=True,
                source_types=["builtin_tool", "mcp_tool"],
            )
            logger.info(
                "🧭 Capability Index Vector Search: query='%s...' → %d hit",
                query[:40],
                len(hits),
            )
            return hits
        except Exception as exc:
            logger.warning("⚠️ Capability index search failed (does not block the process): %s", exc)
            return []

    @staticmethod
    def _infer_skill_role_metadata(spec: SkillSpec, session: SkillCreationSession) -> Dict[str, Any]:
        text = " ".join([
            spec.tool_id or "",
            spec.display_name or "",
            spec.description or "",
            spec.category or "",
            spec.data_source or "",
            " ".join(spec.constraints or []),
            " ".join(spec.expected_output.fields or []),
            spec.expected_output.description or "",
            str((spec.metadata or {}).get("handoff_context_summary") or ""),
            str((spec.metadata or {}).get("generation_context") or ""),
        ]).lower()
        handoff = session.handoff_context
        source = str(getattr(handoff, "source", "") or "") if handoff is not None else ""
        source_capability = str(getattr(handoff, "target_capability", "") or "") if handoff is not None else ""
        if source_capability:
            text += " " + source_capability.lower()

        capability_tags: List[str] = []
        tag_patterns = [
            (r"cash flow|cash\s*flow|cashflow|ocf|fcf|cfo|free cash flow", "cashflow_quality"),
            (r"financial health|debt repayment|Liabilities|debt|solvency|liquidity|current_ratio|interest_coverage", "financial_health"),
            (r"risk|risk|early warning|Abnormal|goodwill|receivable|goodwill|receivable", "financial_risk"),
            (r"Valuation|valuation|pe|pb|percentile|Quantile|dcf|peg", "valuation"),
            (r"Trend|trend|series|history|many years|time_series", "historical_series"),
            (r"quality|quality|roe|roa|roic|piotroski|altman|beneish", "quality_factor"),
            (r"technology|technical|macd|rsi|kdj|ma20", "technical"),
            (r"News|news|public opinion|sentiment", "news_sentiment"),
        ]
        for pattern, tag in tag_patterns:
            if re.search(pattern, text):
                capability_tags.append(tag)

        output_fields = [str(item or "").lower() for item in (spec.expected_output.fields or [])]
        output_type = str(spec.expected_output.type or "").lower()
        if output_type in {"dict", "list[dict]", "list"} and output_fields:
            if any(re.search(r"ratio|rate|score|metrics?|indicator|Ratio|score|flag", field) for field in output_fields):
                output_shape = "structured_metrics"
            else:
                output_shape = "structured_records"
        elif "markdown" in text or "报告" in text or "report" in text:
            output_shape = "report"
        else:
            output_shape = "structured_records" if output_fields else "text"

        preferred_for: List[str] = []
        if "financial_risk" in capability_tags:
            preferred_for.append("financial_risk_signal_detection")
        if "cashflow_quality" in capability_tags:
            preferred_for.append("cashflow_quality_analysis")
        if "financial_health" in capability_tags:
            preferred_for.append("financial_health_analysis")
        if "valuation" in capability_tags:
            preferred_for.append("valuation_analysis")
        if "historical_series" in capability_tags:
            preferred_for.append("historical_trend_analysis")

        if source in {"agent_studio_gap", "agent_workshop_gap"}:
            tool_role_hint = "specialized"
        elif output_shape == "report":
            tool_role_hint = "supporting"
        elif len(preferred_for) == 1:
            tool_role_hint = "specialized"
        elif preferred_for:
            tool_role_hint = "specialized"
        else:
            tool_role_hint = "supporting"

        not_replacement_for: List[str] = []
        if tool_role_hint in {"supporting", "generic", "fallback"}:
            not_replacement_for.extend(preferred_for)
        if output_shape == "report":
            not_replacement_for.extend(["structured_metric_calculation", "primary_capability"])

        return {
            "capability_tags": SkillGenerationService._dedupe_text_list(capability_tags),
            "tool_role_hint": tool_role_hint,
            "output_shape": output_shape,
            "preferred_for": SkillGenerationService._dedupe_text_list(preferred_for),
            "not_replacement_for": SkillGenerationService._dedupe_text_list(not_replacement_for),
        }

    @staticmethod
    def _get_last_generated_code(pipeline_result: Optional[PipelineResult]) -> str:
        if not pipeline_result:
            return ""
        if pipeline_result.final_code:
            return pipeline_result.final_code
        for iteration in reversed(pipeline_result.iterations or []):
            generated = iteration.generated_code
            if generated and generated.code:
                return generated.code
        return ""

    @staticmethod
    def _persist_generated_code_snapshots(
        *,
        session_id: str,
        tool_id: str,
        attempt_number: int,
        pipeline_result: Optional[PipelineResult],
    ) -> List[Path]:
        if not pipeline_result:
            return []

        session_dir = SKILL_CODE_SNAPSHOT_DIR / tool_id / session_id
        attempt_dir = session_dir / f"attempt_{attempt_number:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        written_files: List[Path] = []

        for iteration in pipeline_result.iterations or []:
            generated = iteration.generated_code
            code = (generated.code if generated and generated.code else "").strip()
            if not code:
                continue

            round_path = attempt_dir / f"round_{iteration.round_number:02d}.py"
            round_path.write_text(code + "\n", encoding="utf-8")
            written_files.append(round_path)

        latest_code = SkillGenerationService._get_last_generated_code(pipeline_result).strip()
        if latest_code:
            attempt_latest_path = attempt_dir / "latest.py"
            attempt_latest_path.write_text(latest_code + "\n", encoding="utf-8")
            written_files.append(attempt_latest_path)

            session_latest_path = session_dir / "latest.py"
            session_latest_path.write_text(latest_code + "\n", encoding="utf-8")
            written_files.append(session_latest_path)

        return written_files

    @staticmethod
    def _summarize_text(
        text: Any,
        *,
        max_chars: int,
        head_chars: Optional[int] = None,
        separator: str = "\n... (Omit the middle) ...\n",
    ) -> str:
        """Long text summaries keep the beginning and the end by default to avoid misjudgment caused by only seeing the first half."""
        if text is None:
            return ""

        text_str = str(text)
        if len(text_str) <= max_chars:
            return text_str

        if head_chars is None:
            head_chars = max_chars // 2

        head_chars = max(1, min(head_chars, max_chars - len(separator) - 1))
        tail_chars = max_chars - head_chars - len(separator)
        if tail_chars <= 0:
            return text_str[:max_chars]

        return text_str[:head_chars] + separator + text_str[-tail_chars:]

    @staticmethod
    def _format_single_pipeline(
        pipeline_result: PipelineResult,
        label: str = "",
        compact: bool = False,
    ) -> List[str]:
        """
        Format single-shot pipeline results into a structured list of text lines.

        Args:
            compact: True When only retaining root cause analysis and scoring, omit stdout/stderr/feedback
                     Equally large volume field, used to compress historical pipelines.
        """
        parts: List[str] = []
        if label:
            parts.append(f"\n{'='*20} {label} {'='*20}")
        if pipeline_result.error:
            parts.append(f"Final conclusion:{pipeline_result.error}")

        for iteration in pipeline_result.iterations or []:
            parts.append(f"\n[第{iteration.round_number}轮 | 决策={iteration.decision or 'UNKNOWN'}]")

            if iteration.validation and iteration.validation.errors:
                parts.append("Static validation issues:")
                parts.extend(f"- {item}" for item in iteration.validation.errors[:3])

            if iteration.sandbox and not iteration.sandbox.success:
                parts.append(f"Sandbox execution failed:{iteration.sandbox.error or 'unknown error'}")

            if not compact and iteration.sandbox and iteration.sandbox.success and iteration.sandbox.output is not None:
                import json as _json
                try:
                    out_str = SkillGenerationService._summarize_text(
                        _json.dumps(iteration.sandbox.output, ensure_ascii=False, default=str),
                        max_chars=1200,
                        head_chars=700,
                    )
                except Exception:
                    out_str = SkillGenerationService._summarize_text(
                        iteration.sandbox.output,
                        max_chars=1200,
                        head_chars=700,
                    )
                parts.append(f"Sandbox return value (summary):{out_str}")

            if iteration.eval_score:
                parts.append(
                    "Assessment score:"
                    f"total={iteration.eval_score.total}, "
                    f"executability={iteration.eval_score.executability}, "
                    f"authenticity={iteration.eval_score.authenticity}, "
                    f"completeness={iteration.eval_score.completeness}, "
                    f"relevance={iteration.eval_score.relevance}, "
                    f"format_quality={iteration.eval_score.format_quality}"
                )

            if iteration.reflection and iteration.reflection.root_cause:
                parts.append(f"Root cause analysis:{iteration.reflection.root_cause}")
                if iteration.reflection.fix_plan:
                    parts.append("Repair plan:" + " → ".join(iteration.reflection.fix_plan[:5]))

            if not compact and iteration.feedback:
                feedback_excerpt = SkillGenerationService._summarize_text(
                    iteration.feedback,
                    max_chars=1200,
                    head_chars=700,
                )
                parts.append(f"System feedback (summary):{feedback_excerpt}")

        return parts

    @staticmethod
    def _extract_lessons(results: List[PipelineResult]) -> List[str]:
        """Key lessons for extracting duplicates from pipeline result lists."""
        lessons: List[str] = []
        for pr in results:
            for it in pr.iterations or []:
                if it.reflection and it.reflection.root_cause:
                    lessons.append(it.reflection.root_cause)
        return list(dict.fromkeys(lessons))[:15]

    @staticmethod
    def _build_pipeline_failure_feedback(
        pipeline_result: Optional[PipelineResult],
        user_feedback: str = "",
    ) -> str:
        if not pipeline_result:
            return user_feedback.strip()

        parts: List[str] = ["=== Last round of pipeline failure information ==="]
        parts.extend(
            SkillGenerationService._format_single_pipeline(pipeline_result, compact=False)
        )

        if user_feedback.strip():
            parts.append(f"\n=== User s additional correction comments ===\n{user_feedback.strip()}")

        return "\n".join(parts)

    # Token budget for experience feedback (press 1 Chinese character ≈ 2 token estimate,8K token ≈ 4K characters)
    _EXPERIENCE_CHAR_BUDGET = 6000

    @staticmethod
    def _build_accumulated_experience(
        pipeline_history: List[PipelineResult],
        current_pipeline: Optional[PipelineResult],
        user_feedback: str = "",
    ) -> str:
        """
        Build cumulative experience feedback — Progressive compression strategy:

        1. Most recent pipeline: full details (stdout/return value/feedback)
        2. Older pipeline: only root cause analysis and scoring (compact mode)
        3. Summary of all lessons learned with deduplication
        4. If still over budget, start cropping from oldest history
        """
        history = list(pipeline_history or [])
        all_results = list(history)
        if current_pipeline is not None:
            all_results.append(current_pipeline)

        if not all_results:
            return user_feedback.strip()

        budget = SkillGenerationService._EXPERIENCE_CHAR_BUDGET
        parts: List[str] = [
            f"=== 累积生成经验（共 {len(all_results)} 次尝试）===",
            "Please learn from the lessons of history and avoid making the same mistakes again.\n",
        ]

        # ---- Summary of key lessons learned (always retained, highest priority)----
        lessons = SkillGenerationService._extract_lessons(all_results)
        if lessons:
            parts.append(f"=== 关键教训总结（{len(lessons)} 条，必须遵守）===")
            for i, lesson in enumerate(lessons, 1):
                parts.append(f"{i}. {lesson}")
            parts.append("")

        # ---- Most recent pipeline: full details ----
        latest = all_results[-1]
        success_label = "✅ 成功" if latest.success else "❌ 失败"
        latest_label = f"最近一次尝试（第 {len(all_results)} 次, {latest.total_rounds} 轮, {latest.total_time}s, {success_label}）"
        latest_lines = SkillGenerationService._format_single_pipeline(latest, latest_label, compact=False)
        parts.extend(latest_lines)

        # ---- Earlier pipeline: compact mode, filling from latest to earliest ----
        older = all_results[:-1]
        if older:
            parts.append(f"\n=== 更早的 {len(older)} 次尝试（摘要）===")

            current_len = sum(len(p) for p in parts)
            remaining = budget - current_len - 300  # Reserve tail space

            included = 0
            for pr in reversed(older):
                idx = older.index(pr) + 1
                s_label = "✅" if pr.success else "❌"
                pr_label = f"第 {idx} 次（{pr.total_rounds} 轮, {s_label}）"
                pr_lines = SkillGenerationService._format_single_pipeline(pr, pr_label, compact=True)
                block = "\n".join(pr_lines)
                if current_len + len(block) > remaining and included > 0:
                    parts.append(f"（更早的 {len(older) - included} 次尝试因篇幅省略，教训已汇总在上方）")
                    break
                parts.extend(pr_lines)
                current_len += len(block)
                included += 1

        if user_feedback.strip():
            parts.append(f"\n=== Users additional comments in this round ===\n{user_feedback.strip()}")

        parts.append("\n=== 要求 ===")
        parts.append("Please combine the above lessons to avoid repeating previous mistakes, make targeted repairs, and generate high-quality code.")

        return "\n".join(parts)

    @staticmethod
    def _build_repair_plan_fallback(
        spec: SkillSpec,
        feedback: str,
        pipeline_feedback: str,
    ) -> str:
        return "\n".join([
            "## 我理解到的问题",
            f"- The current goal of Skill is still:{spec.description}",
            f"- The new issues you highlighted are:{feedback.strip() or 'Please correct the failure message'}",
            "- I will give priority to fixing the deterministic errors that have been exposed in the static verification, sandbox execution and scoring phases, and will not change the confirmed requirement boundaries.",
            "",
            "## 修正计划",
            "1. First, locate the root cause of the failure based on the previous round of failure information, and prioritize the elimination of problems that block execution.",
            "2. Preserve existing skill specifications and target outputs to avoid extending the revision process into new requirements.",
            "3. Directly modify based on the previous round of code instead of regenerating it from scratch.",
            "4. Explicitly return error / invalid in scenarios where key inputs or key data are missing, to avoid using forged default values to continue output.",
            "5. After correction, it re-passed static verification, sandbox execution and quality assessment.",
            "",
            "## Important things to check when regenerating",
            pipeline_feedback.strip() or "- Repairs are made one by one, focusing on static verification, sandboxing and evaluation errors in the previous round of failed sessions.",
            "",
            "If there is no deviation from this plan, please confirm and let me regenerate according to this plan.",
        ])

    def _generate_repair_plan_message(
        self,
        session: SkillCreationSession,
        feedback: str,
    ) -> Tuple[str, Optional[Any]]:
        """
        Generate correction plan messages.

        Returns:
            (ai_message, llm_response) — llm_response May be None (no specification or fallback scheme).
            llm_response Used by asynchronous callers to record tokens to avoid calling asynchronous methods in a synchronous context.
        """
        spec = session.spec
        if not spec:
            return "There are no Skill specifications available for the current session and a remediation plan cannot be generated.", None

        accumulated_exp = self._build_accumulated_experience(
            pipeline_history=session.pipeline_history,
            current_pipeline=session.pipeline_result,
            user_feedback=feedback,
        )
        pipeline_feedback = self._build_pipeline_failure_feedback(
            session.pipeline_result,
            feedback,
        )
        last_code = self._get_last_generated_code(session.pipeline_result)
        code_excerpt = self._summarize_text(
            last_code,
            max_chars=12000,
            head_chars=7000,
        )
        attempt_count = len(session.pipeline_history) + (1 if session.pipeline_result else 0)
        prompt = f"""
你现在是 Skill 生成失败后的修正协作者。该 Skill 已经经过 {attempt_count} 次生成尝试，均未达标。
先不要输出代码，而是先向用户说明：
1. 从所有历史尝试中你总结出的关键问题是什么
2. 你准备怎么修（避免重复之前犯过的错误）
3. 重新生成时会重点检查什么

请严格遵守：
- 不要重新定义需求，不要扩展到新的功能范围
- 不要输出完整代码
- 不要承诺无法验证的内容
- 用中文回答
- 输出结构固定为：
  ## 历史尝试中的关键问题
  ## 修正计划
  ## 重新生成时的重点检查项

=== 当前 Skill 规格 ===
tool_id: {spec.tool_id}
display_name: {spec.display_name}
description: {spec.description}
category: {spec.category}
data_source: {spec.data_source}
test_input: {spec.test_input}

=== 累积经验（共 {attempt_count} 次尝试）===
{accumulated_exp}

=== 最近一次生成的代码（摘要，保留首尾） ===
{code_excerpt or '无'}

请给出一份让用户可以确认的修正计划。
""".strip()

        try:
            client = self._analyzer._get_client()
            response = client.chat([Message(role="user", content=prompt)])
            content = (getattr(response, "content", "") or "").strip()
            if content:
                return content, response
        except Exception as e:
            logger.warning(f"Failed to generate correction plan, use fallback plan: {e}")

        return self._build_repair_plan_fallback(spec, feedback, pipeline_feedback), None

    async def _launch_pipeline_task(
        self,
        *,
        session: SkillCreationSession,
        spec: SkillSpec,
        initial_feedback: str = "",
        initial_code: str = "",
        fact_report: Optional[ImplementationFactReport] = None,
        codegen_timeout: Optional[int] = None,
        iteration_mode: str = "repair",
    ) -> Dict[str, Any]:
        # Code generation single call timeout (seconds): None Use pipeline default; only accepted 60~1800 integer
        if isinstance(codegen_timeout, bool) or not isinstance(codegen_timeout, int):
            codegen_timeout = None
        elif not (60 <= codegen_timeout <= 1800):
            codegen_timeout = None

        # external_api Mode: Inject the interface preflight measured facts (connectivity/real fields/measured query parameters)
        # spec.metadata, Code generation prompt constructs the [Interface Measured Facts] block based on this——
        # LLM No more imaginary return fields, no more business filtering parameters (such as brand) URL
        try:
            if classify_requirement_mode(spec) == "external_api":
                sess_doc = await self._db[SESSION_COLLECTION].find_one(
                    {"session_id": session.session_id}, {"interface_preflight": 1}
                )
                preflight = (sess_doc or {}).get("interface_preflight")
                if preflight:
                    metadata = dict(getattr(spec, "metadata", None) or {})
                    metadata["interface_preflight"] = preflight
                    spec.metadata = metadata
                    logger.info(
                        "[Preflight] Interface measured facts are injected into code generation: status=%s data_items=%s fields=%s probed_params=%s",
                        preflight.get("status"),
                        preflight.get("data_items"),
                        preflight.get("sample_fields"),
                        list((preflight.get("probed_params") or {}).keys()),
                    )
        except Exception as exc:
            logger.debug("[Preflight] Measured fact injection code generation failed (ignored): %s", exc)

        session.status = SessionStatus.GENERATING
        if session.pipeline_result is not None:
            session.pipeline_history.append(session.pipeline_result)
        session.pipeline_result = None
        attempt_number = len(session.pipeline_history) + 1
        await self._save_session(session)
        await self._db[SESSION_COLLECTION].update_one(
            {"session_id": session.session_id},
            {
                "$set": {
                    "pipeline_stage": "code_generation",
                    "pipeline_message": "准备开始生成...",
                    "pipeline_iteration": 0,
                    "pipeline_progress": 0,
                    "pipeline_thinking": "",
                    "pipeline_eval_result": None,
                    "pipeline_details": [],
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        from app.core.database import get_mongo_db_sync
        sync_db = get_mongo_db_sync()
        session_id = session.session_id

        def _progress_cb(stage: str, message: str, iteration: int, progress: float,
                         extra: Optional[Dict[str, Any]] = None):
            try:
                detail_event: Dict[str, Any] = {
                    "stage": stage,
                    "message": message,
                    "iteration": iteration,
                    "progress": progress,
                    "timestamp": datetime.utcnow(),
                }
                set_fields: Dict[str, Any] = {
                    "pipeline_stage": stage,
                    "pipeline_message": message,
                    "pipeline_iteration": iteration,
                    "pipeline_progress": progress,
                    "updated_at": datetime.utcnow(),
                }
                # Quality assessment completed: structured results are logged into the database in real time, and scores/comments can be seen through front-end polling
                eval_result = (extra or {}).get("eval_result")
                if eval_result:
                    detail_event["eval_result"] = eval_result
                    set_fields["pipeline_eval_result"] = eval_result

                sync_db[SESSION_COLLECTION].update_one(
                    {"session_id": session_id},
                    {
                        "$set": set_fields,
                        "$push": {
                            "pipeline_details": {
                                "$each": [detail_event],
                                "$slice": -30,
                            }
                        },
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to update pipeline progress: {e}")

        # Real-time display of the thinking process: buffering reasoning increments, throttling writing of session documents (front-end polling reading)
        thinking_state = {"buf": "", "last_flush": 0.0}
        THINKING_FLUSH_INTERVAL = 1.5   # seconds
        THINKING_DOC_TAIL = 6000        # Only the tail is retained in the document to prevent unlimited growth

        def _flush_thinking() -> None:
            try:
                sync_db[SESSION_COLLECTION].update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "pipeline_thinking": thinking_state["buf"][-THINKING_DOC_TAIL:],
                        "updated_at": datetime.utcnow(),
                    }},
                )
            except Exception as e:
                logger.warning(f"Writing to pipeline_thinking failed: {e}")

        def _thinking_cb(kind: str, text: str):
            try:
                import time as _time
                if kind == "reset":
                    thinking_state["buf"] = ""
                    thinking_state["last_flush"] = _time.time()
                    _flush_thinking()
                    return
                if kind != "reasoning" or not text:
                    return
                thinking_state["buf"] = (thinking_state["buf"] + text)[-THINKING_DOC_TAIL * 2:]
                now = _time.time()
                if now - thinking_state["last_flush"] >= THINKING_FLUSH_INTERVAL:
                    thinking_state["last_flush"] = now
                    _flush_thinking()
            except Exception as e:
                logger.warning(f"Update pipeline_thinking failed: {e}")

        async def _run_pipeline():
            try:
                # mem0: Recall the historical lessons of similar skills and inject them into initial_feedback
                enriched_feedback = initial_feedback
                try:
                    mem0_lessons = await _recall_skill_lessons(self._db, spec)
                    if mem0_lessons:
                        enriched_feedback = (
                            f"{mem0_lessons}\n\n{initial_feedback}" if initial_feedback
                            else mem0_lessons
                        )
                        metadata = dict(getattr(spec, "metadata", None) or {})
                        metadata["cross_session_skill_lessons"] = mem0_lessons[:2000]
                        spec.metadata = metadata
                except Exception as e:
                    logger.debug("[mem0] Skill Lesson recall failed (ignored): %s", e)

                # Capture fact_report into local variables to avoid lambda closure issues
                _fr = fact_report
                method_name = "run_agentic" if SKILL_GENERATION_AGENTIC_ENABLED else "run"
                logger.info("Skill Build engine: %s", method_name)
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: getattr(self._controller, method_name)(
                        spec,
                        initial_feedback=enriched_feedback,
                        initial_code=initial_code,
                        progress_callback=_progress_cb,
                        fact_report=_fr,
                        codegen_timeout=codegen_timeout,
                        thinking_callback=_thinking_cb,
                        iteration_mode=iteration_mode,
                    ),
                )
                # After the flow ends, flush the remaining thinking content to avoid tail loss.
                _flush_thinking()
                session.status = SessionStatus.COMPLETED if result.success else SessionStatus.FAILED
                session.pipeline_result = result
                await self._save_session(session)

                try:
                    written_files = self._persist_generated_code_snapshots(
                        session_id=session.session_id,
                        tool_id=spec.tool_id,
                        attempt_number=attempt_number,
                        pipeline_result=result,
                    )
                    if written_files:
                        logger.info(
                            "📝 Skill Code snapshot saved: %s",
                            str((SKILL_CODE_SNAPSHOT_DIR / spec.tool_id / session.session_id).resolve()),
                        )
                except Exception as e:
                    logger.warning("⚠️ Failed to save skill code snapshot: %s", e)

                if result.success:
                    await self._save_skill(session, spec, result)

                # mem0: Write the lessons learned from this iteration into memory
                try:
                    await _store_skill_lessons(self._db, spec, result)
                except Exception as e:
                    logger.debug("[mem0] Skill Lesson storage failed (ignored): %s", e)
            except Exception as e:
                logger.error(f"管线执行异常: {e}", exc_info=True)
                await self._db[SESSION_COLLECTION].update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "status": "failed",
                            "pipeline_stage": "error",
                            "pipeline_message": str(e),
                            "updated_at": datetime.utcnow(),
                        },
                        "$push": {
                            "pipeline_details": {
                                "$each": [{
                                    "stage": "error",
                                    "message": str(e),
                                    "iteration": 0,
                                    "progress": 0,
                                    "timestamp": datetime.utcnow(),
                                }],
                                "$slice": -30,
                            }
                        },
                    },
                )

        asyncio.create_task(_run_pipeline())

        return {
            "status": "generating",
            "session_id": session_id,
            "skill_id": None,
            "spec": spec.model_dump() if spec else None,
            "success": False,
            "total_rounds": 0,
            "total_time": 0,
            "final_score": None,
            "error": None,
        }

    @staticmethod
    def _apply_handoff_context_to_spec(spec: SkillSpec, handoff_context: Any) -> None:
        """Attach the upstream handoff context to SkillSpec.metadata for use by Agentic Loop."""
        if spec is None or handoff_context is None:
            return
        metadata = dict(getattr(spec, "metadata", None) or {})

        def _string_list(field: str, limit: int) -> List[str]:
            return [
                str(item).strip()
                for item in list(getattr(handoff_context, field, None) or [])
                if str(item).strip()
            ][:limit]

        context_summary = {
            "source": str(getattr(handoff_context, "source", "") or ""),
            "source_spec_id": str(getattr(handoff_context, "source_spec_id", "") or getattr(handoff_context, "spec_id", "") or ""),
            "source_name": str(getattr(handoff_context, "source_name", "") or getattr(handoff_context, "agent_name", "") or ""),
            "target_capability": str(getattr(handoff_context, "target_capability", "") or ""),
            "handoff_intent": str(getattr(handoff_context, "handoff_intent", "") or ""),
            "workshop_session_id": str(getattr(handoff_context, "workshop_session_id", "") or ""),
            "gap_id": str(getattr(handoff_context, "gap_id", "") or ""),
            "agent_goal": str(getattr(handoff_context, "agent_goal", "") or ""),
            "gap_context": str(getattr(handoff_context, "gap_context", "") or ""),
            "searched_capabilities": _string_list("searched_capabilities", 12),
            "confirmed_data_sources": _string_list("confirmed_data_sources", 12),
            "user_clarifications": _string_list("user_clarifications", 12),
            "related_gaps": _string_list("related_gaps", 12),
        }
        context_summary = {
            key: value for key, value in context_summary.items()
            if value not in ("", [], None)
        }
        if context_summary:
            metadata["handoff_context_summary"] = context_summary

        failures = _string_list("known_failure_summaries", 5)
        facts = _string_list("known_verified_facts", 12)
        if failures:
            metadata["known_failure_summaries"] = failures
        if facts:
            metadata["known_verified_facts"] = facts
        if context_summary or failures or facts:
            logger.info(
                "[SkillGeneration][HandoffContext] tool_id=%s context_keys=%s known_failures=%s known_facts=%s",
                getattr(spec, "tool_id", ""),
                sorted(context_summary.keys()),
                len(metadata.get("known_failure_summaries") or []),
                len(metadata.get("known_verified_facts") or []),
            )
        spec.metadata = metadata

    @staticmethod
    def _has_generation_context(context: Optional[Dict[str, Any]]) -> bool:
        if not context:
            return False
        return bool(
            context.get("category_hint")
            or context.get("data_source_hint")
            or context.get("stock_collections")
            or context.get("external_sources")
        )

    def _build_spec_from_skill_doc(self, doc: Dict[str, Any]) -> Optional[SkillSpec]:
        try:
            params = [SkillParameter(**p) for p in doc.get("parameters", [])]
            expected_output_data = doc.get("expected_output", {})
            expected_output = ExpectedOutput(**expected_output_data) if expected_output_data else ExpectedOutput()
            return SkillSpec(
                tool_id=doc.get("tool_id", ""),
                display_name=doc.get("display_name", ""),
                description=doc.get("description", ""),
                category=doc.get("category", "other"),
                data_source=doc.get("data_source", ""),
                parameters=params,
                expected_output=expected_output,
                test_input=doc.get("test_input", {}),
            )
        except Exception:
            return None

    async def _hydrate_skill_generation_context(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        context = doc.get("generation_context")
        if self._has_generation_context(context):
            return doc

        metadata = dict(doc.get("metadata") or {})
        metadata_context = metadata.get("generation_context")
        if self._has_generation_context(metadata_context):
            doc["generation_context"] = metadata_context
            return doc

        recommendations: Optional[Dict[str, Any]] = None
        session_id = doc.get("session_id")
        if session_id:
            session = await self._load_session(session_id)
            if session:
                spec = session.spec if isinstance(session.spec, SkillSpec) else None
                recommendations = self._build_session_recommendations(spec=spec, session=session)

        if not self._has_generation_context(recommendations):
            spec = self._build_spec_from_skill_doc(doc)
            if spec is not None:
                recommendations = self._build_session_recommendations(spec=spec)

        if self._has_generation_context(recommendations):
            doc["generation_context"] = recommendations

        return doc

    # ==================== Requirements communication ====================

    async def start_session(
        self,
        description: str,
        user_id: str = "",
        handoff_context: Optional[Dict[str, Any]] = None,
        iterate_skill_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Start creating a session: Submit initial requirements

        Args:
            description: User requirement description
            user_id: User ID
            handoff_context: Handover context from upstream workshop
            iterate_skill_id: Existing in iteration mode Skill tool_id

        Returns:
            contains session_id, ai_message, clarity_level Waiting for information dict
        """
        # Create session
        context = SkillHandoffContext(**handoff_context) if handoff_context else None
        session = self._analyzer.create_session(
            user_id=user_id, handoff_context=context, iterate_skill_id=iterate_skill_id,
        )

        # Iterative mode: load the context of an existing Skill
        skill_context: Optional[str] = None
        if iterate_skill_id:
            try:
                skill_doc = await self._db[SKILL_COLLECTION].find_one(
                    {"tool_id": iterate_skill_id}
                )
                if skill_doc:
                    skill_doc.pop("_id", None)
                    code = skill_doc.get("code") or skill_doc.get("implementation") or ""
                    skill_context = json.dumps({
                        "tool_id": skill_doc.get("tool_id", ""),
                        "display_name": skill_doc.get("display_name", ""),
                        "description": skill_doc.get("description", ""),
                        "category": skill_doc.get("category", ""),
                        "parameters": skill_doc.get("parameters", []),
                        "status": skill_doc.get("status", ""),
                        "code_abbreviated": code[:1500] + ("..." if len(code) > 1500 else ""),
                    }, ensure_ascii=False, indent=2)
                    logger.info(
                        "[SkillGeneration][Iterate] Load an existing Skill context: tool_id=%s",
                        iterate_skill_id,
                    )
                else:
                    logger.warning(
                        "[SkillGeneration][Iterate] not found Skill: tool_id=%s",
                        iterate_skill_id,
                    )
            except Exception as exc:
                logger.error("[SkillGeneration][Iterate] Failed to load skill: %s", exc)

        # Process the first round of input (will do clarity evaluation and boundary detection)
        session, ai_message = await asyncio.get_event_loop().run_in_executor(
            None,
            self._analyzer.process_user_input,
            session,
            description,
            skill_context,  # Pass in existing Skill context in iterative mode
        )

        # persist to MongoDB
        session_doc = session.model_dump(mode="json")
        await self._db[SESSION_COLLECTION].insert_one(session_doc)

        max_rounds = self._analyzer._get_max_rounds(session.clarity_level)

        return {
            "session_id": session.session_id,
            "ai_message": ai_message,
            "clarity_level": session.clarity_level.value if session.clarity_level else "medium",
            "boundary_check": session.boundary_check.model_dump() if session.boundary_check else None,
            "current_round": session.current_round,
            "expected_rounds": max_rounds,
        }

    async def respond_to_session(
        self, session_id: str, user_message: str
    ) -> Dict[str, Any]:
        """
        User reply conversation turn

        Returns:
            contains ai_message, current_round, is_final_round Waiting for information dict
        """
        # Load session from MongoDB
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        if session.spec_confirmed:
            raise ValueError("The specifications have been confirmed and the conversation cannot be continued.")

        # Handle user input
        session, ai_message = await asyncio.get_event_loop().run_in_executor(
            None, self._analyzer.process_user_input, session, user_message
        )

        # update MongoDB
        await self._save_session(session)

        max_rounds = self._analyzer._get_max_rounds(session.clarity_level)

        return {
            "session_id": session.session_id,
            "ai_message": ai_message,
            "current_round": session.current_round,
            "expected_rounds": max_rounds,
            "is_final_round": session.current_round >= max_rounds,
            "boundary_check": session.boundary_check.model_dump() if session.boundary_check else None,
        }

    async def _inherit_parent_interface_constraints(
        self, spec: SkillSpec, parent_tool_id: str
    ) -> bool:
        """Iteration mode: Inherit interface specification constraints (including URL constraints) from the parent Skill.

        Background: There is no original requirement text in the dialogue of the upgrade session, and the URL generated by the specification is extracted.
        Unable to obtain the interface address, causing the new version spec to lose the interface contract——Confirmation page appears
         [ Interface URL not recognized warning, the URL will be forged during the code generation phase.
        Source priority: constraints field of parent Skill (new version has been persisted);
        Older versions fall back to extracting the interface URL from the parent code.
        """
        url_re = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")

        def _base_urls(text: str) -> set:
            return {
                m.group(0).split("?")[0].rstrip(".,;:")
                for m in url_re.finditer(text or "")
            }

        try:
            parent = await self._db[SKILL_COLLECTION].find_one(
                {"tool_id": parent_tool_id},
                {"constraints": 1, "code": 1, "session_id": 1},
            )
        except Exception as exc:
            logger.warning("[Iterate] Failed to load parent Skill (interface constraint inheritance skipped): %s", exc)
            return False
        if not parent:
            return False

        # Source priority:
        # 1) The constraints field of the parent Skill (_save_skill has been persisted and the new version of the skill is available)
        # 2) spec.constraints of the parent Skill source session (older version skills also have complete interface constraint lines)
        # 3) Extract the interface URL from the parent code (finally, multi-level paths are required to exclude pure domain names such as Referer)
        interface_lines = [
            str(c) for c in (parent.get("constraints") or []) if url_re.search(str(c))
        ]
        if not interface_lines:
            origin_session_id = parent.get("session_id")
            if origin_session_id:
                try:
                    origin_sess = await self._db[SESSION_COLLECTION].find_one(
                        {"session_id": origin_session_id}, {"spec.constraints": 1}
                    )
                except Exception as exc:
                    logger.debug("[Iterate] Failed to load parent session: %s", exc)
                    origin_sess = None
                if origin_sess and origin_sess.get("spec"):
                    interface_lines = [
                        str(c)
                        for c in ((origin_sess["spec"] or {}).get("constraints") or [])
                        if url_re.search(str(c))
                    ]
        if not interface_lines:
            urls = [
                u
                for u in _base_urls(parent.get("code") or "")
                # At least 2 levels of path after the domain name (such as /motor/pc/car/rank_data),
                # Exclude Referer references of pure domain names and single-level paths
                if len([s for s in u.split("//", 1)[-1].split("/") if s]) >= 3
            ]
            interface_lines = [
                f"【接口规格 — 必须原样使用】接口 URL: {u}（继承自父版本 {parent_tool_id}，"
                "It is strictly prohibited to rewrite the path/parameter name. For example, rank_data must not be written as rank/data;"
                "URL The query parameters in are only examples, and parameters are passed as function parameters during implementation)"
                for u in urls
            ]
        if not interface_lines:
            return False

        existing = _base_urls("\n".join(str(c) for c in (spec.constraints or [])))
        added = False
        for line in interface_lines:
            line_urls = _base_urls(line)
            if line_urls and not (line_urls & existing):
                spec.constraints.insert(0, line)
                existing |= line_urls
                added = True
        if added:
            logger.info(
                "[Iterate] Inherited the interface specification constraints of the parent version (parent=%s)", parent_tool_id
            )
        return added

    async def _load_parent_skill_code(self, parent_tool_id: str) -> str:
        """Iteration mode: Load the complete verified code of the parent version as the upgrade baseline.

        Background: Upgrades are usually just small adjustments such as adding fields/parameters. The human approach is to change a few lines of the original code.
        If there is no parent code, the first round of generation will be rewritten from scratch, which is wasteful and will lose the parent version. It took many rounds of iterations to fix it.
        Details (pagination/retries/local filtering/field mapping, etc.).
        """
        try:
            parent = await self._db[SKILL_COLLECTION].find_one(
                {"tool_id": parent_tool_id},
                {"code": 1, "implementation": 1, "status": 1},
            )
        except Exception as exc:
            logger.warning("[Iterate] Failed to load parent Skill code (handled as generated from scratch): %s", exc)
            return ""
        if not parent:
            logger.warning("[Iterate] Parent not found Skill: tool_id=%s", parent_tool_id)
            return ""
        code = parent.get("code") or parent.get("implementation") or ""
        if code:
            logger.info(
                "[Iterate] Parent version code loaded as upgrade baseline: parent=%s chars=%d status=%s",
                parent_tool_id, len(code), parent.get("status"),
            )
        return code

    async def _load_parent_skill_contract(
        self, parent_tool_id: str
    ) -> Optional[Dict[str, Any]]:
        """Iteration mode: load the parent version of the complete contract (parameters/constraints/output/complete code)+ Calculate the new version number.

        Source of truth for upgrade patch mode: spec generation LLM reads it to locate change points, patch is applied
        Unmentioned fields are inherited from it as is. Version number query has the same logic as _save_skill.
        Ensure that spec.tool_id is consistent with the final library during the generation period (codegen function name/
        Static verification is aligned according to tool_id, and subsequent changes will invalidate the entire round).
        """
        try:
            parent = await self._db[SKILL_COLLECTION].find_one(
                {"tool_id": parent_tool_id}
            )
        except Exception as exc:
            logger.warning("[Iterate] Failed to load parent Skill contract: %s", exc)
            return None
        if not parent:
            logger.warning("[Iterate] Parent Skill not found (contract loading): tool_id=%s", parent_tool_id)
            return None

        root_tool_id = parent.get("parent_skill_id") or parent_tool_id
        # The maximum version number in the series (including the root version), consistent with the version calculation of _save_skill
        new_version = 2
        try:
            cursor = (
                self._db[SKILL_COLLECTION]
                .find({"$or": [{"tool_id": root_tool_id}, {"parent_skill_id": root_tool_id}]})
                .sort("version", -1)
                .limit(1)
            )
            max_docs = await cursor.to_list(1)
            if max_docs:
                new_version = int(max_docs[0].get("version") or 1) + 1
        except Exception as exc:
            logger.warning("[Iterate] Failed to query the series version number, use the default v2: %s", exc)

        contract = {
            "tool_id": parent.get("tool_id") or parent_tool_id,
            "root_tool_id": root_tool_id,
            "new_tool_id": f"{root_tool_id}_v{new_version}",
            "new_version": new_version,
            "display_name": parent.get("display_name") or "",
            "description": parent.get("description") or "",
            "category": parent.get("category") or "utility",
            "data_source": parent.get("data_source") or "",
            "parameters": list(parent.get("parameters") or []),
            "expected_output": dict(parent.get("expected_output") or {}),
            "constraints": list(parent.get("constraints") or []),
            "test_input": dict(parent.get("test_input") or {}),
            "code": parent.get("code") or parent.get("implementation") or "",
        }
        logger.info(
            "[Iterate] Parent version contract loaded (patch mode base): parent=%s root=%s next=%s "
            "params=%d constraints=%d code_chars=%d",
            contract["tool_id"], root_tool_id, contract["new_tool_id"],
            len(contract["parameters"]), len(contract["constraints"]),
            len(contract["code"]),
        )
        return contract

    async def _preflight_external_interface(
        self, spec: SkillSpec, parent_code: str = ""
    ) -> Optional[Dict[str, Any]]:
        """external_api Mode: Really call the interface in the sandbox to do connectivity pre-check.

        During the specification confirmation stage, URL error/interface unreachable/parameter problem was discovered.
        Avoid waiting for code generation (2-4 minutes per round) before sandbox execution is exposed.

        parent_code: Upgrade the parent version code of the scene——When there is only a bare URL (no query string) in the constraint,
        Extract the parent code s validated query parameters (such as count/offset) from it as a preflight baseline,
        Prevent new spec parameters (such as limit) from being misjudged as interface available parameters.
        """
        from core.tools.external.interface_preflight import (
            build_interface_probe,
            interpret_probe_result,
        )
        from core.tools.external.sandbox_runner import SandboxRunner

        probe = build_interface_probe(spec, parent_code=parent_code)
        if probe is None:
            return None
        runner = SandboxRunner(timeout=25)
        sandbox = await asyncio.get_event_loop().run_in_executor(
            None, lambda: runner.run(probe["code"], spec, test_input=probe["params"])
        )
        verdict = interpret_probe_result(sandbox)
        verdict["url"] = probe["url"]
        # Available query parameters verified by actual testing = Baseline parameters (user URL documented query parameters).
        # The suspected business filtering parameters (such as brand_name) fall into
        # ignored_params (ignored→Local filtering)/server_filter_params (server filtering takes effect)
        baseline = probe.get("baseline_params") or {}
        if baseline:
            verdict["probed_params"] = dict(baseline)
        verdict["checked_at"] = datetime.utcnow().isoformat()
        logger.info(
            "[Preflight] External interface preflight tool_id=%s url=%s status=%s message=%s",
            spec.tool_id,
            probe["url"],
            verdict.get("status"),
            verdict.get("message"),
        )
        return verdict

    async def preview_spec(
        self, session_id: str, user_message: str = "确认"
    ) -> Optional[Dict[str, Any]]:
        """
        Only a SkillSpec preview is generated, the session state is not modified.
        Used to demonstrate specification confirmation steps.

        Process: First generate a draft spec → run recon → Regenerate enriched spec based on recon facts.
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        # Iteration mode: Load the parent version contract, and use the upgrade patch mode for specification generation (parent contract + delta) 
        parent_contract = None
        if session.iterate_skill_id:
            parent_contract = await self._load_parent_skill_contract(
                session.iterate_skill_id
            )

        # First pass: Generate draft spec (no recon facts)
        draft_spec = await asyncio.get_event_loop().run_in_executor(
            None, self._analyzer.preview_spec, session, user_message, None, parent_contract
        )
        if not draft_spec:
            return None

        # Vector Search: Tools for Recalling Semantic Relevance from Capability Indexes Using Spec Descriptions
        capability_hits = await self._search_capability_index(draft_spec)

        # Run reconnaissance layer: detect real data availability based on draft spec (with vector search results)
        fact_report = await asyncio.get_event_loop().run_in_executor(
            None, self._reconnaissance.analyze, draft_spec, capability_hits
        )
        logger.info("🧭 Reconnaissance completed (preview), Confidence: %.0f%%", fact_report.confidence * 100)

        # Second pass: Regenerate enriched spec based on recon facts.
        # Only executed when scouting output field-level empirical facts and not in external_api mode——
        # external_api Pattern reconnaissance does not detect external interfaces, and the report content is static guidance derived from the pattern.
        #  (The field list is still copied from the draft), and there is no substantial difference between the secondary generation input and the draft.
        # It only costs one more LLM call (about 5 minutes under the thinking model).
        enriched_spec = None
        if (
            classify_requirement_mode(draft_spec) != "external_api"
            and fact_report.has_spec_grounding_facts
        ):
            enriched_spec = await asyncio.get_event_loop().run_in_executor(
                None, self._analyzer.preview_spec, session, user_message, fact_report,
                parent_contract,
            )
        final_spec = enriched_spec or draft_spec

        # Cache spec and fact_report to session and reuse them directly when confirm_spec.
        # Avoid calling LLM generation specs again causing the front end to stay at 0% for a long time.
        session.spec = final_spec
        self._apply_handoff_context_to_spec(session.spec, session.handoff_context)
        # Iteration mode: inherit the parent version interface specification constraints (including URL), and the confirmation page will no longer appear
        # ""Interface URL not recognized" warning, code generation does not lose the interface contract
        if session.iterate_skill_id:
            await self._inherit_parent_interface_constraints(
                session.spec, session.iterate_skill_id
            )
        session.fact_report = fact_report
        await self._save_session(session)

        # External interface pre-check: Really call the interface in the sandbox to verify connectivity, and the results are displayed on the confirmation page
        interface_preflight = None
        if classify_requirement_mode(session.spec) == "external_api":
            # Upgrade scenario: with parent code, the preflight baseline inherits the verified query parameters of the parent version
            preview_parent_code = ""
            if session.iterate_skill_id:
                preview_parent_code = await self._load_parent_skill_code(session.iterate_skill_id)
            try:
                interface_preflight = await self._preflight_external_interface(
                    session.spec, parent_code=preview_parent_code
                )
            except Exception as exc:
                logger.warning("[Preflight] Interface preflight failed (no blocking confirmation): %s", exc)
            if interface_preflight is not None:
                try:
                    await self._db[SESSION_COLLECTION].update_one(
                        {"session_id": session.session_id},
                        {"$set": {"interface_preflight": interface_preflight}},
                    )
                except Exception as exc:
                    logger.warning("[Preflight] The pre-check result failed to be dropped into the database.: %s", exc)

        return {
            "spec": final_spec.model_dump(),
            "recommendations": self._build_session_recommendations(spec=final_spec, fact_report=fact_report),
            "fact_report": fact_report.model_dump() if fact_report else None,
            "interface_preflight": interface_preflight,
            # List of change points in the upgrade patch mode (diff-style display on the confirmation page: what has been changed, the rest will be inherited)
            "upgrade_change_points": (
                (final_spec.metadata or {}).get("upgrade_change_points")
                if parent_contract else None
            ),
        }

    async def confirm_spec(
        self, session_id: str, user_message: str = "确认", codegen_timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Confirm specs and trigger code generation

        Process: Reuse the fact_report cached in the preview stage, and conduct on-site reconnaissance if there is none.
        Inject fact_report into spec generation and pipeline execution at the same time to achieve"reconnaissance→Make rules→generate"Closed loop.

        Args:
            session_id: session ID
            user_message: Confirm message
            codegen_timeout: Code generation single LLM call timeout (seconds), None uses the default value

        Returns:
            contains status, spec, generation_result Waiting for information dict
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")

        # Reuse the fact_report cached in the preview stage. If there is none, run reconnaissance first.
        fact_report = session.fact_report
        if fact_report is None:
            # Need to generate draft spec first for reconnaissance
            draft_parent_contract = (
                await self._load_parent_skill_contract(session.iterate_skill_id)
                if session.iterate_skill_id else None
            )
            draft_spec = await asyncio.get_event_loop().run_in_executor(
                None, self._analyzer.preview_spec, session, user_message,
                None, draft_parent_contract,
            )
            if draft_spec:
                # Vector search: Recalling semantically related tools from capability indexes
                capability_hits = await self._search_capability_index(draft_spec)
                fact_report = await asyncio.get_event_loop().run_in_executor(
                    None, self._reconnaissance.analyze, draft_spec, capability_hits
                )
                logger.info("🧭 Reconnaissance completed (confirm), Confidence: %.0f%%", fact_report.confidence * 100)

        # If the specification has been cached in the preview stage and is currently only regular"Confirm", 
        # Then reuse it directly to avoid calling LLM again to generate SkillSpec when confirming.
        normalized_message = (user_message or "").strip()
        can_reuse_preview_spec = bool(
            session.spec
            and fact_report is not None
            and normalized_message in ("", "确认", "确认生成", "继续生成")
        )

        if can_reuse_preview_spec:
            spec = session.spec
            session.spec_confirmed = True
            session.status = SessionStatus.CONFIRMED
            session.updated_at = datetime.utcnow()
            await self._save_session(session)
        else:
            # Generate the final SkillSpec based on the reconnaissance facts (iteration mode with parent contract in patch mode)
            confirm_parent_contract = (
                await self._load_parent_skill_contract(session.iterate_skill_id)
                if session.iterate_skill_id else None
            )
            session, spec = await asyncio.get_event_loop().run_in_executor(
                None, self._analyzer.confirm_spec, session, user_message, fact_report,
                confirm_parent_contract,
            )

        if not spec:
            return {
                "status": "failed",
                "message": "Specification generation failed, please describe the requirements again",
            }

        self._apply_handoff_context_to_spec(spec, session.handoff_context)

        # Iteration mode: inherit the parent version interface specification constraints (including URL)——preview Cache reuse path
        # We must also be careful to prevent the upgraded version from losing the interface contract, resulting in fictitious code generation. URL
        if session.iterate_skill_id and await self._inherit_parent_interface_constraints(
            spec, session.iterate_skill_id
        ):
            session.spec = spec
            await self._save_session(session)

        # Iteration mode: Load parent version code in advance (preflight baseline parameters + Pipeline upgrade baselines are shared to avoid repeated library checks)
        parent_code = ""
        if session.iterate_skill_id:
            parent_code = await self._load_parent_skill_code(session.iterate_skill_id)

        # External interface preflight interception: prevent code generation when the interface is clearly unavailable (unreachable/4xx/5xx),
        # Avoid burning through 2-4 minutes/round of builds only to discover interface issues in the sandbox.
        # preview Cached results are reused; run now when confirmed directly (skip preview).
        if classify_requirement_mode(spec) == "external_api":
            preflight = None
            try:
                sess_doc = await self._db[SESSION_COLLECTION].find_one(
                    {"session_id": session_id}, {"interface_preflight": 1}
                )
                preflight = (sess_doc or {}).get("interface_preflight")
            except Exception:
                preflight = None
            if preflight is None:
                try:
                    preflight = await self._preflight_external_interface(
                        spec, parent_code=parent_code
                    )
                except Exception as exc:
                    logger.warning("[Preflight] Confirmation phase pre-inspection failed (release): %s", exc)
                if preflight is not None:
                    try:
                        await self._db[SESSION_COLLECTION].update_one(
                            {"session_id": session_id},
                            {"$set": {"interface_preflight": preflight}},
                        )
                    except Exception:
                        pass
            if preflight and preflight.get("status") == "failed":
                return {
                    "status": "failed",
                    "message": (
                        f"The external interface preflight failed and code generation has been blocked:{preflight.get('message')}. "
                        "Please correct the interface specifications (URL/request headers/parameters) and reconfirm."
                    ),
                    "interface_preflight": preflight,
                }

        # Iteration mode: The parent version code is used as the upgrade baseline (small change scenarios to avoid rewriting from scratch)
        iteration_mode = "upgrade" if parent_code else "repair"

        # fact_report Also passed to the pipeline, skipping internal repeated reconnaissance
        return await self._launch_pipeline_task(
            session=session, spec=spec, fact_report=fact_report,
            codegen_timeout=codegen_timeout,
            initial_code=parent_code,
            iteration_mode=iteration_mode,
        )

    async def repair_session(
        self,
        session_id: str,
        feedback: str,
        repair_plan: str = "",
        codegen_timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Re-correct and generate based on the current failed session.

        Use all accumulated historical pipeline experience + Users additional comments serve as the initial feedback for a new round,
        Make sure the LLM learns from each previous attempt rather than just seeing the latest failure.
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        if not session.spec_confirmed or not session.spec:
            raise ValueError("The current session has not confirmed the specifications and cannot enter correction mode.")
        if session.status != SessionStatus.FAILED:
            raise ValueError("Only failed creation sessions can be confirmed and rerun.")

        merged_feedback = feedback.strip()
        if repair_plan.strip():
            merged_feedback = (
                f"{merged_feedback}\n\n=== Confirmed correction plan ===\n{repair_plan.strip()}"
            )

        attempt_count = len(session.pipeline_history) + (1 if session.pipeline_result else 0)
        session.rounds.append(ConversationRound(
            round_number=len(session.rounds) + 1,
            user_message=f"[修正] {feedback}",
            ai_message=(
                f"已确认修正计划，结合前 {attempt_count} 次经验重新生成..."
                if repair_plan.strip() else
                f"已接收修正意见，结合前 {attempt_count} 次经验重新生成..."
            ),
        ))

        initial_feedback = self._build_accumulated_experience(
            pipeline_history=session.pipeline_history,
            current_pipeline=session.pipeline_result,
            user_feedback=merged_feedback,
        )
        initial_code = self._get_last_generated_code(session.pipeline_result)

        return await self._launch_pipeline_task(
            session=session,
            spec=session.spec,
            initial_feedback=initial_feedback,
            initial_code=initial_code,
            codegen_timeout=codegen_timeout,
        )

    async def preview_repair_session(
        self,
        session_id: str,
        feedback: str,
    ) -> Dict[str, Any]:
        """
        First generate an AI correction plan and wait for user confirmation before running again.
        """
        session = await self._load_session(session_id)
        if not session:
            raise ValueError(f"会话 {session_id} 不存在")
        if not session.spec_confirmed or not session.spec:
            raise ValueError("The current session has not confirmed the specifications and cannot generate a correction plan.")
        if session.status != SessionStatus.FAILED:
            raise ValueError("Only failed creation sessions can generate remediation plans first")

        ai_message, repair_llm_response = await asyncio.get_event_loop().run_in_executor(
            None,
            self._generate_repair_plan_message,
            session,
            feedback,
        )

        # Logging token usage (LLM calls are done in synchronous methods, here they are logged in their asynchronous callers)
        try:
            if repair_llm_response is not None:
                from app.services.usage_statistics_service import usage_statistics_service
                await usage_statistics_service.record_llm_usage(
                    response=repair_llm_response,
                    session_id=session_id,
                    analysis_type="skill_generation",
                )
        except Exception as e:
            logger.warning(f"Record token usage failure: {e}")

        session.rounds.append(ConversationRound(
            round_number=len(session.rounds) + 1,
            user_message=f"[修正讨论] {feedback}",
            ai_message=ai_message,
        ))
        await self._save_session(session)

        return {
            "status": "repair-planned",
            "session_id": session_id,
            "ai_message": ai_message,
        }

    # ==================== Skill management ====================

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话详情"""
        doc = await self._db[SESSION_COLLECTION].find_one({"session_id": session_id})
        if not doc:
            return None
        doc.pop("_id", None)
        try:
            session = SkillCreationSession(**doc)
            spec = session.spec if isinstance(session.spec, SkillSpec) else None
            doc["recommendations"] = self._build_session_recommendations(spec=spec, session=session)
        except Exception:
            rounds = doc.get("rounds", []) or []
            conversation = "\n\n".join(
                f"[用户 - 第{item.get('round_number', '?')}轮]: {item.get('user_message', '')}\n"
                f"[AI - No.{item.get('round_number', '?')}wheel]: {item.get('ai_message', '')}"
                for item in rounds
            )
            doc["recommendations"] = self._analyzer.build_recommendations(conversation=conversation)
        return doc

    async def list_sessions(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List creation sessions (draft/incomplete)"""
        query: Dict[str, Any] = {}
        if status:
            # Supports comma separated multiple states:gathering,confirmed
            statuses = [s.strip() for s in status.split(",")]
            query["status"] = {"$in": statuses}
        if user_id:
            query["user_id"] = user_id

        total = await self._db[SESSION_COLLECTION].count_documents(query)
        skip = (page - 1) * page_size

        sessions = []
        cursor = (
            self._db[SESSION_COLLECTION]
            .find(query)
            .sort("updated_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        async for doc in cursor:
            doc.pop("_id", None)
            try:
                session = SkillCreationSession(**doc)
                spec = session.spec if isinstance(session.spec, SkillSpec) else None
                doc["recommendations"] = self._build_session_recommendations(spec=spec, session=session)
            except Exception:
                rounds = doc.get("rounds", []) or []
                conversation = "\n\n".join(
                    f"[用户 - 第{item.get('round_number', '?')}轮]: {item.get('user_message', '')}\n"
                    f"[AI - No.{item.get('round_number', '?')}wheel]: {item.get('ai_message', '')}"
                    for item in rounds
                )
                doc["recommendations"] = self._analyzer.build_recommendations(conversation=conversation)
            sessions.append(doc)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": sessions,
        }

    async def delete_session(self, session_id: str) -> bool:
        """删除草稿会话"""
        result = await self._db[SESSION_COLLECTION].delete_one({"session_id": session_id})
        return result.deleted_count > 0

    async def list_skills(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List external skills (paginated)"""
        query: Dict[str, Any] = {}
        if category:
            query["category"] = category
        if status:
            query["status"] = status
        if source:
            clean_source = str(source or "").strip()
            if clean_source == "agent_studio_auto_gap_resolution":
                query["origin_source"] = clean_source
            elif clean_source == "manual_or_other":
                query["origin_source"] = {"$ne": "agent_studio_auto_gap_resolution"}
            else:
                query["source"] = clean_source

        logger.info(
            "[SkillGeneration][ListSkills] start source=%s category=%s status=%s page=%s page_size=%s query=%s",
            source or "-",
            category or "-",
            status or "-",
            page,
            page_size,
            query,
        )

        total = await self._db[SKILL_COLLECTION].count_documents(query)
        skip = (page - 1) * page_size

        skills = []
        cursor = (
            self._db[SKILL_COLLECTION]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        async for doc in cursor:
            doc.pop("_id", None)
            doc = await self._hydrate_skill_generation_context(doc)
            doc["used_by_agents"] = await self._find_skill_agent_usage(str(doc.get("tool_id") or ""))
            skills.append(doc)

        logger.info(
            "[SkillGeneration][ListSkills] done source=%s total=%s returned=%s",
            source or "-",
            total,
            len(skills),
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": skills,
        }

    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """获取 Skill 详情"""
        clean_skill_id = str(skill_id or "").strip()
        logger.info(
            "[SkillGeneration][GetSkill] start skill_id=%s",
            clean_skill_id or "-",
        )
        doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": clean_skill_id})
        if not doc:
            logger.info("[SkillGeneration][GetSkill] not_found skill_id=%s", clean_skill_id or "-")
            return None
        doc.pop("_id", None)
        doc = await self._hydrate_skill_generation_context(doc)
        doc["used_by_agents"] = await self._find_skill_agent_usage(str(doc.get("tool_id") or ""))
        logger.info(
            "[SkillGeneration][GetSkill] done skill_id=%s status=%s source=%s origin_source=%s",
            clean_skill_id or "-",
            doc.get("status", ""),
            doc.get("source", ""),
            doc.get("origin_source", ""),
        )
        return doc

    async def _find_skill_agent_usage(self, skill_id: str) -> List[Dict[str, Any]]:
        """Check which Agent versions the Skill is used by."""
        clean_skill_id = str(skill_id or "").strip()
        if not clean_skill_id:
            return []

        try:
            cursor = self._db["agent_versions"].find(
                {"required_tools": clean_skill_id},
                {
                    "_id": 0,
                    "version_id": 1,
                    "spec_id": 1,
                    "version": 1,
                    "status": 1,
                    "agent_metadata": 1,
                    "published_from_session_id": 1,
                    "updated_at": 1,
                },
            ).sort("updated_at", -1).limit(20)
            docs = await cursor.to_list(length=20)
        except Exception as exc:
            logger.debug("[SkillGeneration][AgentUsage] query failed skill_id=%s err=%s", clean_skill_id, exc)
            return []

        usage: List[Dict[str, Any]] = []
        for doc in docs or []:
            metadata = doc.get("agent_metadata") if isinstance(doc.get("agent_metadata"), dict) else {}
            usage.append({
                "version_id": str(doc.get("version_id") or ""),
                "spec_id": str(doc.get("spec_id") or ""),
                "version": doc.get("version"),
                "status": str(doc.get("status") or ""),
                "agent_name": str(metadata.get("name") or metadata.get("agent_name") or ""),
                "published_from_session_id": str(doc.get("published_from_session_id") or ""),
                "updated_at": str(doc.get("updated_at") or ""),
            })

        logger.info(
            "[SkillGeneration][AgentUsage] done skill_id=%s agents=%s",
            clean_skill_id,
            len(usage),
        )
        return usage

    async def get_skill_code(self, skill_id: str) -> Optional[str]:
        """获取 Skill 源代码"""
        doc = await self._db[SKILL_COLLECTION].find_one(
            {"tool_id": skill_id}, {"code": 1}
        )
        if not doc:
            return None
        return doc.get("code", "")

    async def get_skill_history(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Skill full communication history: original creation session + All optimization sessions

        Returns:
            {
                "skill_id": "...",
                "sections": [
                    { "type": "creation", "label": "Create", "session_id": "...", "rounds": [...], "created_at": "..." },
                    { "type": "optimize", "label": "Optimize v2", "session_id": "...", "rounds": [...], "created_at": "...", "feedback": "..." },
                    ...
                ]
            }
        """
        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            return None

        sections = []

        # original create session
        original_session_id = skill_doc.get("session_id", "")
        if original_session_id:
            session = await self.get_session(original_session_id)
            if session:
                sections.append({
                    "type": "creation",
                    "label": "初始创建",
                    "session_id": original_session_id,
                    "rounds": session.get("rounds", []),
                    "created_at": session.get("created_at", ""),
                })

        # All optimization sessions
        optimize_ids = skill_doc.get("optimize_session_ids", [])
        # Backward compatibility: if only the old optimize_session_id field
        legacy_id = skill_doc.get("optimize_session_id", "")
        if legacy_id and legacy_id not in optimize_ids:
            optimize_ids = [legacy_id] + optimize_ids

        for idx, opt_sid in enumerate(optimize_ids):
            session = await self.get_session(opt_sid)
            if session:
                version_label = f"优化 v{idx + 2}"
                # Extract optimization feedback from rounds
                feedback = ""
                rounds = session.get("rounds", [])
                if rounds:
                    first_msg = rounds[0].get("user_message", "")
                    if first_msg.startswith("[优化] "):
                        feedback = first_msg[len("[优化] "):]
                sections.append({
                    "type": "optimize",
                    "label": version_label,
                    "session_id": opt_sid,
                    "rounds": rounds,
                    "created_at": session.get("created_at", ""),
                    "feedback": feedback,
                })

        return {
            "skill_id": skill_id,
            "display_name": skill_doc.get("display_name", ""),
            "sections": sections,
        }

    async def update_skill_status(
        self, skill_id: str, new_status: str
    ) -> bool:
        """Update Skill status (active / disabled / archived) and synchronize the runtime ToolRegistry."""
        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            return False

        result = await self._db[SKILL_COLLECTION].update_one(
            {"tool_id": skill_id},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow().isoformat()}},
        )

        try:
            from core.tools.registry import get_tool_registry
            registry = get_tool_registry()
            if new_status == "active":
                from core.tools.external_skill_loader import register_single_external_skill
                skill_doc["status"] = new_status
                register_single_external_skill(None, registry, skill_doc)
            else:
                registry.unregister(skill_id)
        except Exception as e:
            logger.warning(f"⚠️ Skill '{skill_id}' 运行时状态同步失败: {e}")

        return result.modified_count > 0

    async def update_skill_info(
        self, skill_id: str, display_name: str, description: str
    ) -> bool:
        """Update the display name and function description of the Skill (manually edited by the user).

        Only these two display fields are allowed to be changed——Parameters/code/constraints belong to the verified contract,
        To change, please use iterative optimization to generate a new version. Sync runtime after update ToolRegistry
         (The name/description is part of the ToolMetadata) and capability index.
        """
        clean_name = str(display_name or "").strip()
        clean_desc = str(description or "").strip()
        if not clean_name:
            raise ValueError("Skill 名称不能为空")

        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            return False

        await self._db[SKILL_COLLECTION].update_one(
            {"tool_id": skill_id},
            {
                "$set": {
                    "display_name": clean_name,
                    "description": clean_desc,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            },
        )

        # Synchronous runtime registration (re-register with updated documentation, ToolMetadata name/description refreshed)
        try:
            from core.tools.registry import get_tool_registry
            from core.tools.external_skill_loader import register_single_external_skill

            skill_doc["display_name"] = clean_name
            skill_doc["description"] = clean_desc
            skill_doc["status"] = skill_doc.get("status", "active")
            register_single_external_skill(None, get_tool_registry(), skill_doc)
        except Exception as e:
            logger.warning(f"⚠️ Skill '{skill_id}' Description Runtime synchronization failed after update: {e}")

        # Capability index contains name/description, refreshed asynchronously
        try:
            asyncio.create_task(CapabilityIndexService(self._db).ensure_index())
        except Exception as e:
            logger.warning(f"⚠️ Skill '{skill_id}' 能力索引刷新失败: {e}")

        return True

    async def delete_skill(self, skill_id: str) -> bool:
        """Remove the skill and clean up the runtime registration and tool bindings."""
        result = await self._db[SKILL_COLLECTION].delete_one({"tool_id": skill_id})
        if result.deleted_count:
            await self._db.tool_agent_bindings.delete_many({"tool_id": skill_id})
            try:
                from core.tools.registry import get_tool_registry
                get_tool_registry().unregister(skill_id)
            except Exception as e:
                logger.warning(f"⚠️ Skill '{skill_id}' 运行时注销失败: {e}")
        return result.deleted_count > 0

    async def test_skill(
        self, skill_id: str, test_args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """手动测试 Skill"""
        doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not doc:
            raise ValueError(f"Skill {skill_id} 不存在")

        code = doc.get("code", "")
        if not code:
            raise ValueError("Skill 没有代码")

        # 🔬 Write the code to be executed to the log
        logger.info(f"🔬 [test_skill] About to be executed skill={skill_id}, code_len={len(code)}\n" + code)

        # Execute using SandboxRunner
        from core.tools.external import SandboxRunner, SkillSpec

        # 🔬 Printed from the front end test_args
        logger.info(f"🔬 [test_skill] original test_args={test_args}")

        # Filter out unfilled parameters (None/empty string) and let the function default value take effect.
        # Note that 0/False is a legal input parameter (such as offset=0) , It cannot be deleted as falsy.
        if test_args:
            test_args = {k: v for k, v in test_args.items() if v is not None and v != ''}
            logger.info(f"🔬 [test_skill] After filtering test_args={test_args}")

        runner = SandboxRunner()
        # Build a simple spec for testing
        spec = SkillSpec(
            tool_id=doc["tool_id"],
            display_name=doc.get("display_name", ""),
            description=doc.get("description", ""),
            test_input=test_args or doc.get("test_input", {}),
        )
        sandbox_result = runner.run(code, spec)

        # Write the stdout/stderr of the child process to the webapi log
        if sandbox_result.stdout:
            for line in sandbox_result.stdout.split("\n"):
                line = line.strip()
                if line:
                    logger.info(f"📦 [Skill Test sandbox stdout] {line}")
        if sandbox_result.stderr:
            for line in sandbox_result.stderr.split("\n"):
                line = line.strip()
                if line:
                    logger.warning(f"📦 [Skill Test sandbox stderr] {line}")

        return {
            "success": sandbox_result.success,
            "output": sandbox_result.output,
            "stdout": sandbox_result.stdout,
            "stderr": sandbox_result.stderr,
            "execution_time": sandbox_result.execution_time,
            "error": sandbox_result.error,
        }

    async def optimize_skill(
        self, skill_id: str, feedback: str
    ) -> Dict[str, Any]:
        """
        Optimize existing skills: regenerate code based on user feedback

        Process:
        1. Load existing Skill and original Session
        2. convert original conversation + current code + User feedback Synthesize new context
        3. Create a new Session to record the optimization process
        4. Execute code generation pipeline
        5. If successful, the Skill code will be updated and the optimized version number will be saved.
        """
        # Load existing Skill
        skill_doc = await self._db[SKILL_COLLECTION].find_one({"tool_id": skill_id})
        if not skill_doc:
            raise ValueError(f"Skill {skill_id} 不存在")

        # Load the original session (get the original communication record and spec)
        original_session_id = skill_doc.get("session_id", "")
        original_session = None
        if original_session_id:
            original_session = await self.get_session(original_session_id)

        # rebuild SkillSpec
        params = [SkillParameter(**p) for p in skill_doc.get("parameters", [])]
        expected_output_data = skill_doc.get("expected_output", {})
        expected_output = ExpectedOutput(**expected_output_data) if expected_output_data else ExpectedOutput()

        spec = SkillSpec(
            tool_id=skill_doc["tool_id"],
            display_name=skill_doc.get("display_name", ""),
            description=skill_doc.get("description", ""),
            category=skill_doc.get("category", "other"),
            data_source=skill_doc.get("data_source", ""),
            parameters=params,
            expected_output=expected_output,
            test_input=skill_doc.get("test_input", {}),
        )

        # Constructing Augmented Feedback: Raw Conversation Summaries + current code + User feedback
        enhanced_feedback = self._build_optimization_feedback(
            original_session=original_session,
            current_code=skill_doc.get("code", ""),
            user_feedback=feedback,
        )

        # Create optimization Session
        optimize_session = self._analyzer.create_session(
            user_id=skill_doc.get("user_id", "")
        )
        optimize_session.status = SessionStatus.GENERATING
        optimize_session.rounds.append(ConversationRound(
            round_number=1,
            user_message=f"[优化] {feedback}",
            ai_message="Start optimizing Skill...",
        ))
        optimize_session.spec = spec
        optimize_session.spec_confirmed = True
        await self._save_session(optimize_session)

        # Execute code generation pipeline (with feedback and previous_code)
        current_code = skill_doc.get("code", "")
        method_name = "run_agentic" if SKILL_GENERATION_AGENTIC_ENABLED else "run"
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: getattr(self._controller, method_name)(
                spec,
                initial_feedback=enhanced_feedback,
                initial_code=current_code,
            )
        )

        # Update optimization Session
        optimize_session.status = (
            SessionStatus.COMPLETED if result.success else SessionStatus.FAILED
        )
        optimize_session.pipeline_result = result
        await self._save_session(optimize_session)

        generation_context = None

        # If successful, update Skill
        if result.success:
            version = skill_doc.get("version", 1) + 1
            now = datetime.utcnow().isoformat()
            generation_context = self._build_session_recommendations(spec=spec, session=optimize_session)
            metadata = dict(result.final_metadata or {})
            metadata["generation_context"] = generation_context
            await self._db[SKILL_COLLECTION].update_one(
                {"tool_id": skill_id},
                {
                    "$set": {
                        "code": result.final_code,
                        "metadata": metadata,
                        "generation_context": generation_context,
                        "version": version,
                        "optimize_feedback": feedback,
                        "generation_rounds": result.total_rounds,
                        "generation_time": result.total_time,
                        "final_score": (
                            result.iterations[-1].eval_score.total
                            if result.iterations and result.iterations[-1].eval_score
                            else None
                        ),
                        "updated_at": now,
                    },
                    "$push": {
                        "optimize_session_ids": optimize_session.session_id,
                    },
                },
            )
            logger.info(f"✅ Skill '{skill_id}' 已优化到 v{version}")

        return {
            "status": "completed" if result.success else "failed",
            "skill_id": skill_id,
            "optimize_session_id": optimize_session.session_id,
            "success": result.success,
            "version": skill_doc.get("version", 1) + 1 if result.success else skill_doc.get("version", 1),
            "total_rounds": result.total_rounds,
            "total_time": result.total_time,
            "final_score": (
                result.iterations[-1].eval_score.total
                if result.iterations and result.iterations[-1].eval_score
                else None
            ),
            "generation_context": generation_context,
            "error": result.error,
        }

    @staticmethod
    def _build_optimization_feedback(
        original_session: Optional[Dict],
        current_code: str,
        user_feedback: str,
    ) -> str:
        """构建优化反馈上下文"""
        parts = []

        # Summary of original requirements communication
        if original_session and original_session.get("rounds"):
            parts.append("=== Original requirement communication record ===")
            for r in original_session["rounds"]:
                parts.append(f"[用户]: {r.get('user_message', '')}")
                parts.append(f"[AI]: {r.get('ai_message', '')}")

        # current code
        if current_code:
            parts.append(f"\n=== Current code (needs optimization)===\n```python\n{current_code}\n```")

        # User feedback
        parts.append(f"\n=== User optimization needs ===\n{user_feedback}")

        return "\n".join(parts)

    # ==================== internal tool methods ====================

    async def _load_session(self, session_id: str) -> Optional[SkillCreationSession]:
        """Load session from MongoDB"""
        doc = await self._db[SESSION_COLLECTION].find_one({"session_id": session_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return SkillCreationSession(**doc)

    async def _save_session(self, session: SkillCreationSession) -> None:
        """Save session to MongoDB"""
        session.updated_at = datetime.utcnow()
        session_doc = session.model_dump(mode="json")
        await self._db[SESSION_COLLECTION].update_one(
            {"session_id": session.session_id},
            {"$set": session_doc},
            upsert=True,
        )

    async def _save_skill(
        self,
        session: SkillCreationSession,
        spec: SkillSpec,
        result: PipelineResult,
    ) -> str:
        """Save the generated Skill to the external_skills collection"""
        now = datetime.utcnow().isoformat()
        generation_context = self._build_session_recommendations(spec=spec, session=session)
        role_metadata = self._infer_skill_role_metadata(spec, session)
        metadata = dict(result.final_metadata or {})
        metadata["generation_context"] = generation_context
        metadata.update({key: value for key, value in role_metadata.items() if value})
        skill_doc = {
            "tool_id": spec.tool_id,
            "display_name": spec.display_name,
            "description": spec.description,
            "category": spec.category,
            "data_source": spec.data_source,
            "parameters": [p.model_dump() for p in spec.parameters],
            "expected_output": spec.expected_output.model_dump(),
            # Persistence behavior/interface specification constraints: inherit the interface contract (including URL) from it during iterative upgrades,
            # Prevent the new version from losing the interface address, resulting in code generation and artifacts URL
            "constraints": list(spec.constraints or []),
            "code": result.final_code,
            "metadata": metadata,
            "test_input": spec.test_input,
            "generation_context": generation_context,
            "capability_tags": role_metadata.get("capability_tags") or [],
            "tool_role_hint": role_metadata.get("tool_role_hint") or "",
            "output_shape": role_metadata.get("output_shape") or "",
            "preferred_for": role_metadata.get("preferred_for") or [],
            "not_replacement_for": role_metadata.get("not_replacement_for") or [],
            "known_failure_summaries": metadata.get("known_failure_summaries") or [],
            "known_verified_facts": metadata.get("known_verified_facts") or [],
            "status": "active",
            "source": "generated",
            "session_id": session.session_id,
            "user_id": session.user_id,
            "generation_rounds": result.total_rounds,
            "generation_time": result.total_time,
            "final_score": (
                result.iterations[-1].eval_score.total
                if result.iterations and result.iterations[-1].eval_score
                else None
            ),
            "created_at": now,
            "updated_at": now,
        }

        # Reverse provenance: Skill writeback from Agent Studio gap filling origin_* Fields (Phase 2)
        handoff = session.handoff_context
        if handoff is not None:
            handoff_source = str(getattr(handoff, "source", "") or "").strip()
            if handoff_source in ("agent_studio_gap", "agent_workshop_gap"):
                skill_doc["origin_source"] = "agent_studio_auto_gap_resolution"
                skill_doc["origin_workshop_session_id"] = str(getattr(handoff, "workshop_session_id", "") or "")
                skill_doc["origin_spec_id"] = str(getattr(handoff, "spec_id", "") or getattr(handoff, "source_spec_id", "") or "")
                skill_doc["origin_version_id"] = str(getattr(handoff, "version_id", "") or "")
                skill_doc["origin_gap_id"] = str(getattr(handoff, "gap_id", "") or "")
                skill_doc["origin_agent_name"] = str(getattr(handoff, "agent_name", "") or getattr(handoff, "source_name", "") or "")

        # 🔧 Version management: Calculate the version number in iteration mode to ensure that tool_id matches _v{N} Naming rules
        is_iteration = bool(session.iterate_skill_id)
        if is_iteration:
            original_tool_id = session.iterate_skill_id or ""
            try:
                original = await self._db[SKILL_COLLECTION].find_one(
                    {"tool_id": original_tool_id}
                )
            except Exception as exc:
                logger.warning("[SkillGeneration][Iterate] Failed to query the original Skill, press New Process: %s", exc)
                original = None

            if original:
                # parent_skill_id Points to the root Skill (if the original Skill also has a parent, it will be used; otherwise, the original tool_id will be used)
                parent_skill_id = original.get("parent_skill_id") or original_tool_id

                # Find the current maximum version number (among all versions in the same series)
                try:
                    cursor = self._db[SKILL_COLLECTION].find({
                        "$or": [
                            {"tool_id": parent_skill_id},
                            {"parent_skill_id": parent_skill_id},
                        ]
                    }).sort("version", -1).limit(1)
                    max_docs = await cursor.to_list(1)
                    new_version = (max_docs[0].get("version", 1) + 1) if max_docs else 2
                except Exception as exc:
                    logger.warning("[SkillGeneration][Iterate] Failed to query version number, use default v2: %s", exc)
                    new_version = 2

                # Make sure tool_id follows naming rules:{parent_skill_id}_v{new_version}
                expected_tool_id = f"{parent_skill_id}_v{new_version}"
                if skill_doc["tool_id"] != expected_tool_id:
                    # LLM Constraints may not be adhered to, so corrections are mandatory here.
                    logger.info(
                        "[SkillGeneration][Iterate] Correction tool_id: %s → %s",
                        skill_doc["tool_id"],
                        expected_tool_id,
                    )
                    skill_doc["tool_id"] = expected_tool_id
                    spec.tool_id = expected_tool_id

                # Extract the version description (take the first 50 words of the first round of user messages in the session)
                version_note = ""
                if session.rounds:
                    version_note = (session.rounds[0].user_message or "")[:50]
                if not version_note:
                    version_note = "迭代优化"

                skill_doc["parent_skill_id"] = parent_skill_id
                skill_doc["version"] = new_version
                skill_doc["version_note"] = version_note
                skill_doc["iteration_session_id"] = session.session_id

                logger.info(
                    "[SkillGeneration][Iterate] iterative save: parent=%s, version=%d, tool_id=%s",
                    parent_skill_id,
                    new_version,
                    expected_tool_id,
                )
            else:
                # The original Skill does not exist and is downgraded to a new one.
                logger.warning(
                    "[SkillGeneration][Iterate] The original Skill %s does not exist and is downgraded to new",
                    original_tool_id,
                )
                skill_doc["version"] = 1
        else:
            skill_doc["version"] = 1

        await self._db[SKILL_COLLECTION].insert_one(skill_doc)
        logger.info(f"✅ Skill '{spec.tool_id}' Saved to database (version={skill_doc.get('version', 1)})")

        try:
            from core.tools.registry import get_tool_registry
            from core.tools.external_skill_loader import register_single_external_skill
            register_single_external_skill(None, get_tool_registry(), skill_doc)
            await CapabilityIndexService(self._db).ensure_index()
        except Exception as e:
            logger.warning(f"⚠️ Skill '{spec.tool_id}' Hot registration failed (takes effect after restart): {e}")

        return spec.tool_id


# ------------------------------------------------------------------
#  mem0 unified memory layer — Skill Build integration
# ------------------------------------------------------------------

def _build_skill_memory_metadata_filters(spec: SkillSpec) -> Optional[Dict[str, str]]:
    filters: Dict[str, str] = {}

    category = (spec.category or "").strip()
    data_source = (spec.data_source or "").strip()
    tool_id = (spec.tool_id or "").strip()

    if category:
        filters["category"] = category
    if data_source:
        filters["data_source"] = data_source
    if filters:
        return filters
    if tool_id:
        return {"tool_id": tool_id}
    return None


async def _recall_skill_lessons(db, spec: SkillSpec) -> str:
    """Historical lessons from recalling similar Skills from mem0"""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        query = f"{spec.description} {spec.data_source} {spec.category}"
        return await svc.recall_formatted(
            query=query.strip(),
            agent_id="skill_generator",
            scopes=["skill_lesson"],
            limit=10,
            max_chars=2000,
            metadata_filters=_build_skill_memory_metadata_filters(spec),
            ranking_profile="skill_generation",
            group_by_scope=True,
            per_scope_limit=5,
        )
    except Exception as e:
        logger.debug("[mem0] Skill Lesson recall failed: %s", e)
        return ""


async def _store_skill_lessons(db, spec: SkillSpec, result: PipelineResult) -> None:
    """Write the iteration lessons learned in this pipeline to mem0."""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)

        lessons = []
        metadata = dict(result.final_metadata or {})
        verified_facts = [str(item) for item in list(metadata.get("verified_facts") or []) if str(item).strip()]
        agentic_trace = metadata.get("agentic_trace") if isinstance(metadata.get("agentic_trace"), list) else []
        last_failure_summary = str(result.error or "").strip()
        if not last_failure_summary:
            for item in reversed(agentic_trace):
                if isinstance(item, dict) and str(item.get("failure_summary") or "").strip():
                    last_failure_summary = str(item.get("failure_summary") or "").strip()
                    break

        if last_failure_summary:
            lessons.append(
                f"Skill '{spec.tool_id}' ({spec.category}/{spec.data_source}) Agentic Failure summary: {last_failure_summary[:1200]}"
            )
        if verified_facts:
            lessons.append(
                f"Skill '{spec.tool_id}' 已验证环境事实: " + "；".join(verified_facts[:8])
            )
        for it in (result.iterations or []):
            if it.reflection and it.reflection.root_cause:
                lessons.append(
                    f"Skill '{spec.tool_id}' ({spec.category}/{spec.data_source}) "
                    f"No.{it.round_number}Round failed: {it.reflection.root_cause}"
                )

        if result.success:
            lessons.append(
                f"Skill '{spec.tool_id}' 最终在第{result.total_rounds}轮通过"
            )

        if not lessons:
            return

        messages = [{"role": "system", "content": "\n".join(lessons)}]
        await svc.store(
            messages,
            agent_id="skill_generator",
            scope="skill_lesson",
            metadata={
                "tool_id": spec.tool_id,
                "category": spec.category,
                "data_source": spec.data_source,
                "success": result.success,
                "total_rounds": result.total_rounds,
                "generation_engine": metadata.get("generation_engine", ""),
                "verified_fact_count": len(verified_facts),
            },
        )
    except Exception as e:
        logger.debug("[mem0] Skill Lesson storage failed: %s", e)


# === capability_index_service.py ===
import hashlib
import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

from app.models.capability_index import (
    CapabilityDocument,
    CapabilityIndexSyncResult,
    CapabilitySearchHit,
)
from core.agents.config import AgentMaintenanceStatus, BUILTIN_AGENTS
from core.llm.embedding_manager import EmbeddingManager
from core.memory.memory_manager import VectorStoreManager
from core.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)

CAPABILITY_INDEX_COLLECTION = "capability_registry"
CAPABILITY_INDEX_STATE_COLLECTION = "capability_index_state"
CAPABILITY_INDEX_STATE_KEY = "default"
CAPABILITY_INDEX_TOP_K = 24


class CapabilityIndexService:
    """Unified capability index service."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._embedding_manager = EmbeddingManager(db=db)
        self._vector_store_manager = VectorStoreManager()
        self._collection = None
        self._cached_documents: Dict[str, CapabilityDocument] = {}

    async def ensure_index(self, force: bool = False) -> CapabilityIndexSyncResult:
        documents, fingerprint, document_hashes = await self._collect_source_documents()
        state = await self._load_state()
        current_fingerprint = str(state.get("fingerprint") or "") if state else ""
        collection_count = int(state.get("indexed_documents") or 0) if state else 0
        previous_hashes = state.get("document_hashes") or {} if state else {}

        if not force and current_fingerprint == fingerprint and collection_count > 0:
            self._cached_documents = {doc.capability_id: doc for doc in documents}
            logger.info(
                "[CapabilityIndex] 📦 Index already exists, fingerprint matches, build skipped"
                " (%d tools / %d indexed / backends: %s) ",
                len(documents), collection_count, self._vector_store_manager.backend,
            )
            return CapabilityIndexSyncResult(
                collection_name=CAPABILITY_INDEX_COLLECTION,
                fingerprint=fingerprint,
                total_documents=len(documents),
                indexed_documents=collection_count,
                skipped_documents=max(len(documents) - collection_count, 0),
                vector_backend=self._vector_store_manager.backend,
                sync_mode="no_change",
            )

        # Check if embedding model is available
        config = self._embedding_manager.get_config()
        if not config.get("has_provider"):
            logger.warning(
                "[CapabilityIndex] ⚠️ The embedding model is not configured and index construction is skipped."
                " (%d tool will use keyword matching fallback)",
                len(documents),
            )
            self._cached_documents = {doc.capability_id: doc for doc in documents}
            return CapabilityIndexSyncResult(
                collection_name=CAPABILITY_INDEX_COLLECTION,
                fingerprint=fingerprint,
                total_documents=len(documents),
                indexed_documents=0,
                skipped_documents=len(documents),
                vector_backend=self._vector_store_manager.backend,
                sync_mode="skipped_no_embedding",
            )

        if force or not previous_hashes:
            # Pre-check: first test whether the first embedding call is successful
            # If the API Key is invalid or the network is unavailable, skip quickly to avoid long timeouts.
            test_embedding, _ = self._embedding_manager.get_embedding("test")
            if test_embedding is None:
                logger.warning(
                    "[CapabilityIndex] ⚠️ Embedding API Not available, skip index building"
                    " (%d tool will use keyword matching fallback)",
                    len(documents),
                )
                self._cached_documents = {doc.capability_id: doc for doc in documents}
                return CapabilityIndexSyncResult(
                    collection_name=CAPABILITY_INDEX_COLLECTION,
                    fingerprint=fingerprint,
                    total_documents=len(documents),
                    indexed_documents=0,
                    skipped_documents=len(documents),
                    vector_backend=self._vector_store_manager.backend,
                    sync_mode="skipped_embedding_unavailable",
                )
            logger.info(
                "[CapabilityIndex] 🔄 Starting index building (%d tools, vector dimensions: %d) ...",
                len(documents), self._embedding_manager.get_embedding_dimension(),
            )
            result = await asyncio.to_thread(self._rebuild_index, documents, fingerprint)
        else:
            logger.info(
                "[CapabilityIndex] 🔄 Incremental synchronization of indexes (%d tools, %d existing indexes)...",
                len(documents), collection_count,
            )
            result = await asyncio.to_thread(
                self._sync_index_incrementally,
                documents=documents,
                fingerprint=fingerprint,
                document_hashes=document_hashes,
                previous_hashes=previous_hashes,
                expected_count=collection_count,
            )

        await self._save_state(result, document_hashes)
        self._cached_documents = {doc.capability_id: doc for doc in documents}
        logger.info(
            "[CapabilityIndex] ✅ index ready: %d/%d Indexed, %d skipped, pattern: %s",
            result.indexed_documents, result.total_documents,
            result.skipped_documents, result.sync_mode,
        )
        return result

    async def search_capabilities(
        self,
        query: str,
        top_k: int = CAPABILITY_INDEX_TOP_K,
        bindable_only: bool = False,
        source_types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> List[CapabilitySearchHit]:
        await self.ensure_index()
        documents = list(self._cached_documents.values())
        if not documents:
            return []

        allowed_sources = set(source_types or [])
        allowed_categories = set(categories or [])
        filtered_documents = [
            doc for doc in documents
            if (not bindable_only or doc.bindable)
            and (not allowed_sources or doc.source_type in allowed_sources)
            and (not allowed_categories or doc.category in allowed_categories)
        ]
        if not filtered_documents:
            return []

        hits = self._vector_search(query, top_k=max(top_k * 4, top_k))
        search_method = "vector"
        if not hits:
            hits = self._lexical_search(query, filtered_documents, top_k=max(top_k * 4, top_k))
            search_method = "lexical"

        filtered: List[CapabilitySearchHit] = []
        allowed_ids = {doc.capability_id for doc in filtered_documents}
        for hit in hits:
            capability = hit.capability
            if capability.capability_id not in allowed_ids:
                continue
            filtered.append(hit)
            if len(filtered) >= top_k:
                break

        if len(filtered) < top_k and hits:
            lexical_hits = self._lexical_search(query, filtered_documents, top_k=max(top_k * 2, top_k))
            seen_ids = {hit.capability.capability_id for hit in filtered}
            for hit in lexical_hits:
                if hit.capability.capability_id in seen_ids:
                    continue
                filtered.append(hit)
                if len(filtered) >= top_k:
                    break
        logger.debug(
            "[CapabilityIndex] search method=%s query_len=%d results=%d top3=%s",
            search_method,
            len(query),
            len(filtered),
            [(h.capability.capability_id, round(float(h.score or 0), 3)) for h in filtered[:3]],
        )
        return filtered

    async def list_capabilities(self) -> List[CapabilityDocument]:
        await self.ensure_index()
        return list(self._cached_documents.values())

    async def rebuild_index(self) -> CapabilityIndexSyncResult:
        return await self.ensure_index(force=True)

    @staticmethod
    async def refresh_after_change(db) -> None:
        """Trigger index synchronization after tool changes (delete/add/modify) to clean up ghost tools.

        Incremental synchronization automatically detects and deletes tool vectors that no longer exist.
        No exceptions are thrown, only logs are logged on failure——The allowed_ids filtering when searching will give you a clue.
        """
        try:
            service = CapabilityIndexService(db)
            result = await service.ensure_index()
            logger.info(
                "[CapabilityIndex] Synchronization completed after tool change: mode=%s, total=%d, indexed=%d",
                result.sync_mode, result.total_documents, result.indexed_documents,
            )
        except Exception as e:
            logger.warning(f"[CapabilityIndex] Synchronization failed after tool change: {e}")

    async def get_index_state(self) -> Dict[str, Any]:
        state = await self._load_state()
        return state or {}

    async def _collect_source_documents(self) -> Tuple[List[CapabilityDocument], str, Dict[str, str]]:
        registry_docs = self._build_registry_documents()
        await self._merge_skills_documents(registry_docs)
        await self._merge_external_skills_documents(registry_docs)
        await self._merge_agents_documents(registry_docs)  # 🔥 v3.0: Agent Incorporate into unified capability index (including DB customization)

        documents = sorted(registry_docs.values(), key=lambda item: (item.source_type, item.capability_id))
        payload = [
            {
                "capability_id": doc.capability_id,
                "registry_tool_id": doc.registry_tool_id,
                "source_type": doc.source_type,
                "status": doc.status,
                "bindable": doc.bindable,
                "fc_enabled": doc.fc_enabled,
                "category": doc.category,
                "name": doc.name,
                "description": doc.description,
                "when_to_use": doc.when_to_use,
                "when_not_to_use": doc.when_not_to_use,
                "returns": doc.returns,
                "related_tools": doc.related_tools,
                "coverage_terms": doc.coverage_terms,
                "retrieval_text": doc.retrieval_text,
                "data_source": doc.data_source,
                "capability_tags": doc.capability_tags,
                "tool_role_hint": doc.tool_role_hint,
                "output_shape": doc.output_shape,
                "preferred_for": doc.preferred_for,
                "not_replacement_for": doc.not_replacement_for,
            }
            for doc in documents
        ]
        fingerprint = hashlib.sha1(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        document_hashes = {
            doc.capability_id: hashlib.sha1(
                json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            for doc in documents
        }
        return documents, fingerprint, document_hashes

    def _build_registry_documents(self) -> Dict[str, CapabilityDocument]:
        registry = get_tool_registry()
        documents: Dict[str, CapabilityDocument] = {}
        for tool in registry.list_all():
            tool_id = str(tool.id or "").strip()
            if not tool_id:
                continue
            source_type = "mcp_tool" if str(tool.category) == "mcp" else "builtin_tool"
            coverage_terms = self._extract_coverage_terms(self._build_searchable_text(
                tool_id,
                str(tool.name or ""),
                str(tool.description or ""),
                str(tool.when_to_use or ""),
                str(tool.when_not_to_use or ""),
                str(tool.returns or ""),
                str(tool.data_source or ""),
                " ".join(tool.related_tools or []),
            ))
            doc = CapabilityDocument(
                capability_id=tool_id,
                registry_tool_id=tool_id,
                source_type=source_type,
                status="active",
                bindable=True,
                fc_enabled=bool(tool.fc_enabled),
                category=str(tool.category or ""),
                name=str(tool.name or tool_id),
                label=f"{tool_id} | {tool.name}",
                description=str(tool.description or ""),
                when_to_use=str(tool.when_to_use or ""),
                when_not_to_use=str(tool.when_not_to_use or ""),
                returns=str(tool.returns or ""),
                related_tools=[str(item) for item in (tool.related_tools or []) if str(item).strip()],
                coverage_terms=coverage_terms,
                retrieval_text=self._build_retrieval_text(
                    tool_id=tool_id,
                    name=str(tool.name or tool_id),
                    source_type=source_type,
                    category=str(tool.category or ""),
                    description=str(tool.description or ""),
                    when_to_use=str(tool.when_to_use or ""),
                    when_not_to_use=str(tool.when_not_to_use or ""),
                    returns=str(tool.returns or ""),
                    related_tools=[str(item) for item in (tool.related_tools or []) if str(item).strip()],
                    data_source=str(tool.data_source or ""),
                    coverage_terms=coverage_terms,
                    capability_tags=[str(item) for item in (tool.capability_tags or []) if str(item).strip()],
                    tool_role_hint=str(tool.tool_role_hint or ""),
                    output_shape=str(tool.output_shape or ""),
                    preferred_for=[str(item) for item in (tool.preferred_for or []) if str(item).strip()],
                    not_replacement_for=[str(item) for item in (tool.not_replacement_for or []) if str(item).strip()],
                ),
                data_source=str(tool.data_source or ""),
                capability_tags=[str(item) for item in (tool.capability_tags or []) if str(item).strip()],
                tool_role_hint=str(tool.tool_role_hint or ""),
                output_shape=str(tool.output_shape or ""),
                preferred_for=[str(item) for item in (tool.preferred_for or []) if str(item).strip()],
                not_replacement_for=[str(item) for item in (tool.not_replacement_for or []) if str(item).strip()],
                metadata={
                    "is_online": bool(tool.is_online),
                    "timeout_tier": str(tool.timeout_tier or ""),
                    "parameters": [p.model_dump(mode="json") for p in (tool.parameters or [])],
                },
            )
            documents[tool_id] = doc
        return documents

    async def _merge_skills_documents(self, documents: Dict[str, CapabilityDocument]) -> None:
        cursor = self._db.skills.find({"enabled": True})
        async for doc in cursor:
            skill_name = str(doc.get("name") or "").strip()
            if not skill_name:
                continue
            tool_id = skill_name.replace("-", "_")
            description = str(doc.get("description") or "").strip()
            implementation = doc.get("implementation")
            parameters = doc.get("parameters") or []
            bindable = bool(implementation and parameters and tool_id in documents)

            base = documents.get(tool_id)
            merged = self._merge_capability_document(
                base=base,
                capability_id=tool_id,
                registry_tool_id=tool_id if tool_id in documents else None,
                source_type="skill",
                status="active",
                bindable=bindable,
                fc_enabled=bool(base.fc_enabled) if base else True,
                category=str(doc.get("category") or getattr(base, "category", "utility") or "utility"),
                name=skill_name,
                label=(base.label if base else f"{tool_id} | {skill_name}"),
                description=description or (base.description if base else ""),
                when_to_use=str(doc.get("when_to_use") or getattr(base, "when_to_use", "") or ""),
                when_not_to_use=str(doc.get("when_not_to_use") or getattr(base, "when_not_to_use", "") or ""),
                returns=str(doc.get("returns") or getattr(base, "returns", "") or ""),
                related_tools=list(getattr(base, "related_tools", []) or []),
                data_source=str(doc.get("data_source") or getattr(base, "data_source", "") or ""),
                capability_tags=list(getattr(base, "capability_tags", []) or []),
                tool_role_hint=str(getattr(base, "tool_role_hint", "") or ""),
                output_shape=str(getattr(base, "output_shape", "") or ""),
                preferred_for=list(getattr(base, "preferred_for", []) or []),
                not_replacement_for=list(getattr(base, "not_replacement_for", []) or []),
                metadata={
                    **(base.metadata if base else {}),
                    "skill_type": doc.get("skill_type"),
                    "source_url": doc.get("source_url"),
                },
            )
            documents[tool_id] = merged

    async def _merge_external_skills_documents(self, documents: Dict[str, CapabilityDocument]) -> None:
        cursor = self._db.external_skills.find({"status": {"$in": ["active", "draft"]}})
        async for doc in cursor:
            tool_id = str(doc.get("tool_id") or "").strip()
            if not tool_id:
                continue
            status = str(doc.get("status") or "draft")
            display_name = str(doc.get("display_name") or tool_id).strip()
            description = str(doc.get("description") or "").strip()
            base = documents.get(tool_id)
            bindable = status == "active" and tool_id in documents
            metadata = dict(doc.get("metadata") or {})
            capability_tags = self._dedupe([
                *list(getattr(base, "capability_tags", []) or []),
                *[str(item) for item in (doc.get("capability_tags") or metadata.get("capability_tags") or []) if str(item).strip()],
            ])
            tool_role_hint = str(doc.get("tool_role_hint") or metadata.get("tool_role_hint") or getattr(base, "tool_role_hint", "") or "").strip()
            output_shape = str(doc.get("output_shape") or metadata.get("output_shape") or getattr(base, "output_shape", "") or "").strip()
            preferred_for = self._dedupe([
                *list(getattr(base, "preferred_for", []) or []),
                *[str(item) for item in (doc.get("preferred_for") or metadata.get("preferred_for") or []) if str(item).strip()],
            ])
            not_replacement_for = self._dedupe([
                *list(getattr(base, "not_replacement_for", []) or []),
                *[str(item) for item in (doc.get("not_replacement_for") or metadata.get("not_replacement_for") or []) if str(item).strip()],
            ])
            merged = self._merge_capability_document(
                base=base,
                capability_id=tool_id,
                registry_tool_id=tool_id if tool_id in documents else None,
                source_type="external_skill",
                status=status,
                bindable=bindable,
                fc_enabled=bool(base.fc_enabled) if base else True,
                category=str(doc.get("category") or getattr(base, "category", "external") or "external"),
                name=display_name,
                label=(base.label if base else f"{tool_id} | {display_name}"),
                description=description or (base.description if base else ""),
                when_to_use=str(doc.get("when_to_use") or getattr(base, "when_to_use", "") or ""),
                when_not_to_use=str(doc.get("when_not_to_use") or getattr(base, "when_not_to_use", "") or ""),
                returns=str(doc.get("returns") or getattr(base, "returns", "") or ""),
                related_tools=list(getattr(base, "related_tools", []) or []),
                data_source=str(doc.get("data_source") or getattr(base, "data_source", "") or ""),
                capability_tags=capability_tags,
                tool_role_hint=tool_role_hint,
                output_shape=output_shape,
                preferred_for=preferred_for,
                not_replacement_for=not_replacement_for,
                metadata={
                    **(base.metadata if base else {}),
                    "session_id": doc.get("session_id"),
                    "source": doc.get("source"),
                },
            )
            documents[tool_id] = merged

    async def _merge_agents_documents(self, documents: Dict[str, CapabilityDocument]) -> None:
        """
        will BUILTIN_AGENTS + MongoDB Custom Agent merged into capability index

        Each Agent serves as an independent capability item,source_type="agent". 
        The built-in only collects the MAINTAINED status, and the DB only collects enabled=True of.
        """
        before_count = len(documents)
        # ── 1. Built-in Agent ──
        builtin_added = 0
        for agent_id, meta in BUILTIN_AGENTS.items():
            status = meta.maintenance_status
            if status not in (AgentMaintenanceStatus.MAINTAINED,):
                logger.debug(
                    "[CapabilityIndex] skip Agent: %s (status=%s)",
                    agent_id, status.value if hasattr(status, 'value') else status,
                )
                continue
            self._add_agent_document(
                documents, agent_id,
                name=meta.name,
                description=meta.description or "",
                category=meta.category.value if hasattr(meta.category, 'value') else str(meta.category),
                default_tools=list(meta.default_tools) if meta.default_tools else [],
                inputs=[i.name for i in meta.inputs] if meta.inputs else [],
                outputs=[o.name for o in meta.outputs] if meta.outputs else [],
                output_field=meta.output_field or "",
                source="builtin",
            )
            builtin_added += 1

        logger.info(
            "[CapabilityIndex] 📥 Agent Documentation: %d built-in, Total documents before merge %d, After merger %d",
            builtin_added, before_count, len(documents),
        )

        # ── 2. MongoDB Customize Agent ──
        if self._db is not None:
            try:
                builtin_ids = {agent_id for agent_id, _ in BUILTIN_AGENTS.items()}
                cursor = self._db.agent_configs.find({"enabled": True})
                async for doc in cursor:
                    aid = doc.get("agent_id", "").strip()
                    if not aid or aid in builtin_ids:
                        continue
                    self._add_agent_document(
                        documents, aid,
                        name=doc.get("name", aid),
                        description=doc.get("description", ""),
                        category=doc.get("category", "custom"),
                        default_tools=doc.get("default_tools", []) or [],
                        inputs=doc.get("inputs", []) or [],
                        outputs=doc.get("outputs", []) or [],
                        output_field=doc.get("output_field", doc.get("report_label", "")) or "",
                        source="database",
                    )
                    logger.info(
                        f"📥 [CapabilityIndex] Indexed custom Agent: {aid} ({doc.get('name', '')})"
                    )
            except Exception as e:
                logger.warning(f"Loading custom Agent from MongoDB to index fails: {e}")

    def _add_agent_document(
        self, documents: Dict[str, CapabilityDocument],
        agent_id: str, name: str, description: str, category: str,
        default_tools: list, inputs: list, outputs: list,
        output_field: str, source: str,
    ) -> None:
        """Build and index a CapabilityDocument for a single Agent"""
        safe_inputs = self._safe_list_to_str(inputs)
        safe_outputs = self._safe_list_to_str(outputs)
        safe_tools = self._safe_list_to_str(default_tools)

        when_to_use_parts = []
        if safe_inputs:
            when_to_use_parts.append(f"需要的输入: {', '.join(safe_inputs)}")
        if safe_outputs:
            when_to_use_parts.append(f"产生的输出: {', '.join(safe_outputs)}")
        if safe_tools:
            when_to_use_parts.append(f"默认工具: {', '.join(safe_tools)}")
        if output_field:
            when_to_use_parts.append(f"产出字段: {output_field}")

        documents[agent_id] = self._merge_capability_document(
            base=None,
            capability_id=agent_id,
            registry_tool_id=None,
            source_type="agent",
            status="active",
            bindable=True,
            fc_enabled=False,
            category=category,
            name=name,
            label=f"{agent_id} | {name}",
            description=description,
            when_to_use="; ".join(when_to_use_parts) if when_to_use_parts else "",
            when_not_to_use="",
            returns="报告文本",
            related_tools=list(safe_tools),
            data_source=source,
            capability_tags=list(safe_tools),
            tool_role_hint="agent",
            output_shape="report",
            preferred_for=[],
            not_replacement_for=[],
            metadata={
                "agent_id": agent_id,
                "source": source,
                "output_field": output_field,
                "default_tools": list(safe_tools),
                "has_inputs": len(safe_inputs) > 0,
                "has_outputs": len(safe_outputs) > 0,
            },
        )

    @staticmethod
    def _safe_list_to_str(items: list) -> List[str]:
        """Safely convert a list to a list of strings, handling dict elements and non-list input"""
        if not items:
            return []
        if not isinstance(items, list):
            return [str(items)]
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # Try to get common field names, if not, then str()
                for key in ("field", "name", "desc", "key", "label"):
                    if key in item:
                        result.append(str(item[key]))
                        break
                else:
                    result.append(str(item))
            else:
                result.append(str(item))
        return result

    def _merge_capability_document(
        self,
        base: Optional[CapabilityDocument],
        capability_id: str,
        registry_tool_id: Optional[str],
        source_type: str,
        status: str,
        bindable: bool,
        fc_enabled: bool,
        category: str,
        name: str,
        label: str,
        description: str,
        when_to_use: str,
        when_not_to_use: str,
        returns: str,
        related_tools: List[str],
        data_source: str,
        metadata: Dict[str, Any],
        capability_tags: Optional[List[str]] = None,
        tool_role_hint: str = "",
        output_shape: str = "",
        preferred_for: Optional[List[str]] = None,
        not_replacement_for: Optional[List[str]] = None,
    ) -> CapabilityDocument:
        searchable = self._build_searchable_text(
            capability_id,
            name,
            description,
            when_to_use,
            when_not_to_use,
            returns,
            data_source,
            " ".join(related_tools),
        )
        coverage_terms = self._extract_coverage_terms(searchable)
        return CapabilityDocument(
            capability_id=capability_id,
            registry_tool_id=registry_tool_id,
            source_type=source_type,
            status=status,
            bindable=bindable,
            fc_enabled=fc_enabled,
            category=category,
            name=name,
            label=label,
            description=description,
            when_to_use=when_to_use,
            when_not_to_use=when_not_to_use,
            returns=returns,
            related_tools=related_tools,
            coverage_terms=coverage_terms,
            retrieval_text=self._build_retrieval_text(
                tool_id=capability_id,
                name=name,
                source_type=source_type,
                category=category,
                description=description,
                when_to_use=when_to_use,
                when_not_to_use=when_not_to_use,
                returns=returns,
                related_tools=related_tools,
                data_source=data_source,
                coverage_terms=coverage_terms,
                capability_tags=capability_tags or [],
                tool_role_hint=tool_role_hint,
                output_shape=output_shape,
                preferred_for=preferred_for or [],
                not_replacement_for=not_replacement_for or [],
            ),
            data_source=data_source,
            capability_tags=self._dedupe([str(item) for item in (capability_tags or []) if str(item).strip()]),
            tool_role_hint=str(tool_role_hint or ""),
            output_shape=str(output_shape or ""),
            preferred_for=self._dedupe([str(item) for item in (preferred_for or []) if str(item).strip()]),
            not_replacement_for=self._dedupe([str(item) for item in (not_replacement_for or []) if str(item).strip()]),
            metadata=metadata,
        )

    def _build_retrieval_text(
        self,
        tool_id: str,
        name: str,
        source_type: str,
        category: str,
        description: str,
        when_to_use: str,
        when_not_to_use: str,
        returns: str,
        related_tools: List[str],
        data_source: str,
        coverage_terms: List[str],
        capability_tags: Optional[List[str]] = None,
        tool_role_hint: str = "",
        output_shape: str = "",
        preferred_for: Optional[List[str]] = None,
        not_replacement_for: Optional[List[str]] = None,
    ) -> str:
        parts = [
            f"tool_id: {tool_id}",
            f"name: {name}",
            f"source_type: {source_type}",
            f"category: {category}",
            f"description: {description}",
            f"when_to_use: {when_to_use}",
            f"when_not_to_use: {when_not_to_use}",
            f"returns: {returns}",
            f"related_tools: {' '.join(related_tools)}",
            f"data_source: {data_source}",
            f"coverage_terms: {' '.join(coverage_terms)}",
            f"capability_tags: {' '.join(capability_tags or [])}",
            f"tool_role_hint: {tool_role_hint}",
            f"output_shape: {output_shape}",
            f"preferred_for: {' '.join(preferred_for or [])}",
            f"not_replacement_for: {' '.join(not_replacement_for or [])}",
        ]
        return "\n".join(part for part in parts if part.strip())

    def _build_searchable_text(self, *parts: str) -> str:
        return " ".join(str(part or "").strip() for part in parts if str(part or "").strip()).lower()

    def _extract_coverage_terms(self, text: str) -> List[str]:
        import re

        searchable = str(text or "").lower()
        patterns = [
            # ── Valuation class ──
            (r"(?<![a-z0-9])(valuation|valuations)(?![a-z0-9])", "valuation"),
            (r"(?<![a-z0-9])dcf(?![a-z0-9])", "dcf"),
            (r"(?<![a-z0-9])pe(?![a-z0-9])|P/E ratio|pe_ttm|p/e", "pe"),
            (r"(?<![a-z0-9])pb(?![a-z0-9])|price to book ratio|pb_mrq", "pb"),
            (r"(?<![a-z0-9])peg(?![a-z0-9])", "peg"),
            (r"(?<![a-z0-9])ps(?![a-z0-9])", "ps"),
            (r"ev/?ebitda", "ev_ebitda"),
            (r"Comparable companies|Comparison with peers|peer comparison|peer", "peer_comparison"),
            (r"Valuation|Valuation|Pricing|target price|price range|Valuation range|relative valuation", "valuation_cn"),
            (r"growth|growth|Year-on-year revenue|Net profit year-on-year|cagr", "growth"),
            (r"cash flow|cashflow|fcf|ocf|operating cash flow|free cash flow", "cashflow"),
            (r"roe|roa|roic|Gross profit margin|net profit margin|profit margin|Profitability stability|capital efficiency|piotroski|altman|beneish", "quality"),
            (r"history|many years|annual report sequence|time series|trend|series", "historical_series"),
            (r"Quantile|percentile|Valuation quantile", "percentile"),
            (r"ma20|rsi14|rsi|kdj|macd|Technical indicators|technical", "technical"),
            # ── Asset Quality/Fundamental Risk ──
            (r"Accounts receivable|receivables|(?<![a-z0-9])dso(?![a-z0-9])|Aging|bad debts|bad_debt|Refund|Collection", "asset_quality_receivables"),
            (r"Inventory|inventory|(?<![a-z0-9])dio(?![a-z0-9])|inventory turnover|Falling price", "asset_quality_inventory"),
            (r"Asset quality|asset_quality|Asset impairment", "asset_quality"),
            (r"debt repayment|solvency|debt_to_equity|Asset-liability ratio|interest coverage|Interest protection|debt_structure|Interest-bearing liabilities", "solvency"),
            (r"Liquidity|liquidity|current_ratio|quick_ratio|current ratio|quick ratio|short term debt service", "liquidity"),
            (r"goodwill|goodwill|Impairment test|impairment", "goodwill"),
            (r"Bankruptcy|bankruptcy|ohlson|z_score|zscore|altman|beneish|mscore|oscore|Fraud|fraud|financial fraud|financial fraud|risk|risk_adjusted|risk_profile|risk_event|risk_flag", "risk"),
            # ── Cost of Capital / Risk Measurement / Portfolio / Attribution Analysis / Statistical Analysis ──
            (r"wacc|capm|cost_of_equity|cost_of_debt|discount rate|capital cost|weighted average cost of capital", "cost_of_capital"),
            (r"(?<![a-z0-9])beta(?![a-z0-9])|(?<![a-z0-9])alpha(?![a-z0-9])|sharpe|sortino|treynor|calmar|jensen|information_ratio|(?<![a-z0-9])var(?![a-z0-9])|cvar|volatility|Volatility|maximum drawdown|max_drawdown|downside|risk adjustment", "risk_metrics"),
            (r"portfolio|combination|efficient_frontier|monte_carlo|Monte Carlo|Markowitz|markowitz|optimal_weight|optimal weight|scenario_analysis|Scenario analysis", "portfolio"),
            (r"attribution|attribution|brinson|factor_attribution|sector_attribution", "attribution"),
            (r"correlation|cointegration|cointegration|regression|Return|normality|normal|stationarity|Smooth|(?<![a-z0-9])adf(?![a-z0-9])|garch|ewma|statistics|statistical", "statistics"),
            # ── Screening/Macro/Dividend/Chips/Volume and Price ──
            (r"screen|Filter|filter|filter|stock picking", "screening"),
            (r"macro|Macro|economic_cycle|business cycle|monetary|monetary environment|Merrill Lynch Clock|yield_curve|yield curve|prosperity|recession|recession|recovery|recovery|overheating|overheating|stagflation|stagflation", "macro"),
            (r"dividend|dividends|dividend|Bonus shares|bonus|dividend|Send for transfer|Dividend per share", "dividend"),
            (r"chip|chips|Profit ratio|average cost|Concentration", "chip_distribution"),
            (r"vwap|obv|turnover|turnover rate|Volume|Volume and price|volume_profile|Turnover|Main net inflow|capital flow|capital_flow|fund_flow", "volume_analysis"),
            # ── Technical Analysis Extension ──
            (r"pivot|support|resistance|pressure level|fibonacci|Fibonacci|pivot point|Neckline|trend line", "support_resistance"),
            (r"candlestick|k line|k line|chart_pattern|form|Head and shoulders|double top|double bottom|triangle|flag shape|Wedge|notch|Doji|hammer head", "chart_pattern"),
            # ── Bonds/Options/Event Research ──
            (r"bond|bonds|Duration|duration|Convexity|convexity|credit_spread|credit spread|national debt|corporate bonds|Convertible bonds", "bond"),
            (r"option|options|black_scholes|greeks|greek letters|delta|gamma|theta|vega|rho|implied_volatility|Implied volatility|exercise price|strike", "option"),
            (r"event_study|event study|event day|event driven|event_driven|Announcement event|regulatory events|event_timeline", "event_study"),
            # ── Financial Statements / ETFs / Insiders / Market Breadth / Securities Master Data ──
            (r"income_analysis|income statement|Revenue|Main business|main_business|income structure|cost analysis", "income_statement"),
            (r"financial_statement|financial statements|balance_sheet|balance sheet|financial_statements|fundamentals_unified|financial data", "financial_statements"),
            (r"(?<![a-z0-9])etf(?![a-z0-9])|Fund fundamentals", "etf_fundamentals"),
            (r"insider|insider|insiders|insider_sentiment|insider_transaction", "insider"),
            (r"market_breadth|market breadth|market_overview|Market overview|market_environment|market environment|market_cycle|market cycle|Number of stocks rising and falling|breadth|index_data|index data|sector_data|Sector data|sector_analysis|Sector analysis", "market_breadth"),
            (r"security_master|Securities master data|Listing status|stock_master|Securities information|exchange|Market value", "security_master"),
        ]
        matched: List[str] = []
        for pattern, normalized in patterns:
            if re.search(pattern, searchable):
                matched.append(normalized)
        return self._dedupe(matched)

    def _rebuild_index(
        self,
        documents: List[CapabilityDocument],
        fingerprint: str,
    ) -> CapabilityIndexSyncResult:
        try:
            self._vector_store_manager.delete_collection(CAPABILITY_INDEX_COLLECTION)
        except Exception:
            pass

        self._collection = self._vector_store_manager.get_or_create_collection(
            CAPABILITY_INDEX_COLLECTION,
            vector_size=self._embedding_manager.get_embedding_dimension(),
        )

        indexed = 0
        skipped = 0
        total = len(documents)
        batch_size = max(1, total // 10)  # Output progress every 10%
        consecutive_failures = 0  # 🔥 Continuous failure counter, if the threshold is exceeded, the remaining documents will be skipped
        max_consecutive_failures = 5
        for idx, document in enumerate(documents):
            embedding, provider = self._embedding_manager.get_embedding(document.retrieval_text)
            if embedding is None:
                skipped += 1
                consecutive_failures += 1
                # 🔥 If consecutive failures exceed the threshold, the remaining documents will be skipped to avoid long-term blocking.
                if consecutive_failures >= max_consecutive_failures:
                    remaining = total - idx - 1
                    logger.warning(
                        "[CapabilityIndex] ⚠️ %d consecutive failures, skipping remaining %d documents (Embedding API unavailable)",
                        consecutive_failures, remaining,
                    )
                    skipped += remaining
                    break
                continue
            consecutive_failures = 0  # Reset if successful
            metadata = document.model_dump(mode="json")
            metadata["embedding_provider"] = provider
            self._collection.add(
                documents=[document.retrieval_text],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[str(uuid.uuid5(uuid.NAMESPACE_DNS, document.capability_id))],
            )
            indexed += 1
            if indexed % batch_size == 0 or idx == total - 1:
                logger.info(
                    "[CapabilityIndex] Under construction... %d/%d (%d skip)",
                    indexed, total, skipped,
                )

        return CapabilityIndexSyncResult(
            collection_name=CAPABILITY_INDEX_COLLECTION,
            fingerprint=fingerprint,
            total_documents=len(documents),
            indexed_documents=indexed,
            skipped_documents=skipped,
            vector_backend=self._vector_store_manager.backend,
            sync_mode="full_rebuild",
        )

    def _sync_index_incrementally(
        self,
        documents: List[CapabilityDocument],
        fingerprint: str,
        document_hashes: Dict[str, str],
        previous_hashes: Dict[str, str],
        expected_count: int,
    ) -> CapabilityIndexSyncResult:
        self._collection = self._vector_store_manager.get_or_create_collection(
            CAPABILITY_INDEX_COLLECTION,
            vector_size=self._embedding_manager.get_embedding_dimension(),
        )

        current_count = self._collection.count()
        if expected_count > 0 and current_count == 0 and documents:
            logger.warning(
                "[CapabilityIndex] It is detected that the state exists but the vector set is empty, and the fallback is to full reconstruction.: expected=%s actual=%s",
                expected_count,
                current_count,
            )
            return self._rebuild_index(documents, fingerprint)

        docs_by_id = {doc.capability_id: doc for doc in documents}
        deleted_ids = sorted(set(previous_hashes.keys()) - set(document_hashes.keys()))
        changed_ids = sorted(
            capability_id
            for capability_id, doc_hash in document_hashes.items()
            if previous_hashes.get(capability_id) != doc_hash
        )

        deleted_count = 0
        if deleted_ids:
            point_ids = [self._build_point_id(capability_id) for capability_id in deleted_ids]
            if not self._collection.delete_ids(point_ids):
                logger.warning("[CapabilityIndex] Incremental deletion failed and fell back to full reconstruction.")
                return self._rebuild_index(documents, fingerprint)
            deleted_count = len(deleted_ids)

        upserted = 0
        skipped = 0
        consecutive_failures = 0  # 🔥 Continuous failure counter
        max_consecutive_failures = 5
        if changed_ids:
            upsert_documents: List[str] = []
            upsert_embeddings: List[List[float]] = []
            upsert_metadatas: List[Dict[str, Any]] = []
            upsert_ids: List[str] = []

            for capability_id in changed_ids:
                document = docs_by_id[capability_id]
                embedding, provider = self._embedding_manager.get_embedding(document.retrieval_text)
                if embedding is None:
                    skipped += 1
                    consecutive_failures += 1
                    # 🔥 If the continuous failure exceeds the threshold, the remaining change documents will be skipped.
                    if consecutive_failures >= max_consecutive_failures:
                        remaining = len(changed_ids) - len(upsert_ids) - skipped
                        logger.warning(
                            "[CapabilityIndex] ⚠️ Incremental sync failed %d times in a row, skipping remaining %d documents",
                            consecutive_failures, remaining,
                        )
                        skipped += remaining
                        break
                    continue
                consecutive_failures = 0  # Reset if successful
                metadata = document.model_dump(mode="json")
                metadata["embedding_provider"] = provider
                upsert_documents.append(document.retrieval_text)
                upsert_embeddings.append(embedding)
                upsert_metadatas.append(metadata)
                upsert_ids.append(self._build_point_id(document.capability_id))

            if upsert_ids and not self._collection.add(
                documents=upsert_documents,
                embeddings=upsert_embeddings,
                metadatas=upsert_metadatas,
                ids=upsert_ids,
            ):
                logger.warning("[CapabilityIndex] Incremental upsert fails and falls back to full rebuild")
                return self._rebuild_index(documents, fingerprint)
            upserted = len(upsert_ids)

        indexed_documents = self._collection.count()
        return CapabilityIndexSyncResult(
            collection_name=CAPABILITY_INDEX_COLLECTION,
            fingerprint=fingerprint,
            total_documents=len(documents),
            indexed_documents=indexed_documents,
            skipped_documents=skipped,
            vector_backend=self._vector_store_manager.backend,
            sync_mode="incremental_sync",
        )

    def _build_point_id(self, capability_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, capability_id))

    def _vector_search(self, query: str, top_k: int) -> List[CapabilitySearchHit]:
        if not query.strip():
            return []
        try:
            if self._collection is None:
                self._collection = self._vector_store_manager.get_or_create_collection(
                    CAPABILITY_INDEX_COLLECTION,
                    vector_size=self._embedding_manager.get_embedding_dimension(),
                )
            query_embedding, _provider = self._embedding_manager.get_embedding(query)
            if query_embedding is None:
                return []
            result = self._collection.query(query_embeddings=[query_embedding], n_results=top_k)
            hits: List[CapabilitySearchHit] = []
            documents = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            for _doc_text, metadata, distance in zip(documents, metadatas, distances):
                capability = CapabilityDocument.model_validate(metadata)
                hits.append(CapabilitySearchHit(capability=capability, score=round(1.0 - float(distance), 4)))
            return hits
        except Exception as exc:
            logger.warning("[CapabilityIndex] Vector retrieval failed, fallback to lexical retrieval: %s", exc)
            return []

    def _lexical_search(
        self,
        query: str,
        documents: Iterable[CapabilityDocument],
        top_k: int,
    ) -> List[CapabilitySearchHit]:
        tokens = [token for token in self._tokenize(query) if token]
        scored: List[CapabilitySearchHit] = []
        for doc in documents:
            haystack = self._build_searchable_text(
                doc.capability_id,
                doc.name,
                doc.description,
                doc.when_to_use,
                doc.returns,
                " ".join(doc.coverage_terms),
                " ".join(doc.capability_tags),
                " ".join(doc.preferred_for),
            )
            score = 0.0
            for token in tokens:
                if token in haystack:
                    score += 1.0
            if score > 0:
                scored.append(CapabilitySearchHit(capability=doc, score=score / max(len(tokens), 1)))
        scored.sort(key=lambda item: (-item.score, item.capability.label))
        return scored[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        import re

        pieces = re.split(r"[^0-9A-Za-z\u4e00-\u9fff_]+", str(text or "").lower())
        return [piece for piece in pieces if piece and len(piece) > 1]

    def _dedupe(self, items: List[str]) -> List[str]:
        seen = set()
        results = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            results.append(item)
        return results

    async def _load_state(self) -> Optional[Dict[str, Any]]:
        return await self._db[CAPABILITY_INDEX_STATE_COLLECTION].find_one({"_id": CAPABILITY_INDEX_STATE_KEY})

    async def _save_state(self, result: CapabilityIndexSyncResult, document_hashes: Dict[str, str]) -> None:
        payload = result.model_dump(mode="json")
        payload["_id"] = CAPABILITY_INDEX_STATE_KEY
        payload["document_hashes"] = document_hashes
        await self._db[CAPABILITY_INDEX_STATE_COLLECTION].update_one(
            {"_id": CAPABILITY_INDEX_STATE_KEY},
            {"$set": payload},
            upsert=True,
        )
