"""
Knowledge Store — persistent graph-based memory for the HITL engine.

Uses NetworkX DiGraph with three node types (source, fact, topic) and
edges representing relationships (extracted_from, belongs_to, supports/contradicts).

Persists to three JSON files under agents_code/{agent_id}/knowledge/:
  - graph.json      — NetworkX graph serialized via node_link_data
  - ledger.json     — Session state (phase, steers, options, outputs, gaps)
  - scratchpad.json — Raw tool results buffer (cleared after STORE phase)
"""
import os
import json
import time

import networkx as nx
from networkx.readwrite import json_graph

AGENTS_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents_code")

# Auto-increment counters (reset per load)
_counters = {"src": 0, "fact": 0, "topic": 0, "ent": 0}


class KnowledgeStore:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.knowledge_dir = os.path.join(AGENTS_CODE_DIR, agent_id, "knowledge")
        self.graph = nx.DiGraph()
        self.ledger = {}
        self.scratchpad = {"pending": []}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self):
        """Load graph, ledger, scratchpad from disk. Create dir if missing."""
        os.makedirs(self.knowledge_dir, exist_ok=True)

        graph_path = os.path.join(self.knowledge_dir, "graph.json")
        if os.path.exists(graph_path):
            try:
                with open(graph_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.graph = json_graph.node_link_graph(data, directed=True, edges="links")
            except Exception:
                self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()

        ledger_path = os.path.join(self.knowledge_dir, "ledger.json")
        if os.path.exists(ledger_path):
            try:
                with open(ledger_path, "r", encoding="utf-8") as f:
                    self.ledger = json.load(f)
            except Exception:
                self.ledger = {}
        else:
            self.ledger = {}

        scratch_path = os.path.join(self.knowledge_dir, "scratchpad.json")
        if os.path.exists(scratch_path):
            try:
                with open(scratch_path, "r", encoding="utf-8") as f:
                    self.scratchpad = json.load(f)
            except Exception:
                self.scratchpad = {"pending": []}
        else:
            self.scratchpad = {"pending": []}

        # Sync counters from existing nodes
        for node_id in self.graph.nodes:
            for prefix in ("src_", "fact_", "topic_"):
                if str(node_id).startswith(prefix):
                    try:
                        num = int(str(node_id).split("_", 1)[1])
                        key = prefix.rstrip("_")
                        _counters[key] = max(_counters[key], num)
                    except (ValueError, IndexError):
                        pass

    def save(self):
        """Persist all three files to disk."""
        os.makedirs(self.knowledge_dir, exist_ok=True)

        graph_path = os.path.join(self.knowledge_dir, "graph.json")
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(json_graph.node_link_data(self.graph, edges="links"), f, indent=2)

        ledger_path = os.path.join(self.knowledge_dir, "ledger.json")
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump(self.ledger, f, indent=2)

        scratch_path = os.path.join(self.knowledge_dir, "scratchpad.json")
        with open(scratch_path, "w", encoding="utf-8") as f:
            json.dump(self.scratchpad, f, indent=2)

    # ------------------------------------------------------------------
    # Graph operations
    # ------------------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        _counters[prefix] = _counters.get(prefix, 0) + 1
        return f"{prefix}_{_counters[prefix]:03d}"

    def add_source(self, url: str, title: str, snippet: str, full_text: str = "", metadata: dict = None) -> str:
        """Add a source node with rich metadata (tables, dates)."""
        # Deduplicate by URL
        for nid, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") == "source" and attrs.get("url") == url:
                return nid

        sid = self._next_id("src")
        # Store full rich data in the node attributes
        self.graph.add_node(sid,
            node_type="source",
            url=url,
            title=title,
            snippet=snippet[:300],
            full_text=full_text[:5000], # Increased for better local context
            tables=metadata.get("tables", []) if metadata else [],
            published_date=metadata.get("date") if metadata else None,
            scraped_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        return sid

    def add_entity(self, name: str, entity_type: str, source_id: str) -> str:
        """Create or update an entity node and link it to a source."""
        # Normalize name for the ID (e.g., "Apple Inc." -> "ent_apple_inc")
        ent_id = f"ent_{name.lower().replace(' ', '_')}"
        
        if not self.graph.has_node(ent_id):
            self.graph.add_node(ent_id,
                node_type="entity",
                label=name,
                category=entity_type # PERSON, ORG, DATE, etc.
            )
        
        # Create a 'mentioned_in' relationship for "hopping"
        if source_id and self.graph.has_node(source_id):
            self.graph.add_edge(ent_id, source_id, edge_type="mentioned_in")
            
        return ent_id

    def add_fact(self, content: str, source_id: str, topic_tags: list, confidence: float = 0.8, context_or_evidence: str = "") -> str:
        """Add a fact node with edges to its source and topics. Returns fact_id."""
        fid = self._next_id("fact")
        self.graph.add_node(fid,
            node_type="fact",
            content=content,
            context_or_evidence=context_or_evidence,
            confidence=confidence,
            extracted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Edge: source -> fact
        if source_id and self.graph.has_node(source_id):
            self.graph.add_edge(source_id, fid, edge_type="extracted_from")

        # Edge: fact -> topic (create topic if missing)
        for tag in topic_tags:
            topic_id = self._ensure_topic(tag)
            self.graph.add_edge(fid, topic_id, edge_type="belongs_to")

        return fid

    def add_fact_node(self, content: str, source_id: str, entity_ids: list) -> str:
        """Adds a Fact and links it to both the Source and relevant Entities."""
        fid = self._next_id("fact")
        self.graph.add_node(fid, node_type="fact", content=content, extracted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        
        # Link Fact to its Source
        if source_id and self.graph.has_node(source_id):
            self.graph.add_edge(source_id, fid, edge_type="extracted_from")
        
        # Link Fact to Entities (The Bridge)
        for eid in entity_ids:
            if self.graph.has_node(eid):
                self.graph.add_edge(fid, eid, edge_type="relates_to")
        return fid

    def add_entity_node(self, name: str, category: str, source_id: str) -> str:
        """Creates a unique entity node (deduplicated) and links to source."""
        eid = f"ent_{name.lower().replace(' ', '_')}"
        if not self.graph.has_node(eid):
            self.graph.add_node(eid, node_type="entity", label=name, category=category)
        
        # Link Entity to Source (Direct Mention)
        if source_id and self.graph.has_node(source_id):
            self.graph.add_edge(eid, source_id, edge_type="mentioned_in")
        return eid

    def get_entity_connections(self, entity_label: str) -> dict:
        """Finds all sources and tables connected to a specific entity."""
        ent_id = f"ent_{entity_label.lower().replace(' ', '_')}"
        if not self.graph.has_node(ent_id):
            return {"error": f"Entity '{entity_label}' not found in graph."}

        connected_sources = []
        # Find all source nodes connected to this entity via 'mentioned_in'
        for source_id in self.graph.neighbors(ent_id):
            attrs = self.graph.nodes[source_id]
            if attrs.get("node_type") == "source":
                connected_sources.append({
                    "source_id": source_id,
                    "title": attrs.get("title"),
                    "url": attrs.get("url"),
                    "date": attrs.get("published_date"),
                    "tables": attrs.get("tables", [])
                })

        return {
            "entity": entity_label,
            "category": self.graph.nodes[ent_id].get("category"),
            "mentions": connected_sources
        }

    def get_full_report_context(self, topic_label: str) -> dict:
        """Gathers all facts, tables, and source info for a final report."""
        facts = self.get_facts_by_topic(topic_label)
        
        # FIX: If the exact topic isn't found, grab facts from ALL topics
        if not facts:
            for topic in self.get_all_topics():
                facts.extend(self.get_facts_by_topic(topic["label"]))
        
        # Also find every Source node connected to these facts to grab their Tables
        sources = {}
        for fact in facts:
            fact_id = fact["id"]
            if self.graph.has_node(fact_id):
                for src_pred in self.graph.predecessors(fact_id):
                    attrs = self.graph.nodes[src_pred]
                    if attrs.get("node_type") == "source":
                        sources[src_pred] = {
                            "title": attrs.get("title"),
                            "url": attrs.get("url"),
                            "tables": attrs.get("tables", []),
                            "date": attrs.get("published_date")
                        }

        return {"facts": facts, "sources": list(sources.values())}

    def get_llm_graph(self) -> dict:
        """Returns the graph structure (nodes/links) while explicitly stripping 'full_text' from the output."""
        from networkx.readwrite import json_graph
        # Convert to dictionary first
        data = json_graph.node_link_data(self.graph, edges="links")
        
        # Strip the computationally heavy content from the output list
        if "nodes" in data:
            for node in data["nodes"]:
                if "full_text" in node:
                    del node["full_text"]
                    
        return data

    def _ensure_topic(self, label: str) -> str:
        """Get or create a topic node by label. Returns topic_id."""
        # Normalize label
        norm = label.strip().lower().replace(" ", "_")
        topic_id = f"topic_{norm}"

        if not self.graph.has_node(topic_id):
            self.graph.add_node(topic_id,
                node_type="topic",
                label=label.strip(),
                summary="",
            )
        return topic_id

    def add_topic(self, label: str, summary: str = ""):
        """Add or update a topic node."""
        topic_id = self._ensure_topic(label)
        if summary:
            self.graph.nodes[topic_id]["summary"] = summary

    def get_facts_by_topic(self, topic_label: str) -> list:
        """Return all fact nodes connected to a topic."""
        norm = topic_label.strip().lower().replace(" ", "_")
        topic_id = f"topic_{norm}"
        if not self.graph.has_node(topic_id):
            return []

        facts = []
        for pred in self.graph.predecessors(topic_id):
            attrs = self.graph.nodes[pred]
            if attrs.get("node_type") == "fact":
                # Also get source URLs
                sources = self.get_sources_for_fact(pred)
                facts.append({
                    "id": pred,
                    "content": attrs.get("content", ""),
                    # ADD THIS LINE SO THE EVIDENCE ISN'T LOST:
                    "context_or_evidence": attrs.get("context_or_evidence", ""),
                    "confidence": attrs.get("confidence", 0),
                    "sources": sources,
                })
        return facts

    def get_all_topics(self) -> list:
        """Return all topic nodes with their fact counts."""
        topics = []
        for nid, attrs in self.graph.nodes(data=True):
            if attrs.get("node_type") == "topic":
                fact_count = sum(
                    1 for pred in self.graph.predecessors(nid)
                    if self.graph.nodes[pred].get("node_type") == "fact"
                )
                topics.append({
                    "id": nid,
                    "label": attrs.get("label", ""),
                    "summary": attrs.get("summary", ""),
                    "fact_count": fact_count,
                })
        return topics

    def get_sources_for_fact(self, fact_id: str) -> list:
        """Trace back from fact to its source URLs."""
        sources = []
        for pred in self.graph.predecessors(fact_id):
            attrs = self.graph.nodes[pred]
            if attrs.get("node_type") == "source":
                sources.append({
                    "url": attrs.get("url", ""),
                    "title": attrs.get("title", ""),
                })
        return sources

    def get_graph_summary(self) -> str:
        """Condensed string for LLM context."""
        sources = [d for n, d in self.graph.nodes(data=True) if d.get("node_type") == "source"]
        facts = [n for n, d in self.graph.nodes(data=True) if d.get("node_type") == "fact"]
        topics = self.get_all_topics()

        topic_lines = []
        for t in topics:
            topic_lines.append(f"  - {t['label']} ({t['fact_count']} facts)")

        summary = f"Knowledge Graph: {len(sources)} sources, {len(facts)} facts, {len(topics)} topics"
        if topic_lines:
            summary += "\nTopics:\n" + "\n".join(topic_lines)

        # --- THE FIX: Reveal URLs to the agent so it can scrape them ---
        if sources:
            summary += "\n\nKnown Sources (You MUST scrape these if you haven't yet):\n"
            for s in sources[-15:]: # Show up to 15 recent URLs
                url = s.get('url', 'unknown')
                title = s.get('title', 'Untitled')[:50]
                summary += f"  - {title}... | URL: {url}\n"
        # ---------------------------------------------------------------

        recent_facts = facts[-10:]
        if recent_facts:
            summary += "\n\nRecent facts:"
            for fid in recent_facts:
                content = self.graph.nodes[fid].get("content", "")[:100]
                summary += f"\n  - {content}"

        return summary

    def get_fact_snippets_for_reflect(self, max_facts: int = 20) -> str:
        """Get a string of fact snippets for the REFLECT prompt."""
        facts = [
            (nid, attrs) for nid, attrs in self.graph.nodes(data=True)
            if attrs.get("node_type") == "fact"
        ]
        lines = []
        for fid, attrs in facts[-max_facts:]:
            sources = self.get_sources_for_fact(fid)
            src_str = sources[0]["url"] if sources else "unknown"
            lines.append(f"[{fid}] {attrs.get('content', '')[:150]} (source: {src_str})")
        return "\n".join(lines) if lines else "No facts extracted yet."

    # ------------------------------------------------------------------
    # Scratchpad
    # ------------------------------------------------------------------

    def add_raw_results(self, results: list):
        """Append raw tool results to scratchpad."""
        self.scratchpad["pending"].extend(results)

    def get_pending_results(self) -> list:
        return self.scratchpad.get("pending", [])

    def clear_scratchpad(self):
        self.scratchpad = {"pending": []}

    # ------------------------------------------------------------------
    # Ledger — session state
    # ------------------------------------------------------------------

    def get_active_session(self) -> bool:
        """Check if an active (non-DONE) HITL session exists."""
        phase = self.ledger.get("current_phase", "")
        return bool(phase) and phase != "DONE"

    def init_session(self, goal: str):
        """Create a new session in the ledger."""
        self.ledger = {
            "session_id": f"hitl_{int(time.time())}",
            "goal": goal,
            "current_phase": "UNDERSTAND",
            "understanding": {},
            "phase_history": [],
            "user_steers": [],
            "options_presented": [],
            "outputs_written": [],
            "gaps": [],
            "gather_cycles_completed": 0,
            "max_gather_cycles": 10,
        }
        self.scratchpad = {"pending": []}
        self.save()

    def update_phase(self, phase: str, summary: str = ""):
        """Set current_phase and append to phase_history."""
        self.ledger["current_phase"] = phase
        self.ledger.setdefault("phase_history", []).append({
            "phase": phase,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": summary[:200],
        })

    def add_steer(self, steer: str, phase: str):
        """Append a user steer to the ledger."""
        self.ledger.setdefault("user_steers", []).append({
            "steer": steer,
            "phase_at": phase,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    def set_options(self, options: list):
        """Set options_presented in ledger. Each: {id, text, status}"""
        self.ledger["options_presented"] = options

    def add_output(self, topic: str, text: str, fact_ids: list):
        """Track a written output section."""
        self.ledger.setdefault("outputs_written", []).append({
            "topic": topic,
            "text": text[:500],
            "fact_ids": fact_ids,
        })

    def set_gaps(self, gaps: list):
        """Update identified gaps."""
        self.ledger["gaps"] = gaps

    def get_ledger_summary(self) -> str:
        """Condensed string for LLM context."""
        goal = self.ledger.get("goal", "unknown")
        phase = self.ledger.get("current_phase", "unknown")
        steers = self.ledger.get("user_steers", [])
        gaps = self.ledger.get("gaps", [])
        outputs = self.ledger.get("outputs_written", [])
        gather_count = self.ledger.get("gather_cycles_completed", 0)

        steer_str = "; ".join(s["steer"] for s in steers[-3:]) if steers else "none"
        gap_str = "; ".join(gaps[:5]) if gaps else "none identified"
        output_topics = [o["topic"] for o in outputs]
        output_str = ", ".join(output_topics) if output_topics else "none yet"

        return (
            f"Goal: {goal}\n"
            f"Phase: {phase} | Gather cycles: {gather_count}\n"
            f"User steers: {steer_str}\n"
            f"Gaps: {gap_str}\n"
            f"Outputs written: {output_str}"
        )

    def clear(self):
        """Reset everything for a new session."""
        self.graph = nx.DiGraph()
        self.ledger = {}
        self.scratchpad = {"pending": []}
        # Reset counters
        for k in _counters:
            _counters[k] = 0
        self.save()
