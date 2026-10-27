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
                "message": f"Skill SKILL.md file not found in package",
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
