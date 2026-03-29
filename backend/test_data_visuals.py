"""
Test script: Fetch real data from all data APIs and render a single PDF
with proper matplotlib charts. No LLM calls.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agents_code.Visual_Analyst.data_tools import fetch_data, fetch_multiple
from pdf_generator import ReportPDFGenerator


async def gather_all_data():
    """Hit every API with a demo query and return results dict."""
    print("Fetching data from all sources in parallel...")

    results = await fetch_multiple([
        # === ECONOMICS & POLICY ===
        {"source": "sec_edgar", "cik": "0000320193"},
        {"source": "world_bank", "indicator": "NY.GDP.MKTP.CD", "country": "US;CN;DE;JP;IN;GB;FR;BR;CA;KR",
         "date_range": "2019:2023", "per_page": 100},
        {"source": "world_bank", "indicator": "SP.DYN.LE00.IN", "country": "US;CN;JP;DE;BR;IN;NG;RU",
         "date_range": "2015:2022", "per_page": 100},
        {"source": "who", "indicator_code": "WHOSIS_000001"},  # All countries
        {"source": "federal_register", "search_term": "artificial intelligence", "per_page": 20},
        {"source": "treasury", "endpoint": "rates_of_exchange", "page_size": 100},
        {"source": "census", "variables": "NAME,B01001_001E,B19013_001E", "geo": "state:*", "year": 2023},
        # === SCIENCE & ENVIRONMENT ===
        {"source": "ncbi", "query": "BRCA1,TP53,EGFR,MYC,KRAS,PIK3CA,PTEN,AKT1"},
        {"source": "usgs_water", "site_id": "01646500", "param_code": "00060", "period": "P7D"},
        {"source": "gbif", "scientific_name": "Panthera tigris", "limit": 300},
        {"source": "nws_observations", "station_id": "KJFK", "limit": 24},
        {"source": "ebi", "domain": "pdb", "query": "SARS-CoV-2", "limit": 50},
        {"source": "hepdata", "query": "cross section measurement LHC", "limit": 15},
        {"source": "nasa_svs", "search_term": "earth climate", "limit": 30},
    ])

    names = [
        "sec_edgar", "world_bank_gdp", "world_bank_life_exp", "who_life",
        "fed_register", "treasury_fx", "census_pop",
        "ncbi_genes", "usgs_water", "gbif_tiger", "nws_obs",
        "ebi_covid", "hepdata", "nasa_climate",
    ]

    data = {}
    for name, result in zip(names, results):
        status = "OK" if not result["error"] else "FAIL"
        print(f"  [{status}] {name:22s} -> {result['count']} records")
        if result["error"]:
            print(f"         Error: {result['error'][:80]}")
        data[name] = result

    return data


def build_sections(data: dict) -> list:
    """Transform raw API data into PDF sections with charts."""
    sections = []

    # ─────────────────────────────────────────────────────────────
    # 1. World Bank — GDP Top 10 (horizontal bar — long country names)
    # ─────────────────────────────────────────────────────────────
    wb = data["world_bank_gdp"]
    if wb["data"]:
        latest_gdp = {}
        for d in wb["data"]:
            country = d.get("country", "")
            year = d.get("year", "")
            val = d.get("value")
            if val and (country not in latest_gdp or year > latest_gdp[country]["year"]):
                latest_gdp[country] = {"year": year, "value": val}

        ranked = sorted(latest_gdp.items(), key=lambda x: x[1]["value"], reverse=True)
        year_label = ranked[0][1]["year"] if ranked else "?"

        sections.append({
            "title": "1. World Bank: Top Economies by GDP",
            "content": (
                f"Gross Domestic Product for major economies in {year_label}, measured in trillions of US dollars. "
                f"Data sourced from the World Bank Open Data API (indicator NY.GDP.MKTP.CD)."
            ),
            "chart": {
                "type": "barh",
                "title": f"GDP by Country ({year_label}) — Trillions USD",
                "labels": [c[0] for c in ranked],
                "values": [round(c[1]["value"] / 1e12, 2) for c in ranked],
                "xlabel": "Trillions USD",
                "source": "World Bank Open Data API — Indicator NY.GDP.MKTP.CD",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 2. World Bank — Life Expectancy Trend (multi-line via multi_bar)
    # ─────────────────────────────────────────────────────────────
    wb_le = data["world_bank_life_exp"]
    if wb_le["data"]:
        # Pivot: {country: {year: value}}
        pivot = {}
        years_set = set()
        for d in wb_le["data"]:
            country = d.get("country", "")
            year = d.get("year", "")
            val = d.get("value")
            if val:
                pivot.setdefault(country, {})[year] = round(val, 1)
                years_set.add(year)

        years = sorted(years_set)
        # Pick countries with full data
        full_countries = [c for c in pivot if len(pivot[c]) >= len(years) - 1][:5]

        if full_countries and len(years) >= 3:
            series_data = []
            for c in full_countries:
                series_data.append([pivot[c].get(y, 0) for y in years])

            sections.append({
                "title": "2. World Bank: Life Expectancy Trends (2015-2022)",
                "content": (
                    f"Life expectancy at birth for {len(full_countries)} countries from {years[0]} to {years[-1]}. "
                    f"Notice the COVID-19 impact visible in 2020-2021 dips across most nations."
                ),
                "chart": {
                    "type": "multi_bar",
                    "title": "Life Expectancy at Birth (Years)",
                    "labels": years,
                    "values": series_data,
                    "series_labels": full_countries,
                    "ylabel": "Years",
                    "source": "World Bank Open Data API — Indicator SP.DYN.LE00.IN",
                }
            })

    # ─────────────────────────────────────────────────────────────
    # 3. WHO — Life Expectancy: Top vs Bottom Countries
    # ─────────────────────────────────────────────────────────────
    who = data["who_life"]
    if who["data"]:
        # Get latest "Both Sexes" reading per country
        by_country = {}
        for d in who["data"]:
            sex = d.get("sex", "")
            country = d.get("country", "")
            year = d.get("year", 0)
            val = d.get("value")
            if sex == "BTSX" and val and country and len(country) == 3:
                if country not in by_country or year > by_country[country]["year"]:
                    by_country[country] = {"year": year, "value": val}

        ranked = sorted(by_country.items(), key=lambda x: x[1]["value"], reverse=True)
        top5 = ranked[:5]
        bottom5 = list(reversed(ranked[-5:]))
        combined = top5 + bottom5
        gap = top5[0][1]["value"] - bottom5[-1][1]["value"] if top5 and bottom5 else 0

        sections.append({
            "title": "3. WHO: Global Life Expectancy — Highest vs Lowest",
            "content": (
                f"The 5 countries with highest and 5 with lowest life expectancy (both sexes). "
                f"The gap between the top and bottom is {gap:.1f} years."
            ),
            "chart": {
                "type": "barh",
                "title": "Life Expectancy — Top 5 vs Bottom 5 (Years)",
                "labels": [c[0] for c in combined],
                "values": [round(c[1]["value"], 1) for c in combined],
                "xlabel": "Life Expectancy (Years)",
                "source": "WHO Global Health Observatory — Indicator WHOSIS_000001",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 4. SEC EDGAR — Apple Filing Types (pie)
    # ─────────────────────────────────────────────────────────────
    sec = data["sec_edgar"]
    if sec["data"]:
        form_counts = {}
        for filing in sec["data"]:
            form = filing.get("form", "Other")
            form_counts[form] = form_counts.get(form, 0) + 1

        top_forms = sorted(form_counts.items(), key=lambda x: x[1], reverse=True)[:6]

        sections.append({
            "title": "4. SEC EDGAR: Apple Inc. Filing Distribution",
            "content": (
                f"Distribution of Apple's most recent {len(sec['data'])} SEC filings by form type. "
                f"Most common: {top_forms[0][0]} ({top_forms[0][1]} filings)."
            ),
            "chart": {
                "type": "pie",
                "title": "Apple SEC Filing Types (Recent 20)",
                "labels": [f[0] for f in top_forms],
                "values": [f[1] for f in top_forms],
                "source": "SEC EDGAR — CIK 0000320193 (Apple Inc.)",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 5. Federal Register — AI Documents by Type (pie)
    # ─────────────────────────────────────────────────────────────
    fed = data["fed_register"]
    if fed["data"]:
        type_counts = {}
        for doc in fed["data"]:
            dtype = doc.get("type", "Other")
            type_counts[dtype] = type_counts.get(dtype, 0) + 1

        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

        doc_list = "\n".join([
            f"- {d['title'][:70]} ({d['publication_date']})"
            for d in fed["data"][:5]
        ])

        sections.append({
            "title": "5. Federal Register: AI Policy Documents",
            "content": (
                f"Classification of {len(fed['data'])} recent federal documents mentioning "
                f"'artificial intelligence' by document type.\n\n"
                f"Recent documents:\n{doc_list}"
            ),
            "chart": {
                "type": "pie",
                "title": "AI-Related Federal Documents by Type",
                "labels": [t[0] for t in sorted_types],
                "values": [t[1] for t in sorted_types],
                "source": "Federal Register API — federalregister.gov",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 6. U.S. Treasury — Exchange Rates (bar, top currencies)
    # ─────────────────────────────────────────────────────────────
    fx = data["treasury_fx"]
    if fx["data"]:
        # Get unique currencies with their latest rate
        seen = {}
        for rec in fx["data"]:
            currency = rec.get("country_currency_desc", "")
            rate = rec.get("exchange_rate")
            if currency and rate and currency not in seen:
                try:
                    seen[currency] = float(rate)
                except (ValueError, TypeError):
                    pass

        # Pick currencies in a displayable range (1-200)
        displayable = [(c, v) for c, v in seen.items() if 0.5 < v < 200]
        displayable.sort(key=lambda x: x[1], reverse=True)
        top = displayable[:12]

        if top:
            sections.append({
                "title": "6. U.S. Treasury: Exchange Rates (USD per Unit)",
                "content": (
                    f"Current exchange rates from the U.S. Treasury for {len(top)} major currencies. "
                    f"Values represent units of foreign currency per 1 USD."
                ),
                "chart": {
                    "type": "barh",
                    "title": "Exchange Rates (Foreign Currency per 1 USD)",
                    "labels": [c[0].split("-")[-1].strip()[:20] if "-" in c[0] else c[0][:20] for c in top],
                    "values": [c[1] for c in top],
                    "xlabel": "Units per USD",
                    "source": "U.S. Treasury Fiscal Data — Rates of Exchange",
                }
            })

    # ─────────────────────────────────────────────────────────────
    # 7. U.S. Census — Income vs Population (top 15 states)
    # ─────────────────────────────────────────────────────────────
    census = data["census_pop"]
    if census["data"]:
        states = []
        for s in census["data"]:
            name = s.get("NAME", "")
            pop = s.get("B01001_001E")
            income = s.get("B19013_001E")
            if pop and name and name != "Puerto Rico":
                try:
                    states.append((name, int(pop), int(income) if income else 0))
                except (ValueError, TypeError):
                    pass

        # Top 15 by population, show income
        states.sort(key=lambda x: x[1], reverse=True)
        top15 = [s for s in states[:15] if s[2] > 0]

        if top15:
            sections.append({
                "title": "7. U.S. Census: Median Household Income (Top 15 States by Pop.)",
                "content": (
                    f"Median household income for the 15 most populous U.S. states (ACS 2023). "
                    f"Highest income: {max(top15, key=lambda x: x[2])[0]} "
                    f"(${max(top15, key=lambda x: x[2])[2]:,})."
                ),
                "chart": {
                    "type": "bar",
                    "title": "Median Household Income by State (USD)",
                    "labels": [s[0] for s in top15],
                    "values": [s[2] for s in top15],
                    "ylabel": "USD",
                    "source": "U.S. Census Bureau — American Community Survey 2023 (Table B19013)",
                }
            })

    # ─────────────────────────────────────────────────────────────
    # 8. NCBI — Cancer Gene Genomic Spans (horizontal bar)
    # ─────────────────────────────────────────────────────────────
    ncbi = data["ncbi_genes"]
    if ncbi["data"]:
        gene_spans = []
        for g in ncbi["data"]:
            loc = g.get("genomic_location", {})
            begin = loc.get("begin")
            end = loc.get("end")
            if begin and end:
                span_kb = abs(int(end) - int(begin)) / 1000
                gene_spans.append((g["symbol"], round(span_kb, 1), g.get("chromosome", "?")))

        gene_spans.sort(key=lambda x: x[1], reverse=True)

        gene_detail = ", ".join([f"{g[0]} (chr{g[2]}, {g[1]} kb)" for g in gene_spans])

        sections.append({
            "title": "8. NCBI: Cancer Gene Genomic Spans",
            "content": (
                f"Genomic span (kilobases) of 8 key cancer-associated genes. "
                f"Larger spans often correlate with complex regulation.\n\n"
                f"Genes: {gene_detail}"
            ),
            "chart": {
                "type": "barh",
                "title": "Gene Genomic Span (Kilobases)",
                "labels": [g[0] for g in gene_spans],
                "values": [g[1] for g in gene_spans],
                "xlabel": "Kilobases",
                "source": "NCBI Datasets API — Gene records (Homo sapiens)",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 9. USGS — Potomac River Streamflow (line chart)
    # ─────────────────────────────────────────────────────────────
    usgs = data["usgs_water"]
    if usgs["data"]:
        # Sample to ~30 points across the week (one every ~6 hours)
        step = max(1, len(usgs["data"]) // 30)
        sampled = usgs["data"][::step][:30]

        labels = []
        values = []
        for d in sampled:
            dt = d.get("datetime", "")
            if "T" in dt:
                # Show "Mar 22 06:00" style
                date_part = dt.split("T")[0][5:]  # MM-DD
                time_part = dt.split("T")[1][:5]
                labels.append(f"{date_part}\n{time_part}")
            else:
                labels.append("?")
            try:
                values.append(float(d.get("value", 0)))
            except (ValueError, TypeError):
                values.append(0)

        sections.append({
            "title": "9. USGS: Potomac River Streamflow (7-Day Trend)",
            "content": (
                f"Instantaneous discharge at the Potomac River near Washington DC over 7 days. "
                f"Peak: {max(values):,.0f} cfs, Low: {min(values):,.0f} cfs. "
                f"Total readings: {len(usgs['data']):,}."
            ),
            "chart": {
                "type": "line",
                "title": "Potomac River Discharge (cubic ft/s)",
                "labels": labels,
                "values": values,
                "ylabel": "Discharge (cfs)",
                "source": "USGS Water Services — Site 01646500, Parameter 00060 (Discharge)",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 10. GBIF — Tiger Sightings by Country (pie)
    # ─────────────────────────────────────────────────────────────
    gbif = data["gbif_tiger"]
    if gbif["data"]:
        country_counts = {}
        for occ in gbif["data"]:
            c = occ.get("country", "")
            if c:
                country_counts[c] = country_counts.get(c, 0) + 1

        top_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
        # Group small slices into "Other"
        if len(top_countries) > 6:
            main = top_countries[:6]
            other_count = sum(c[1] for c in top_countries[6:])
            main.append(("Other", other_count))
            top_countries = main

        sections.append({
            "title": "10. GBIF: Tiger (Panthera tigris) Occurrence by Country",
            "content": (
                f"Geographic distribution of {len(gbif['data'])} tiger occurrence records "
                f"from the Global Biodiversity Information Facility. "
                f"Total records globally: {gbif.get('total_available', '?'):,}."
            ),
            "chart": {
                "type": "pie",
                "title": "Tiger Occurrence Records by Country",
                "labels": [c[0] for c in top_countries],
                "values": [c[1] for c in top_countries],
                "source": "Global Biodiversity Information Facility (GBIF) — Panthera tigris",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 11. NWS — JFK Temperature Trend (line)
    # ─────────────────────────────────────────────────────────────
    nws = data["nws_obs"]
    if nws["data"]:
        labels = []
        temps = []
        winds = []
        for obs in reversed(nws["data"]):
            ts = obs.get("timestamp", "")
            temp = obs.get("temperature_c")
            wind = obs.get("wind_speed_kmh")
            if temp is not None and ts:
                hour = ts[11:16] if len(ts) > 16 else "?"
                labels.append(hour)
                temps.append(round(temp, 1))
                winds.append(round(wind, 1) if wind else 0)

        if len(temps) >= 3:
            sections.append({
                "title": "11. NWS/NOAA: JFK Airport — Temperature & Wind (24h)",
                "content": (
                    f"Hourly observations at JFK International Airport. "
                    f"Temperature range: {min(temps):.1f}°C to {max(temps):.1f}°C. "
                    f"Max wind: {max(winds):.0f} km/h."
                ),
                "chart": {
                    "type": "multi_bar",
                    "title": "JFK Airport: Temperature (°C) & Wind Speed (km/h)",
                    "labels": labels,
                    "values": [temps, winds],
                    "series_labels": ["Temperature (°C)", "Wind (km/h)"],
                    "source": "National Weather Service API — Station KJFK",
                }
            })

    # ─────────────────────────────────────────────────────────────
    # 12. EBI — SARS-CoV-2 Structures by Taxonomy
    # ─────────────────────────────────────────────────────────────
    ebi = data["ebi_covid"]
    if ebi["data"]:
        tax_counts = {}
        for entry in ebi["data"]:
            tax = entry.get("taxonomy", "Unknown")
            if tax:
                tax_counts[tax] = tax_counts.get(tax, 0) + 1

        top_tax = sorted(tax_counts.items(), key=lambda x: x[1], reverse=True)[:6]
        total = ebi.get("total_available", len(ebi["data"]))

        sections.append({
            "title": "12. EMBL-EBI: SARS-CoV-2 PDB Structures by Taxonomy",
            "content": (
                f"Distribution of {total} SARS-CoV-2 related protein structures in the "
                f"Protein Data Bank, grouped by source organism taxonomy ID."
            ),
            "chart": {
                "type": "pie",
                "title": f"SARS-CoV-2 PDB Structures by Taxonomy ({total} total)",
                "labels": [f"Taxon {t[0]}" for t in top_tax],
                "values": [t[1] for t in top_tax],
                "source": "EMBL-EBI Search — Protein Data Bank (PDB)",
            }
        })

    # ─────────────────────────────────────────────────────────────
    # 13. HEPData — LHC Publications by Data Table Count
    # ─────────────────────────────────────────────────────────────
    hep = data["hepdata"]
    if hep["data"]:
        papers = [(p.get("collaboration", "?"), p.get("data_tables", 0), p.get("year", "?"))
                  for p in hep["data"] if p.get("data_tables", 0) > 0]
        papers.sort(key=lambda x: x[1], reverse=True)
        papers = papers[:10]

        if papers:
            sections.append({
                "title": "13. CERN HEPData: LHC Publications by Data Volume",
                "content": (
                    f"High-energy physics publications from HEPData ranked by number of "
                    f"associated data tables. More tables indicates richer experimental results."
                ),
                "chart": {
                    "type": "barh",
                    "title": "Data Tables per Publication",
                    "labels": [f"{p[0]} ({p[2]})" for p in papers],
                    "values": [p[1] for p in papers],
                    "xlabel": "Number of Data Tables",
                    "source": "CERN HEPData — hepdata.net",
                }
            })

    # ─────────────────────────────────────────────────────────────
    # 14. NASA SVS — Climate Visualizations by Year
    # ─────────────────────────────────────────────────────────────
    nasa = data["nasa_climate"]
    if nasa["data"]:
        year_counts = {}
        for v in nasa["data"]:
            date = str(v.get("release_date", v.get("date", "")))
            year = date[:4] if len(date) >= 4 and date[:4].isdigit() else None
            if year:
                year_counts[year] = year_counts.get(year, 0) + 1

        sorted_years = sorted(year_counts.items())

        viz_list = "\n".join([
            f"- {v.get('title', '?')[:65]}"
            for v in nasa["data"][:5]
        ])

        if sorted_years:
            sections.append({
                "title": "14. NASA SVS: Earth & Climate Visualizations Over Time",
                "content": (
                    f"Scientific visualizations from NASA's SVS related to Earth and climate science, "
                    f"grouped by release year.\n\nRecent visualizations:\n{viz_list}"
                ),
                "chart": {
                    "type": "bar",
                    "title": "NASA Climate Visualizations by Year",
                    "labels": [y[0] for y in sorted_years],
                    "values": [y[1] for y in sorted_years],
                    "ylabel": "Visualizations",
                    "source": "NASA Scientific Visualization Studio — svs.gsfc.nasa.gov",
                }
            })

    return sections


async def main():
    data = await gather_all_data()

    print("\nBuilding PDF sections...")
    sections = build_sections(data)
    print(f"  {len(sections)} sections with charts")

    summary = (
        "This report demonstrates the Visual Analyst's data tools by querying 15 authoritative "
        "public APIs and rendering live data as charts. Every number is sourced in real-time "
        "with zero API keys required. Sources span economics (World Bank, Treasury, Census), "
        "policy (Federal Register, SEC), health (WHO), science (NCBI, EMBL-EBI, CERN), "
        "environment (USGS, NWS/NOAA, GBIF), and space (NASA SVS)."
    )

    content_data = {
        "summary": summary,
        "sections": sections,
        "sources": [
            {"title": "World Bank Open Data", "url": "https://api.worldbank.org/v2/"},
            {"title": "WHO Global Health Observatory", "url": "https://ghoapi.azureedge.net/api/"},
            {"title": "SEC EDGAR", "url": "https://data.sec.gov/submissions/"},
            {"title": "Federal Register", "url": "https://www.federalregister.gov/api/v1/"},
            {"title": "U.S. Treasury Fiscal Data", "url": "https://api.fiscaldata.treasury.gov/"},
            {"title": "U.S. Census Bureau", "url": "https://api.census.gov/data/"},
            {"title": "NCBI Datasets", "url": "https://api.ncbi.nlm.nih.gov/datasets/v2/"},
            {"title": "USGS Water Services", "url": "https://waterservices.usgs.gov/nwis/"},
            {"title": "GBIF", "url": "https://api.gbif.org/v1/"},
            {"title": "NWS/NOAA", "url": "https://api.weather.gov/"},
            {"title": "EMBL-EBI", "url": "https://www.ebi.ac.uk/ebisearch/"},
            {"title": "CERN HEPData", "url": "https://www.hepdata.net/"},
            {"title": "NASA SVS", "url": "https://svs.gsfc.nasa.gov/api/"},
        ],
    }

    output_path = os.path.join(os.path.dirname(__file__), "agents_code", "Visual_Analyst", "data_tools_demo.pdf")
    print(f"\nGenerating PDF -> {output_path}")

    gen = ReportPDFGenerator(output_path, "Visual Analyst: Data Tools Capability Report")
    gen.generate(content_data, agent_name="Visual Analyst", agent_id="visual-analyst-001")

    file_size = os.path.getsize(output_path)
    print(f"Done! {len(sections)} charts, {file_size / 1024:.0f} KB")


if __name__ == "__main__":
    asyncio.run(main())
