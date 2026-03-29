"""
Visual Analyst Agent - Extracts metrics and structured data from graph.json
Model: Gemini 3.1 Pro (for pattern detection and extraction)
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Any
import httpx
import asyncio

class VisualAnalystAgent:
    def __init__(self, agent_id: str = "visual-analyst-001"):
        self.id = agent_id
        self.name = "Visual Analyst"
        self.model = "gemini-3.1-pro-preview"
        self.working_dir = os.path.dirname(__file__)

    def get_personality(self):
        """Load agent personality configuration."""
        try:
            personality_path = os.path.join(self.working_dir, 'personality.json')
            with open(personality_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "name": "Visual Analyst",
                "style": "data-driven, precise, chart-focused",
                "goal": "Extract structured metrics and visualization data from knowledge graphs"
            }

    async def analyze_graph(self, graph_path: str) -> Dict[str, Any]:
        """
        Main entry point: Read graph.json and extract visualization data.

        Returns:
            visuals.json structure with charts, metrics, timeline, networks
        """
        try:
            with open(graph_path, 'r', encoding='utf-8') as f:
                graph = json.load(f)
        except Exception as e:
            return {"error": f"Failed to load graph: {str(e)}"}

        # Extract different data types
        visuals = {
            "metadata": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "agent_id": self.id,
                "agent_version": "v1"
            },
            "charts": self._extract_charts(graph),
            "timeline": self._extract_timeline(graph),
            "metrics": self._extract_metrics(graph),
            "networks": self._extract_networks(graph),
            "summary": self._generate_summary(graph)
        }

        return visuals

    def _extract_charts(self, graph: Dict) -> List[Dict]:
        """Extract chart-worthy data from facts and sources."""
        charts = []
        facts = [n for n in graph.get('nodes', []) if n.get('node_type') == 'fact']

        # Group facts by patterns (percentages, comparisons, etc.)
        percentage_facts = [f for f in facts if '%' in f.get('content', '')]
        comparison_facts = [f for f in facts if any(
            word in f.get('content', '').lower()
            for word in ['more than', 'less than', 'increase', 'decrease', 'higher', 'lower']
        )]

        if percentage_facts:
            charts.append({
                "id": "chart_percentages",
                "type": "bar",
                "title": "Key Percentages",
                "data": [
                    {
                        "label": self._extract_percentage_label(f['content']),
                        "value": self._extract_percentage_value(f['content']),
                        "fact_id": f['id']
                    }
                    for f in percentage_facts[:5]
                ],
                "source_facts": [f['id'] for f in percentage_facts[:5]],
                "confidence": 0.9
            })

        if comparison_facts:
            charts.append({
                "id": "chart_comparisons",
                "type": "bar",
                "title": "Key Comparisons",
                "data": [
                    {
                        "comparison": f['content'][:80],
                        "fact_id": f['id'],
                        "confidence": f.get('confidence', 0.8)
                    }
                    for f in comparison_facts[:5]
                ],
                "source_facts": [f['id'] for f in comparison_facts[:5]],
                "confidence": 0.85
            })

        return charts

    def _extract_timeline(self, graph: Dict) -> Dict:
        """Extract date-based events from facts and sources."""
        events = []
        facts = [n for n in graph.get('nodes', []) if n.get('node_type') == 'fact']

        for fact in facts:
            dates = self._extract_dates(fact.get('content', ''))
            for date in dates:
                events.append({
                    "date": date,
                    "event": fact['content'][:100],
                    "source_fact": fact['id'],
                    "confidence": fact.get('confidence', 0.8)
                })

        return {
            "event_count": len(events),
            "events": sorted(events, key=lambda x: x['date'])[:10],
            "earliest": events[0]['date'] if events else None,
            "latest": events[-1]['date'] if events else None
        }

    def _extract_metrics(self, graph: Dict) -> Dict:
        """Extract monetary and numerical metrics."""
        facts = [n for n in graph.get('nodes', []) if n.get('node_type') == 'fact']

        metrics = {
            "money": [],
            "percentages": [],
            "quantities": [],
            "comparisons": []
        }

        for fact in facts:
            content = fact.get('content', '')

            # Money extraction
            money_values = re.findall(r'\$[\d,]+(?:\.\d{2})?|\b\d+\s*(?:million|billion|trillion|thousand)\b', content, re.IGNORECASE)
            for val in money_values:
                metrics["money"].append({
                    "value": val,
                    "context": content[:100],
                    "fact_id": fact['id']
                })

            # Percentage extraction
            percentages = re.findall(r'(\d+(?:\.\d+)?)\s*%', content)
            for pct in percentages:
                metrics["percentages"].append({
                    "value": float(pct),
                    "context": content[:100],
                    "fact_id": fact['id']
                })

            # Quantity extraction
            quantities = re.findall(r'\b(\d+(?:,\d{3})*(?:\.\d+)?)\s+(?:people|items|units|million|billion)\b', content, re.IGNORECASE)
            for qty in quantities:
                metrics["quantities"].append({
                    "value": qty,
                    "context": content[:100],
                    "fact_id": fact['id']
                })

        return metrics

    def _extract_networks(self, graph: Dict) -> List[Dict]:
        """Extract entity relationship networks."""
        networks = []

        # Build topic network
        topics = [n for n in graph.get('nodes', []) if n.get('node_type') == 'topic']
        edges = graph.get('links', [])

        if topics:
            networks.append({
                "id": "network_topics",
                "label": "Topic Relationships",
                "node_count": len(topics),
                "edge_count": len(edges),
                "nodes": [{"id": t['id'], "label": t.get('label', 'unknown')} for t in topics[:20]],
                "edges": edges[:30],
                "description": "Network of interconnected topics and concepts"
            })

        return networks

    def _extract_dates(self, text: str) -> List[str]:
        """Extract dates from text (YYYY-MM-DD format)."""
        date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',  # ISO format
            r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',  # MM/DD/YYYY
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b'
        ]

        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            dates.extend([str(m) if isinstance(m, str) else '-'.join(m) for m in matches])

        return dates[:5]

    def _extract_percentage_label(self, text: str) -> str:
        """Extract context label for a percentage fact."""
        words = text.split()[:15]
        return ' '.join(words)

    def _extract_percentage_value(self, text: str) -> float:
        """Extract percentage value from text."""
        match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
        if match:
            return float(match.group(1))
        return 0.0

    def _generate_summary(self, graph: Dict) -> Dict:
        """Generate overview statistics."""
        nodes = graph.get('nodes', [])
        return {
            "total_nodes": len(nodes),
            "sources": len([n for n in nodes if n.get('node_type') == 'source']),
            "facts": len([n for n in nodes if n.get('node_type') == 'fact']),
            "topics": len([n for n in nodes if n.get('node_type') == 'topic']),
            "total_edges": len(graph.get('links', []))
        }

    def export_to_pdf(self, visuals: Dict, pdf_path: str):
        """Builds a formatted PDF report out of the extracted structured visual data."""
        import sys
        backend_dir = os.path.abspath(os.path.join(self.working_dir, "../.."))
        if backend_dir not in sys.path:
            sys.path.append(backend_dir)
            
        from pdf_generator import ReportPDFGenerator
        
        sections = []
        
        # Timeline Section
        timeline = visuals.get("timeline", {})
        if timeline.get("events"):
            timeline_content = "### Event Timeline\n"
            for event in timeline["events"]:
                timeline_content += f"- **{event['date']}**: {event['event']}\n"
            sections.append({
                "title": "Timeline of Events",
                "content": timeline_content
            })
            
        # Metrics Section
        metrics = visuals.get("metrics", {})
        parts = []
        for key in ["money", "percentages", "quantities"]:
            if metrics.get(key):
                parts.append(f"**{key.capitalize()} Extracted:**\n" + "\n".join([f"- {m['value']}: {m['context']}" for m in metrics[key][:5]]))
        if parts:
            sections.append({
                "title": "Extracted Metrics & Measurements",
                "content": "\n\n".join(parts)
            })

        # Charts Section
        for i, chart in enumerate(visuals.get("charts", [])):
            sections.append({
                "title": chart.get("title", f"Chart {i+1}"),
                "content": f"The following chart illustrates the extracted metric patterns for {chart.get('title', 'this topic')}. The data was extracted confidentially from the underlying knowledge graph.",
                "chart": chart
            })
            
        summary_counts = visuals.get("summary", {})
        summary_text = (
            f"This Visual Analysis Report summarizes information extracted from a knowledge graph containing "
            f"{summary_counts.get('total_nodes', 0)} nodes and {summary_counts.get('total_edges', 0)} edges. "
            f"We analyzed {summary_counts.get('facts', 0)} facts from {summary_counts.get('sources', 0)} sources."
        )

        content_data = {
            "summary": summary_text,
            "sections": sections,
            "sources": []
        }
        
        gen = ReportPDFGenerator(pdf_path, "Visual Analysis Report")
        gen.generate(content_data, agent_name=self.name, agent_id=self.id)


async def main():
    """Test the Visual Analyst Agent."""
    agent = VisualAnalystAgent()

    # Example usage
    test_graph_path = os.path.join(
        os.path.dirname(__file__),
        '../agent-bot-1774568580435/knowledge/graph.json'
    )

    if os.path.exists(test_graph_path):
        visuals = await agent.analyze_graph(test_graph_path)

        # Save visuals.json
        output_path = os.path.join(os.path.dirname(__file__), 'visuals.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(visuals, f, indent=2, ensure_ascii=False)

        print(f"✅ Visuals extracted and saved to {output_path}")
        print(f"📊 Generated {len(visuals.get('charts', []))} charts")
        print(f"📅 Found {visuals.get('timeline', {}).get('event_count', 0)} timeline events")
        
        pdf_out = os.path.join(os.path.dirname(__file__), 'visual_analysis.pdf')
        agent.export_to_pdf(visuals, pdf_out)
        print(f"📄 Standalone PDF generated and saved to {pdf_out}")
    else:
        print(f"❌ Graph file not found at {test_graph_path}")


if __name__ == "__main__":
    asyncio.run(main())
