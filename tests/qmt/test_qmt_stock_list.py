import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

os.environ["LOGURU_AUTOINIT"] = "0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

from app.core.config import get_settings
from app.services.data_sources.qmt_adapter import QMTAdapter


def run_test():
    logger.info("=" * 80)
    logger.info("QMTAdapter.get_stock_list() independent testing")
    logger.info("=" * 80)

    print()

    settings = get_settings()

    logger.info(f"QMT_UNIFIED_ENABLED: {settings.QMT_UNIFIED_ENABLED}")
    logger.info(f"QMT_DATA_DIR: {settings.QMT_DATA_DIR}")
    logger.info(f"QMT_LISTEN_PORT_RANGE: {settings.QMT_LISTEN_PORT_RANGE}")

    print()

    t0 = time.perf_counter()
    logger.info("1. initialization QMTAdapter")
    adapter = QMTAdapter()
    t1 = time.perf_counter()
    logger.info(f"✅ QMTAdapter Initialization completed, time consuming {t1 - t0:.2f}s")

    print()

    logger.info("2. Check is_available")
    t2 = time.perf_counter()
    available = adapter.is_available()
    t3 = time.perf_counter()
    logger.info(f"is_available: {available}")
    logger.info(f"✅ is_available completed, time consuming {t3 - t2:.2f}s")

    if not available:
        logger.warning("QMTAdapter Unavailable, end test early")
        return

    print()

    logger.info("3. Call get_stock_list (not allowed to automatically download sections/details to quickly get stock codes)")
    t4 = time.perf_counter()
    try:
        stocks = adapter.get_stock_list()
    except Exception as e:
        logger.exception(f"❌ get_stock_list throw exception: {e}")
        return
    t5 = time.perf_counter()

    print()

    logger.info("=" * 80)
    logger.info("get_stock_list() result")
    logger.info(f"Total time spent: {t5 - t4:.2f}s")
    logger.info(f"Return quantity: {len(stocks)}")
    logger.info(f"Top 10 stocks: {stocks[:10]}")
    logger.info("=" * 80)

    if stocks:
        print()
        logger.info("=" * 80)
        logger.info("Stock list example (top 20)")
        for idx, s in enumerate(stocks[:20], 1):
            print(f"  {idx:2d}. {s.symbol} {s.name}")
        logger.info("=" * 80)

    print()
    logger.info("✅ QMT get_stock_list End of test")


if __name__ == "__main__":
    run_test()
