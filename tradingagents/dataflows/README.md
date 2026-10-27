# Dataflows Module architecture description

## 📁 Directory structure

```
tradingagents/dataflows/
├── cache/                           # Cache module
│   ├── file_cache.py               # File cache
│   ├── db_cache.py                 # database cache (MongoDB + Redis) 
│   ├── adaptive.py                 # Adaptive caching
│   ├── integrated.py               # Integrated cache
│   ├── app_adapter.py              # App cache adapter
│   └── mongodb_cache_adapter.py    # MongoDB cache adapter
│
├── providers/                       # data provider
│   ├── base_provider.py            # Basic provider class
│   ├── china/                      # Chinese market
│   │   ├── tushare.py             # Tushare provider
│   │   ├── akshare.py             # AKShare provider
│   │   ├── baostock.py            # Baostock provider
│   │   ├── tdx.py                 # Tongdaxin provider
│   │   └── fundamentals_snapshot.py # fundamental snapshot
│   ├── hk/                         # Hong Kong market
│   │   ├── hk_stock.py            # Hong Kong Stocks Provider
│   │   └── improved_hk.py         # Improved Hong Kong stock provider
│   ├── us/                         # US market
│   │   ├── yfinance.py            # Yahoo Finance
│   │   ├── finnhub.py             # Finnhub
│   │   └── optimized.py           # Optimized US stock provider
│   └── examples/                   # Example
│       └── example_sdk.py         # Sample SDK provider
│
├── news/                            # News module
│   ├── google_news.py              # Google News
│   ├── realtime_news.py            # real time news
│   ├── reddit.py                   # Reddit News
│   └── chinese_finance.py          # China financial sentiment analysis
│
├── technical/                       # Technical analysis module
│   └── stockstats.py               # Technical indicator calculation
│
├── data_source_manager.py           # ⭐ Core: Data source manager (including DataFrame interface)
├── interface.py                     # ⭐ Core: public interface
└── optimized_china_data.py          # ⭐ Core: Optimized A-share data provider

**Note**: Configuration management has been unified to `tradingagents/config/` Directory
```

---

## 🎯 Core file description

### 1. interface.py (60.25 KB) ⭐⭐⭐
**Responsibilities**: The public interface layer provides a unified entrance for all data acquisition.

**Main functions**:
- China market interface (6 functions)
  - `get_china_stock_data_unified()` - Unified A-share data acquisition
  - `get_china_stock_info_unified()` - Unified A-share information acquisition
  - `get_china_stock_data_tushare()` - Tushare data acquisition
  - `get_china_stock_fundamentals_tushare()` - Tushare fundamental data
  - `switch_china_data_source()` - Switch data source
  - `get_current_china_data_source()` - Get the current data source

- Hong Kong market interface (2 functions)
  - `get_hk_stock_data_unified()` - Unified Hong Kong stock data acquisition
  - `get_hk_stock_info_unified()` - Unified acquisition of Hong Kong stock information

- US market interface (7 functions)
  - `get_finnhub_news()` - Finnhub News
  - `get_YFin_data()` - Yahoo Finance data
  - `get_fundamentals_finnhub()` - Finnhub fundamental data
  - Wait

- News interface (5 functions)
  - `get_google_news()` - Google News
  - `get_reddit_global_news()` - Reddit global news
  - `get_stock_news_openai()` - OpenAI news analysis
  - Wait

- Technical analysis interface (2 functions)
  - `get_stockstats_indicator()` - Technical indicator calculation

**Usage scenarios**: Agent Tool functions, API routing, business logic

**Depend on**: data_source_manager, providers, news, technical

---

### 2. data_source_manager.py (67.81 KB) ⭐⭐⭐
**Responsibilities**: Data source manager, responsible for unified management and automatic degradation of multiple data sources

**Main functions**:
- Data source management
  - Support multiple data sources:MongoDB, Tushare, AKShare, Baostock, TDX
  - Automatic downgrade mechanism
  - Data source switching

- Cache management
  - Unified cache interface
  - Automatically cache data
  - Cache invalidation

- data acquisition
  - `get_china_stock_data_unified()` - Unified A-share data acquisition
  - `get_china_stock_info_unified()` - Unified A-share information acquisition
  - `get_fundamentals_data()` - Fundamental data acquisition

**Usage scenarios**: interface.py The underlying implementation of

**Depend on**: providers, cache

---

### 3. optimized_china_data.py (67.68 KB) ⭐⭐⭐
**Responsibilities**: Optimized A-share data provider, providing caching and fundamental analysis functions

**Main functions**:
- Optimized data acquisition
  - `get_china_stock_data_cached()` - Cached stock data retrieval
  - `get_china_fundamentals_cached()` - Cached fundamental data retrieval

- fundamental analysis
  - `_generate_fundamentals_report()` - Generate fundamental analysis report
  - Calculation of financial indicators
  - Valuation analysis

**Usage scenarios**: 
- Agent Tool function (agent_utils.py)
- Market Analyst (market_analyst.py)
- Web Cache management (cache_management.py)

**Depend on**: cache, providers

---

## 📊 Auxiliary file description

### 4. stock_data_service.py (12.14 KB)
**Responsibilities**: Stock data service, implementation MongoDB → TDX downgrade mechanism

**Main functions**:
- `StockDataService` class
- `get_stock_basic_info()` - Get basic stock information
- MongoDB → TDX Downgrade

**Usage scenarios**:
- `tradingagents/api/stock_api.py`
- `tradingagents/dataflows/stock_api.py`
- `app/routers/stock_data.py`
- `app/worker/` service

**Differences from data_source_manager**:
- `stock_data_service`: focus on MongoDB → TDX Downgrade
- `data_source_manager`: Support more data sources (Tushare/AKShare/Baostock)

---

### 5. stock_api.py (3.91 KB)
**Responsibilities**: Simplified stock API interface

**Main functions**:
- `get_stock_info()` - Get individual stock information
- `get_all_stocks()` - Get a list of all stocks

**Usage scenarios**: `app/services/simple_analysis_service.py`

**Differences from interface.py**:
- `stock_api`: Simplified interface, suitable for simple scenarios
- `interface.py`: Complete interface, supports all functions

---

### 6. unified_dataframe.py (5.77 KB)
**Responsibilities**: Unify the DataFrame format and support multiple data source degradation

**Main functions**:
- `get_china_daily_df_unified()` - Unified A-share daily data acquisition
- Multiple data source downgrade:Tushare → AKShare → Baostock
- DataFrame Format standardization

**Usage scenarios**: `app/services/screening_service.py`

**Differences from data_source_manager**:
- `unified_dataframe`: Returns a DataFrame, suitable for data analysis
- `data_source_manager`: Returns a formatted string suitable for Agent use

---

### 7. providers_config.py (9.29 KB)
**Responsibilities**: Data source provider configuration management

**Main functions**:
- `DataSourceConfig` class
- Manage the configuration of all data sources (Tushare/AKShare/Baostock/TDX/Finnhub, etc.)
- Environment variable reading
- Configuration verification

**Usage scenarios**: 
- `app/core/unified_config.py`
- `app/models/config.py`
- `app/routers/config.py`
- `app/services/config_service.py`

**Differences from config.py**:
- `providers_config`: Data source provider configuration
- `config.py`: Dataflows Module general configuration

---

### 8. config.py (2.32 KB)
**Responsibilities**: Dataflows Common configuration management of modules

**Main functions**:
- `initialize_config()` - Initial configuration
- `set_config()` - Set configuration
- `get_config()` - Get configuration
- `DATA_DIR` - data directory

**Usage scenarios**: `optimized_china_data.py`

---

### 9. utils.py (1.17 KB)
**Responsibilities**: General utility functions

**Main functions**:
- `save_output()` - Save DataFrame to CSV
- `get_current_date()` - Get current date
- `decorate_all_methods()` - Decorator
- `get_next_weekday()` - Get next working day

**Usage scenarios**: `tradingagents/utils/news_filter_integration.py`

---

## 🔄 Usage suggestions

### For new feature development

1. **Get stock data**:
   - Recommended: `interface.get_china_stock_data_unified()`
   - alternative: `data_source_manager.get_china_stock_data_unified()`

2. **Get fundamental data**:
   - Recommended: `optimized_china_data.get_china_fundamentals_cached()`
   - alternative: `interface.get_china_stock_fundamentals_tushare()`

3. **Data analysis scenario**:
   - Recommended: `unified_dataframe.get_china_daily_df_unified()`
   - Returns a DataFrame, suitable for pandas operations

4. **Simple query scenario**:
   - Recommended: `stock_api.get_stock_info()`
   - Simplify the interface and quickly obtain basic information

### For maintenance and refactoring

1. **Large file problem**:
   - `interface.py`, `data_source_manager.py`, `optimized_china_data.py` All are core files
   - It is recommended to maintain the status quo and avoid the risks caused by large-scale refactoring
   - If optimization is needed, use progressive refactoring

2. **Functional overlap**:
   - Different files serve different scenarios, and overlap is reasonable.
   - `data_source_manager`: Agent Scenario (return string)
   - `unified_dataframe`: Data analysis scenario (return DataFrame)
   - `stock_data_service`: MongoDB → TDX Downgrade scenario

3. **Configuration management**:
   - `providers_config.py`: Data source configuration (widely used, reserved)
   - `config.py`: Dataflows Common configuration (reserved)

---

## 📚 Related documents

- `docs/CACHE_CONFIGURATION.md` - Cache configuration guide
- `docs/CACHE_REFACTORING_SUMMARY.md` - Summary of caching system reconstruction
- `docs/UTILS_CLEANUP_SUMMARY.md` - Utils File cleaning summary
- `docs/TUSHARE_ADAPTER_REFACTORING.md` - Tushare Adapter Refactoring summary
- `docs/ADAPTER_PROVIDER_REORGANIZATION.md` - Adapter and Provider file reorganization summary
- `docs/DATAFLOWS_ARCHITECTURE_ANALYSIS.md` - Dataflows Architecture analysis
- `docs/DATAFLOWS_CONSERVATIVE_REFACTORING.md` - Dataflows Conservative optimization summary

---

## 🎯 design principles

1. **backwards compatible**: Keep existing interfaces unchanged
2. **progressive refactoring**: Avoid large-scale changes
3. **Segregation of duties**: Use different files for different scenarios
4. **Documentation first**: Document the architecture rather than forcing refactoring

---

**last updated**: 2025-10-01

