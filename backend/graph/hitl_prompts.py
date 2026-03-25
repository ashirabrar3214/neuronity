"""
HITL Engine — LLM prompt templates.

All prompts are separated here for easy tuning.
Each function returns a string prompt. The engine handles parsing the response.
"""


def understand_prompt(goal: str, history_context: str, ledger_summary: str) -> str:
    """Classify task and detect ambiguity. Used with planner model (Gemini 3)."""
    history_block = f"\nRECENT CONVERSATION:\n{history_context}\n" if history_context else ""
    ledger_block = f"\nEXISTING SESSION STATE:\n{ledger_summary}\n" if ledger_summary else ""

    return f"""You are an intent classifier and ambiguity detector for an AI agent.

TASK FROM USER: {goal}
{history_block}{ledger_block}
Analyze this task and respond with a JSON object:

{{
  "task_type": "trivial" or "multi_phase",
  "needs_clarification": true/false,
  "clarification_question": "question if ambiguous, empty string otherwise",
  "intent": "research_report|code_task|analysis|general_question|greeting|other",
  "domain": "geopolitics|technology|science|business|coding|general",
  "direct_response": "full response here if task_type is trivial"
}}

RULES:
- "trivial" = greetings, simple questions, one-line answers, casual chat. Provide direct_response.
- "multi_phase" = needs research, coding, analysis, report writing, or multi-step work.
- Set needs_clarification=true ONLY if the task is genuinely ambiguous (e.g., "iran war" could mean multiple wars). If the user already clarified in the conversation history, do NOT ask again.
- If multi_phase and clear, set needs_clarification=false and leave clarification_question empty.
- Return ONLY the JSON object. No markdown, no explanation."""


def gather_plan_prompt(goal: str, steers: str, gaps: str, tool_names: list,
                       batch_size: int, graph_summary: str) -> str:
    """Select next N tool calls. Used with fast model (Flash)."""
    return f"""You are a research planner selecting the next batch of tool calls.

GOAL: {goal}

USER DIRECTION: {steers if steers else "No specific direction yet."}

KNOWN GAPS: {gaps if gaps else "None identified yet."}

CURRENT KNOWLEDGE:
{graph_summary}

AVAILABLE TOOLS: {", ".join(tool_names)}

Select exactly {batch_size} tool calls to fill gaps and advance the goal.
Prioritize diverse sources — don't repeat searches you've already done.

TOOL USAGE GUIDE:
- web_search: Use for finding sources. Args: {{"query": "search terms"}}
- scrape_website: Use to read a specific URL found via web_search. Args: {{"url": "https://..."}}
- read_file: Use to read a file. Args: {{"path": "file_path"}}
- scout_file: Use to check file metadata. Args: {{"path": "file_path"}}
- list_workspace: Use to see working directory contents. Args: {{}}

Return ONLY a JSON object:
{{
  "tool_calls": [
    {{"tool_name": "web_search", "tool_args": {{"query": "specific search terms"}}}},
    {{"tool_name": "scrape_website", "tool_args": {{"url": "https://..."}}}}
  ],
  "reasoning": "Brief explanation of why these calls"
}}

RULES:
- Return exactly {batch_size} tool calls (or fewer if the goal is nearly complete).
- Use web_search to discover URLs, then scrape_website to read them in detail.
- If gaps mention specific missing topics, search for those topics.
- Return ONLY the JSON. No markdown."""


def extract_facts_prompt(raw_results: str, goal: str) -> str:
    """Extract structured facts from raw tool results. Used with fast model (Flash)."""
    return f"""You are a fact extraction engine. Extract key claims and data points from raw research data.

RESEARCH GOAL: {goal}

RAW DATA:
{raw_results[:6000]}

Extract facts as a JSON object:
{{
  "facts": [
    {{
      "content": "One specific factual claim or data point",
      "source_url": "URL where this was found (or 'unknown')",
      "source_title": "Title of the source article/page",
      "topic_tags": ["tag1", "tag2"],
      "confidence": 0.9
    }}
  ]
}}

RULES:
- Each fact must be a SINGLE, specific claim — not a paragraph.
- Include numbers, dates, names, and specifics when available.
- topic_tags should be 1-3 short labels (e.g., "casualties", "political_response", "economic_impact").
- confidence: 0.9+ for stats/quotes from reliable sources, 0.7-0.8 for general claims, 0.5-0.6 for uncertain/unverified.
- Extract 3-15 facts per batch. Quality over quantity.
- Do NOT hallucinate facts — only extract what is actually in the raw data.
- Return ONLY the JSON. No markdown."""


def reflect_prompt(goal: str, graph_summary: str, ledger_summary: str,
                   steers: str, fact_snippets: str) -> str:
    """Analyze findings, identify gaps, generate options. Used with planner model (Gemini 3)."""
    return f"""You are an editorial analyst reviewing research progress.

GOAL: {goal}

{ledger_summary}

KNOWLEDGE GRAPH STATE:
{graph_summary}

USER STEERS SO FAR: {steers if steers else "None yet."}

EXTRACTED FACTS:
{fact_snippets}

Analyze the research and respond with a JSON object:
{{
  "analysis": "2-3 sentence assessment of what has been found and what's missing",
  "gaps": ["Gap 1", "Gap 2", "Gap 3"],
  "options": [
    {{"id": 1, "text": "Option description derived from findings", "rationale": "Why this is interesting"}},
    {{"id": 2, "text": "Another option", "rationale": "Why"}},
    {{"id": 3, "text": "Third option", "rationale": "Why"}}
  ],
  "ready_to_act": true/false,
  "recommendation": "Which option you'd recommend and why"
}}

RULES:
- options MUST be derived from actual facts found — not generic suggestions.
- Each option should represent a specific angle or focus area that the data supports.
- ready_to_act = true if there's enough data to write at least one output unit on any topic.
- gaps should be specific, not vague (e.g., "No data on economic sanctions impact" not "More research needed").
- Generate 2-4 options, not more.
- Return ONLY the JSON. No markdown."""


def act_synthesis_prompt(goal: str, steer: str, relevant_facts: str,
                         outputs_so_far: str) -> str:
    """Write ONE unit of output with citations. Used with planner model (Gemini 3)."""
    existing = f"\nALREADY WRITTEN:\n{outputs_so_far}\n" if outputs_so_far else ""

    return f"""You are an expert analyst writing one focused section of a deliverable.

GOAL: {goal}

CURRENT FOCUS: {steer}
{existing}
FACTS TO USE (cite these by their ID):
{relevant_facts}

Write ONE focused paragraph (or code block, or analysis section) that:
1. Directly addresses the current focus
2. Uses SPECIFIC data from the facts provided
3. Cites sources inline (e.g., "according to Reuters [src_001]" or "500 casualties were reported [fact_003]")
4. Provides analysis — don't just list facts, synthesize them into insight

RULES:
- Write EXACTLY ONE unit of output — one paragraph, one function, one section. Not more.
- Every claim must be backed by a fact from the list above.
- Use professional, authoritative language.
- Do NOT write introductions, conclusions, or meta-commentary. Just the content.
- Return ONLY the written content. No JSON, no markdown headers wrapping it."""


def present_prompt(output_text: str, graph_summary: str, gaps: str,
                   ledger_summary: str) -> str:
    """Format output and generate next-step options. Used with fast model (Flash)."""
    return f"""You are formatting a research deliverable and suggesting next steps.

JUST WRITTEN:
{output_text}

{ledger_summary}

REMAINING GAPS: {gaps}

KNOWLEDGE STATE:
{graph_summary}

Respond with a JSON object:
{{
  "formatted_output": "The written content, cleaned up and formatted nicely",
  "next_options": [
    {{"id": 1, "text": "Short description of next action"}},
    {{"id": 2, "text": "Another option"}},
    {{"id": 3, "text": "Third option"}}
  ]
}}

RULES:
- formatted_output should be the written content above, lightly cleaned (fix any formatting issues).
- next_options should include:
  - An option to edit/expand what was just written
  - An option to move to a new topic from the gaps
  - An option to generate the final report (if enough has been written)
- 2-4 options maximum.
- Return ONLY the JSON. No markdown."""


def parse_steer_prompt(user_message: str, options_presented: list,
                       ledger_summary: str) -> str:
    """Interpret user's checkpoint response. Used with fast model (Flash)."""
    options_str = "\n".join(
        f"  {o.get('id', i+1)}. {o.get('text', '')}"
        for i, o in enumerate(options_presented)
    ) if options_presented else "  No specific options were presented."

    return f"""You are interpreting a user's response to a research checkpoint.

OPTIONS THAT WERE PRESENTED:
{options_str}

USER'S RESPONSE: "{user_message}"

SESSION CONTEXT:
{ledger_summary}

Determine what the user wants and respond with a JSON object:
{{
  "selected_option": 2,
  "next_phase": "GATHER" or "ACT" or "DONE",
  "refined_focus": "What the user wants to focus on next",
  "is_new_session": false
}}

RULES:
- If the user picks a number (e.g., "2", "go for 2", "option 2"), set selected_option to that number.
- If the user says something completely unrelated to the current session, set is_new_session=true.
- next_phase="GATHER" if more research is needed (e.g., user wants more data, picks a new topic to explore).
- next_phase="ACT" if the user wants to write/produce output on a chosen topic.
- next_phase="DONE" if the user says "done", "finish", "that's enough", etc.
- refined_focus should capture the user's intent in one clear sentence.
- Return ONLY the JSON. No markdown."""
