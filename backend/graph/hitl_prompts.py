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
    """Select next N tool calls with a focus on depth and critique."""
    return f"""You are a Lead Researcher planning the next deep-dive investigation.

GOAL: {goal}
USER DIRECTION: {steers if steers else "No specific direction yet."}
KNOWN GAPS: {gaps if gaps else "None identified yet."}

CURRENT KNOWLEDGE:
{graph_summary}

AVAILABLE TOOLS: {", ".join(tool_names)}

Select up to {batch_size} tool calls to fill gaps. You MUST maximize your batch size to gather data quickly!

STRATEGY RULES - CRITICAL:
1. THE SEARCH-SCRAPE RHYTHM: If your CURRENT KNOWLEDGE contains sources that were only found via `web_search` (you only have their snippets), you MUST prioritize calling `scrape_website` on those exact URLs in this batch to read the full text.
2. NEVER rely solely on search engine snippets for facts. You must read the full page.
3. NEVER use placeholder URLs like "https://...". 
4. If you need new information, use `web_search` with highly specific, analytical search terms (e.g., "Methodology behind [Data Point]").
5. MAXIMUM ONE SEARCH: You are STRICTLY FORBIDDEN from outputting more than ONE `web_search` tool call per batch. If you have 20 slots, use 1 for search and 19 for scraping.

Return ONLY a JSON object in this format:
{{
  "tool_calls": [
    {{"tool_name": "scrape_website", "tool_args": {{"url": "exact_url_from_previous_search_1"}}}},
    {{"tool_name": "scrape_website", "tool_args": {{"url": "exact_url_from_previous_search_2"}}}},
    {{"tool_name": "web_search", "tool_args": {{"query": "new highly specific search term"}}}}
  ],
  "reasoning": "Brief explanation of why this deepens the research"
}}

Return ONLY the JSON. No markdown."""


def extract_facts_prompt(raw_results: str, goal: str) -> str:
    """Extract relational facts from raw tool results."""
    return f"""# ROLE: STRATEGIC INTELLIGENCE ANALYST
    TASK: Extract high-value, evidence-backed strategic claims and granular data points.
    
    RESEARCH GOAL: {goal}
    
    # RAW RESEARCH DATA:
    {raw_results[:8000]}
    
    # EXTRACTION PROTOCOL:
    1. EXTRACT DEEP CONTEXT: For every claim, you MUST fill the 'context_or_evidence' field with the specific methodology, reasoning, or data-source mentioned in the text.
       - POOR: "The market is growing."
       - ELITE: Include the exact numbers, timeframes, growth rates, and the name of the report or institution that published the data.
    2. NUMERICAL RIGOR: If you see a percentage, dollar amount, or date, you MUST extract it as a fact and explain its significance.
    3. STRATEGIC DYNAMICS: Identify 'how' and 'why' something is happening, not just 'what'. Look for tensions, competitive advantages, and technical bottlenecks.
    4. ENTITIES: Identify the key companies, leaders, and technologies involved in each fact.
    
    # OUTPUT STRUCTURE (JSON):
    {{
      "facts": [
        {{
          "content": "The core claim or data point",
          "context_or_evidence": "The detailed proof, methodology, or reasoning behind this specific claim",
          "source_url": "URL where this was found",
          "source_title": "Title of the source",
          "topic_tags": ["specific_tag1", "specific_tag2"],
          "confidence": 0.9
        }}
      ]
    }}
    
    # RULES:
    - NO GENERIC DEFINITIONS: Skip "AI is a tool". Find the specific model names, version numbers, and performance metrics.
    - MAXIMUM YIELD: Extract 5-15 highly detailed facts per batch.
    - Return ONLY the JSON object. No markdown."""



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
- options MUST be derived from actual facts found.
- AMNESIA PREVENTION: Do NOT suggest options that the user has already rejected, skipped, or complained about in the USER STEERS.
- DIRECT COMMANDS: If the USER STEERS indicate a direct command (e.g., "focus on strikes", "told you to look for X"), your analysis MUST acknowledge this, and your options MUST be specific sub-topics of that command. Do not revert to old topics.
- ready_to_act = true ONLY IF the knowledge graph contains deeply scraped facts from actual websites. If you have only performed initial web_searches (and thus only have brief snippets), you MUST set ready_to_act to false so the next turn triggers a deep-dive scraping phase.
- gaps should be specific.
- Generate 2-3 options, not more.
- Return ONLY the JSON. No markdown."""


def act_synthesis_prompt(goal: str, steer: str, relevant_facts: str,
                         outputs_so_far: str) -> str:
    """Write ONE unit of output focusing on tensions and second-order effects."""
    existing = f"\nALREADY WRITTEN:\n{outputs_so_far}\n" if outputs_so_far else ""

    return f"""You are a Senior Strategic Analyst writing a high-level briefing.

GOAL: {goal}
CURRENT FOCUS: {steer}
{existing}

EVIDENCE BASE (cite using numbers in brackets):
{relevant_facts}

Write ONE focused analytical section (2-3 paragraphs) that:
1. Directly addresses the current focus using the provided evidence.
2. Analyzes the data for tensions, contradictions, or emergent trends. (e.g., If one source says AI creates jobs and another says it destroys them, analyze that conflict).
3. Evaluates the second-order effects or strategic implications of these facts. Do NOT just summarize the history.
4. Cites sources strictly using numbered citations: [1], [2].

RULES:
- Assume the reader already knows the basic definitions. Skip the intro fluff.
- Every major claim must be backed by a fact from the list and cited.
- Use professional, authoritative, and objective language (e.g., McKinsey or RAND Corporation style).
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


def checkpoint_prompt(goal: str, sources_count: int, facts_count: int,
                      topics: list, recent_facts: list, options: list,
                      gaps: list) -> str:
    """Generate a short, conversational checkpoint message. Used with fast model (Flash)."""
    topics_str = ", ".join(t["label"] for t in topics[:8]) if topics else "various topics"
    recent_str = "; ".join(f["content"][:80] for f in recent_facts[:4]) if recent_facts else "no facts yet"
    options_str = "\n".join(
        f"{o.get('id', i+1)}. {o.get('text', '')}"
        for i, o in enumerate(options)
    )
    gaps_str = "; ".join(gaps[:3]) if gaps else "none identified yet"

    return f"""You are summarizing research progress in a friendly, conversational way for a user.

RESEARCH GOAL: {goal}
SOURCES READ: {sources_count}
FACTS EXTRACTED: {facts_count}
TOPICS COVERED: {topics_str}
SAMPLE RECENT FACTS: {recent_str}
GAPS STILL OPEN: {gaps_str}
OPTIONS TO PRESENT:
{options_str}

Write a SHORT message (2-4 sentences max) that:
1. Briefly says what you've found so far in plain English — mention 1-2 specific things you learned, or a source read.
2. Naturally asks where the user wants to go next, listing the numbered options inline or as a short list.

RULES:
- Sound like a knowledgeable researcher talking to a colleague — warm, concise, no jargon.
- Do NOT mention "Knowledge Graph", "facts", "sources", "gaps", "topics", or any internal system terms.
- Do NOT use headers, bullet points for findings, or technical formatting.
- The options CAN be a short numbered list at the end, but keep their text tight.
- Return ONLY the final message text. No JSON, no markdown wrapper."""


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
