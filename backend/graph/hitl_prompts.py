"""
HITL Engine — LLM prompt templates.

All prompts are separated here for easy tuning.
Each function returns a string prompt. The engine handles parsing the response.
"""


def understand_prompt(goal: str, history_context: str, ledger_summary: str,
                      current_date: str = "") -> str:
    """Classify task and detect ambiguity. Used with planner model (Gemini 3)."""
    history_block = f"\nRECENT CONVERSATION:\n{history_context}\n" if history_context else ""
    ledger_block = f"\nEXISTING SESSION STATE:\n{ledger_summary}\n" if ledger_summary else ""
    date_line = f"\nTODAY'S DATE: {current_date}" if current_date else ""

    return f"""You are an intent classifier and ambiguity detector for an AI agent.{date_line}

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
                       batch_size: int, graph_summary: str, current_date: str = "") -> str:
    """Select next N tool calls with a focus on depth and critique."""
    date_line = f"\nTODAY'S DATE: {current_date}" if current_date else ""
    return f"""You are a Lead Researcher planning the next deep-dive investigation.{date_line}

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


def extract_facts_prompt(raw_results: str, goal: str, current_date: str = "") -> str:
    """Extract relational facts from raw tool results."""
    date_line = f"\n    TODAY'S DATE: {current_date}\n" if current_date else ""
    return f"""# ROLE: STRATEGIC INTELLIGENCE ANALYST{date_line}
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
                   steers: str, fact_snippets: str, current_date: str = "") -> str:
    """Analyze findings, identify gaps, generate options. Used with planner model (Gemini 3)."""
    date_line = f"\nTODAY'S DATE: {current_date}" if current_date else ""
    return f"""You are an editorial analyst reviewing research progress.{date_line}

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
                         outputs_so_far: str, current_date: str = "") -> str:
    """Write ONE unit of output focusing on tensions and second-order effects."""
    existing = f"\nALREADY WRITTEN:\n{outputs_so_far}\n" if outputs_so_far else ""
    date_line = f"\nTODAY'S DATE: {current_date}" if current_date else ""

    return f"""You are a Senior Strategic Analyst writing a high-level briefing.{date_line}

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


def checkpoint_chat_prompt(goal: str, current_date: str, mode: str,
                           top_facts: list, editorial_context: dict,
                           gaps: list, user_steers: list,
                           reflect_analysis: str) -> str:
    """Single Flash call: algorithm picks conversation mode, Flash writes naturally.

    Modes determine the TONE and PURPOSE — Flash decides the exact words.
    """
    # Build facts block
    facts_block = ""
    for i, f in enumerate(top_facts[:3]):
        facts_block += f"\n  FACT {i+1}: {f['content']}"
        if f.get("evidence"):
            facts_block += f"\n    WHY IT MATTERS: {f['evidence']}"
        if f.get("source_title"):
            facts_block += f"\n    FROM: {f['source_title']}"

    gaps_block = "\n".join(f"  - {g}" for g in gaps) if gaps else "  - None identified yet"
    steers_block = "; ".join(user_steers) if user_steers else "No direction given yet"

    stage = editorial_context.get("research_stage", "mid")
    total_facts = editorial_context.get("total_facts", 0)
    total_sources = editorial_context.get("total_sources", 0)
    topics = ", ".join(editorial_context.get("topics_covered", [])[:5])

    # Mode-specific instructions
    mode_instructions = {
        "early_checkin": (
            "You just started researching and found some initial leads. "
            "Share what direction the research is taking and WHY it matters for the goal. "
            "Then check if you're heading the right way — the user might have a preference you don't know about."
        ),
        "share_insight": (
            "You found something significant. Don't just state the fact — explain WHY it's important "
            "for the report. Connect it to the bigger picture. Then ask what the user thinks or "
            "where they want you to go deeper. Vary your question style — don't always give two options."
        ),
        "flag_problem": (
            "You found contradictory or confusing information. Explain the contradiction clearly — "
            "what conflicts with what. Ask for the user's judgment since you're genuinely unsure."
        ),
        "propose_draft": (
            "You think you have enough material to start writing a section. Briefly summarize what "
            "you'd cover, and ask if the user wants you to go ahead or if something is missing."
        ),
        "progress_update": (
            "Quick status update — what you've covered so far and what's still missing. "
            "Make sure the user knows you're on track. Ask if they want to adjust anything."
        ),
    }

    instruction = mode_instructions.get(mode, mode_instructions["share_insight"])

    return f"""Today is {current_date}. You are a research intern chatting with your supervisor over text.

RESEARCH GOAL: {goal}
SUPERVISOR'S DIRECTION SO FAR: {steers_block}

YOUR FINDINGS (ranked by importance):
{facts_block}

WHAT YOU STILL DON'T KNOW:
{gaps_block}

RESEARCH PROGRESS: {stage} stage, {total_facts} facts from {total_sources} sources, covering: {topics}
ANALYSIS NOTES: {reflect_analysis[:300] if reflect_analysis else "Just getting started."}

YOUR SITUATION: {instruction}

Write 1-3 short chat messages. Return as JSON:
{{
  "messages": ["first message", "second message if needed"]
}}

RULES:
- You are a PERSON texting, not a system generating output.
- EXPLAIN why a finding matters for the report — don't just state raw facts.
- Vary your style. These are all valid:
    "So I've been reading about X and I think the key thing for our report is Y, because Z."
    "Interesting problem — source A says X but source B says the opposite. What's your read?"
    "I think I have enough on the technical side. Want me to start drafting, or should I dig into the impact stuff first?"
    "Quick update: covered A, B, C so far. The main gap is D — is that important for what you need?"
- Do NOT always ask "Should I do X or Y?" — vary between open questions, proposals, confirmations, opinions.
- Each message MAX 2 sentences. Total MAX 4 sentences across all messages.
- No numbered lists. No "Option 1/2". No "Would you like to".
- Return ONLY the JSON. No markdown."""


def parse_steer_prompt(user_message: str, options_presented: list,
                       ledger_summary: str) -> str:
    """Interpret user's natural-language steering response. Used with fast model (Flash)."""
    options_str = "\n".join(
        f"  {o.get('id', i+1)}. {o.get('text', '')}"
        for i, o in enumerate(options_presented)
    ) if options_presented else "  No specific options were presented."

    return f"""You are interpreting a user's response to a research check-in.
The user was asked a natural question (not a numbered menu), so their response
will be conversational, not a number pick.

RESEARCH CONTEXT:
{ledger_summary}

DIRECTIONS THE AGENT WAS CONSIDERING:
{options_str}

USER'S RESPONSE: "{user_message}"

Determine what the user wants and respond with a JSON object:
{{
  "selected_option": null,
  "next_phase": "GATHER",
  "refined_focus": "What the user wants to focus on next",
  "is_new_session": false
}}

RULES:
- refined_focus is the MOST IMPORTANT field. Capture the user's intent as a
  clear, specific research direction. If the user said "yeah dig into the
  compliance stuff", refined_focus should be something like "Deep dive into
  EU AI Act compliance requirements and penalties for non-compliance".
- If the user says "continue", "keep going", "your call", or similar,
  set refined_focus to the most promising direction from the agent's options
  and next_phase="GATHER".
- next_phase="GATHER" for more research. next_phase="ACT" to produce output.
  next_phase="DONE" only if user explicitly says to stop.
- selected_option: set to a number if the user clearly references one of the
  directions. Otherwise null.
- is_new_session=true ONLY if the user asks about something completely unrelated.
- Return ONLY the JSON. No markdown."""
