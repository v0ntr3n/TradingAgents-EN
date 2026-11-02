#!/usr/bin/env python3
"""
Standalone document conversion test script
Used to test Markdown to Word/PDF conversion without regenerating analysis content
"""

import os
import tempfile
import pypandoc
from datetime import datetime

def test_markdown_content():
    """Generate Markdown content for testing"""
    
    # Simulate real analysis result data
    test_content = """# 605499 Stock analysis report

**Generation time**: 2025-01-12 16:20:00  
**analysis status**: formal analysis

## 🎯 Investment Decision Summary

| indicator | numerical value |
|------|------|
| **investment advice** | BUY |
| **Confidence** | 85.0% |
| **risk score** | 25.0% |
| **target price** | ¥275.00 |

### analytical reasoning
Based on technical and fundamental analysis, the stock is showing a strong upward trend. The market sentiment is positive and it is recommended to buy.

## 📋 Analyze configuration information

- **LLM provider**: qwen
- **LLM model**: qwen-turbo  
- **analyst**: market, fundamentals
- **Research depth**: standard analysis

## 📊 Market technical analysis

### Technical indicator analysis
- **trend direction**: rise
- **support level**: ¥250.00
- **resistance level**: ¥300.00
- **RSI indicator**: 65 (Neutral to strong)

### Volume analysis
The recent increase in trading volume shows that market attention has increased.

## 📈 fundamental analysis

### financial condition
- **revenue growth**: 15.2%
- **net profit margin**: 8.5%
- **ROE**: 12.3%

### Industry status
The company is in a leading position in the industry and has strong competitive advantages.

## ⚠️ Risk warning

1. **market risk**: Overall market volatility may affect share prices
2. **Industry risks**: Risks of industry policy changes
3. **corporate risk**: Operation and management risks

## 📝 Disclaimer

This report is for reference only and does not constitute investment advice. Investment is risky, so be cautious when entering the market.

---
*Report generation time: 2025-01-12 16:20:00*
"""
    
    return test_content

def save_test_content():
    """Save test content to file"""
    content = test_markdown_content()
    
    with open('test_content.md', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Test content has been saved to test_content.md")
    print(f"📊 content length: {len(content)} character")
    return content

def test_word_conversion(md_content):
    """Test Word conversion"""
    print("\n🔄 Test Word conversion...")
    
    try:
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
            output_file = tmp_file.name
        
        print(f"📁 temporary files: {output_file}")
        
        # Test different conversion parameters
        test_cases = [
            {
                'name': 'Basic conversion',
                'format': 'markdown',
                'extra_args': []
            },
            {
                'name': 'With directory conversion',
                'format': 'markdown',
                'extra_args': ['--toc', '--number-sections']
            },
            {
                'name': 'Disable YAML conversion',
                'format': 'markdown',
                'extra_args': ['--from=markdown-yaml_metadata_block']
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📝 test {i}: {test_case['name']}")
            print(f"🔧 parameters: format={test_case['format']}, extra_args={test_case['extra_args']}")
            
            try:
                pypandoc.convert_text(
                    md_content,
                    'docx',
                    format=test_case['format'],
                    outputfile=output_file,
                    extra_args=test_case['extra_args']
                )
                
                # Check files
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    file_size = os.path.getsize(output_file)
                    print(f"✅ Conversion successful! file size: {file_size} Bytes")
                    
                    # Successfully saved file
                    success_file = f"test_output_{i}.docx"
                    os.rename(output_file, success_file)
                    print(f"💾 The file has been saved as: {success_file}")
                    return True
                else:
                    print(f"❌ Conversion failed: File not generated or empty")
                    
            except Exception as e:
                print(f"❌ Conversion failed: {e}")
                
            # Clean temporary files
            if os.path.exists(output_file):
                os.unlink(output_file)
        
        return False
        
    except Exception as e:
        print(f"❌ Word Conversion test failed: {e}")
        return False

def test_pdf_conversion(md_content):
    """Test PDF conversion"""
    print("\n🔄 Test PDF conversion...")
    
    try:
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            output_file = tmp_file.name
        
        print(f"📁 temporary files: {output_file}")
        
        # Test different PDF engines
        test_engines = [
            ('wkhtmltopdf', 'HTML Convert to PDF engine'),
            ('weasyprint', 'Modern HTML to PDF engine'),
            (None, 'Default engine')
        ]
        
        for i, (engine, description) in enumerate(test_engines, 1):
            print(f"\n📊 test {i}: {description}")
            
            try:
                extra_args = []
                if engine:
                    extra_args.append(f'--pdf-engine={engine}')
                    print(f"🔧 use engine: {engine}")
                else:
                    print(f"🔧 Use default engine")
                
                pypandoc.convert_text(
                    md_content,
                    'pdf',
                    format='markdown',
                    outputfile=output_file,
                    extra_args=extra_args
                )
                
                # Check files
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    file_size = os.path.getsize(output_file)
                    print(f"✅ Conversion successful! file size: {file_size} Bytes")
                    
                    # Successfully saved file
                    success_file = f"test_output_{i}.pdf"
                    os.rename(output_file, success_file)
                    print(f"💾 The file has been saved as: {success_file}")
                    return True
                else:
                    print(f"❌ Conversion failed: File not generated or empty")
                    
            except Exception as e:
                print(f"❌ Conversion failed: {e}")
                
            # Clean temporary files
            if os.path.exists(output_file):
                os.unlink(output_file)
        
        return False
        
    except Exception as e:
        print(f"❌ PDF Conversion test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Standalone document conversion testing (Volume Mapping version)")
    print("=" * 50)
    print(f"📁 current working directory: {os.getcwd()}")
    print(f"🐳 Docker Environmental testing: {os.path.exists('/.dockerenv')}")
    
    # Save test content
    md_content = save_test_content()
    
    # Test Word conversion
    word_success = test_word_conversion(md_content)
    
    # Test PDF conversion
    pdf_success = test_pdf_conversion(md_content)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary of test results")
    print("=" * 50)
    print(f"Word Convert: {'✅ success' if word_success else '❌ failed'}")
    print(f"PDF Convert:  {'✅ success' if pdf_success else '❌ failed'}")
    
    if word_success or pdf_success:
        print("\n🎉 At least one format was converted successfully!")
        print("💡 Success parameters can be applied to the main program")
    else:
        print("\n⚠️ All conversions failed")
        print("💡 Need to check pandoc installation and configuration")

if __name__ == "__main__":
    main()
