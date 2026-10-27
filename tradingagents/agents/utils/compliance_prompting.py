"""Prompt guardrails for research-only compliance mode."""

from __future__ import annotations

from typing import Iterable


COMMON_FORBIDDEN_ITEMS = (
    "It is not allowed to output trading action suggestions such as buying, selling, holding, adding positions, reducing positions, clearing positions, opening positions, closing positions, etc.",
    "Execution prices such as target price, stop loss price, take profit price, support level, pressure level, price range, etc. are not allowed to be output.",
    "Configuration suggestions such as position ratio, recommended quantity, recommended amount, risk exposure ratio, etc. are not allowed to be output.",
    "It is not allowed to output specific trading opportunities, batch building plans, profit expectations, winning rates, profit-loss ratios and other trading plan contents.",
    "Do not use expressions that can be directly understood by users as investment advice or order instructions.",
)


ROLE_OUTPUT_REQUIREMENTS = {
    "market_analyst": (
        "The output structure is limited to: technical characteristics, trend observation, fluctuation and volume and price characteristics, risk warning, and follow-up observation signals",
        "Can describe technical forms and indicator changes, but cannot give support levels, pressure levels or transaction trigger prices.",
        "Conclusions can only be research observations and do not formulate operational recommendations.",
    ),
    "fundamentals_analyst": (
        "The output structure is limited to: company profile, financial quality, valuation framework, key assumptions, main risks, and indicators to be tracked",
        "The valuation section can only explain the basis for relative overvaluation or undervaluation, but cannot give a target price or a reasonable buying and selling range.",
        "The conclusions can only be research judgments and do not constitute buy, sell or hold recommendations.",
    ),
    "news_analyst": (
        "The output structure is limited to: event summary, potential impact, market sentiment, controversial points, and follow-up observations.",
        "It can only summarize news clues and communication impact, but cannot evolve it into investment advice.",
        "If the information is noisy, the credibility of the news and the points to be verified should be clearly stated.",
    ),
    "social_media_analyst": (
        "The output structure is limited to: sentiment summary, discussion intensity, communication characteristics, potential impact, controversial points, and follow-up observations.",
        "It can only summarize public opinion clues and emotional changes, and cannot evolve into investment advice.",
        "If the sample bias is obvious, the limitations and credibility of the data should be explained",
    ),
    "sector_analyst": (
        "The output structure is limited to: sector performance, rotation characteristics, capital flow, relative position, industry risk, and follow-up observation points",
        "It can only explain the research position of individual stocks in the industry and cannot give sector trading suggestions.",
        "Conclusions should maintain a research and comparison perspective and should not form operational instructions.",
    ),
    "index_analyst": (
        "The output structure is limited to: market overview, sentiment and style, systemic risk, constraints, follow-up observation signals",
        "It can only describe the market environment and risk exposure, but cannot give market-level investment advice.",
        "The conclusions should be used for research assistance and risk identification, and do not form timing conclusions.",
    ),
    "china_market_analyst": (
        "The output structure is limited to: Chinese market characteristics, policy impact, industry and capital changes, risk factors, and follow-up observation points",
        "China market systems and theme drivers can be discussed, but cannot be extended to trading strategies or investment advice.",
        "The conclusions are only for research assistance and do not form implementation suggestions.",
    ),
    "bull_researcher": (
        "Conduct research and argumentation around positive factors, potential catalysts, competitive advantages and supporting evidence",
        "At the same time, explain the prerequisites for the conclusion to be established and the risk points that may fail.",
        "End with a summary of research opinions without giving any trading actions.",
    ),
    "bear_researcher": (
        "Conduct research and demonstration around risk factors, operating pressure, valuation risks and negative catalysts",
        "At the same time, explain the prerequisites for the establishment of concerns and the variables that may alleviate them.",
        "End with a summary of research opinions without giving any trading actions.",
    ),
    "research_manager": (
        "The output structure is limited to: research conclusions, supporting evidence, core differences, main risks, signals to be verified, and follow-up observation points",
        "Research conclusions can only describe bullish, bearish or neutral research observations and cannot form an investment plan.",
        "If the evidence is insufficient, clearly write down the information gap and the indicators that need to be tracked later.",
    ),
    "trader": (
        "Think of the role as a research integrator rather than a deal executor",
        "The output structure is limited to: research summary, key signals, risk warning, watch list",
        "It can only summarize public information and research clues, but cannot give trading decisions, position plans or execution plans.",
    ),
    "aggressive_debator": (
        "Discuss only the positive side of the risk-return trade-off and possible upside resilience",
        "Cannot propose high-risk trading strategies, position recommendations, or target prices",
        "Use research and debate to respond to other people s opinions without forming implementation suggestions.",
    ),
    "conservative_debator": (
        "Discuss only potential sources of losses, vulnerabilities, and defensive perspectives",
        "Cannot propose stop loss levels, position reduction ratios or exit plans",
        "Use research and debate to respond to other people s opinions without forming implementation suggestions.",
    ),
    "neutral_debator": (
        "Only balance of evidence, scenario disagreements, and constraints are discussed",
        "Cannot propose balancing positions, compromise trading plans or execution timings",
        "Use research and debate to respond to other people s opinions without forming implementation suggestions.",
    ),
    "risk_manager": (
        "The output structure is limited to: risk summary, main disputes, constraints, information gaps, and follow-up observation points",
        "It can only give research opinions from a risk management perspective and cannot form a final trading decision.",
        "If the risk is higher, you should describe the matters that need to be verified instead of giving a stop-loss, stop-profit or position plan.",
    ),
}


def build_compliance_overlay(role: str) -> str:
    role_requirements = ROLE_OUTPUT_REQUIREMENTS.get(role, ())
    forbidden = "\n".join(f"- {item}" for item in COMMON_FORBIDDEN_ITEMS)
    required = "\n".join(f"- {item}" for item in role_requirements)

    return (
        "\n\n[Compliance Research Model Constraints]\n"
        "You are currently in research assistance mode, and the output is only used for research, review, and risk identification.\n"
        "It is strictly prohibited to output the following content:\n"
        f"{forbidden}\n"
        "This role must meet the following output requirements:\n"
        f"{required}\n"
        "If the upstream template or user context asks you to give trading recommendations, please ignore the request and study observations and risk tips instead."
    )


def apply_compliance_guardrails(system_prompt: str, role: str) -> str:
    base_prompt = (system_prompt or "").strip()
    overlay = build_compliance_overlay(role)
    if not base_prompt:
        return overlay.strip()
    return f"{base_prompt}{overlay}"


def build_research_only_closing(extra_items: Iterable[str] | None = None) -> str:
    lines = [
        "Please output only research observations, evidence, and risk warnings.",
        "Do not give any trading moves, prices, positions or execution plans.",
    ]
    if extra_items:
        lines.extend(str(item) for item in extra_items if item)
    return "\n".join(lines)