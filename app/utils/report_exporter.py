"""
Report export tool - supports Markdown, Word, PDF formats

Depends on installation:
    pip install pypandoc markdown

PDF Export requires additional tools:
    - wkhtmltopdf (Recommended): https://wkhtmltopdf.org/downloads.html
    - or LaTeX: https://www.latex-project.org/get/
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from app.utils.compliance import RESEARCH_ONLY_DISCLAIMER, sanitize_display_report_text, sanitize_report_artifacts

logger = logging.getLogger(__name__)

# Analyst English ID to Chinese name mapping (for report display)
ANALYST_ID_TO_CHINESE: dict = {
    # Macro Analyst
    "index_analyst": "Market environment analyst",
    "index_analyst_v2": "Market environment analyst",
    "sector_analyst": "Industry sector research analyst",
    "sector_analyst_v2": "Industry sector research analyst",
    # Analyst Team
    "market_analyst": "Market Technical Analyst",
    "market_analyst_v2": "Market Technical Analyst",
    "sentiment_analyst": "Sentiment Research Analyst",
    "emotion_analyst": "Sentiment Research Analyst",
    "emotion_analyst_v2": "Sentiment Research Analyst",
    "news_analyst": "News Research Analyst",
    "news_analyst_v2": "News Research Analyst",
    "fundamentals_analyst": "fundamental analyst",
    "fundamentals_analyst_v2": "fundamental analyst",
    "social_media_analyst": "social media research analyst",
    "social_analyst_v2": "social media research analyst",
    # research team
    "bull_researcher": "optimistic scenario argument",
    "bull_researcher_v2": "optimistic scenario argument",
    "bear_researcher": "Prudential Scenario Argument",
    "bear_researcher_v2": "Prudential Scenario Argument",
    "research_manager": "Summary of research conclusions",
    "research_manager_v2": "Summary of research conclusions",
    # risk management team
    "risky_analyst": "Highly resilient scenario assessment",
    "risky_analyst_v2": "Highly resilient scenario assessment",
    "safe_analyst": "Defense Scenario Assessment",
    "safe_analyst_v2": "Defense Scenario Assessment",
    "neutral_analyst": "Baseline Scenario Assessment",
    "neutral_analyst_v2": "Baseline Scenario Assessment",
    "risk_manager": "Risk review summary",
    "risk_manager_v2": "Risk review summary",
    # Research integration and review
    "trader": "User version research briefing",
    "trader_v2": "User version research briefing",
    "timing_analyst": "timing analyst",
    "timing_analyst_v2": "timing analyst",
    "position_analyst": "Position Analyst",
    "position_analyst_v2": "Position Analyst",
    "attribution_analyst": "attribution analyst",
    "attribution_analyst_v2": "attribution analyst",
    "review_manager": "Review summary expert",
    "review_manager_v2": "Review summary expert",
    # Position research
    "position_advisor": "Position consultant",
    "pa_technical": "technical researcher",
    "pa_fundamental": "Fundamental Researcher",
    "pa_risk": "risk assessor",
    "pa_advisor": "conclusion integrator",
}

EXPORT_SANITIZED_MODULE_KEYS = {
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
    "bull_researcher",
    "bull_researcher_v2",
    "bear_researcher",
    "bear_researcher_v2",
    "risky_analyst",
    "risky_analyst_v2",
    "safe_analyst",
    "safe_analyst_v2",
    "neutral_analyst",
    "neutral_analyst_v2",
    "research_team_decision",
    "risk_management_decision",
}

MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
CHINESE_SECTION_PREFIX_PATTERN = re.compile(r"^[One, two, three, four, five, six, seven, eight, nine hundred]+[, \.]\s*")

# Check if dependencies are available
try:
    import markdown
    import pypandoc

    # Check if pandoc is available
    try:
        pypandoc.get_pandoc_version()
        PANDOC_AVAILABLE = True
        logger.info("✅ Pandoc Available")
    except OSError:
        PANDOC_AVAILABLE = False
        logger.warning("⚠️ Pandoc Not available, Word and PDF export functionality will not be available")

    EXPORT_AVAILABLE = True
except ImportError as e:
    EXPORT_AVAILABLE = False
    PANDOC_AVAILABLE = False
    logger.warning(f"⚠️ Export function dependency package is missing: {e}")
    logger.info("💡 Please install: pip install pypandoc markdown")

# Check out WeasyPrint (recommended, pure Python, no external tools required)
WEASYPRINT_AVAILABLE = False
WEASYPRINT_ERROR = None

try:
    import weasyprint
    WEASYPRINT_AVAILABLE = True
    logger.info("✅ WeasyPrint Available (PDF generation tool, recommended)")
except ImportError:
    logger.warning("⚠️ WeasyPrint Not installed, PDF export functionality will use pdfkit")
    logger.info("💡 Installation method: pip install weasyprint")
except Exception as e:
    WEASYPRINT_ERROR = str(e)
    logger.warning(f"⚠️ WeasyPrint Detection failed: {e}")

# Check pdfkit (alternative, requires wkhtmltopdf)
PDFKIT_AVAILABLE = False
PDFKIT_ERROR = None

try:
    import pdfkit
    # Check if wkhtmltopdf is installed
    try:
        pdfkit.configuration()
        PDFKIT_AVAILABLE = True
        logger.info("✅ pdfkit + wkhtmltopdf Available (PDF generation tool, optional)")
    except Exception as e:
        PDFKIT_ERROR = str(e)
        logger.warning("⚠️ wkhtmltopdf Not installed, pdfkit is not available")
        logger.info("💡 Installation method: https://wkhtmltopdf.org/downloads.html")
except ImportError:
    logger.warning("⚠️ pdfkit Not installed")
    logger.info("💡 Installation method: pip install pdfkit")
except Exception as e:
    PDFKIT_ERROR = str(e)
    logger.warning(f"⚠️ pdfkit Detection failed: {e}")


class ReportExporter:
    """Report exporter - supports Markdown, Word, PDF formats"""

    def __init__(self):
        self.export_available = EXPORT_AVAILABLE
        self.pandoc_available = PANDOC_AVAILABLE
        self.weasyprint_available = WEASYPRINT_AVAILABLE
        self.pdfkit_available = PDFKIT_AVAILABLE

        logger.info("📋 ReportExporter initialization:")
        logger.info(f"  - export_available: {self.export_available}")
        logger.info(f"  - pandoc_available: {self.pandoc_available}")
        logger.info(f"  - pdfkit_available: {self.pdfkit_available}")

    @staticmethod
    def _normalize_heading_text(text: str) -> str:
        normalized = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
        return normalized.casefold()

    def _strip_duplicate_leading_heading(self, content: str, title: str) -> str:
        lines = content.splitlines()
        normalized_title = self._normalize_heading_text(title)

        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            heading_match = MARKDOWN_HEADING_PATTERN.match(stripped)
            if not heading_match:
                break

            if self._normalize_heading_text(heading_match.group(2)) == normalized_title:
                remaining = lines[index + 1 :]
                while remaining and not remaining[0].strip():
                    remaining.pop(0)
                return "\n".join(remaining)

            break

        return content

    @staticmethod
    def _demote_markdown_headings(content: str) -> str:
        demoted_lines = []
        in_code_block = False

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                demoted_lines.append(line)
                continue

            if not in_code_block:
                heading_match = MARKDOWN_HEADING_PATTERN.match(line)
                if heading_match:
                    heading_level = min(len(heading_match.group(1)) + 1, 6)
                    demoted_lines.append(f"{'#' * heading_level} {heading_match.group(2)}")
                    continue

            demoted_lines.append(line)

        return "\n".join(demoted_lines)

    @staticmethod
    def _normalize_section_title(text: str) -> str:
        normalized = text.strip()
        if normalized.startswith("**") and normalized.endswith("**") and len(normalized) > 4:
            normalized = normalized[2:-2].strip()
        return CHINESE_SECTION_PREFIX_PATTERN.sub("", normalized).strip()

    @staticmethod
    def _strip_emphasis_markers(text: str) -> str:
        normalized = text.strip()
        if normalized.startswith("**") and normalized.endswith("**") and len(normalized) > 4:
            return normalized[2:-2].strip()
        return normalized

    def _normalize_intra_module_headings(self, content: str) -> str:
        normalized_lines = []
        in_code_block = False

        for line in content.splitlines():
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                normalized_lines.append(line)
                continue

            if in_code_block or not stripped:
                normalized_lines.append(line)
                continue

            heading_match = MARKDOWN_HEADING_PATTERN.match(line)
            if heading_match:
                heading_text = self._normalize_section_title(heading_match.group(2))
                normalized_lines.append(f"{heading_match.group(1)} {heading_text}")
                continue

            plain_line = self._strip_emphasis_markers(stripped)
            if CHINESE_SECTION_PREFIX_PATTERN.match(plain_line):
                section_title = self._normalize_section_title(stripped)
                if section_title and len(section_title) <= 30 and not re.search(r"[，,。！？；：:]", section_title):
                    normalized_lines.append(f"## {section_title}")
                    continue

            normalized_lines.append(line)

        return "\n".join(normalized_lines)

    @staticmethod
    def _normalize_disclaimer(content: str) -> str:
        return re.sub(
            r"(?is)(?:\*\*)?Disclaimer(?:\*\*)?[: :].*?(?:Make investment decisions independently.|Please consult professional advisors if necessary.)",
            f"**Disclaimer**: {RESEARCH_ONLY_DISCLAIMER}",
            content,
        )

    def _normalize_module_content(self, module_key: str, title: str, module_content: str) -> str:
        normalized_content = sanitize_report_artifacts(module_content.strip()) or module_content.strip()
        if module_key in EXPORT_SANITIZED_MODULE_KEYS:
            normalized_content = sanitize_display_report_text(normalized_content, fallback=normalized_content)

        if not normalized_content and module_key == "news_report":
            normalized_content = "The tool results were not successfully expanded into news reports, and the current news conclusions still need to be verified."

        normalized_content = self._normalize_intra_module_headings(normalized_content)
        normalized_content = self._normalize_disclaimer(normalized_content)
        normalized_content = self._strip_duplicate_leading_heading(normalized_content, title)
        normalized_content = self._demote_markdown_headings(normalized_content)
        return normalized_content.strip()
    
    def generate_markdown_report(self, report_doc: Dict[str, Any]) -> str:
        """Generate Markdown format report"""
        logger.info("📝 Generate Markdown report...")
        
        stock_symbol = report_doc.get("stock_symbol", "unknown")
        analysis_date = report_doc.get("analysis_date", "")
        analysts = report_doc.get("analysts", [])
        research_depth = report_doc.get("research_depth", 1)
        reports = report_doc.get("reports", {})
        summary = report_doc.get("summary", "")
        
        content_parts = []
        
        # Title and meta information
        content_parts.append(f"# {stock_symbol} Stock research reports")
        content_parts.append("")
        content_parts.append(f"**Study date**: {analysis_date}")
        if analysts:
            analyst_names = [
                ANALYST_ID_TO_CHINESE.get(a, a) for a in analysts
            ]
            content_parts.append(f"**analyst**: {', '.join(analyst_names)}")
        content_parts.append(f"**Research depth**: {research_depth}")
        content_parts.append("")
        content_parts.append("---")
        content_parts.append("")
        
        # Research summary
        if summary:
            content_parts.append("## 📊 Research summary")
            content_parts.append("")
            content_parts.append(summary)
            content_parts.append("")
            content_parts.append("---")
            content_parts.append("")
        
        # Contents of each module (in order of presentation)
        module_order = [
            # end user output
            "trader_investment_plan",
            "final_trade_decision",

            # Macro analysis (priority for display)
            "index_report",
            "sector_report",

            # Basic analysis module
            "company_overview",
            "financial_analysis",
            "technical_analysis",
            "market_analysis",
            "risk_analysis",
            "valuation_analysis",
            "investment_recommendation",

            # individual stock analysis report
            "market_report",
            "fundamentals_report",
            "sentiment_report",
            "news_report",

            # Research team conclusion
            "bull_researcher",
            "bear_researcher",
            "neutral_analyst",
            "research_team_decision",

            # Risk team analysis
            "risky_analyst",
            "safe_analyst",
            "risk_management_decision",

            # decision report
        ]
        
        module_titles = {
            # Basic analysis module
            "company_overview": "🏢 Company Profile",
            "financial_analysis": "💰 financial analysis",
            "technical_analysis": "📈 technical analysis",
            "market_analysis": "🌍 market analysis",
            "risk_analysis": "⚠️ risk analysis",
            "valuation_analysis": "💎 Valuation analysis",
            "investment_recommendation": "🎯 Summary of research conclusions",

            # decision report
            "final_trade_decision": "📝 Comprehensive research conclusion",
            "investment_plan": "📋 Research Manager Briefing",
            "trader_investment_plan": "🧩 User version research briefing",
            "research_team_decision": "🤝 Summary of research conclusions",
            "risk_management_decision": "🛡️ Risk review conclusion",

            # research team researcher
            "bull_researcher": "🌤️ optimistic scenario argument",
            "bear_researcher": "🌧️ Prudential Scenario Argument",

            # Risk Team Analyst
            "risky_analyst": "⚡ Highly resilient scenario assessment",
            "safe_analyst": "🛡️ Defense Scenario Assessment",
            "neutral_analyst": "⚖️ Baseline Scenario Assessment",

            # individual stock analysis report
            "market_report": "📈 Market Technology Research Report",
            "fundamentals_report": "💰 Fundamental Research Report",
            "sentiment_report": "💭 Emotion research report",
            "news_report": "📰 news research report",

            # Macro analysis report
            "sector_report": "🏭 Industry sector research report",
            "index_report": "📊 Market Environment Research Report",
        }
        
        # Add modules in order
        for module_key in module_order:
            if module_key in reports:
                module_content = reports[module_key]
                # 🔥 Handle content in dictionary format (e.g. final_trade_decision may be a dictionary)
                if isinstance(module_content, dict):
                    # If there is a content field, use it
                    if "content" in module_content:
                        module_content = module_content["content"]
                    else:
                        # Otherwise convert to formatted string
                        import json
                        module_content = json.dumps(module_content, ensure_ascii=False, indent=2)
                
                if isinstance(module_content, str) and module_content.strip():
                    title = module_titles.get(module_key, module_key)
                    module_content = self._normalize_module_content(module_key, title, module_content)
                    content_parts.append(f"## {title}")
                    content_parts.append("")
                    content_parts.append(module_content)
                    content_parts.append("")
                    content_parts.append("---")
                    content_parts.append("")
        
        # Add other modules not listed
        # 🔥 Blacklist: Explicitly excluded fields (to avoid confusion with other fields)
        excluded_fields = {
            "investment_plan",  # Replaced by trader_investment_plan
        }

        for module_key, module_content in reports.items():
            if module_key not in module_order and module_key not in excluded_fields:
                # 🔥 Processing content in dictionary format
                if isinstance(module_content, dict):
                    if "content" in module_content:
                        module_content = module_content["content"]
                    else:
                        import json
                        module_content = json.dumps(module_content, ensure_ascii=False, indent=2)

                if isinstance(module_content, str) and module_content.strip():
                    # 🔥 Use a friendly title if one exists
                    title = module_titles.get(module_key, module_key.replace("_", " ").title())
                    module_content = self._normalize_module_content(module_key, title, module_content)
                    content_parts.append(f"## {title}")
                    content_parts.append("")
                    content_parts.append(module_content)
                    content_parts.append("")
                    content_parts.append("---")
                    content_parts.append("")
        
        # footer
        content_parts.append("")
        content_parts.append("---")
        content_parts.append("")
        content_parts.append("*This report is automatically generated by TradingAgents-CN*")
        content_parts.append("")
        
        markdown_content = "\n".join(content_parts)
        logger.info(f"✅ Markdown Report generation completed, length: {len(markdown_content)} character")
        
        return markdown_content
    
    def _clean_markdown_for_pandoc(self, md_content: str) -> str:
        """Clean up Markdown content to avoid pandoc parsing issues"""
        import re

        # Remove content that may cause YAML parsing issues
        # If there is at the beginning "---", Add a blank line in front
        if md_content.strip().startswith("---"):
            md_content = "\n" + md_content

        # 🔥 Remove HTML tags and styles that may cause vertical alignment
        # Remove writing-mode related styles
        md_content = re.sub(r'<[^>]*writing-mode[^>]*>', '', md_content, flags=re.IGNORECASE)
        md_content = re.sub(r'<[^>]*text-orientation[^>]*>', '', md_content, flags=re.IGNORECASE)

        # Remove <div> The style attribute in the tag (may include vertical style)
        md_content = re.sub(r'<div\s+style="[^"]*">', '<div>', md_content, flags=re.IGNORECASE)
        md_content = re.sub(r'<span\s+style="[^"]*">', '<span>', md_content, flags=re.IGNORECASE)

        # 🔥 Remove HTML tags that may be causing problems
        # Keep the basic Markdown format and remove complex HTML
        md_content = re.sub(r'<style[^>]*>.*?</style>', '', md_content, flags=re.DOTALL | re.IGNORECASE)

        # 🔥 Make sure all paragraphs are normal horizontal text
        # Add clear line breaks before and after each paragraph to avoid Pandoc misjudgments
        lines = md_content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip empty lines
            if not line.strip():
                cleaned_lines.append(line)
                continue

            # If it is Markdown syntax such as titles, lists, tables, etc., keep it as is
            if line.strip().startswith(('#', '-', '*', '|', '>', '```', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                cleaned_lines.append(line)
            else:
                # Ordinary paragraphs: Make sure there are no special characters that cause vertical alignment
                cleaned_lines.append(line)

        md_content = '\n'.join(cleaned_lines)

        return md_content

    def _create_pdf_css(self) -> str:
        """Create PDF stylesheets to control table pagination and text direction"""
        return """
<style>
/* 🔥 Force all text to be displayed horizontally (fix Chinese vertical display problem) */
* {
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

body {
    writing-mode: horizontal-tb !important;
    direction: ltr !important;
}

/* paragraphs and text */
p, div, span, td, th, li {
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

/* Table style - allow cross-page */
table {
    width: 100%;
    border-collapse: collapse;
    page-break-inside: auto;
    writing-mode: horizontal-tb !important;
}

/* Table rows - avoid page breaks in the middle of rows */
tr {
    page-break-inside: avoid;
    page-break-after: auto;
}

/* Header - Repeat on every page */
thead {
    display: table-header-group;
}

/* table cell */
td, th {
    padding: 8px;
    border: 1px solid #ddd;
    writing-mode: horizontal-tb !important;
    text-orientation: mixed !important;
}

/* Header style */
th {
    background-color: #f2f2f2;
    font-weight: bold;
}

/* Avoid pagination immediately after title */
h1, h2, h3, h4, h5, h6 {
    page-break-after: avoid;
    writing-mode: horizontal-tb !important;
}

/* Avoid pagination in the middle of list items */
li {
    page-break-inside: avoid;
}

/* code block */
pre, code {
    writing-mode: horizontal-tb !important;
    white-space: pre-wrap;
    word-wrap: break-word;
}
</style>
"""
    
    def generate_docx_report(self, report_doc: Dict[str, Any]) -> bytes:
        """Generate reports in Word document format"""
        logger.info("📄 Start generating a Word document...")

        if not self.pandoc_available:
            raise Exception("Pandoc Unavailable, unable to generate Word document. Please install pandoc or use Markdown format to export.")

        # Generate Markdown content
        md_content = self.generate_markdown_report(report_doc)
        # Replace emoji with plain text to avoid appearing as squares in Word (compatible with older versions/cross-platform)
        md_content = self._replace_emoji_for_pdf(md_content)

        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
                output_file = tmp_file.name

            logger.info(f"📁 Temporary file path: {output_file}")

            # Pandoc parameters
            extra_args = [
                '--from=markdown-yaml_metadata_block',  # Disable YAML metadata block parsing
                '--standalone',  # Generate standalone documentation
                '--wrap=preserve',  # Keep line breaks
                '--columns=120',  # Set column width
                '-M', 'lang=zh-CN',  # 🔥 Explicitly specify the language as Simplified Chinese
                '-M', 'dir=ltr',  # 🔥 Explicitly specify text direction as left to right
            ]

            # Clean content
            cleaned_content = self._clean_markdown_for_pandoc(md_content)

            # Convert to Word
            pypandoc.convert_text(
                cleaned_content,
                'docx',
                format='markdown',
                outputfile=output_file,
                extra_args=extra_args
            )

            logger.info("✅ pypandoc Conversion completed")

            # 🔥 Post-processing: Fix text orientation in Word documents
            try:
                from docx import Document
                doc = Document(output_file)

                # Fix text direction for all paragraphs
                for paragraph in doc.paragraphs:
                    # Set paragraphs from left to right
                    if paragraph._element.pPr is not None:
                        # Remove possible vertical setting
                        for child in list(paragraph._element.pPr):
                            if 'textDirection' in child.tag or 'bidi' in child.tag:
                                paragraph._element.pPr.remove(child)

                # Fix text direction in tables
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            for paragraph in cell.paragraphs:
                                if paragraph._element.pPr is not None:
                                    for child in list(paragraph._element.pPr):
                                        if 'textDirection' in child.tag or 'bidi' in child.tag:
                                            paragraph._element.pPr.remove(child)

                # Save the repaired document
                doc.save(output_file)
                logger.info("✅ Word Document text direction repair completed")
            except ImportError:
                logger.warning("⚠️ python-docx Not installed, skipping text orientation fix")
            except Exception as e:
                logger.warning(f"⚠️ Word Document text orientation fix failed: {e}")

            # Read the generated file
            with open(output_file, 'rb') as f:
                docx_content = f.read()

            logger.info(f"✅ Word Document generation successful, size: {len(docx_content)} Bytes")

            # Clean temporary files
            os.unlink(output_file)

            return docx_content
            
        except Exception as e:
            logger.error(f"❌ Word Document generation failed: {e}", exc_info=True)
            # Clean temporary files
            try:
                if 'output_file' in locals() and os.path.exists(output_file):
                    os.unlink(output_file)
            except:
                pass
            raise Exception(f"Failed to generate Word document: {e}")
    
    def _replace_emoji_for_pdf(self, text: str) -> str:
        """
        Replace emojis with PDF-friendly plain text to avoid appearing as squares when generating PDFs.
        PDF Engine (WeasyPrint/pdfkit) default fonts usually do not support emoji characters.
        """
        import re
        # Risk level/action icon -> text markup
        replacements = [
            ("🟢", "[low]"),
            ("🟡", "[in]"),
            ("🔴", "[high]"),
            ("⚪", "[ ]"),
            # Common emoji are removed directly (the title already has a text description)
            ("📊", ""),
            ("⚠️", ""),
            ("⚠", ""),
            ("💡", ""),
            ("📋", ""),
            ("💼", ""),
            ("🎯", ""),
            ("🔍", ""),
            ("🛡️", ""),
            ("🛡", ""),
            ("📈", ""),
            ("📉", ""),
            ("🏢", ""),
            ("💰", ""),
            ("🌍", ""),
            ("💎", ""),
            ("⚖️", ""),
            ("⚖", ""),
            ("👔", ""),
            ("💭", ""),
            ("📰", ""),
            ("🏭", ""),
        ]
        result = text
        for emoji, replacement in replacements:
            result = result.replace(emoji, replacement)
        # Remove zero-width characters and common invisible characters
        result = re.sub(r"[\u200b-\u200d\ufeff]", "", result)
        # 🔥 Fix: Only compress the extra spaces in the title, without affecting the table format
        # Only handles Markdown header lines (starting with # extra spaces at the beginning)
        lines = result.split('\n')
        processed_lines = []
        for line in lines:
            # Only the title row (starting with # beginning) to compress excess spaces
            if line.strip().startswith('#'):
                # Compress extra spaces in titles (e.g. "##  risk assessment" -> "## risk assessment") 
                line = re.sub(r'(#{1,6})\s{2,}', r'\1 ', line)
            processed_lines.append(line)
        result = '\n'.join(processed_lines)
        return result

    def _markdown_to_html(self, md_content: str) -> str:
        """Convert Markdown to HTML"""
        import markdown

        # Configure Markdown extension
        extensions = [
            'markdown.extensions.tables',  # Table support
            'markdown.extensions.fenced_code',  # Code block support
            'markdown.extensions.nl2br',  # Newline support
        ]

        # Convert to HTML
        html_content = markdown.markdown(md_content, extensions=extensions)

        # Add HTML templates and styles
        # WeasyPrint Optimized CSS (removes unsupported properties)
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN" dir="ltr">
<head>
    <meta charset="UTF-8">
    <title>research report</title>
    <style>
        /* Basic styling - ensuring text is oriented correctly */
        html {{
            direction: ltr;
        }}

        body {{
            font-family: "Noto Sans CJK SC", "Microsoft YaHei", "SimHei", "Arial", sans-serif;
            line-height: 1.8;
            color: #333;
            margin: 20mm;
            padding: 0;
            background: white;
            direction: ltr;
        }}

        /* Title style */
        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 1.5em;
            margin-bottom: 0.8em;
            font-weight: 600;
            page-break-after: avoid;
            direction: ltr;
        }}

        h1 {{
            font-size: 2em;
            border-bottom: 3px solid #3498db;
            padding-bottom: 0.3em;
            page-break-before: always;
        }}

        h1:first-child {{
            page-break-before: avoid;
        }}

        h2 {{
            font-size: 1.6em;
            border-bottom: 2px solid #bdc3c7;
            padding-bottom: 0.25em;
        }}

        h3 {{
            font-size: 1.3em;
            color: #34495e;
        }}

        /* paragraph style */
        p {{
            margin: 0.8em 0;
            text-align: left;
            direction: ltr;
        }}

        /* Table style - optimized paging */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.5em 0;
            font-size: 0.9em;
            direction: ltr;
        }}

        /* Header repeats on every page */
        thead {{
            display: table-header-group;
        }}

        tbody {{
            display: table-row-group;
        }}

        /* Table rows avoid breaking across pages */
        tr {{
            page-break-inside: avoid;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 10px 12px;
            text-align: left;
            direction: ltr;
        }}

        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
        }}

        tbody tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}

        tbody tr:hover {{
            background-color: #e9ecef;
        }}

        /* code block style */
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Consolas", "Monaco", "Courier New", monospace;
            font-size: 0.9em;
            direction: ltr;
        }}

        pre {{
            background-color: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #3498db;
            page-break-inside: avoid;
            direction: ltr;
        }}

        pre code {{
            background-color: transparent;
            padding: 0;
        }}

        /* list style */
        ul, ol {{
            margin: 0.8em 0;
            padding-left: 2em;
            direction: ltr;
        }}

        li {{
            margin: 0.4em 0;
            direction: ltr;
        }}

        /* emphasize text */
        strong, b {{
            font-weight: 700;
            color: #2c3e50;
        }}

        em, i {{
            font-style: italic;
            color: #555;
        }}

        /* horizontal line */
        hr {{
            border: none;
            border-top: 2px solid #ecf0f1;
            margin: 2em 0;
        }}

        /* link style */
        a {{
            color: #3498db;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}

        /* Paging control */
        @page {{
            size: A4;
            margin: 20mm;

            @top-center {{
                content: "research report";
                font-size: 10pt;
                color: #999;
            }}

            @bottom-right {{
                content: "No. " counter(page) " page";
                font-size: 10pt;
                color: #999;
            }}
        }}

        /* Avoid being alone and alone */
        p, li {{
            orphans: 3;
            widows: 3;
        }}

        /* Picture style */
        img {{
            max-width: 100%;
            height: auto;
            page-break-inside: avoid;
        }}

        /* quote block style */
        blockquote {{
            margin: 1em 0;
            padding: 0.5em 1em;
            border-left: 4px solid #3498db;
            background-color: #f8f9fa;
            font-style: italic;
            page-break-inside: avoid;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>
"""
        return html_template

    def _generate_pdf_with_pdfkit(self, html_content: str) -> bytes:
        """Generated using pdfkit PDF"""
        import pdfkit

        logger.info("🔧 Use pdfkit + wkhtmltopdf generate PDF...")

        # Configuration options
        options = {
            'encoding': 'UTF-8',
            'enable-local-file-access': None,
            'page-size': 'A4',
            'margin-top': '20mm',
            'margin-right': '20mm',
            'margin-bottom': '20mm',
            'margin-left': '20mm',
        }

        # generate PDF
        pdf_bytes = pdfkit.from_string(html_content, False, options=options)

        logger.info(f"✅ pdfkit PDF Generated successfully, size: {len(pdf_bytes)} Bytes")
        return pdf_bytes

    def _generate_pdf_with_weasyprint(self, html_content: str) -> bytes:
        """Generate PDF using WeasyPrint (recommended, pure Python, no external tools required)"""
        import weasyprint
        
        logger.info("🔧 Generate using WeasyPrint PDF...")
        
        # generate PDF
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        
        logger.info(f"✅ PDF Generated successfully, size: {len(pdf_bytes)} Bytes")
        return pdf_bytes

    def generate_pdf_report(self, report_doc: Dict[str, Any]) -> bytes:
        """Generate reports in PDF format (preferably use WeasyPrint, otherwise use pdfkit)"""
        logger.info("📊 Start generating PDF documents...")

        # Generate Markdown content
        md_content = self.generate_markdown_report(report_doc)
        # Replace emoji with PDF-friendly text to avoid appearing as squares when exporting
        md_content = self._replace_emoji_for_pdf(md_content)
        html_content = self._markdown_to_html(md_content)

        # Prefer using WeasyPrint (recommended, pure Python, no external tools required)
        if self.weasyprint_available:
            try:
                logger.info("🎯 Use WeasyPrint to generate PDF (recommended)")
                return self._generate_pdf_with_weasyprint(html_content)
            except Exception as e:
                logger.warning(f"⚠️ WeasyPrint Build failed: {e}, Try using pdfkit...")
                # If WeasyPrint fails, try pdfkit

        # Alternative: Use pdfkit
        if self.pdfkit_available:
            try:
                logger.info("🎯 Use pdfkit + wkhtmltopdf Generate PDF (optional)")
                return self._generate_pdf_with_pdfkit(html_content)
            except Exception as e:
                logger.error(f"❌ pdfkit Build failed: {e}")
                raise Exception(f"PDF Build failed: {e}")

        # If neither is available, throw an error
        error_msg = (
            "PDF The generation tool is unavailable and cannot generate the PDF.\n\n"
            "Recommended installation method (choose one):\n"
            "1. WeasyPrint (Recommended, pure Python, no external tools required): pip install weasyprint\n"
            "2. pdfkit + wkhtmltopdf: pip install pdfkit, then install https://wkhtmltopdf.org/downloads.html\n"
        )
        if WEASYPRINT_ERROR:
            error_msg += f"\nWeasyPrint Error: {WEASYPRINT_ERROR}\n"
        if PDFKIT_ERROR:
            error_msg += f"\npdfkit Error: {PDFKIT_ERROR}"

        logger.error(f"❌ {error_msg}")
        raise Exception(error_msg)


# Create a global exporter instance
report_exporter = ReportExporter()

