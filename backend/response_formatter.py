import re

def format_response(text: str) -> str:
    """
    Converts raw LLM markdown text into clean, structured plain text.
    
    Args:
        text (str): Raw markdown string from the LLM.
    
    Returns:
        str: Cleaned, human-readable plain text.
    """
    if not text:
        return text

    lines = text.split('\n')
    output = []

    for line in lines:
        # ── H1 / H2 / H3 headings → UPPERCASE label
        line = re.sub(r'^#{1,3}\s+(.+)', lambda m: f"\n{'━' * 40}\n  {m.group(1).upper()}\n{'━' * 40}", line)

        # ── Bold **text** or __text__ → just the text (no asterisks)
        line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
        line = re.sub(r'__(.+?)__', r'\1', line)

        # ── Italic *text* or _text_ → just the text
        line = re.sub(r'\*(.+?)\*', r'\1', line)
        line = re.sub(r'_(.+?)_', r'\1', line)

        # ── Unordered bullets: * or - at start → clean bullet
        line = re.sub(r'^\s*[\*\-]\s+', '  • ', line)

        # ── Numbered lists: "1. item" stays clean but with extra indent
        line = re.sub(r'^\s*(\d+)\.\s+', r'  \1. ', line)

        # ── Inline code `code` → strip backticks
        line = re.sub(r'`(.+?)`', r'"\1"', line)

        # ── Code blocks ``` → skip the fence lines
        if line.strip().startswith('```'):
            continue

        # ── Horizontal rules --- or ***
        if re.match(r'^(\-{3,}|\*{3,}|_{3,})$', line.strip()):
            line = '  ' + '─' * 38

        output.append(line)

    result = '\n'.join(output)

    # ── Collapse more than 2 consecutive blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


def format_tool_result(tool_name: str, result: str) -> str:
    """
    Wraps a tool result in a neat system block before feeding back to the LLM.
    """
    tool_label = tool_name.replace('_', ' ').upper()
    divider = '─' * 40
    return f"\n{divider}\n  TOOL RESULT: {tool_label}\n{divider}\n{result}\n{divider}\n"
