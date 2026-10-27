"""
A Stock ticker standardization tool

For the code generator to reference in Prompt, so that the generated Skill supports multiple input formats.
The generated code runs in a sandbox and cannot import core, so the logic needs to be inlined into the generated code.
"""


def normalize_a_share_symbol(symbol: str) -> str:
    """
    Unify multiple formats of A-share codes into a 6-digit code.

    Supported input formats:
    - 600519 (pure numbers)
    - SH600519, SZ000001, BJ830001, BJ920985 (exchange prefix)
    - 600519.SH, 000001.SZ, 830001.BJ, 920985.BJ (Exchange suffix, 920 is the unified number section of the Beijing Stock Exchange starting from 2025-10)

    Args:
        symbol: Stock code entered by user

    Returns:
        6 digit code such as "600519", "000001"
    """
    if not symbol:
        return ""
    s = str(symbol).strip().upper()
    # Remove SH/SZ/SS/BJ prefix
    for prefix in ("SH", "SZ", "SS", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Remove .SH/.SZ/.SS/.BJ suffix
    for suffix in (".SH", ".SZ", ".SS", ".BJ"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    # Keep only numbers
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return ""
    # Keep 6 digits (A-share standard). If insufficient, leading zeros will be added. If exceeded, the last 6 digits will be used.
    return digits.zfill(6)[-6:] if len(digits) <= 6 else digits[-6:]


# Inline code snippet (for Prompt injection, used when LLM is generated)
# The generated Skill cannot import core, so the logic needs to be copied into the function body.
SYMBOL_NORMALIZE_INLINE = '''
def _normalize_a_share_symbol(symbol: str) -> str:
    """Unify multiple formats of A-share codes into 6 digits. support: 600519, SH600519, 600519.SH, 830001.BJ, 920985.BJ Wait"""
    if not symbol:
        return ""
    s = str(symbol).strip().upper()
    for prefix in ("SH", "SZ", "SS", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    for suffix in (".SH", ".SZ", ".SS", ".BJ"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return ""
    return digits[-6:].zfill(6) if len(digits) <= 6 else digits[-6:]
'''
