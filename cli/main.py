# Standard library imports
import datetime
import os
import re
import subprocess
import sys
import time
from collections import deque
from difflib import get_close_matches
from functools import wraps
from pathlib import Path
from typing import Optional

# Third-party library imports
import typer
from dotenv import load_dotenv
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

# Internal project imports
from cli.models import AnalystType
from cli.utils import (
    select_analysts,
    select_deep_thinking_agent,
    select_llm_provider,
    select_research_depth,
    select_shallow_thinking_agent,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.utils.logging_manager import get_logger

# Load environment variables
load_dotenv()

# Constants
DEFAULT_MESSAGE_BUFFER_SIZE = 100
DEFAULT_MAX_TOOL_ARGS_LENGTH = 100
DEFAULT_MAX_CONTENT_LENGTH = 200
DEFAULT_MAX_DISPLAY_MESSAGES = 12
DEFAULT_REFRESH_RATE = 4
DEFAULT_API_KEY_DISPLAY_LENGTH = 12

# Initialize logging system
logger = get_logger("cli")

# CLI-specific logging configuration: disable console output and keep file logging only
def setup_cli_logging():
    """
    Configure logging for CLI mode: remove console output to keep the interface clean
    """
    import logging
    from tradingagents.utils.logging_manager import get_logger_manager

    logger_manager = get_logger_manager()

    # Get root logger
    root_logger = logging.getLogger()

    # Remove all console handlers and keep file logs only
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and hasattr(handler, 'stream'):
            if handler.stream.name in ['<stderr>', '<stdout>']:
                root_logger.removeHandler(handler)

    # Also remove console handlers from the tradingagents logger
    tradingagents_logger = logging.getLogger('tradingagents')
    for handler in tradingagents_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and hasattr(handler, 'stream'):
            if handler.stream.name in ['<stderr>', '<stdout>']:
                tradingagents_logger.removeHandler(handler)

    # Log CLI startup (written to file only)
    logger.debug("🚀 CLI mode started; console logging disabled to keep the interface clean")

# Apply CLI logging configuration
setup_cli_logging()

console = Console()

# CLI User Interface Manager
class CLIUserInterface:
    """CLI User Interface Manager: handles user display and progress prompts"""

    def __init__(self):
        self.console = Console()
        self.logger = get_logger("cli")

    def show_user_message(self, message: str, style: str = ""):
        """Display a message to the user"""
        if style:
            self.console.print(f"[{style}]{message}[/{style}]")
        else:
            self.console.print(message)

    def show_progress(self, message: str):
        """Display progress information"""
        self.console.print(f"🔄 {message}")
        # Also record to log file
        self.logger.info(f"Progress: {message}")

    def show_success(self, message: str):
        """Display success message"""
        self.console.print(f"[green]✅ {message}[/green]")
        self.logger.info(f"Success: {message}")

    def show_error(self, message: str):
        """Display error message"""
        self.console.print(f"[red]❌ {message}[/red]")
        self.logger.error(f"Error: {message}")

    def show_warning(self, message: str):
        """Display warning message"""
        self.console.print(f"[yellow]⚠️ {message}[/yellow]")
        self.logger.warning(f"Warning: {message}")

    def show_step_header(self, step_num: int, title: str):
        """Display step header"""
        self.console.print(f"\n[bold cyan]Step {step_num}: {title}[/bold cyan]")
        self.console.print("─" * 60)

    def show_data_info(self, data_type: str, symbol: str, details: str = ""):
        """Display data fetching info"""
        if details:
            self.console.print(f"📊 {data_type}: {symbol} - {details}")
        else:
            self.console.print(f"📊 {data_type}: {symbol}")

# Create global UI manager
ui = CLIUserInterface()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
    rich_markup_mode="rich",  # Enable rich markup
    no_args_is_help=False,  # Enter analysis mode directly when invoked without arguments
)


# Create a deque to store recent messages with a maximum length
class MessageBuffer:
    def __init__(self, max_length=DEFAULT_MESSAGE_BUFFER_SIZE):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None  # Store the complete final report
        self.agent_status = {
            # Analyst Team
            "Market Analyst": "pending",
            "Social Analyst": "pending",
            "News Analyst": "pending",
            "Fundamentals Analyst": "pending",
            # Research Team
            "Bull Researcher": "pending",
            "Bear Researcher": "pending",
            "Research Manager": "pending",
            # Trading Team
            "Trader": "pending",
            # Risk Management Team
            "Risky Analyst": "pending",
            "Neutral Analyst": "pending",
            "Safe Analyst": "pending",
            # Portfolio Management Team
            "Portfolio Manager": "pending",
        }
        self.current_agent = None
        self.report_sections = {
            "market_report": None,
            "sentiment_report": None,
            "news_report": None,
            "fundamentals_report": None,
            "investment_plan": None,
            "trader_investment_plan": None,
            "final_trade_decision": None,
        }

    def add_message(self, message_type, content):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name, args):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def update_agent_status(self, agent, status):
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name, content):
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()

    def _update_current_report(self):
        # For the panel display, only show the most recently updated section
        latest_section = None
        latest_content = None

        # Find the most recently updated section
        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content
               
        if latest_section and latest_content:
            # Format the current section for display
            section_titles = {
                "market_report": "Market Analysis",
                "sentiment_report": "Social Sentiment",
                "news_report": "News Analysis",
                "fundamentals_report": "Fundamentals Analysis",
                "investment_plan": "Research Team Decision",
                "trader_investment_plan": "Trading Team Plan",
                "final_trade_decision": "Portfolio Management Decision",
            }
            self.current_report = (
                f"### {section_titles[latest_section]}\n{latest_content}"
            )

        # Update the final complete report
        self._update_final_report()

    def _update_final_report(self):
        report_parts = []

        # Analyst Team Reports
        if any(
            self.report_sections[section]
            for section in [
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
            ]
        ):
            report_parts.append("## Analyst Team Reports")
            if self.report_sections["market_report"]:
                report_parts.append(
                    f"### Market Analysis\n{self.report_sections['market_report']}"
                )
            if self.report_sections["sentiment_report"]:
                report_parts.append(
                    f"### Social Sentiment\n{self.report_sections['sentiment_report']}"
                )
            if self.report_sections["news_report"]:
                report_parts.append(
                    f"### News Analysis\n{self.report_sections['news_report']}"
                )
            if self.report_sections["fundamentals_report"]:
                report_parts.append(
                    f"### Fundamentals Analysis\n{self.report_sections['fundamentals_report']}"
                )

        # Research Team Reports
        if self.report_sections["investment_plan"]:
            report_parts.append("## Research Team Decision")
            report_parts.append(f"{self.report_sections['investment_plan']}")

        # Trading Team Reports
        if self.report_sections["trader_investment_plan"]:
            report_parts.append("## Trading Team Plan")
            report_parts.append(f"{self.report_sections['trader_investment_plan']}")

        # Portfolio Management Decision
        if self.report_sections["final_trade_decision"]:
            report_parts.append("## Portfolio Management Decision")
            report_parts.append(f"{self.report_sections['final_trade_decision']}")

        self.final_report = "\n\n".join(report_parts) if report_parts else None


message_buffer = MessageBuffer()


def create_layout():
    """
    Create the layout structure for the CLI interface
    """
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["main"].split_column(
        Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5)
    )
    layout["upper"].split_row(
        Layout(name="progress", ratio=2), Layout(name="messages", ratio=3)
    )
    return layout


def update_display(layout, spinner_text=None):
    """
    Update CLI interface display content
    
    Args:
        layout: Rich Layout object
        spinner_text: Optional spinner text
    """
    # Header with welcome message
    layout["header"].update(
        Panel(
            "[bold green]Welcome to TradingAgents CLI[/bold green]\n"
            "[dim]© [Tauric Research](https://github.com/TauricResearch)[/dim]",
            title="Welcome to TradingAgents",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )
    )

    # Progress panel showing agent status
    progress_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,  # Use simple header with horizontal lines
        title=None,  # Remove the redundant Progress title
        padding=(0, 2),  # Add horizontal padding
        expand=True,  # Make table expand to fill available space
    )
    progress_table.add_column("Team", style="cyan", justify="center", width=20)
    progress_table.add_column("Agent", style="green", justify="center", width=20)
    progress_table.add_column("Status", style="yellow", justify="center", width=20)

    # Group agents by team
    teams = {
        "Analyst Team": [
            "Market Analyst",
            "Social Analyst",
            "News Analyst",
            "Fundamentals Analyst",
        ],
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Risky Analyst", "Neutral Analyst", "Safe Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    for team, agents in teams.items():
        # Add first agent with team name
        first_agent = agents[0]
        status = message_buffer.agent_status[first_agent]
        if status == "in_progress":
            spinner = Spinner(
                "dots", text="[blue]in_progress[/blue]", style="bold cyan"
            )
            status_cell = spinner
        else:
            status_color = {
                "pending": "yellow",
                "completed": "green",
                "error": "red",
            }.get(status, "white")
            status_cell = f"[{status_color}]{status}[/{status_color}]"
        progress_table.add_row(team, first_agent, status_cell)

        # Add remaining agents in team
        for agent in agents[1:]:
            status = message_buffer.agent_status[agent]
            if status == "in_progress":
                spinner = Spinner(
                    "dots", text="[blue]in_progress[/blue]", style="bold cyan"
                )
                status_cell = spinner
            else:
                status_color = {
                    "pending": "yellow",
                    "completed": "green",
                    "error": "red",
                }.get(status, "white")
                status_cell = f"[{status_color}]{status}[/{status_color}]"
            progress_table.add_row("", agent, status_cell)

        # Add horizontal line after each team
        progress_table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")

    layout["progress"].update(
        Panel(progress_table, title="Progress", border_style="cyan", padding=(1, 2))
    )

    # Messages panel showing recent messages and tool calls
    messages_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,  # Make table expand to fill available space
        box=box.MINIMAL,  # Use minimal box style for a lighter look
        show_lines=True,  # Keep horizontal lines
        padding=(0, 1),  # Add some padding between columns
    )
    messages_table.add_column("Time", style="cyan", width=8, justify="center")
    messages_table.add_column("Type", style="green", width=10, justify="center")
    messages_table.add_column(
        "Content", style="white", no_wrap=False, ratio=1
    )  # Make content column expand

    # Combine tool calls and messages
    all_messages = []

    # Add tool calls
    for timestamp, tool_name, args in message_buffer.tool_calls:
        # Truncate tool call args if too long
        if isinstance(args, str) and len(args) > DEFAULT_MAX_TOOL_ARGS_LENGTH:
            args = args[:97] + "..."
        all_messages.append((timestamp, "Tool", f"{tool_name}: {args}"))

    # Add regular messages
    for timestamp, msg_type, content in message_buffer.messages:
        # Convert content to string if it's not already
        content_str = content
        if isinstance(content, list):
            # Handle list of content blocks (Anthropic format)
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                    elif item.get('type') == 'tool_use':
                        text_parts.append(f"[Tool: {item.get('name', 'unknown')}]")
                else:
                    text_parts.append(str(item))
            content_str = ' '.join(text_parts)
        elif not isinstance(content_str, str):
            content_str = str(content)
            
        # Truncate message content if too long
        if len(content_str) > DEFAULT_MAX_CONTENT_LENGTH:
            content_str = content_str[:197] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    # Sort by timestamp
    all_messages.sort(key=lambda x: x[0])

    # Calculate how many messages we can show based on available space
    # Start with a reasonable number and adjust based on content length
    max_messages = DEFAULT_MAX_DISPLAY_MESSAGES  # Increased from 8 to better fill the space

    # Get the last N messages that will fit in the panel
    recent_messages = all_messages[-max_messages:]

    # Add messages to table
    for timestamp, msg_type, content in recent_messages:
        # Format content with word wrapping
        wrapped_content = Text(content, overflow="fold")
        messages_table.add_row(timestamp, msg_type, wrapped_content)

    if spinner_text:
        messages_table.add_row("", "Spinner", spinner_text)

    # Add a footer to indicate if messages were truncated
    if len(all_messages) > max_messages:
        messages_table.footer = (
            f"[dim]Showing last {max_messages} of {len(all_messages)} messages[/dim]"
        )

    layout["messages"].update(
        Panel(
            messages_table,
            title="Messages & Tools",
            border_style="blue",
            padding=(1, 2),
        )
    )

    # Analysis panel showing current report
    if message_buffer.current_report:
        layout["analysis"].update(
            Panel(
                Markdown(message_buffer.current_report),
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )
    else:
        layout["analysis"].update(
            Panel(
                "[italic]Waiting for analysis report...[/italic]",
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )

    # Footer with statistics
    tool_calls_count = len(message_buffer.tool_calls)
    llm_calls_count = sum(
        1 for _, msg_type, _ in message_buffer.messages if msg_type == "Reasoning"
    )
    reports_count = sum(
        1 for content in message_buffer.report_sections.values() if content is not None
    )

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("Stats", justify="center")
    stats_table.add_row(
        f"Tool Calls: {tool_calls_count} | LLM Calls: {llm_calls_count} | Generated Reports: {reports_count}"
    )

    layout["footer"].update(Panel(stats_table, border_style="grey50"))


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    welcome_file = Path(__file__).parent / "static" / "welcome.txt"
    try:
        with open(welcome_file, "r", encoding="utf-8") as f:
            welcome_ascii = f.read()
    except FileNotFoundError:
        welcome_ascii = "TradingAgents"

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += (
        "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"
    )

    # Create and center the welcome box
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()  # Add a blank line after the welcome box

    # Create a boxed questionnaire for each step
    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Market selection
    console.print(
        create_question_box(
            "Step 1: Select Market",
            "Please select the stock market to analyze",
            ""
        )
    )
    selected_market = select_market()

    # Step 2: Ticker symbol
    console.print(
        create_question_box(
            "Step 2: Ticker Symbol",
            f"Enter {selected_market['name_en']} ticker symbol",
            selected_market['default']
        )
    )
    selected_ticker = get_ticker(selected_market)

    # Step 3: Analysis date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(
        create_question_box(
            "Step 3: Analysis Date",
            "Enter the analysis date (YYYY-MM-DD)",
            default_date,
        )
    )
    analysis_date = get_analysis_date()

    # Step 4: Select analysts
    console.print(
        create_question_box(
            "Step 4: Analysts Team",
            "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts(selected_ticker)
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 5: Research depth
    console.print(
        create_question_box(
            "Step 5: Research Depth",
            "Select your research depth level"
        )
    )
    selected_research_depth = select_research_depth()

    # Step 6: LLM Provider
    console.print(
        create_question_box(
            "Step 6: LLM Provider",
            "Select which LLM service to use"
        )
    )
    selected_llm_provider, backend_url = select_llm_provider()

    # Step 7: Thinking agents
    console.print(
        create_question_box(
            "Step 7: Thinking Agents",
            "Select your thinking agents for analysis"
        )
    )
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    return {
        "ticker": selected_ticker,
        "market": selected_market,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
    }


def select_market():
    """Select stock market"""
    markets = {
        "1": {
            "name": "US Stock",
            "name_en": "US Stock",
            "default": "SPY",
            "examples": ["SPY", "AAPL", "TSLA", "NVDA", "MSFT"],
            "format": "Ticker symbol directly (e.g., AAPL)",
            "pattern": r'^[A-Z]{1,5}$',
            "data_source": "yahoo_finance"
        },
        "2": {
            "name": "China A-Share",
            "name_en": "China A-Share",
            "default": "600036",
            "examples": ["000001 (Ping An Bank)", "600036 (China Merchants Bank)", "000858 (Wuliangye)"],
            "format": "6-digit code (e.g., 600036, 000001)",
            "pattern": r'^\d{6}$',
            "data_source": "china_stock"
        },
        "3": {
            "name": "Hong Kong Stock",
            "name_en": "Hong Kong Stock",
            "default": "0700.HK",
            "examples": ["0700.HK (Tencent)", "09988.HK (Alibaba)", "03690.HK (Meituan)"],
            "format": "Code.HK (e.g., 0700.HK, 09988.HK)",
            "pattern": r'^\d{4,5}\.HK$',
            "data_source": "yahoo_finance"
        }
    }

    console.print("\n[bold cyan]Please select stock market:[/bold cyan]")
    for key, market in markets.items():
        examples_str = ", ".join(market["examples"][:3])
        console.print(f"[cyan]{key}[/cyan]. 🌍 {market['name_en']}")
        console.print(f"   Examples: {examples_str}")

    while True:
        choice = typer.prompt("\nSelect market", default="2")
        if choice in markets:
            selected_market = markets[choice]
            console.print(f"[green]✅ Selected: {selected_market['name_en']}[/green]")
            # Record to system log (file only)
            logger.info(f"User selected market: {selected_market['name_en']}")
            return selected_market
        else:
            console.print("[red]❌ Invalid choice, please enter 1, 2, or 3[/red]")
            logger.warning(f"User entered invalid choice: {choice}")


def get_ticker(market):
    """Get ticker symbol for the selected market"""
    console.print(f"\n[bold cyan]{market['name_en']} Examples:[/bold cyan]")
    for example in market['examples']:
        console.print(f"  • {example}")

    console.print(f"\n[dim]Format: {market['format']}[/dim]")

    while True:
        ticker = typer.prompt(f"\nEnter {market['name_en']} ticker",
                             default=market['default'])

        # Log user input (file only)
        logger.info(f"User entered ticker: {ticker}")

        # Validate ticker format
        import re
        
        # Check boundary conditions
        ticker = ticker.strip()  # Strip leading/trailing whitespace
        if not ticker:  # Check for empty string
            console.print("[red]❌ Ticker cannot be empty[/red]")
            logger.warning("User entered empty ticker")
            continue
            
        ticker_to_check = ticker.upper() if market['data_source'] != 'china_stock' else ticker

        if re.match(market['pattern'], ticker_to_check):
            # For China A-shares, return numeric code as-is
            if market['data_source'] == 'china_stock':
                console.print(f"[green]✅ Valid A-share ticker: {ticker} (using China stock data source)[/green]")
                logger.info(f"A-share ticker validated: {ticker}")
                return ticker
            else:
                console.print(f"[green]✅ Valid ticker: {ticker.upper()}[/green]")
                logger.info(f"Ticker validated: {ticker.upper()}")
                return ticker.upper()
        else:
            console.print("[red]❌ Invalid ticker format[/red]")
            console.print(f"[yellow]Please use the required format: {market['format']}[/yellow]")
            logger.warning(f"Ticker format validation failed: {ticker}")


def get_analysis_date():
    """Get the analysis date from user input."""
    while True:
        date_str = typer.prompt(
            "Enter analysis date", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            # Validate date format and ensure it's not in the future
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                logger.warning(f"User entered a future date: {date_str}")
                continue
            return date_str
        except ValueError:
            console.print(
                "[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]"
            )


def display_complete_report(final_state):
    """Display the complete analysis report with team-based panels."""
    logger.info("\n[bold green]Complete Analysis Report[/bold green]\n")

    # I. Analyst Team Reports
    analyst_reports = []

    # Market Analyst Report
    if final_state.get("market_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["market_report"]),
                title="Market Analyst",
                border_style="blue",
                padding=(1, 2),
            )
        )

    # Social Analyst Report
    if final_state.get("sentiment_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["sentiment_report"]),
                title="Social Analyst",
                border_style="blue",
                padding=(1, 2),
            )
        )

    # News Analyst Report
    if final_state.get("news_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["news_report"]),
                title="News Analyst",
                border_style="blue",
                padding=(1, 2),
            )
        )

    # Fundamentals Analyst Report
    if final_state.get("fundamentals_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["fundamentals_report"]),
                title="Fundamentals Analyst",
                border_style="blue",
                padding=(1, 2),
            )
        )

    if analyst_reports:
        console.print(
            Panel(
                Columns(analyst_reports, equal=True, expand=True),
                title="I. Analyst Team Reports",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    # II. Research Team Reports
    if final_state.get("investment_debate_state"):
        research_reports = []
        debate_state = final_state["investment_debate_state"]

        # Bull Researcher Analysis
        if debate_state.get("bull_history"):
            research_reports.append(
                Panel(
                    Markdown(debate_state["bull_history"]),
                    title="Bull Researcher",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # Bear Researcher Analysis
        if debate_state.get("bear_history"):
            research_reports.append(
                Panel(
                    Markdown(debate_state["bear_history"]),
                    title="Bear Researcher",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # Research Manager Decision
        if debate_state.get("judge_decision"):
            research_reports.append(
                Panel(
                    Markdown(debate_state["judge_decision"]),
                    title="Research Manager",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        if research_reports:
            console.print(
                Panel(
                    Columns(research_reports, equal=True, expand=True),
                    title="II. Research Team Decision",
                    border_style="magenta",
                    padding=(1, 2),
                )
            )

    # III. Trading Team Reports
    if final_state.get("trader_investment_plan"):
        console.print(
            Panel(
                Panel(
                    Markdown(final_state["trader_investment_plan"]),
                    title="Trader",
                    border_style="blue",
                    padding=(1, 2),
                ),
                title="III. Trading Team Plan",
                border_style="yellow",
                padding=(1, 2),
            )
        )

    # IV. Risk Management Team Reports
    if final_state.get("risk_debate_state"):
        risk_reports = []
        risk_state = final_state["risk_debate_state"]

        # Aggressive (Risky) Analyst Analysis
        if risk_state.get("risky_history"):
            risk_reports.append(
                Panel(
                    Markdown(risk_state["risky_history"]),
                    title="Aggressive Analyst",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # Conservative (Safe) Analyst Analysis
        if risk_state.get("safe_history"):
            risk_reports.append(
                Panel(
                    Markdown(risk_state["safe_history"]),
                    title="Conservative Analyst",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # Neutral Analyst Analysis
        if risk_state.get("neutral_history"):
            risk_reports.append(
                Panel(
                    Markdown(risk_state["neutral_history"]),
                    title="Neutral Analyst",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        if risk_reports:
            console.print(
                Panel(
                    Columns(risk_reports, equal=True, expand=True),
                    title="IV. Risk Management Team Decision",
                    border_style="red",
                    padding=(1, 2),
                )
            )

        # V. Portfolio Manager Decision
        if risk_state.get("judge_decision"):
            console.print(
                Panel(
                    Panel(
                        Markdown(risk_state["judge_decision"]),
                        title="Portfolio Manager",
                        border_style="blue",
                        padding=(1, 2),
                    ),
                    title="V. Portfolio Manager Decision",
                    border_style="green",
                    padding=(1, 2),
                )
            )


def update_research_team_status(status):
    """
    Update status for all research team members and trader
    
    Args:
        status: New status value
    """
    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager", "Trader"]
    for agent in research_team:
        message_buffer.update_agent_status(agent, status)

def extract_content_string(content):
    """
    Extract string content from various message formats
    
    Args:
        content: Message content, which may be a string, list, or other format
    
    Returns:
        str: Extracted string content
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # Handle Anthropic's list format
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get('type')  # Cache type value
                if item_type == 'text':
                    text_parts.append(item.get('text', ''))
                elif item_type == 'tool_use':
                    tool_name = item.get('name', 'unknown')  # Cache name value
                    text_parts.append(f"[Tool: {tool_name}]")
            else:
                text_parts.append(str(item))
        return ' '.join(text_parts)
    else:
        return str(content)

def check_api_keys(llm_provider: str) -> bool:
    """Check whether required API keys are configured"""

    missing_keys = []

    # Check API key corresponding to the selected LLM provider
    if "dashscope" in llm_provider.lower() or "bailian" in llm_provider.lower():
        if not os.getenv("DASHSCOPE_API_KEY"):
            missing_keys.append("DASHSCOPE_API_KEY (Alibaba Bailian / DashScope)")
    elif "openai" in llm_provider.lower():
        if not os.getenv("OPENAI_API_KEY"):
            missing_keys.append("OPENAI_API_KEY")
    elif "anthropic" in llm_provider.lower():
        if not os.getenv("ANTHROPIC_API_KEY"):
            missing_keys.append("ANTHROPIC_API_KEY")
    elif "google" in llm_provider.lower():
        if not os.getenv("GOOGLE_API_KEY"):
            missing_keys.append("GOOGLE_API_KEY")

    # Check financial data API key
    if not os.getenv("FINNHUB_API_KEY"):
        missing_keys.append("FINNHUB_API_KEY (Financial data)")

    if missing_keys:
        logger.error("[red]❌ Missing required API keys[/red]")
        for key in missing_keys:
            logger.info(f"   • {key}")

        logger.info("\n[yellow]💡 Solutions:[/yellow]")
        logger.info("1. Create a .env file in the project root:")
        logger.info("   DASHSCOPE_API_KEY=your_dashscope_key")
        logger.info("   FINNHUB_API_KEY=your_finnhub_key")
        logger.info("\n2. Or set environment variables")
        logger.info("\n3. Run 'python -m cli.main config' for detailed configuration instructions")

        return False

    return True

def run_analysis():
    import time
    start_time = time.time()  # Record start time
    
    # First get all user selections
    selections = get_user_selections()

    # Check API keys before proceeding
    if not check_api_keys(selections["llm_provider"]):
        ui.show_error("Analysis terminated")
        return

    # Display analysis start information
    ui.show_step_header(1, "Preparing Analysis Environment")
    ui.show_progress(f"Analyzing ticker: {selections['ticker']}")
    ui.show_progress(f"Analysis date: {selections['analysis_date']}")
    ui.show_progress(f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}")

    # Create config with selected research depth
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    # Normalize LLM provider name
    selected_llm_provider_name = selections["llm_provider"].lower()
    if "dashscope" in selected_llm_provider_name or "bailian" in selected_llm_provider_name:
        config["llm_provider"] = "dashscope"
    elif "deepseek" in selected_llm_provider_name:
        config["llm_provider"] = "deepseek"
    elif "openai" in selected_llm_provider_name and "custom" not in selected_llm_provider_name:
        config["llm_provider"] = "openai"
    elif "custom" in selected_llm_provider_name:
        config["llm_provider"] = "custom_openai"
        # Retrieve custom URL from environment variable
        custom_url = os.getenv('CUSTOM_OPENAI_BASE_URL', selections["backend_url"])
        config["custom_openai_base_url"] = custom_url
        config["backend_url"] = custom_url
    elif "anthropic" in selected_llm_provider_name:
        config["llm_provider"] = "anthropic"
    elif "google" in selected_llm_provider_name:
        config["llm_provider"] = "google"
    else:
        config["llm_provider"] = selected_llm_provider_name

    # Initialize the graph
    ui.show_progress("Initializing analysis system...")
    try:
        graph = TradingAgentsGraph(
            [analyst.value for analyst in selections["analysts"]], config=config, debug=True
        )
        ui.show_success("Analysis system initialized")
    except ImportError as e:
        ui.show_error(f"Module import failed: {str(e)}")
        ui.show_warning("💡 Please check dependencies installation")
        return
    except ValueError as e:
        ui.show_error(f"Configuration error: {str(e)}")
        ui.show_warning("💡 Please check configuration parameters")
        return
    except Exception as e:
        ui.show_error(f"Initialization failed: {str(e)}")
        ui.show_warning("💡 Please check API key configuration")
        return

    # Create result directory
    results_dir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            content = content.replace("\n", " ")  # Replace newlines with spaces
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [{message_type}] {content}\n")
        return wrapper
    
    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")
        return wrapper

    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                content = obj.report_sections[section_name]
                if content:
                    file_name = f"{section_name}.md"
                    with open(report_dir / file_name, "w", encoding="utf-8") as f:
                        f.write(content)
        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    # Now start the display layout
    layout = create_layout()

    with Live(layout, refresh_per_second=DEFAULT_REFRESH_RATE) as live:
        # Initial display
        update_display(layout)

        # Add initial messages
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        message_buffer.add_message(
            "System", f"Analysis date: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        update_display(layout)

        # Reset agent statuses
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "pending")

        # Reset report sections
        for section in message_buffer.report_sections:
            message_buffer.report_sections[section] = None
        message_buffer.current_report = None
        message_buffer.final_report = None

        # Update agent status to in_progress for the first analyst
        first_analyst = f"{selections['analysts'][0].value.capitalize()} Analyst"
        message_buffer.update_agent_status(first_analyst, "in_progress")
        update_display(layout)

        # Create spinner text
        spinner_text = (
            f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        )
        update_display(layout, spinner_text)

        # Display data pre-fetching and validation phase
        ui.show_step_header(2, "Data Validation Phase")
        ui.show_progress("🔍 Validating ticker and pre-fetching data...")

        try:
            from tradingagents.utils.stock_validator import prepare_stock_data

            # Pre-fetch stock data (default 30 days of historical data, auto-detect market type)
            preparation_result = prepare_stock_data(
                stock_code=selections["ticker"],
                market_type="auto",
                period_days=30,
                analysis_date=selections["analysis_date"]
            )

            if not preparation_result.is_valid:
                ui.show_error(f"❌ Stock data validation failed: {preparation_result.error_message}")
                ui.show_warning(f"💡 Suggestion: {preparation_result.suggestion}")
                logger.error(f"Stock data validation failed: {preparation_result.error_message}")
                return

            # Data pre-fetching succeeded
            ui.show_success(f"✅ Data preparation completed: {preparation_result.stock_name} ({preparation_result.market_type})")
            ui.show_user_message(f"📊 Cache status: {preparation_result.cache_status}", "dim")
            logger.info(f"Stock data pre-fetched successfully: {preparation_result.stock_name}")

        except Exception as e:
            ui.show_error(f"❌ Error occurred during data pre-fetching: {str(e)}")
            ui.show_warning("💡 Please check your network connection or try again later")
            logger.error(f"Data pre-fetching error: {str(e)}")
            return

        # Display data collection phase
        ui.show_step_header(3, "Data Collection Phase")
        ui.show_progress("Fetching basic stock information...")

        # Initialize state and get graph args
        init_agent_state = graph.propagator.create_initial_state(
            selections["ticker"], selections["analysis_date"]
        )
        args = graph.propagator.get_graph_args()

        ui.show_success("Data collection preparation completed")

        # Display AI analysis phase
        ui.show_step_header(4, "AI Analysis Phase (estimated ~10 minutes)")
        ui.show_progress("Starting analyst team...")
        ui.show_user_message("💡 Tip: AI analysis involves multi-team collaboration; please wait ~10 minutes", "dim")

        # Stream the analysis
        trace = []
        current_analyst = None
        analysis_steps = {
            "market_report": "📈 Market Analyst",
            "fundamentals_report": "📊 Fundamentals Analyst",
            "technical_report": "🔍 Technical Analyst",
            "sentiment_report": "💭 Sentiment Analyst",
            "final_report": "🤖 Signal Processor"
        }

        # Track completed analysts to avoid duplicate notifications
        completed_analysts = set()

        for chunk in graph.graph.stream(init_agent_state, **args):
            if len(chunk["messages"]) > 0:
                # Get the last message from the chunk
                last_message = chunk["messages"][-1]

                # Extract message content and type
                if hasattr(last_message, "content"):
                    content = extract_content_string(last_message.content)  # Use the helper function
                    msg_type = "Reasoning"
                else:
                    content = str(last_message)
                    msg_type = "System"

                # Add message to buffer
                message_buffer.add_message(msg_type, content)                

                # If it's a tool call, add it to tool calls
                if hasattr(last_message, "tool_calls"):
                    for tool_call in last_message.tool_calls:
                        # Handle both dictionary and object tool calls
                        if isinstance(tool_call, dict):
                            message_buffer.add_tool_call(
                                tool_call["name"], tool_call["args"]
                            )
                        else:
                            message_buffer.add_tool_call(tool_call.name, tool_call.args)

                # Update reports and agent status based on chunk content
                # Analyst Team Reports
                if "market_report" in chunk and chunk["market_report"]:
                    # Show notification only on first completion
                    if "market_report" not in completed_analysts:
                        ui.show_success("📈 Market analysis completed")
                        completed_analysts.add("market_report")
                        logger.info(f"First market analysis completion notification shown; completed analysts: {completed_analysts}")
                    else:
                        logger.debug(f"Skipping duplicate market analysis completion notification; completed analysts: {completed_analysts}")

                    message_buffer.update_report_section(
                        "market_report", chunk["market_report"]
                    )
                    message_buffer.update_agent_status("Market Analyst", "completed")
                    # Set next analyst to in_progress
                    if "social" in selections["analysts"]:
                        message_buffer.update_agent_status(
                            "Social Analyst", "in_progress"
                        )

                if "sentiment_report" in chunk and chunk["sentiment_report"]:
                    # Show notification only on first completion
                    if "sentiment_report" not in completed_analysts:
                        ui.show_success("💭 Sentiment analysis completed")
                        completed_analysts.add("sentiment_report")
                        logger.info(f"First sentiment analysis completion notification shown; completed analysts: {completed_analysts}")
                    else:
                        logger.debug(f"Skipping duplicate sentiment analysis completion notification; completed analysts: {completed_analysts}")

                    message_buffer.update_report_section(
                        "sentiment_report", chunk["sentiment_report"]
                    )
                    message_buffer.update_agent_status("Social Analyst", "completed")
                    # Set next analyst to in_progress
                    if "news" in selections["analysts"]:
                        message_buffer.update_agent_status(
                            "News Analyst", "in_progress"
                        )

                if "news_report" in chunk and chunk["news_report"]:
                    # Show notification only on first completion
                    if "news_report" not in completed_analysts:
                        ui.show_success("📰 News analysis completed")
                        completed_analysts.add("news_report")
                        logger.info(f"First news analysis completion notification shown; completed analysts: {completed_analysts}")
                    else:
                        logger.debug(f"Skipping duplicate news analysis completion notification; completed analysts: {completed_analysts}")

                    message_buffer.update_report_section(
                        "news_report", chunk["news_report"]
                    )
                    message_buffer.update_agent_status("News Analyst", "completed")
                    # Set next analyst to in_progress
                    if "fundamentals" in selections["analysts"]:
                        message_buffer.update_agent_status(
                            "Fundamentals Analyst", "in_progress"
                        )

                if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
                    # Show notification only on first completion
                    if "fundamentals_report" not in completed_analysts:
                        ui.show_success("📊 Fundamentals analysis completed")
                        completed_analysts.add("fundamentals_report")
                        logger.info(f"First fundamentals analysis completion notification shown; completed analysts: {completed_analysts}")
                    else:
                        logger.debug(f"Skipping duplicate fundamentals analysis completion notification; completed analysts: {completed_analysts}")

                    message_buffer.update_report_section(
                        "fundamentals_report", chunk["fundamentals_report"]
                    )
                    message_buffer.update_agent_status(
                        "Fundamentals Analyst", "completed"
                    )
                    # Set all research team members to in_progress
                    update_research_team_status("in_progress")

                # Research Team - Handle Investment Debate State
                if (
                    "investment_debate_state" in chunk
                    and chunk["investment_debate_state"]
                ):
                    debate_state = chunk["investment_debate_state"]

                    # Update Bull Researcher status and report
                    if "bull_history" in debate_state and debate_state["bull_history"]:
                        # Show research team started notification
                        if "research_team_started" not in completed_analysts:
                            ui.show_progress("🔬 Research team starting in-depth analysis...")
                            completed_analysts.add("research_team_started")

                        # Keep all research team members in progress
                        update_research_team_status("in_progress")
                        # Extract latest bull response
                        bull_responses = debate_state["bull_history"].split("\n")
                        latest_bull = bull_responses[-1] if bull_responses else ""
                        if latest_bull:
                            message_buffer.add_message("Reasoning", latest_bull)
                            # Update research report with bull's latest analysis
                            message_buffer.update_report_section(
                                "investment_plan",
                                f"### Bull Researcher Analysis\n{latest_bull}",
                            )

                    # Update Bear Researcher status and report
                    if "bear_history" in debate_state and debate_state["bear_history"]:
                        # Keep all research team members in progress
                        update_research_team_status("in_progress")
                        # Extract latest bear response
                        bear_responses = debate_state["bear_history"].split("\n")
                        latest_bear = bear_responses[-1] if bear_responses else ""
                        if latest_bear:
                            message_buffer.add_message("Reasoning", latest_bear)
                            # Update research report with bear's latest analysis
                            message_buffer.update_report_section(
                                "investment_plan",
                                f"{message_buffer.report_sections['investment_plan']}\n\n### Bear Researcher Analysis\n{latest_bear}",
                            )

                    # Update Research Manager status and final decision
                    if (
                        "judge_decision" in debate_state
                        and debate_state["judge_decision"]
                    ):
                        # Show research team completion notification
                        if "research_team" not in completed_analysts:
                            ui.show_success("🔬 Research team analysis completed")
                            completed_analysts.add("research_team")

                        # Keep all research team members in progress until final decision
                        update_research_team_status("in_progress")
                        message_buffer.add_message(
                            "Reasoning",
                            f"Research Manager: {debate_state['judge_decision']}",
                        )
                        # Update research report with final decision
                        message_buffer.update_report_section(
                            "investment_plan",
                            f"{message_buffer.report_sections['investment_plan']}\n\n### Research Manager Decision\n{debate_state['judge_decision']}",
                        )
                        # Mark all research team members as completed
                        update_research_team_status("completed")
                        # Set first risk analyst to in_progress
                        message_buffer.update_agent_status(
                            "Risky Analyst", "in_progress"
                        )

                # Trading Team
                if (
                    "trader_investment_plan" in chunk
                    and chunk["trader_investment_plan"]
                ):
                    # Show trading team started notification
                    if "trading_team_started" not in completed_analysts:
                        ui.show_progress("💼 Trading team formulating investment plan...")
                        completed_analysts.add("trading_team_started")

                    # Show trading team completion notification
                    if "trading_team" not in completed_analysts:
                        ui.show_success("💼 Trading team plan completed")
                        completed_analysts.add("trading_team")

                    message_buffer.update_report_section(
                        "trader_investment_plan", chunk["trader_investment_plan"]
                    )
                    # Set first risk analyst to in_progress
                    message_buffer.update_agent_status("Risky Analyst", "in_progress")

                # Risk Management Team - Handle Risk Debate State
                if "risk_debate_state" in chunk and chunk["risk_debate_state"]:
                    risk_state = chunk["risk_debate_state"]

                    # Update Risky Analyst status and report
                    if (
                        "current_risky_response" in risk_state
                        and risk_state["current_risky_response"]
                    ):
                        # Show risk management team started notification
                        if "risk_team_started" not in completed_analysts:
                            ui.show_progress("⚖️ Risk management team evaluating investment risks...")
                            completed_analysts.add("risk_team_started")

                        message_buffer.update_agent_status(
                            "Risky Analyst", "in_progress"
                        )
                        message_buffer.add_message(
                            "Reasoning",
                            f"Risky Analyst: {risk_state['current_risky_response']}",
                        )
                        # Update risk report with risky analyst's latest analysis only
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### Risky Analyst Analysis\n{risk_state['current_risky_response']}",
                        )

                    # Update Safe Analyst status and report
                    if (
                        "current_safe_response" in risk_state
                        and risk_state["current_safe_response"]
                    ):
                        message_buffer.update_agent_status(
                            "Safe Analyst", "in_progress"
                        )
                        message_buffer.add_message(
                            "Reasoning",
                            f"Safe Analyst: {risk_state['current_safe_response']}",
                        )
                        # Update risk report with safe analyst's latest analysis only
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### Safe Analyst Analysis\n{risk_state['current_safe_response']}",
                        )

                    # Update Neutral Analyst status and report
                    if (
                        "current_neutral_response" in risk_state
                        and risk_state["current_neutral_response"]
                    ):
                        message_buffer.update_agent_status(
                            "Neutral Analyst", "in_progress"
                        )
                        message_buffer.add_message(
                            "Reasoning",
                            f"Neutral Analyst: {risk_state['current_neutral_response']}",
                        )
                        # Update risk report with neutral analyst's latest analysis only
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### Neutral Analyst Analysis\n{risk_state['current_neutral_response']}",
                        )

                    # Update Portfolio Manager status and final decision
                    if "judge_decision" in risk_state and risk_state["judge_decision"]:
                        # Show risk management team completion notification
                        if "risk_management" not in completed_analysts:
                            ui.show_success("⚖️ Risk management team analysis completed")
                            completed_analysts.add("risk_management")

                        message_buffer.update_agent_status(
                            "Portfolio Manager", "in_progress"
                        )
                        message_buffer.add_message(
                            "Reasoning",
                            f"Portfolio Manager: {risk_state['judge_decision']}",
                        )
                        # Update risk report with final decision only
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### Portfolio Manager Decision\n{risk_state['judge_decision']}",
                        )
                        # Mark risk analysts as completed
                        message_buffer.update_agent_status("Risky Analyst", "completed")
                        message_buffer.update_agent_status("Safe Analyst", "completed")
                        message_buffer.update_agent_status(
                            "Neutral Analyst", "completed"
                        )
                        message_buffer.update_agent_status(
                            "Portfolio Manager", "completed"
                        )

                # Update the display
                update_display(layout)

            trace.append(chunk)

        # Display final decision phase
        ui.show_step_header(5, "Investment Decision Generation")
        ui.show_progress("Processing investment signals...")

        # Get final state and decision
        final_state = trace[-1]
        decision = graph.process_signal(final_state["final_trade_decision"], selections['ticker'])

        ui.show_success("🤖 Investment signal processing completed")

        # Update all agent statuses to completed
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message(
            "Analysis", f"Completed analysis for {selections['analysis_date']}"
        )

        # Update final report sections
        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        # Display report generation phase
        ui.show_step_header(6, "Analysis Report Generation")
        ui.show_progress("Generating final report...")

        # Display the complete final report
        display_complete_report(final_state)

        ui.show_success("📋 Analysis report generation completed")
        ui.show_success(f"🎉 {selections['ticker']} stock analysis completed!")
        
        # Record total execution time
        total_time = time.time() - start_time
        ui.show_user_message(f"⏱️ Total analysis time: {total_time:.1f}s", "dim")

        update_display(layout)


@app.command(
    name="analyze",
    help="Start stock analysis"
)
def analyze():
    """
    Launch interactive stock analysis tool
    """
    run_analysis()


@app.command(
    name="config",
    help="Configuration settings"
)
def config():
    """
    Display and configure system settings
    """
    logger.info("\n[bold blue]🔧 TradingAgents Configuration[/bold blue]")
    logger.info("\n[yellow]Supported LLM Providers:[/yellow]")

    providers_table = Table(show_header=True, header_style="bold magenta")
    providers_table.add_column("Provider", style="cyan")
    providers_table.add_column("Models", style="green")
    providers_table.add_column("Status", style="yellow")
    providers_table.add_column("Description")

    providers_table.add_row(
        "🇨🇳 Alibaba Bailian (DashScope)",
        "qwen-turbo, qwen-plus, qwen-max",
        "✅ Recommended",
        "Domestic flagship models, Chinese-optimized"
    )
    providers_table.add_row(
        "🌍 OpenAI",
        "gpt-4o, gpt-4o-mini, gpt-3.5-turbo",
        "✅ Supported",
        "Requires international API access"
    )
    providers_table.add_row(
        "🤖 Anthropic",
        "claude-3-opus, claude-3-sonnet",
        "✅ Supported",
        "Requires international API access"
    )
    providers_table.add_row(
        "🔍 Google AI",
        "gemini-pro, gemini-2.0-flash",
        "✅ Supported",
        "Requires international API access"
    )

    console.print(providers_table)

    # Check API key status
    logger.info("\n[yellow]API Key Status:[/yellow]")

    api_keys_table = Table(show_header=True, header_style="bold magenta")
    api_keys_table.add_column("API Key", style="cyan")
    api_keys_table.add_column("Status", style="yellow")
    api_keys_table.add_column("Description")

    # Check individual API keys
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")

    api_keys_table.add_row(
        "DASHSCOPE_API_KEY",
        "✅ Configured" if dashscope_key else "❌ Not configured",
        f"Alibaba Bailian | {dashscope_key[:DEFAULT_API_KEY_DISPLAY_LENGTH]}..." if dashscope_key else "Alibaba Bailian API key"
    )
    api_keys_table.add_row(
        "FINNHUB_API_KEY",
        "✅ Configured" if finnhub_key else "❌ Not configured",
        f"Financial data | {finnhub_key[:DEFAULT_API_KEY_DISPLAY_LENGTH]}..." if finnhub_key else "Financial data API key"
    )
    api_keys_table.add_row(
        "OPENAI_API_KEY",
        "✅ Configured" if openai_key else "❌ Not configured",
        f"OpenAI | {openai_key[:DEFAULT_API_KEY_DISPLAY_LENGTH]}..." if openai_key else "OpenAI API key"
    )
    api_keys_table.add_row(
        "ANTHROPIC_API_KEY",
        "✅ Configured" if anthropic_key else "❌ Not configured",
        f"Anthropic | {anthropic_key[:DEFAULT_API_KEY_DISPLAY_LENGTH]}..." if anthropic_key else "Anthropic API key"
    )
    api_keys_table.add_row(
        "GOOGLE_API_KEY",
        "✅ Configured" if google_key else "❌ Not configured",
        f"Google AI | {google_key[:DEFAULT_API_KEY_DISPLAY_LENGTH]}..." if google_key else "Google AI API key"
    )

    console.print(api_keys_table)

    logger.info("\n[yellow]Configure API Keys:[/yellow]")
    logger.info("1. Edit the .env file in the project root")
    logger.info("2. Or set environment variables:")
    logger.info("   - DASHSCOPE_API_KEY (Alibaba Bailian / DashScope)")
    logger.info("   - OPENAI_API_KEY (OpenAI)")
    logger.info("   - FINNHUB_API_KEY (Financial data)")

    # Warn if critical API keys are missing
    if not dashscope_key or not finnhub_key:
        logger.warning("[red]⚠️ Warning:[/red]")
        if not dashscope_key:
            logger.info("   • DASHSCOPE_API_KEY is missing; recommended Chinese-optimized models are unavailable")
        if not finnhub_key:
            logger.info("   • FINNHUB_API_KEY is missing; real-time US stock data may be unavailable")

    logger.info("\n[yellow]Example Programs:[/yellow]")
    logger.info("• python examples/dashscope/demo_dashscope_chinese.py  # DashScope analysis demo")
    logger.info("• python examples/dashscope/demo_dashscope_simple.py   # Simple test")
    logger.info("• python tests/integration/test_dashscope_integration.py  # Integration test")


@app.command(
    name="version",
    help="Version information"
)
def version():
    """
    Display version information
    """
    # Read version number
    try:
        with open("VERSION", "r", encoding="utf-8") as f:
            version = f.read().strip()
    except FileNotFoundError:
        version = "1.0.0"

    logger.info("\n[bold blue]📊 TradingAgents Version Information[/bold blue]")
    logger.info(f"[green]Version:[/green] {version} [yellow](Preview)[/yellow]")
    logger.info("[green]Release Date:[/green] 2025-06-26")
    logger.info("[green]Framework:[/green] Multi-Agent Financial Trading Analysis")
    logger.info("[green]Supported Languages:[/green] English / Chinese")
    logger.info("[green]Development Status:[/green] [yellow]Early preview; features under active development[/yellow]")
    logger.info("[green]Based on:[/green] [blue]TauricResearch/TradingAgents[/blue]")
    logger.info("[green]Purpose:[/green] [cyan]Enhanced multi-market support for TradingAgents[/cyan]")
    logger.info("[green]Features:[/green]")
    logger.info("  • 🤖 Multi-agent collaborative analysis")
    logger.info("  • 🇨🇳 Alibaba Bailian (DashScope) LLM support")
    logger.info("  • 📈 Real-time stock data analysis")
    logger.info("  • 🧠 Intelligent investment recommendations")
    logger.debug("  • 🔍 Risk assessment")

    logger.warning("\n[yellow]⚠️  Preview Version Notice:[/yellow]")
    logger.info("  • This is an early preview release; features are still being refined")
    logger.info("  • Recommended for testing and educational environments only")
    logger.info("  • Investment recommendations are for reference only; please make decisions prudently")
    logger.info("  • Feedback and improvement suggestions are welcome")

    logger.info("\n[blue]🙏 Tribute to Original Project:[/blue]")
    logger.info("  • 💎 Thanks to the Tauric Research team for the open-source codebase")
    logger.info("  • 🔄 Thanks for continuous maintenance, updates, and improvements")
    logger.info("  • 🌍 Released under the Apache 2.0 open-source license")
    logger.info("  • 🔗 Upstream repository: https://github.com/TauricResearch/TradingAgents")


@app.command(
    name="data-config",
    help="Data directory configuration"
)
def data_config(
    show: bool = typer.Option(False, "--show", "-s", help="Show current configuration"),
    set_dir: Optional[str] = typer.Option(None, "--set", "-d", help="Set data directory"),
    reset: bool = typer.Option(False, "--reset", "-r", help="Reset to default configuration")
):
    """
    Configure data directory paths
    """
    from tradingagents.config.config_manager import config_manager

    # Use config_manager methods
    get_data_dir = config_manager.get_data_dir
    set_data_dir = config_manager.set_data_dir
    
    logger.info("\n[bold blue]📁 Data Directory Configuration[/bold blue]")
    
    if reset:
        # Reset to default configuration
        default_data_dir = os.path.join(os.path.expanduser("~"), "Documents", "TradingAgents", "data")
        set_data_dir(default_data_dir)
        logger.info(f"[green]✅ Reset data directory to default path: {default_data_dir}[/green]")
        return
    
    if set_dir:
        # Set new data directory
        try:
            set_data_dir(set_dir)
            logger.info(f"[green]✅ Data directory set to: {set_dir}[/green]")
            
            # Display created directory structure
            if os.path.exists(set_dir):
                logger.info("\n[blue]📂 Directory Structure:[/blue]")
                for root, dirs, files in os.walk(set_dir):
                    level = root.replace(set_dir, '').count(os.sep)
                    if level > 2:  # Limit display depth
                        continue
                    indent = '  ' * level
                    logger.info(f"{indent}📁 {os.path.basename(root)}/")
        except Exception as e:
            logger.error(f"[red]❌ Failed to set data directory: {e}[/red]")
        return
    
    # Show current configuration (default behavior or --show)
    settings = config_manager.load_settings()
    current_data_dir = get_data_dir()
    
    # Configuration table
    config_table = Table(show_header=True, header_style="bold magenta")
    config_table.add_column("Configuration", style="cyan")
    config_table.add_column("Path", style="green")
    config_table.add_column("Status", style="yellow")
    
    directories = {
        "Data Directory": settings.get("data_dir", "Not configured"),
        "Cache Directory": settings.get("cache_dir", "Not configured"),
        "Results Directory": settings.get("results_dir", "Not configured")
    }
    
    for name, path in directories.items():
        if path and path != "Not configured":
            status = "✅ Exists" if os.path.exists(path) else "❌ Does not exist"
        else:
            status = "⚠️ Not configured"
        config_table.add_row(name, str(path), status)
    
    console.print(config_table)
    
    # Environment variables info
    logger.info("\n[blue]🌍 Environment Variables:[/blue]")
    env_table = Table(show_header=True, header_style="bold magenta")
    env_table.add_column("Variable", style="cyan")
    env_table.add_column("Value", style="green")
    
    env_vars = {
        "TRADINGAGENTS_DATA_DIR": os.getenv("TRADINGAGENTS_DATA_DIR", "Not set"),
        "TRADINGAGENTS_CACHE_DIR": os.getenv("TRADINGAGENTS_CACHE_DIR", "Not set"),
        "TRADINGAGENTS_RESULTS_DIR": os.getenv("TRADINGAGENTS_RESULTS_DIR", "Not set")
    }
    
    for var, value in env_vars.items():
        env_table.add_row(var, value)
    
    console.print(env_table)
    
    # Usage instructions
    logger.info("\n[yellow]💡 Usage:[/yellow]")
    logger.info("• Set data directory: tradingagents data-config --set /path/to/data")
    logger.info("• Reset to default: tradingagents data-config --reset")
    logger.info("• Show current config: tradingagents data-config --show")
    logger.info("• Environment variables take highest priority")


@app.command(
    name="examples",
    help="Example programs"
)
def examples():
    """
    Display available example programs
    """
    logger.info("\n[bold blue]📚 TradingAgents Example Programs[/bold blue]")

    examples_table = Table(show_header=True, header_style="bold magenta")
    examples_table.add_column("Type", style="cyan")
    examples_table.add_column("Filename", style="green")
    examples_table.add_column("Description")

    examples_table.add_row(
        "🇨🇳 Alibaba Bailian",
        "examples/dashscope/demo_dashscope_chinese.py",
        "Chinese-optimized stock analysis demonstration"
    )
    examples_table.add_row(
        "🇨🇳 Alibaba Bailian",
        "examples/dashscope/demo_dashscope.py",
        "Full feature demonstration"
    )
    examples_table.add_row(
        "🇨🇳 Alibaba Bailian",
        "examples/dashscope/demo_dashscope_simple.py",
        "Simplified test version"
    )
    examples_table.add_row(
        "🌍 OpenAI",
        "examples/openai/demo_openai.py",
        "OpenAI model demonstration"
    )
    examples_table.add_row(
        "🧪 Test",
        "tests/integration/test_dashscope_integration.py",
        "Integration test"
    )
    examples_table.add_row(
        "📁 Config Demo",
        "examples/data_dir_config_demo.py",
        "Data directory configuration demo"
    )

    console.print(examples_table)

    logger.info("\n[yellow]Run Examples:[/yellow]")
    logger.info("1. Ensure API keys are configured")
    logger.info("2. Choose an appropriate example program to run")
    logger.info("3. Recommended to start with the DashScope examples")


@app.command(
    name="test",
    help="Run tests"
)
def test():
    """
    Run system tests
    """
    logger.info("\n[bold blue]🧪 TradingAgents Tests[/bold blue]")

    logger.info("[yellow]Running integration tests...[/yellow]")

    try:
        result = subprocess.run([
            sys.executable,
            "tests/integration/test_dashscope_integration.py"
        ], capture_output=True, text=True, cwd=".")

        if result.returncode == 0:
            logger.info("[green]✅ Tests passed[/green]")
            console.print(result.stdout)
        else:
            logger.error("[red]❌ Tests failed[/red]")
            console.print(result.stderr)

    except Exception as e:
        logger.error(f"[red]❌ Test execution error: {e}[/red]")
        logger.info("\n[yellow]Manual test execution:[/yellow]")
        logger.info("python tests/integration/test_dashscope_integration.py")


@app.command(
    name="help",
    help="Display help information"
)
def help_chinese():
    """
    Display CLI help information
    """
    logger.info("\n[bold blue]📖 TradingAgents CLI Help[/bold blue]")

    logger.info("\n[bold yellow]🚀 Quick Start:[/bold yellow]")
    logger.info("1. [cyan]python -m cli.main config[/cyan]     # View configuration settings")
    logger.info("2. [cyan]python -m cli.main examples[/cyan]   # View example programs")
    logger.info("3. [cyan]python -m cli.main test[/cyan]       # Run integration tests")
    logger.info("4. [cyan]python -m cli.main analyze[/cyan]    # Start interactive stock analysis")

    logger.info("\n[bold yellow]📋 Main Commands:[/bold yellow]")

    commands_table = Table(show_header=True, header_style="bold magenta")
    commands_table.add_column("Command", style="cyan")
    commands_table.add_column("Function", style="green")
    commands_table.add_column("Description")

    commands_table.add_row(
        "analyze",
        "Stock Analysis",
        "Launch the interactive multi-agent stock analysis tool"
    )
    commands_table.add_row(
        "config",
        "Configuration",
        "View and configure LLM providers, API keys, and other settings"
    )
    commands_table.add_row(
        "examples",
        "Examples",
        "View available demo programs and usage instructions"
    )
    commands_table.add_row(
        "test",
        "Run Tests",
        "Execute system integration tests to verify functionality"
    )
    commands_table.add_row(
        "version",
        "Version",
        "Display software version and feature information"
    )

    console.print(commands_table)

    logger.info("\n[bold yellow]🇨🇳 Alibaba Bailian (DashScope) Highlights:[/bold yellow]")
    logger.info("• Stable domestic network connectivity")
    logger.info("• Strong Chinese financial context understanding")
    logger.info("• Cost-effective pricing")
    logger.info("• Compliant with domestic regulatory requirements")

    logger.info("\n[bold yellow]📞 Get Help:[/bold yellow]")
    logger.info("• Documentation: docs/ directory")
    logger.info("• Examples: examples/ directory")
    logger.info("• Integration tests: tests/ directory")
    logger.info("• GitHub: https://github.com/TauricResearch/TradingAgents")


def main():
    """Main entry point - enters analysis mode by default when called without arguments"""

    # If no arguments are passed, enter analysis mode directly
    if len(sys.argv) == 1:
        run_analysis()
    else:
        # Use typer to handle commands when arguments are provided
        try:
            app()
        except SystemExit as e:
            # Provide smart suggestions only on exit code 2 (typer unknown command error)
            if e.code == 2 and len(sys.argv) > 1:
                unknown_command = sys.argv[1]
                available_commands = ['analyze', 'config', 'version', 'data-config', 'examples', 'test', 'help']
                
                # Find the closest matching commands using difflib
                suggestions = get_close_matches(unknown_command, available_commands, n=3, cutoff=0.6)
                
                if suggestions:
                    logger.error(f"\n[red]❌ Unknown command: '{unknown_command}'[/red]")
                    logger.info("[yellow]💡 Did you mean one of these commands?[/yellow]")
                    for suggestion in suggestions:
                        logger.info(f"   • [cyan]python -m cli.main {suggestion}[/cyan]")
                    logger.info("\n[dim]Use [cyan]python -m cli.main help[/cyan] to see all available commands[/dim]")
                else:
                    logger.error(f"\n[red]❌ Unknown command: '{unknown_command}'[/red]")
                    logger.info("[yellow]Use [cyan]python -m cli.main help[/cyan] to see all available commands[/yellow]")
            raise e

if __name__ == "__main__":
    main()
