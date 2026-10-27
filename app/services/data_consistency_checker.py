"""
Data consistency checking and processing services
Handle data inconsistencies between multiple data sources
"""
import logging
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class DataConsistencyResult:
    """数据一致性检查结果"""
    is_consistent: bool
    primary_source: str
    secondary_source: str
    differences: Dict[str, Any]
    confidence_score: float
    recommended_action: str
    details: Dict[str, Any]

@dataclass
class FinancialMetricComparison:
    """财务指标比较结果"""
    metric_name: str
    primary_value: Optional[float]
    secondary_value: Optional[float]
    difference_pct: Optional[float]
    is_significant: bool
    tolerance: float

class DataConsistencyChecker:
    """数据一致性检查器"""
    
    def __init__(self):
        # Set tolerance thresholds for various indicators
        self.tolerance_thresholds = {
            'pe': 0.05,      # PE Allow 5% difference
            'pb': 0.05,      # PB Allow 5% difference
            'total_mv': 0.02, # Market capitalization allows 2% difference
            'price': 0.01,   # Stock price allows 1% difference
            'volume': 0.10,  # 10% difference allowed in trading volume
            'turnover_rate': 0.05  # A 5% difference is allowed in turnover rate
        }
        
        # Key metric weights (used to calculate confidence scores)
        self.metric_weights = {
            'pe': 0.25,
            'pb': 0.25,
            'total_mv': 0.20,
            'price': 0.15,
            'volume': 0.10,
            'turnover_rate': 0.05
        }
    
    def check_daily_basic_consistency(
        self, 
        primary_data: pd.DataFrame, 
        secondary_data: pd.DataFrame,
        primary_source: str,
        secondary_source: str
    ) -> DataConsistencyResult:
        """
        Check the consistency of daily_basic data
        
        Args:
            primary_data: Master data source data
            secondary_data: secondary data source data
            primary_source: Primary data source name
            secondary_source: Secondary data source name
        """
        try:
            logger.info(f"🔍 检查数据一致性: {primary_source} vs {secondary_source}")
            
            # 1. basic check
            if primary_data.empty or secondary_data.empty:
                return DataConsistencyResult(
                    is_consistent=False,
                    primary_source=primary_source,
                    secondary_source=secondary_source,
                    differences={'error': 'One or both datasets are empty'},
                    confidence_score=0.0,
                    recommended_action='use_primary_only',
                    details={'reason': 'Empty dataset detected'}
                )
            
            # 2. Stock symbol matching
            common_stocks = self._find_common_stocks(primary_data, secondary_data)
            if len(common_stocks) == 0:
                return DataConsistencyResult(
                    is_consistent=False,
                    primary_source=primary_source,
                    secondary_source=secondary_source,
                    differences={'error': 'No common stocks found'},
                    confidence_score=0.0,
                    recommended_action='use_primary_only',
                    details={'reason': 'No overlapping stocks'}
                )
            
            logger.info(f"📊 找到{len(common_stocks)}只共同股票进行比较")
            
            # 3. Indicator-by-Indicator Comparison
            metric_comparisons = []
            for metric in ['pe', 'pb', 'total_mv']:
                comparison = self._compare_metric(
                    primary_data, secondary_data, common_stocks, metric
                )
                if comparison:
                    metric_comparisons.append(comparison)
            
            # 4. Calculate overall consistency
            consistency_result = self._calculate_overall_consistency(
                metric_comparisons, primary_source, secondary_source
            )
            
            return consistency_result
            
        except Exception as e:
            logger.error(f"❌ 数据一致性检查失败: {e}")
            return DataConsistencyResult(
                is_consistent=False,
                primary_source=primary_source,
                secondary_source=secondary_source,
                differences={'error': str(e)},
                confidence_score=0.0,
                recommended_action='use_primary_only',
                details={'exception': str(e)}
            )
    
    def _find_common_stocks(self, df1: pd.DataFrame, df2: pd.DataFrame) -> List[str]:
        """Find common stocks in two datasets"""
        # Try different ticker listings
        code_cols = ['ts_code', 'symbol', 'code', 'stock_code']
        
        df1_codes = set()
        df2_codes = set()
        
        for col in code_cols:
            if col in df1.columns:
                df1_codes.update(df1[col].dropna().astype(str).tolist())
            if col in df2.columns:
                df2_codes.update(df2[col].dropna().astype(str).tolist())
        
        return list(df1_codes.intersection(df2_codes))
    
    def _compare_metric(
        self, 
        df1: pd.DataFrame, 
        df2: pd.DataFrame, 
        common_stocks: List[str], 
        metric: str
    ) -> Optional[FinancialMetricComparison]:
        """比较特定指标"""
        try:
            if metric not in df1.columns or metric not in df2.columns:
                return None
            
            # Get indicator values for common stocks
            df1_values = []
            df2_values = []
            
            for stock in common_stocks[:100]:  # Limit the number of comparisons
                val1 = self._get_stock_metric_value(df1, stock, metric)
                val2 = self._get_stock_metric_value(df2, stock, metric)
                
                if val1 is not None and val2 is not None:
                    df1_values.append(val1)
                    df2_values.append(val2)
            
            if len(df1_values) == 0:
                return None
            
            # Calculate average and difference
            avg1 = np.mean(df1_values)
            avg2 = np.mean(df2_values)
            
            if avg1 != 0:
                diff_pct = abs(avg2 - avg1) / abs(avg1)
            else:
                diff_pct = float('inf') if avg2 != 0 else 0
            
            tolerance = self.tolerance_thresholds.get(metric, 0.1)
            is_significant = diff_pct > tolerance
            
            return FinancialMetricComparison(
                metric_name=metric,
                primary_value=avg1,
                secondary_value=avg2,
                difference_pct=diff_pct,
                is_significant=is_significant,
                tolerance=tolerance
            )
            
        except Exception as e:
            logger.warning(f"⚠️ 比较指标{metric}失败: {e}")
            return None
    
    def _get_stock_metric_value(self, df: pd.DataFrame, stock_code: str, metric: str) -> Optional[float]:
        """获取特定股票的指标值"""
        try:
            # Try different matching methods
            for code_col in ['ts_code', 'symbol', 'code']:
                if code_col in df.columns:
                    mask = df[code_col].astype(str) == stock_code
                    if mask.any():
                        value = df.loc[mask, metric].iloc[0]
                        if pd.notna(value) and value != 0:
                            return float(value)
            return None
        except:
            return None
    
    def _calculate_overall_consistency(
        self, 
        comparisons: List[FinancialMetricComparison],
        primary_source: str,
        secondary_source: str
    ) -> DataConsistencyResult:
        """计算整体一致性结果"""
        if not comparisons:
            return DataConsistencyResult(
                is_consistent=False,
                primary_source=primary_source,
                secondary_source=secondary_source,
                differences={'error': 'No valid metric comparisons'},
                confidence_score=0.0,
                recommended_action='use_primary_only',
                details={'reason': 'No comparable metrics'}
            )
        
        # Calculate weighted confidence score
        total_weight = 0
        weighted_score = 0
        differences = {}
        
        for comp in comparisons:
            weight = self.metric_weights.get(comp.metric_name, 0.1)
            total_weight += weight
            
            # Consistency score: The smaller the difference, the higher the score
            if comp.difference_pct is not None and comp.difference_pct != float('inf'):
                consistency_score = max(0, 1 - (comp.difference_pct / comp.tolerance))
            else:
                consistency_score = 0
            
            weighted_score += weight * consistency_score
            
            # Record differences
            differences[comp.metric_name] = {
                'primary_value': comp.primary_value,
                'secondary_value': comp.secondary_value,
                'difference_pct': comp.difference_pct,
                'is_significant': comp.is_significant,
                'tolerance': comp.tolerance
            }
        
        confidence_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Determine overall consistency
        significant_differences = sum(1 for comp in comparisons if comp.is_significant)
        is_consistent = significant_differences <= len(comparisons) * 0.3  # Allow 30% of indicators to be significantly different
        
        # Recommended action
        if confidence_score > 0.8:
            recommended_action = 'use_either'  # The data is highly consistent and can be used from any data source
        elif confidence_score > 0.6:
            recommended_action = 'use_primary_with_warning'  # Use master data source with warning
        elif confidence_score > 0.3:
            recommended_action = 'use_primary_only'  # Use only primary data sources
        else:
            recommended_action = 'investigate_sources'  # Data source issues need to be investigated
        
        return DataConsistencyResult(
            is_consistent=is_consistent,
            primary_source=primary_source,
            secondary_source=secondary_source,
            differences=differences,
            confidence_score=confidence_score,
            recommended_action=recommended_action,
            details={
                'total_comparisons': len(comparisons),
                'significant_differences': significant_differences,
                'consistency_threshold': 0.3
            }
        )

    def resolve_data_conflicts(
        self, 
        primary_data: pd.DataFrame,
        secondary_data: pd.DataFrame,
        consistency_result: DataConsistencyResult
    ) -> Tuple[pd.DataFrame, str]:
        """
        Resolve data conflicts based on consistency check results
        
        Returns:
            Tuple[pd.DataFrame, str]: (final data, Solution strategy description)
        """
        action = consistency_result.recommended_action
        
        if action == 'use_either':
            logger.info("✅ The data is highly consistent, using the main data source")
            return primary_data, "The data source is highly consistent, using the main data source"
        
        elif action == 'use_primary_with_warning':
            logger.warning("⚠️ There are differences in the data but within the acceptable range, use the primary data source")
            return primary_data, f"There are slight differences in the data (confidence: {consistency_result.confidence_score:.2f}) , Use master data sources"
        
        elif action == 'use_primary_only':
            logger.warning("🚨 The data is very different, so only the primary data source is used")
            return primary_data, f"数据差异显著（置信度: {consistency_result.confidence_score:.2f}），仅使用主数据源"
        
        else:  # investigate_sources
            logger.error("❌ There are serious problems with the data source that require manual investigation")
            return primary_data, f"There are serious inconsistencies in the data source (confidence: {consistency_result.confidence_score:.2f}) , It is recommended to check the data source"
