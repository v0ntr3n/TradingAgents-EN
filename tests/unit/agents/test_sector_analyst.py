"""
Sector Analyst Unit Test
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import pandas as pd


class TestSectorTools:
    """Test section analysis tool function"""
    
    @pytest.fixture
    def mock_tushare_provider(self):
        """Emulate Tushare provider"""
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_provider._normalize_ts_code.side_effect = lambda x: f"{x}.SZ" if not '.' in x else x
        return mock_provider
    
    @pytest.mark.asyncio
    async def test_get_stock_sector_info(self, mock_tushare_provider):
        """Test to obtain stock sector information"""
        # Set simulation return value
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_ths_member = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI', '885611.TI'],
            'con_name': ['Ping An Bank', 'Ping An Bank']
        }))
        mock_tushare_provider.get_ths_index_list = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI'],
            'name': ['bank']
        }))
        
        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_stock_sector_info
            
            result = await get_stock_sector_info("000001")
            
            assert result['ticker'] == "000001"
            assert result['industry'] == "bank"
            assert len(result['sectors']) == 1
            assert result['sectors'][0]['name'] == 'bank'
            assert result['error'] is None
    
    @pytest.mark.asyncio
    async def test_get_sector_performance(self, mock_tushare_provider):
        """Test sector performance analysis"""
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20241202', '20241201'],
            'close': [3300, 3290],
        }))
        mock_tushare_provider.get_ths_member = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI', '885611.TI', '700402.TI'],
            'con_name': ['Ping An Bank', 'Ping An Bank', 'Ping An Bank']
        }))
        mock_tushare_provider.get_ths_index_list = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI', '700402.TI'],
            'name': ['bank', 'commercial bank(A shares)']
        }))

        async def mock_get_ths_daily(ts_code, start_date=None, end_date=None):
            if ts_code == '881155.TI':
                return pd.DataFrame({
                    'trade_date': ['20241201', '20241202'],
                    'close': [100, 105],
                    'pct_change': [0, 5.0]
                })
            if ts_code == '700402.TI':
                return pd.DataFrame({
                    'trade_date': ['20241201', '20241202'],
                    'close': [200, 198],
                    'pct_change': [0, -1.0]
                })
            raise AssertionError(f"unexpected ts_code: {ts_code}")

        mock_tushare_provider.get_ths_daily = AsyncMock(side_effect=mock_get_ths_daily)
        
        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_sector_performance
            
            result = await get_sector_performance("000001", "2024-12-02")
            
            assert "Sector performance analysis report" in result
            assert "bank" in result
            assert "Main industry anchor: bank" in result
            assert "Request analysis date: 2024-12-02" in result
            assert "Actual sector data date: 2024-12-02" in result
            assert "Industry index number: 2 a" in result
            assert "Fintech" not in result
            assert "Only statistics on Flush Industry Index" in result
            assert "Does not change the main industry affiliation" in result
            assert mock_tushare_provider.get_ths_daily.await_count == 2

    @pytest.mark.asyncio
    async def test_get_sector_performance_discloses_fallback_date(self, mock_tushare_provider):
        """The test sector table discloses the actual data date when there is no stable data on the request date."""
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20260420', '20260418'],
            'close': [3290, 3280],
        }))
        mock_tushare_provider.get_ths_member = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI'],
            'con_name': ['Ping An Bank'],
        }))
        mock_tushare_provider.get_ths_index_list = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI'],
            'name': ['bank']
        }))
        mock_tushare_provider.get_ths_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20260418', '20260420'],
            'close': [100, 105],
            'pct_change': [0, 5.0],
        }))

        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_sector_performance

            result = await get_sector_performance("000001", "2026-04-21")

            assert "Request analysis date: 2026-04-21" in result
            assert "Actual sector data date: 2026-04-20" in result
            assert "There is currently no daily frequency data for industry indexes required for sector performance analysis on 2026-04-21." in result

    @pytest.mark.asyncio
    async def test_get_sector_performance_unifies_sector_dates(self, mock_tushare_provider):
        """When testing different industry index update times that are inconsistent, the data will be cut off to the same actual data day."""
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20260421', '20260420', '20260418'],
            'close': [3300, 3290, 3280],
        }))
        mock_tushare_provider.get_ths_member = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI', '700402.TI'],
            'con_name': ['Ping An Bank', 'Ping An Bank'],
        }))
        mock_tushare_provider.get_ths_index_list = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['881155.TI', '700402.TI'],
            'name': ['bank', 'commercial bank(A shares)']
        }))

        async def mock_get_ths_daily(ts_code, start_date=None, end_date=None):
            if ts_code == '881155.TI':
                return pd.DataFrame({
                    'trade_date': ['20260418', '20260420', '20260421'],
                    'close': [100, 104, 110],
                    'pct_change': [0, 4.0, 5.77],
                })
            if ts_code == '700402.TI':
                return pd.DataFrame({
                    'trade_date': ['20260418', '20260420'],
                    'close': [200, 190],
                    'pct_change': [0, -5.0],
                })
            raise AssertionError(f"unexpected ts_code: {ts_code}")

        mock_tushare_provider.get_ths_daily = AsyncMock(side_effect=mock_get_ths_daily)

        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_sector_performance

            result = await get_sector_performance("000001", "2026-04-21")

            assert "Actual sector data date: 2026-04-20" in result
            assert "The following rankings have been uniformly intercepted 2026-04-20" in result
            assert "bank: 📈 +4.00% (today: +4.00%)" in result
            assert "commercial bank(A shares): 📉 -5.00% (today: -5.00%)" in result


    @pytest.mark.asyncio
    async def test_get_peer_comparison_uses_single_primary_industry_anchor(self, mock_tushare_provider):
        """The only main industry anchor point is used for testing peer comparison."""
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_sector_stocks_daily_basic = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['000001.SZ', '600036.SH', '601398.SH'],
            'name': ['Ping An Bank', 'China Merchants Bank', 'ICBC'],
            'total_mv': [21521200.0, 98890000.0, 260530000.0],
            'pe_ttm': [5.05, 6.4, 7.2],
            'pb': [0.48, 0.92, 0.71],
            'turnover_rate': [0.25, 0.31, 0.12],
        }))

        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_peer_comparison

            result = await get_peer_comparison("000001", "2024-12-02")

            assert "Comparative analysis report of peers" in result
            assert "Main industry anchor: bank" in result
            assert "Peer samples are matched exactly according to this" in result
            assert "Listed companies in the industry: 3 home" in result
            assert "Market capitalization ranking: 3/3" in result

    @pytest.mark.asyncio
    async def test_get_peer_comparison_falls_back_to_latest_available_valuation_date(self, mock_tushare_provider):
        """Fallback to the latest available valuation date when testing peer valuation data is missing."""
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20260421', '20260420', '20260418'],
            'close': [3300, 3290, 3280],
        }))

        async def mock_get_sector_stocks_daily_basic(industry, trade_date):
            if trade_date == '20260421':
                return pd.DataFrame()
            if trade_date == '20260420':
                return pd.DataFrame({
                    'ts_code': ['000001.SZ', '600036.SH', '601398.SH'],
                    'name': ['Ping An Bank', 'China Merchants Bank', 'ICBC'],
                    'total_mv': [21521200.0, 98890000.0, 260530000.0],
                    'pe_ttm': [5.05, 6.4, 7.2],
                    'pb': [0.48, 0.92, 0.71],
                    'turnover_rate': [0.25, 0.31, 0.12],
                })
            return pd.DataFrame()

        mock_tushare_provider.get_sector_stocks_daily_basic = AsyncMock(side_effect=mock_get_sector_stocks_daily_basic)

        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_peer_comparison

            result = await get_peer_comparison("000001", "2026-04-21")

            assert "Request analysis date: 2026-04-21" in result
            assert "Valuation Snapshot Date: 2026-04-20" in result
            assert "There is currently no post-closing daily frequency data required for peer valuation on 2026-04-21" in result

    @pytest.mark.asyncio
    async def test_get_peer_comparison_never_looks_forward_after_cutoff(self, mock_tushare_provider):
        """After testing the stable data rollback, peer valuations are only allowed to look back to history and cannot jump back to the current day."""
        mock_tushare_provider.get_stock_industry = AsyncMock(return_value="bank")
        mock_tushare_provider.get_index_daily = AsyncMock(return_value=pd.DataFrame({
            'trade_date': ['20260420', '20260418', '20260417'],
            'close': [3290, 3280, 3270],
        }))

        async def mock_get_sector_stocks_daily_basic(industry, trade_date):
            if trade_date == '20260420':
                return pd.DataFrame({
                    'ts_code': ['000001.SZ', '600036.SH'],
                    'name': ['Ping An Bank', 'China Merchants Bank'],
                    'total_mv': [21521200.0, 98890000.0],
                    'pe_ttm': [5.03, 6.40],
                    'pb': [0.48, 0.92],
                    'turnover_rate': [0.25, 0.31],
                })
            if trade_date == '20260421':
                return pd.DataFrame({
                    'ts_code': ['000001.SZ', '600036.SH'],
                    'name': ['Ping An Bank', 'China Merchants Bank'],
                    'total_mv': [21550000.0, 98950000.0],
                    'pe_ttm': [5.04, 6.41],
                    'pb': [0.49, 0.93],
                    'turnover_rate': [0.26, 0.32],
                })
            return pd.DataFrame()

        mock_tushare_provider.get_sector_stocks_daily_basic = AsyncMock(side_effect=mock_get_sector_stocks_daily_basic)

        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_peer_comparison

            result = await get_peer_comparison("000001", "2026-04-21")

            queried_dates = [call.kwargs['trade_date'] for call in mock_tushare_provider.get_sector_stocks_daily_basic.await_args_list]
            assert queried_dates[0] == '20260420'
            assert '20260421' not in queried_dates
            assert "Valuation Snapshot Date: 2026-04-20" in result
            assert "5.03" in result
    
    @pytest.mark.asyncio
    async def test_get_sector_rotation(self, mock_tushare_provider):
        """Test sector rotation analysis"""
        mock_tushare_provider.get_moneyflow_ind_ths = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['877035.TI', '881157.TI'],
            'industry': ['bank', 'securities'],
            'pct_change': [-0.12, 1.35],
            'company_num': [84, 50],
            'net_amount': [-40.0, 49.0]
        }))
        
        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_sector_rotation
            
            result = await get_sector_rotation("2024-12-02")
            
            assert "Industry rotation trend analysis" in result
            assert "Data caliber: Flush Industry Capital Flow (THS)" in result
            assert "bank" in result
            assert "securities" in result
            assert "+49.00 billion" in result
            assert "-40.00 billion" in result
            assert "Constituent stocks" not in result
            assert "Net inflow of funds" in result or "Net outflow of funds" in result
            mock_tushare_provider.get_moneyflow_ind_ths.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_sector_rotation_falls_back_to_stock_moneyflow(self, mock_tushare_provider):
        """Fall back to individual stock capital flows when testing industry capital flows are unavailable"""
        mock_tushare_provider.get_moneyflow_ind_ths = AsyncMock(return_value=pd.DataFrame())
        mock_tushare_provider.get_moneyflow_ths = AsyncMock(return_value=pd.DataFrame({
            'ts_code': ['300750.SZ', '600519.SH', '000001.SZ'],
            'name': ['Ningde era', 'Kweichow Moutai', 'Ping An Bank'],
            'pct_change': [2.1, -1.3, -0.4],
            'latest': [210.55, 1568.0, 10.25],
            'net_amount': [25600.0, -13200.0, 1800.0]
        }))

        with patch('core.tools.sector_tools._get_tushare_provider', return_value=mock_tushare_provider):
            from core.tools.sector_tools import get_sector_rotation

            result = await get_sector_rotation("2024-12-02")

            assert "Data caliber: Flush Stock Fund Flow (THS) Rewind" in result
            assert "The top list of individual stock capital flows as an alternative reference" in result
            assert "Net capital inflow into TOP stocks" in result
            assert "Net outflow of funds from TOP stocks" in result
            assert "Ningde era" in result
            assert "Ping An Bank" in result
            assert "Kweichow Moutai" in result
            assert "+2.56 billion" in result
            assert "-1.32 billion" in result
            mock_tushare_provider.get_moneyflow_ind_ths.assert_awaited_once()
            mock_tushare_provider.get_moneyflow_ths.assert_awaited_once()


class TestSectorAnalystAgent:
    """Test sector analyst Agent"""
    
    def test_agent_metadata(self):
        """Test Agent Metadata"""
        from core.agents.adapters.sector_analyst import SectorAnalystAgent
        
        metadata = SectorAnalystAgent.get_metadata()
        
        assert metadata.id == "sector_analyst"
        assert metadata.name == "Industry/sector analyst"
        assert "Industry analysis" in metadata.tags
    
    def test_agent_execute(self):
        """Test Agent execution"""
        from core.agents.adapters.sector_analyst import SectorAnalystAgent
        
        agent = SectorAnalystAgent()
        
        # Simulation Analysis Tools
        mock_report = "Test section analysis report"
        with patch('core.tools.sector_tools.analyze_sector_sync', return_value=mock_report):
            state = {
                "company_of_interest": "000001",
                "trade_date": "2024-12-02",
                "messages": []
            }
            
            result = agent.execute(state)
            
            assert "sector_report" in result
            assert result["sector_report"] == mock_report


class TestAgentStateExtension:
    """Testing the AgentState extension"""
    
    def test_sector_report_field(self):
        """Test sector_report field exists"""
        from tradingagents.agents.utils.agent_states import AgentState
        
        # Check field annotations
        annotations = AgentState.__annotations__
        
        assert 'sector_report' in annotations
        assert 'index_report' in annotations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

