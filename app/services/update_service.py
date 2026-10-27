"""
Automatic update service

Function:
1. Check the official website to see if there is a new version
2. Download update package (with progress tracking)
3. Verify update package (SHA256)
4. Trigger updater script (standalone process)
"""
import os
import json
import hashlib
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Default update server address (used when configured as empty)
DEFAULT_UPDATE_BASE_URL = "https://www.tradingagentscn.com/api"


class UpdateInfo:
    """更新信息"""

    def __init__(self, data: dict):
        self.has_update: bool = data.get("has_update", False)
        self.latest_version: str = data.get("version", "")
        self.package_type: str = self._normalize_package_type(data.get("package_type"))
        self.download_url: str = data.get("download_url", "")
        self.file_size: int = data.get("file_size", 0)
        self.sha256: str = data.get("sha256", "")
        self.release_notes: str = data.get("release_notes", "")
        self.release_date: str = data.get("release_date", "")
        self.is_mandatory: bool = data.get("is_mandatory", False)
        self.min_version: str = data.get("min_version", "")
        self.check_failed: bool = data.get("check_failed", False)
        self.error_message: str = data.get("error_message", "")

    def to_dict(self) -> dict:
        return {
            "has_update": self.has_update,
            "latest_version": self.latest_version,
            "package_type": self.package_type,
            "download_url": self.download_url,
            "file_size": self.file_size,
            "sha256": self.sha256,
            "release_notes": self.release_notes,
            "release_date": self.release_date,
            "is_mandatory": self.is_mandatory,
            "min_version": self.min_version,
            "check_failed": self.check_failed,
            "error_message": self.error_message,
        }

    @staticmethod
    def _normalize_package_type(package_type: Optional[str]) -> str:
        raw = (package_type or "installer").strip().lower()
        return raw if raw in {"installer", "update"} else "installer"


class UpdateService:
    """自动更新服务"""

    # Update package download directory
    UPDATES_DIR = PROJECT_ROOT / "runtime" / "updates"

    # Backup directory
    BACKUP_DIR = PROJECT_ROOT / "backup"

    def __init__(self):
        # Read update check address from configuration, support UPDATE_CHECK_BASE_URL coverage in .env (for test verification)
        url = (settings.UPDATE_CHECK_BASE_URL or "").strip()
        self.base_url = url if url else DEFAULT_UPDATE_BASE_URL
        self.channel = self._normalize_update_channel(settings.UPDATE_CHECK_CHANNEL)
        self._download_progress: Dict[str, Any] = {}
        # Make sure the directory exists
        self.UPDATES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Version information ──────────────────────────────────────────

    def get_current_version(self) -> str:
        """读取当前版本号"""
        version_file = PROJECT_ROOT / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            return "0.0.0"

    def get_build_info(self) -> dict:
        """读取构建信息"""
        build_file = PROJECT_ROOT / "BUILD_INFO"
        try:
            raw = build_file.read_text(encoding="utf-8-sig").strip()
            return json.loads(raw)
        except Exception:
            return {}

    def get_update_channel(self) -> str:
        """获取当前更新通道"""
        return self.channel

    # ── Check for updates ──────────────────────────────────────────

    async def check_for_updates(self) -> UpdateInfo:
        """向官网查询是否有新版本"""
        current_version = self.get_current_version()
        build_info = self.get_build_info()

        logger.info(
            f"🔍 检查更新... 当前版本: {current_version}, 通道: {self.channel}"
        )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/app/check-update",
                    params={
                        "version": current_version,
                        "build_type": build_info.get("build_type", "unknown"),
                        "channel": self.channel,
                    },
                    headers={"User-Agent": f"TradingAgentsCN/{current_version}"},
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        info = UpdateInfo(data.get("data", {}))
                        if info.has_update:
                            logger.info(
                                f"📦 发现新版本: {info.latest_version}"
                            )
                        else:
                            logger.info("✅ 已是最新版本")
                        return info

                logger.warning(f"⚠️ Check for updates failed: HTTP {resp.status_code}")
                return UpdateInfo({
                    "has_update": False,
                    "check_failed": True,
                    "error_message": f"Update server returns error (HTTP {resp.status_code})",
                })

        except httpx.ConnectError:
            logger.warning("⚠️ 无法连接更新服务器")
            return UpdateInfo({
                "has_update": False,
                "check_failed": True,
                "error_message": "Unable to connect to update server, please check the network or try again later",
            })
        except httpx.TimeoutException:
            logger.warning("⚠️ 连接更新服务器超时")
            return UpdateInfo({
                "has_update": False,
                "check_failed": True,
                "error_message": "The connection to the update server timed out, please try again later.",
            })
        except Exception as e:
            logger.error(f"❌ 检查更新异常: {e}")
            return UpdateInfo({
                "has_update": False,
                "check_failed": True,
                "error_message": f"检查更新失败: {str(e)}",
            })

    # ── Download update package ────────────────────────────────────────

    async def download_update(self, update_info: UpdateInfo) -> Optional[Path]:
        """Download the update package and return the local file path"""
        if not update_info.download_url:
            logger.error("❌ 下载地址为空")
            return None

        version = update_info.latest_version
        filename = self._build_download_filename(update_info)
        target_path = self.UPDATES_DIR / filename

        # If it has been downloaded and verified, return directly.
        if target_path.exists() and update_info.sha256:
            if self._verify_sha256(target_path, update_info.sha256):
                logger.info(f"✅ The update package already exists and the verification passed.: {filename}")
                return target_path

        logger.info(f"⬇️ 开始下载更新包: {update_info.download_url}")
        self._download_progress = {
            "status": "downloading",
            "version": version,
            "total": update_info.file_size,
            "downloaded": 0,
            "percent": 0,
        }

        try:
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                async with client.stream("GET", update_info.download_url) as resp:
                    if resp.status_code != 200:
                        logger.error(f"❌ 下载失败: HTTP {resp.status_code}")
                        self._download_progress["status"] = "failed"
                        return None

                    total = int(resp.headers.get("content-length", 0)) or update_info.file_size
                    self._download_progress["total"] = total
                    downloaded = 0

                    with open(target_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            self._download_progress["downloaded"] = downloaded
                            if total > 0:
                                self._download_progress["percent"] = round(
                                    downloaded * 100 / total, 1
                                )

            # Verification
            if update_info.sha256:
                if not self._verify_sha256(target_path, update_info.sha256):
                    logger.error("❌ Update package verification failed, SHA256 does not match")
                    target_path.unlink(missing_ok=True)
                    self._download_progress["status"] = "verify_failed"
                    return None

            self._download_progress["status"] = "completed"
            self._download_progress["percent"] = 100
            logger.info(f"✅ 更新包下载完成: {filename} ({downloaded} bytes)")
            return target_path

        except Exception as e:
            logger.error(f"❌ 下载更新包异常: {e}")
            self._download_progress["status"] = "failed"
            target_path.unlink(missing_ok=True)
            return None

    def get_download_progress(self) -> dict:
        """获取下载进度"""
        return dict(self._download_progress) if self._download_progress else {
            "status": "idle",
            "percent": 0,
        }

    def get_download_message(self, update_info: UpdateInfo) -> str:
        """Generate download prompts based on package type."""
        if update_info.package_type == "installer":
            return f"发现 v{update_info.latest_version} 安装包，请下载安装后手动升级"
        return f"开始下载 v{update_info.latest_version} 更新包"

    # ── Apply updates ──────────────────────────────────────────

    async def apply_update(self, update_file: Path, version: str) -> dict:
        """
        Starts a standalone updater process and then notifies the caller that the application needs to exit.

        The update process is handled by scripts/updater/apply_update.ps1:
        1. Wait for the backend process to exit
        2. Back up current version
        3. Unzip the update package
        4. Restart all services
        """
        if not update_file.exists():
            return {"success": False, "message": "更新包文件不存在"}

        updater_script = PROJECT_ROOT / "scripts" / "updater" / "apply_update.ps1"
        if not updater_script.exists():
            return {"success": False, "message": "更新器脚本不存在"}

        current_version = self.get_current_version()
        logger.info(f"🚀 启动更新: {current_version} → {version}")

        try:
            # Start a standalone PowerShell updater process
            cmd = [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", str(updater_script),
                "-UpdateFile", str(update_file),
                "-TargetVersion", version,
                "-CurrentVersion", current_version,
                "-ProjectRoot", str(PROJECT_ROOT),
            ]

            # CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS Make the updater independent of the backend process
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008

            subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info("✅ The updater process has been started and the backend is about to exit...")
            return {
                "success": True,
                "message": f"更新器已启动，正在从 {current_version} 更新到 {version}",
            }

        except Exception as e:
            logger.error(f"❌ 启动更新器失败: {e}")
            return {"success": False, "message": f"启动更新器失败: {e}"}

    # ── clean up ──────────────────────────────────────────────

    def cleanup_old_packages(self, keep_latest: int = 2):
        """Clean up old update packages and keep the latest N ones"""
        if not self.UPDATES_DIR.exists():
            return

        files = sorted(
            self.UPDATES_DIR.glob("update-*.zip"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        for f in files[keep_latest:]:
            try:
                f.unlink()
                logger.info(f"🗑️ 清理旧更新包: {f.name}")
            except Exception as e:
                logger.warning(f"⚠️ 清理失败: {f.name} - {e}")

    # ── internal method ──────────────────────────────────────────

    @staticmethod
    def _build_download_filename(update_info: UpdateInfo) -> str:
        """Infer local file names based on download address and package type."""
        parsed = httpx.URL(update_info.download_url)
        basename = Path(parsed.path).name.strip()
        if basename:
            return basename
        extension = ".exe" if update_info.package_type == "installer" else ".zip"
        prefix = "installer" if update_info.package_type == "installer" else "update"
        return f"{prefix}-{update_info.latest_version}{extension}"

    @staticmethod
    def _normalize_update_channel(channel: Optional[str]) -> str:
        """Normalize the update channel to avoid server-side distribution inconsistency caused by alias configuration."""
        raw = (channel or "").strip().lower()
        alias_map = {
            "": "stable",
            "stable": "stable",
            "formal": "stable",
            "prod": "stable",
            "production": "stable",
            "release": "stable",
            "official": "stable",
            "正式": "stable",
            "线上": "stable",
            "test": "test",
            "testing": "test",
            "beta": "test",
            "staging": "test",
            "preview": "test",
            "测试": "test",
            "预发": "test",
        }
        normalized = alias_map.get(raw)
        if normalized:
            return normalized

        logger.warning("⚠️ Unrecognized update channel configuration '%s', Reverted to stable", channel)
        return "stable"

    @staticmethod
    def _verify_sha256(file_path: Path, expected_hash: str) -> bool:
        """校验文件 SHA256"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha256.update(data)
        actual = sha256.hexdigest()
        match = actual.lower() == expected_hash.lower()
        if not match:
            logger.warning(
                f"SHA256 no match: expected={expected_hash[:16]}... actual={actual[:16]}..."
            )
        return match


# Singleton
_update_service: Optional[UpdateService] = None


def get_update_service() -> UpdateService:
    """获取更新服务单例"""
    global _update_service
    if _update_service is None:
        _update_service = UpdateService()
    return _update_service
