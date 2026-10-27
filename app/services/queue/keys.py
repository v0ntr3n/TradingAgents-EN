"""
Redis key names and configuration constants used by queue services (centrally defined)
"""

# Redis Key name constant
READY_LIST = "qa:ready"

TASK_PREFIX = "qa:task:"
BATCH_PREFIX = "qa:batch:"
SET_PROCESSING = "qa:processing"
SET_COMPLETED = "qa:completed"
SET_FAILED = "qa:failed"
BATCH_TASKS_PREFIX = "qa:batch_tasks:"

# Concurrency control related
USER_PROCESSING_PREFIX = "qa:user_processing:"
GLOBAL_CONCURRENT_KEY = "qa:global_concurrent"
VISIBILITY_TIMEOUT_PREFIX = "qa:visibility:"

# Configuration Constants - Open Source Edition Limitations
DEFAULT_USER_CONCURRENT_LIMIT = 3
GLOBAL_CONCURRENT_LIMIT = 3  # The global maximum concurrency limit of the open source version is 3
VISIBILITY_TIMEOUT_SECONDS = 300  # 5 minutes

