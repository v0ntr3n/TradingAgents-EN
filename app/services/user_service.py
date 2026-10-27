"""
User Services - Database-based user management
"""

import atexit
import hashlib
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import bcrypt
from pymongo import MongoClient
from bson import ObjectId

from app.core.config import settings
from app.models.user import User, UserCreate, UserUpdate, UserResponse

# Try importing log manager
try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    # If the import fails, use standard logging
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger('user_service')


# Legacy SHA-256 hash prefix used to identify existing passwords that need to be upgraded
# SHA-256 Output is a 64-bit hexadecimal string; the bcrypt hash begins with $2 Beginning
_LEGACY_SHA256_PREFIX = "sha256:"
_BCRYPT_PREFIX = "$2"


class UserService:
    """用户服务类"""

    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGO_DB]
        self.users_collection = self.db.users
        self._closed = False
        atexit.register(self._close_at_exit)

    def close(self, log: bool = True):
        """关闭数据库连接"""
        if self._closed:
            return

        if hasattr(self, 'client') and self.client:
            try:
                self.client.close()
            except Exception:
                pass

        self._closed = True

        if log and sys.meta_path is not None:
            try:
                logger.info("UserService MongoDB connection closed")
            except Exception:
                pass

    def _close_at_exit(self):
        """When the interpreter exits normally, the connection is closed and no log is written."""
        try:
            self.close(log=False)
        except Exception:
            pass

    def __del__(self):
        """Destructor, ensuring that the connection is closed and no logs are written during the interpreter shutdown phase."""
        try:
            self.close(log=False)
        except Exception:
            pass
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Password hash (using bcrypt + Automatically add salt)

        The return value is `$2` At the beginning, you can pass `bcrypt.checkpw` verify.
        Compatible with legacy SHA-256 hashes (automatically recognized and upgraded upon verification).
        """
        # bcrypt With built-in salt, the hash result of the same password is different every time, preventing rainbow table attacks.
        # rounds=12 Is the OWASP 2023 recommended value (about 250ms/hash)
        rounds = getattr(settings, "BCRYPT_ROUNDS", 12)
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def _hash_legacy_sha256(password: str) -> str:
        """Legacy SHA-256 hash (no salt, only used to verify existing passwords)"""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_bcrypt_hash(hashed: str) -> bool:
        """Determine whether it is a bcrypt hash (with $2 beginning)"""
        return bool(hashed) and hashed.startswith(_BCRYPT_PREFIX)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password

        Automatically recognizes bcrypt hashes and legacy SHA-256 hashes:
        - bcrypt Hash: Verify using bcrypt.checkpw
        - Legacy SHA-256 hash: Use SHA-256 comparison (caller is responsible for upgrading after successful verification)
        """
        if not hashed_password:
            return False
        if UserService._is_bcrypt_hash(hashed_password):
            try:
                return bcrypt.checkpw(
                    plain_password.encode("utf-8"),
                    hashed_password.encode("utf-8"),
                )
            except (ValueError, TypeError):
                return False
        # Legacy SHA-256 (unsalted) compatible paths
        return UserService._hash_legacy_sha256(plain_password) == hashed_password
    
    async def create_user(self, user_data: UserCreate) -> Optional[User]:
        """创建用户"""
        try:
            # Check if username already exists
            existing_user = self.users_collection.find_one({"username": user_data.username})
            if existing_user:
                logger.warning(f"用户名已存在: {user_data.username}")
                return None
            
            # Check if the mailbox already exists
            existing_email = self.users_collection.find_one({"email": user_data.email})
            if existing_email:
                logger.warning(f"邮箱已存在: {user_data.email}")
                return None
            
            # Create user documentation
            user_doc = {
                "username": user_data.username,
                "email": user_data.email,
                "hashed_password": self.hash_password(user_data.password),
                "is_active": True,
                "is_verified": False,
                "is_admin": False,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": None,
                "preferences": {
                    # Analyze preferences
                    "default_market": "A股",
                    "default_depth": "3",  # 1-5 level, level 3 is standard analysis (recommended)
                    "default_analysts": ["市场分析师", "基本面分析师"],
                    "auto_refresh": True,
                    "refresh_interval": 30,
                    # Appearance settings
                    "ui_theme": "light",
                    "sidebar_width": 240,
                    # language and region
                    "language": "zh-CN",
                    # Notification settings
                    "notifications_enabled": True,
                    "email_notifications": False,
                    "desktop_notifications": True,
                    "analysis_complete_notification": True,
                    "system_maintenance_notification": True
                },
                "daily_quota": 1000,
                "concurrent_limit": 3,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": []
            }
            
            result = self.users_collection.insert_one(user_doc)
            user_doc["_id"] = result.inserted_id
            
            logger.info(f"✅ 用户创建成功: {user_data.username}")
            return User(**user_doc)
            
        except Exception as e:
            logger.error(f"❌ 创建用户失败: {e}")
            return None
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """用户认证"""
        try:
            logger.info(f"🔍 [authenticate_user] Start authenticating users: {username}")

            # Find users
            user_doc = self.users_collection.find_one({"username": username})
            logger.info(f"🔍 [authenticate_user] Database query results: {'Find user' if user_doc else 'User does not exist'}")

            if not user_doc:
                logger.warning(f"❌ [authenticate_user] User does not exist: {username}")
                return None

            logger.info(f"🔍 [authenticate_user] User information: username={user_doc.get('username')}, email={user_doc.get('email')}, is_active={user_doc.get('is_active')}")

            # Verify password (automatically recognizes bcrypt / legacy SHA-256)
            stored_hash = user_doc.get("hashed_password", "")
            # ⚠️ Security: Do not log any password hashes (even prefixes)
            logger.info(f"🔍 [authenticate_user] Store password hash type: {'bcrypt' if self._is_bcrypt_hash(stored_hash) else 'legacy_sha256' if stored_hash else 'empty'}")

            if not self.verify_password(password, stored_hash):
                logger.warning(f"❌ [authenticate_user] Wrong password: {username}")
                return None

            # 🔐 Older SHA-256 hashes are automatically upgraded to bcrypt (transparent upgrade, no user awareness)
            if not self._is_bcrypt_hash(stored_hash):
                try:
                    new_bcrypt_hash = self.hash_password(password)
                    self.users_collection.update_one(
                        {"_id": user_doc["_id"]},
                        {"$set": {
                            "hashed_password": new_bcrypt_hash,
                            "updated_at": datetime.utcnow(),
                            "password_hash_algo": "bcrypt",
                        }}
                    )
                    logger.info(f"🔐 [authenticate_user] Legacy SHA-256 ciphers have been automatically upgraded to bcrypt: {username}")
                except Exception as upgrade_err:
                    # Failure to upgrade does not affect login, but alarms need to be logged.
                    logger.warning(f"⚠️ [authenticate_user] Password hash upgrade failed (login continues): {username} error={upgrade_err}")

            # Check if user is activated
            if not user_doc.get("is_active", True):
                logger.warning(f"❌ [authenticate_user] User disabled: {username}")
                return None

            # Update last login time
            self.users_collection.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"last_login": datetime.utcnow()}}
            )

            logger.info(f"✅ [authenticate_user] User authentication successful: {username}")
            return User(**user_doc)

        except Exception as e:
            logger.error(f"❌ 用户认证失败: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        try:
            user_doc = self.users_collection.find_one({"username": username})
            if user_doc:
                return User(**user_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据用户ID获取用户"""
        try:
            if not ObjectId.is_valid(user_id):
                return None
            
            user_doc = self.users_collection.find_one({"_id": ObjectId(user_id)})
            if user_doc:
                return User(**user_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None
    
    async def update_user(self, username: str, user_data: UserUpdate) -> Optional[User]:
        """更新用户信息"""
        try:
            update_data = {"updated_at": datetime.utcnow()}
            
            # Only update provided fields
            if user_data.email:
                # Check if the mailbox is already used by another user
                existing_email = self.users_collection.find_one({
                    "email": user_data.email,
                    "username": {"$ne": username}
                })
                if existing_email:
                    logger.warning(f"邮箱已被使用: {user_data.email}")
                    return None
                update_data["email"] = user_data.email
            
            if user_data.preferences:
                update_data["preferences"] = user_data.preferences.model_dump()
            
            if user_data.daily_quota is not None:
                update_data["daily_quota"] = user_data.daily_quota
            
            if user_data.concurrent_limit is not None:
                update_data["concurrent_limit"] = user_data.concurrent_limit
            
            result = self.users_collection.update_one(
                {"username": username},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户信息更新成功: {username}")
                return await self.get_user_by_username(username)
            else:
                logger.warning(f"用户不存在或无需更新: {username}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 更新用户信息失败: {e}")
            return None
    
    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改密码"""
        try:
            # Verify old password
            user = await self.authenticate_user(username, old_password)
            if not user:
                logger.warning(f"旧密码验证失败: {username}")
                return False
            
            # Update password
            new_hashed_password = self.hash_password(new_password)
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 密码修改成功: {username}")
                return True
            else:
                logger.error(f"❌ 密码修改失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 修改密码失败: {e}")
            return False
    
    async def reset_password(self, username: str, new_password: str) -> bool:
        """重置密码（管理员操作）"""
        try:
            new_hashed_password = self.hash_password(new_password)
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 密码重置成功: {username}")
                return True
            else:
                logger.error(f"❌ 密码重置失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 重置密码失败: {e}")
            return False
    
    async def create_admin_user(
        self,
        username: str = "admin",
        password: Optional[str] = None,  # 🔥 Changed to optional and must be specified via environment variables or parameters
        email: str = "admin@tradingagents.cn"
    ) -> Optional[User]:
        """Create admin user
        
        ⚠️ Security warning: No more hard-coded default passwords.
        The password must be specified in one of the following ways:
        1. Specified by parameter password
        2. Specified through the environment variable ADMIN_DEFAULT_PASSWORD
        
        If neither is specified, ValueError will be thrown.
        """
        # 🔥 Get passwords from environment variables or parameters, no longer using hardcoded defaults
        if password is None:
            import os
            password = os.getenv("ADMIN_DEFAULT_PASSWORD")
        
        if password is None:
            raise ValueError(
                "Creating an administrator user must specify a password. Please set environment variables ADMIN_DEFAULT_PASSWORD "
                "or calling create_admin_user() Pass in the password parameter."
            )
        
        # Check password strength (at least 8 characters)
        if len(password) < 8:
            logger.warning(f"⚠️ The administrator password is not long enough ({len(password)} bits), at least 8 bits recommended")
        
        try:
            # Check if an administrator already exists
            existing_admin = self.users_collection.find_one({"username": username})
            if existing_admin:
                logger.info(f"管理员用户已存在: {username}")
                return User(**existing_admin)
            
            # Create administrator user document
            admin_doc = {
                "username": username,
                "email": email,
                "hashed_password": self.hash_password(password),
                "is_active": True,
                "is_verified": True,
                "is_admin": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": None,
                "preferences": {
                    "default_market": "A股",
                    "default_depth": "深度",
                    "ui_theme": "light",
                    "language": "zh-CN",
                    "notifications_enabled": True,
                    "email_notifications": False
                },
                "daily_quota": 10000,  # Higher quota for administrators
                "concurrent_limit": 10,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": []
            }
            
            result = self.users_collection.insert_one(admin_doc)
            admin_doc["_id"] = result.inserted_id

            logger.info(f"✅ 管理员用户创建成功: {username}")
            # ⚠️ Security: It is forbidden to output clear text passwords in the log; the password has been passed in through the environment variable, please record it yourself.
            logger.info("   🔐 The password has been encrypted and stored using bcrypt. Please keep the administrator password you set properly.")
            logger.info("   ⚠️  It is recommended to change your password immediately after logging in for the first time!")

            return User(**admin_doc)
            
        except Exception as e:
            logger.error(f"❌ 创建管理员用户失败: {e}")
            return None
    
    async def list_users(self, skip: int = 0, limit: int = 100) -> List[UserResponse]:
        """获取用户列表"""
        try:
            cursor = self.users_collection.find().skip(skip).limit(limit)
            users = []
            
            for user_doc in cursor:
                user = User(**user_doc)
                users.append(UserResponse(
                    id=str(user.id),
                    username=user.username,
                    email=user.email,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    created_at=user.created_at,
                    last_login=user.last_login,
                    preferences=user.preferences,
                    daily_quota=user.daily_quota,
                    concurrent_limit=user.concurrent_limit,
                    total_analyses=user.total_analyses,
                    successful_analyses=user.successful_analyses,
                    failed_analyses=user.failed_analyses
                ))
            
            return users
            
        except Exception as e:
            logger.error(f"❌ 获取用户列表失败: {e}")
            return []
    
    async def deactivate_user(self, username: str) -> bool:
        """禁用用户"""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户已禁用: {username}")
                return True
            else:
                logger.warning(f"用户不存在: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 禁用用户失败: {e}")
            return False
    
    async def activate_user(self, username: str) -> bool:
        """激活用户"""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "is_active": True,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户已激活: {username}")
                return True
            else:
                logger.warning(f"用户不存在: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 激活用户失败: {e}")
            return False

    # =========================================================================
    # JD Cloud Basic Auth User — Automatically create files + Old users return
    # =========================================================================

    async def get_or_create_jdyun_user(self, jdyun_username: str, is_admin: bool = True) -> Optional[User]:
        """
        JD Cloud Cooperation Edition: Obtain or create JD Cloud user records.

        Background:
          - Each request of JD Cloud Gateway proxy will bring Authorization: Basic base64(username:token)
          - username It is the unique user identification assigned by JD Cloud platform (such as jcloud-ugidvcp / jdcloud-pid-test)
          - token It is the access token generated by the JD Cloud platform for the user (not the login password, which is decoupled from the user password)
          - We need to maintain a corresponding record in the users collection so that business functions such as tasks/reports/permissions can work properly
             (because 30+ The code needs to be user["id"] Convert to MongoDB ObjectId)

        Logic:
          1. Find in the users collection by username
          2. Found (old users): Update last_login → Return the user (real ObjectId)
          3. Not found (new user): insert a new record (is_admin=true, password hash placeholder,provider=jdyun) 
                      → Returns the user just created (real ObjectId)

        Args:
            jdyun_username: JD Cloud Platform Basic Auth decoded username
            is_admin: JD Cloud users are regarded as administrators by default (default True)

        Returns:
            User Model instance (id is a legal MongoDB ObjectId), returned on failure None
        """
        if not jdyun_username or not jdyun_username.strip():
            return None
        username = jdyun_username.strip()
        try:
            existing = self.users_collection.find_one({"username": username})
            if existing:
                # ===== Old users: Refresh last_login =====
                self.users_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"last_login": datetime.utcnow(), "updated_at": datetime.utcnow()}},
                )
                existing["last_login"] = datetime.utcnow()
                logger.info(f"✅ [JD Cloud] Old user login: {username} (id={existing['_id']})")
                return User(**existing)

            # ===== New users: automatic profile creation =====
            # Password hash placeholder: The real access token is kept and verified by JD Cloud Gateway, we do not need to store it
            # Use bcrypt to hash a random string as a placeholder (anti-violence, also ensure that the User model hashed_password field is not empty)
            placeholder_password = f"__jdyun__{ObjectId()}__"  # Random and different every time
            hashed_placeholder = self.hash_password(placeholder_password)

            # Email adopts username@jdyun.local (Ensure that the email format is legal and unique)
            safe_email = f"{username.replace('@', '_at_')}@jdyun.local"

            new_user_doc = {
                "username": username,
                "email": safe_email,
                "hashed_password": hashed_placeholder,
                "password_hash_algo": "bcrypt",
                "is_active": True,
                "is_verified": True,          # Those certified by JD Cloud Platform are deemed to have been verified.
                "is_admin": is_admin,
                "provider": "jdyun",          # Source identification: JD Cloud Cooperation Edition
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": datetime.utcnow(),
                "preferences": {
                    "assistant_settings": {"name": "分析助理", "tone": "professional", "custom_instructions": ""},
                    "default_market": "A股",
                    "default_depth": "3",
                    "default_analysts": ["市场分析师", "基本面分析师"],
                    "auto_refresh": True,
                    "refresh_interval": 30,
                    "risk_preference": "neutral",
                    "ui_theme": "light",
                    "sidebar_width": 240,
                    "language": "zh-CN",
                    "notifications_enabled": True,
                    "email_notifications": False,
                    "desktop_notifications": True,
                    "analysis_complete_notification": True,
                    "system_maintenance_notification": True,
                },
                "daily_quota": 1000,
                "concurrent_limit": 3,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": [],
            }
            result = self.users_collection.insert_one(new_user_doc)
            new_user_doc["_id"] = result.inserted_id
            logger.info(
                f"✅ [JD Cloud] New user automatically created profile successfully: {username} "
                f"(id={result.inserted_id}, admin={is_admin})"
            )
            return User(**new_user_doc)

        except Exception as e:
            logger.error(f"❌ [JD Cloud] User profile failed username={username}: {e}", exc_info=True)
            return None

    def is_existing_jdyun_user(self, jdyun_username: str) -> bool:
        """
        Check whether you are a registered JD Cloud user (old user).

        For Basic Auth hierarchical verification:
          - Already created (old user)→ Only verify username, not token (token is variable)
          - Not created (new user)→ Must be strictly verified username + token (Anti-counterfeiting)

        Args:
            jdyun_username: JD Cloud Platform Basic Auth decoded username

        Returns:
            Returns True if archived, otherwise False
        """
        if not jdyun_username or not jdyun_username.strip():
            return False
        try:
            doc = self.users_collection.find_one({
                "username": jdyun_username.strip(),
                "provider": "jdyun",
            })
            return doc is not None
        except Exception as e:
            logger.error(f"❌ [JD Cloud] Failed to query user username={jdyun_username}: {e}")
            return False


async def bootstrap_first_admin() -> bool:
    """First boot boot: When the users collection is empty, create an initial administrator based on ADMIN_DEFAULT_PASSWORD.

    The community version is not open for registration. The first login account is created by this guide (the password comes from .env
    ADMIN_DEFAULT_PASSWORD, Corresponds to the .env.example annotation). Only triggered when the library is empty,
    No existing accounts will be overwritten or modified.
    """
    try:
        if user_service.users_collection.count_documents({}) > 0:
            return False

        import os
        password = os.getenv("ADMIN_DEFAULT_PASSWORD")
        if not password:
            logger.warning(
                "⚠️ The user collection is empty and ADMIN_DEFAULT_PASSWORD is not set, skipping initial administrator creation."
                "Please set ADMIN_DEFAULT_PASSWORD (at least 8 bits) in .env and then restart the backend to complete the initialization."
            )
            return False

        admin = await user_service.create_admin_user(password=password)
        if admin:
            logger.info("✅ Initial administrator account has been created: admin, Please change your password immediately after logging in for the first time")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ 初始管理员引导失败: {e}")
        return False


# Global user service instance
user_service = UserService()
