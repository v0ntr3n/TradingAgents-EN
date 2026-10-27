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
