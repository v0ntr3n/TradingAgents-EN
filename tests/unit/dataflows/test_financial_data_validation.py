#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test financial data validation logic
Verify range checks of gross profit margin, net profit margin, ROE, ROA and other indicators
"""

import sys
import os

# Add project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataFlow


def test_financial_data_validation():
    """Test financial data validation"""
    
    dataflow = OptimizedChinaDataFlow()
    
    # test case 1: normal data
    print("\n" + "="*80)
    print("test case 1: normal data")
    print("="*80)
    
    normal_data = {
        'roe': 15.5,
        'roa': 8.2,
        'gross_margin': 45.3,
        'netprofit_margin': 12.8,
        'code': '000001'
    }
    
    result = dataflow._parse_mongodb_financial_data(normal_data, 10.0)
    print(f"ROE: {result.get('roe')}")
    print(f"ROA: {result.get('roa')}")
    print(f"Gross profit margin: {result.get('gross_margin')}")
    print(f"net profit margin: {result.get('net_margin')}")
    
    # test case 2: Abnormal data (Gross profit margin is out of range)
    print("\n" + "="*80)
    print("test case 2: Abnormal data (Gross profit margin = 339904690.2)")
    print("="*80)
    
    abnormal_data = {
        'roe': 9.5,
        'roa': 8.4,
        'gross_margin': 339904690.2,  # Outliers
        'netprofit_margin': 15.3,
        'code': '000001'
    }
    
    result = dataflow._parse_mongodb_financial_data(abnormal_data, 10.0)
    print(f"ROE: {result.get('roe')}")
    print(f"ROA: {result.get('roa')}")
    print(f"Gross profit margin: {result.get('gross_margin')} (should be N/A)")
    print(f"net profit margin: {result.get('net_margin')}")
    
    # test case 3: boundary value
    print("\n" + "="*80)
    print("test case 3: boundary value")
    print("="*80)
    
    boundary_data = {
        'roe': 100.0,  # boundary value
        'roa': -50.0,  # negative value
        'gross_margin': 99.9,  # Close to the upper limit
        'netprofit_margin': -10.5,  # negative value
        'code': '000001'
    }
    
    result = dataflow._parse_mongodb_financial_data(boundary_data, 10.0)
    print(f"ROE: {result.get('roe')}")
    print(f"ROA: {result.get('roa')}")
    print(f"Gross profit margin: {result.get('gross_margin')}")
    print(f"net profit margin: {result.get('net_margin')}")
    
    # test case 4: out of bounds
    print("\n" + "="*80)
    print("test case 4: out of bounds")
    print("="*80)
    
    out_of_range_data = {
        'roe': 250.0,  # out of range
        'roa': 150.0,  # out of range
        'gross_margin': 120.0,  # out of range
        'netprofit_margin': -150.0,  # out of range
        'code': '000001'
    }
    
    result = dataflow._parse_mongodb_financial_data(out_of_range_data, 10.0)
    print(f"ROE: {result.get('roe')} (should be N/A)")
    print(f"ROA: {result.get('roa')} (should be N/A)")
    print(f"Gross profit margin: {result.get('gross_margin')} (should be N/A)")
    print(f"net profit margin: {result.get('net_margin')} (should be N/A)")
    
    print("\n" + "="*80)
    print("✅ Test completed!")
    print("="*80)


if __name__ == '__main__':
    test_financial_data_validation()

