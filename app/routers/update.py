"""
Automatically update API routes

Endpoint:
- GET  /api/system/update/check     Check for updates
- GET  /api/system/update/progress   Get download progress
- POST /api/system/update/download   Download update package
- POST /api/system/update/apply      Apply updates
- GET  /api/system/update/info       Get current version information
"""
import os
import sys
import signal
import logging
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends

from app.services.update_service import get_update_service, UpdateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system/update")


def _is_docker_env() -> bool:
    """Detect if running inside Docker container."""
    if os.environ.get("DOCKER", "").lower() in ("1", "true", "yes"):
        return True
    if Path("/.dockerenv").exists():
        return True
    if os.environ.get("DOCKER_CONTAINER") == "true":
        return True
    return False


def _supports_in_app_update(build_type: str) -> bool:
    """Windows portable/installer supports in-app update; Docker does not."""
    if _is_docker_env():
        return False
    return build_type in ("portable", "installer")


@router.get("/info")
async def get_version_info():
    """Get current version and build information"""
    svc = get_update_service()
    build_info = svc.get_build_info()
    # Prefer version from BUILD_INFO (build-time source of truth), fallback to VERSION file
    current_version = (build_info.get("version") or "").strip() or svc.get_current_version()
    build_type = build_info.get("build_type") or "unknown"
    is_docker = _is_docker_env()
    supports_in_app_update = _supports_in_app_update(build_type)
    return {
        "success": True,
        "data": {
            "current_version": current_version,
            "build_info": build_info,
            "update_channel": svc.get_update_channel(),
            "is_docker": is_docker,
            "supports_in_app_update": supports_in_app_update,
        },
        "message": "ok",
    }


@router.get("/check")
async def check_update():
    """Check if there is a new version"""
    svc = get_update_service()
    info = await svc.check_for_updates()
    return {
        "success": True,
        "data": info.to_dict(),
        "message": "new version found" if info.has_update else "Already the latest version",
    }


@router.get("/progress")
async def get_download_progress():
    """Get download progress"""
    svc = get_update_service()
    return {
        "success": True,
        "data": svc.get_download_progress(),
        "message": "ok",
    }


# Cache the latest check result to avoid repeated requests during download
_last_update_info = None


@router.post("/download")
async def download_update():
    """Download the update package (only supported by Windows portable/installation version)"""
    global _last_update_info

    svc = get_update_service()
    build_type = svc.get_build_info().get("build_type") or "unknown"
    if not _supports_in_app_update(build_type):
        if _is_docker_env():
            return {
                "success": False,
                "data": None,
                "message": "Docker Deployment does not support in-app updates, please use docker pull to obtain the latest image",
            }
        return {
            "success": False,
            "data": None,
            "message": "In-app updates are not supported for the current build type",
        }

    # Check for updates first
    info = await svc.check_for_updates()
    if not info.has_update:
        return {
            "success": False,
            "data": None,
            "message": "No updates available",
        }

    _last_update_info = info

    if info.package_type == "installer":
        return {
            "success": True,
            "data": {
                "version": info.latest_version,
                "file_size": info.file_size,
                "package_type": info.package_type,
                "download_url": info.download_url,
            },
            "message": svc.get_download_message(info),
        }

    # Background download (no blocking response)
    asyncio.create_task(_do_download(svc, info))

    return {
        "success": True,
        "data": {
            "version": info.latest_version,
            "file_size": info.file_size,
            "package_type": info.package_type,
            "download_url": info.download_url,
        },
        "message": svc.get_download_message(info),
    }


async def _do_download(svc: UpdateService, info):
    """Download in the background"""
    try:
        result = await svc.download_update(info)
        if result:
            logger.info(f"✅ Update package download completed: {result}")
        else:
            logger.error("❌ Update package download failed")
    except Exception as e:
        logger.error(f"❌ Download exception: {e}")


@router.post("/apply")
async def apply_update():
    """Apply updates (launch updater, then exit backend; supported on Windows Portable/Installed editions only)"""
    global _last_update_info

    svc = get_update_service()
    build_type = svc.get_build_info().get("build_type") or "unknown"
    if not _supports_in_app_update(build_type):
        if _is_docker_env():
            return {
                "success": False,
                "data": None,
                "message": "Docker Deployment does not support in-app updates, please use docker pull to obtain the latest image",
            }
        return {
            "success": False,
            "data": None,
            "message": "In-app updates are not supported for the current build type",
        }
    progress = svc.get_download_progress()

    if progress.get("status") != "completed":
        return {
            "success": False,
            "data": None,
            "message": "Please download the update package first",
        }

    # Find the downloaded update package
    if not _last_update_info:
        return {
            "success": False,
            "data": None,
            "message": "Update information is lost, please check for updates again",
        }

    version = _last_update_info.latest_version
    if _last_update_info.package_type != "update":
        return {
            "success": False,
            "data": None,
            "message": "The current version provides an installation package. Please download the installation package and complete the upgrade manually.",
        }

    update_file = svc.UPDATES_DIR / svc._build_download_filename(_last_update_info)

    if not update_file.exists():
        return {
            "success": False,
            "data": None,
            "message": "The update package file does not exist, please download it again",
        }

    # Start the updater
    result = await svc.apply_update(update_file, version)

    if result["success"]:
        # After giving the front-end a response, delay exiting the back-end process
        asyncio.get_event_loop().call_later(3, _shutdown)

    return {
        "success": result["success"],
        "data": None,
        "message": result["message"],
    }


def _shutdown():
    """Gracefully exit the backend process"""
    logger.info("🛑 The backend process is about to exit, waiting for the updater to take over...")
    os._exit(0)

