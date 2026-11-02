from .base_manager import DataSourceManager
from .us_manager import USDataSourceManager
from .hk_manager import HKDataSourceManager
ChinaDataSourceManager = USDataSourceManager
__all__ = ['DataSourceManager', 'USDataSourceManager', 'HKDataSourceManager', 'ChinaDataSourceManager']
