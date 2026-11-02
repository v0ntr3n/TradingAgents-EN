#!/usr/bin/env python3
"""
Test pypandoc functionality
Verify that export function dependencies are working properly
"""

import sys
import os
import tempfile
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_pypandoc_import():
    """Test pypandoc import"""
    print("🔍 Test pypandoc import...")
    try:
        import pypandoc
        print("✅ pypandoc Import successful")
        return True
    except ImportError as e:
        print(f"❌ pypandoc Import failed: {e}")
        return False

def test_pandoc_version():
    """Test pandoc version"""
    print("\n🔍 Test pandoc version...")
    try:
        import pypandoc
        version = pypandoc.get_pandoc_version()
        print(f"✅ Pandoc version: {version}")
        return True
    except Exception as e:
        print(f"❌ Failed to get pandoc version: {e}")
        return False

def test_pandoc_download():
    """Test pandoc automatic download"""
    print("\n🔍 Test pandoc automatic download...")
    try:
        import pypandoc
        
        # Check if there is already pandoc
        try:
            version = pypandoc.get_pandoc_version()
            print(f"✅ Pandoc Already exists: {version}")
            return True
        except:
            print("⚠️ Pandoc Does not exist, try downloading...")
            
        # try download
        pypandoc.download_pandoc()
        
        # Check again
        version = pypandoc.get_pandoc_version()
        print(f"✅ Pandoc Download successful: {version}")
        return True
        
    except Exception as e:
        print(f"❌ Pandoc Download failed: {e}")
        return False

def test_markdown_conversion():
    """Test Markdown conversion function"""
    print("\n🔍 Test Markdown conversion...")
    
    try:
        import pypandoc
        
        # Test content
        test_markdown = """# test report

## Basic information
- **Stock code**: TEST001
- **Generation time**: 2025-01-12 15:30:00

## Analyze results
This is a test report used to verify the conversion functionality of pypandoc.

### technical analysis
- Price trend: rising
- Trading volume: normal
- Technical indicators: good

### investment advice
**Suggestions**: buy
**Confidence**: 85%

---
*Report generation time: 2025-01-12 15:30:00*
"""
        
        print("📄 Test Markdown content is ready")
        
        # Test converted to HTML
        try:
            html_output = pypandoc.convert_text(test_markdown, 'html', format='markdown')
            print("✅ Markdown → HTML Conversion successful")
            print(f"   Output length: {len(html_output)} character")
        except Exception as e:
            print(f"❌ Markdown → HTML Conversion failed: {e}")
            return False
        
        # Test converted to DOCX
        try:
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
                output_file = tmp_file.name
            
            pypandoc.convert_text(
                test_markdown,
                'docx',
                format='markdown',
                outputfile=output_file,
                extra_args=['--toc', '--number-sections']
            )
            
            # Check if the file is generated
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"✅ Markdown → DOCX Conversion successful")
                print(f"   file size: {file_size} Bytes")
                
                # Clean temporary files
                os.unlink(output_file)
            else:
                print("❌ DOCX File not generated")
                return False
                
        except Exception as e:
            print(f"❌ Markdown → DOCX Conversion failed: {e}")
            return False
        
        # Test converted to PDF (May fail because additional tools are required)
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                output_file = tmp_file.name
            
            pypandoc.convert_text(
                test_markdown,
                'pdf',
                format='markdown',
                outputfile=output_file,
                extra_args=['--pdf-engine=wkhtmltopdf']
            )
            
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"✅ Markdown → PDF Conversion successful")
                print(f"   file size: {file_size} Bytes")
                
                # Clean temporary files
                os.unlink(output_file)
            else:
                print("⚠️ PDF File not generated (PDF engine may be missing)")
                
        except Exception as e:
            print(f"⚠️ Markdown → PDF Conversion failed: {e}")
            print("   This is normal, PDF conversion requires additional tools such as wkhtmltopdf")
        
        return True
        
    except Exception as e:
        print(f"❌ Conversion test failed: {e}")
        return False

def test_report_exporter():
    """Test report exporter"""
    print("\n🔍 Test report exporter...")
    
    try:
        from web.utils.report_exporter import ReportExporter
        
        # Create an exporter instance
        exporter = ReportExporter()
        print(f"✅ Report exporter created successfully")
        print(f"   Export function is available: {exporter.export_available}")
        print(f"   Pandoc Available: {exporter.pandoc_available}")
        
        # test data
        test_results = {
            'stock_symbol': 'TEST001',
            'decision': {
                'action': 'buy',
                'confidence': 0.85,
                'risk_score': 0.3,
                'target_price': '¥15.50',
                'reasoning': 'Based on technical analysis and fundamental analysis, the stock has good investment value.'
            },
            'state': {
                'market_report': 'Technical indicators point to an uptrend and trading volume is amplifying.',
                'fundamentals_report': 'The company s financial position is good and its profitability is strong.',
                'sentiment_report': 'Market sentiment is positive and investor confidence is strong.'
            },
            'llm_provider': 'deepseek',
            'llm_model': 'deepseek-chat',
            'analysts': ['technical analyst', 'fundamental analyst', 'sentiment analyst'],
            'research_depth': 'In-depth analysis',
            'is_demo': False
        }
        
        # Test Markdown export
        try:
            md_content = exporter.generate_markdown_report(test_results)
            print("✅ Markdown Report generated successfully")
            print(f"   content length: {len(md_content)} character")
        except Exception as e:
            print(f"❌ Markdown Report generation failed: {e}")
            return False
        
        # Test DOCX export (If pandoc is available)
        if exporter.pandoc_available:
            try:
                docx_content = exporter.generate_docx_report(test_results)
                print("✅ DOCX Report generated successfully")
                print(f"   Content size: {len(docx_content)} Bytes")
            except Exception as e:
                print(f"❌ DOCX Report generation failed: {e}")
                return False
        else:
            print("⚠️ Skip DOCX test (pandoc Not available)")
        
        return True
        
    except Exception as e:
        print(f"❌ Report exporter test failure: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 pypandoc Functional testing")
    print("=" * 50)
    
    tests = [
        ("pypandoc import", test_pypandoc_import),
        ("pandoc version", test_pandoc_version),
        ("pandoc Download", test_pandoc_download),
        ("Markdown Convert", test_markdown_conversion),
        ("report exporter", test_report_exporter),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 Summary of test results")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1
    
    print(f"\n total: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! pypandoc functions normally")
        return True
    else:
        print("⚠️ Some tests failed, please check the configuration")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
