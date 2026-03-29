"""
Visual Analyst Data Tools — Public API connectors for structured data retrieval.

15 authoritative data sources, zero API keys required:

  === ECONOMICS & POLICY ===
  1.  SEC EDGAR        — Corporate filings (10-K, 10-Q)
  2.  World Bank       — Global development indicators
  3.  IMF SDMX         — International trade & finance
  4.  WHO GHO          — Global health indicators
  5.  Federal Register  — U.S. policy & regulation
  6.  U.S. Treasury    — Fiscal data & exchange rates
  7.  U.S. Census      — Demographics & economy
  8.  OECD             — Economic development (developed nations)

  === SCIENCE & ENVIRONMENT ===
  9.  NCBI Datasets    — Genomics & gene records
  10. USGS Water       — Real-time hydrology & streamflow
  11. GBIF             — Global biodiversity occurrences
  12. NWS/NOAA         — Weather observations & alerts
  13. EMBL-EBI         — Molecular biology (proteins, chemicals)
  14. CERN HEPData     — High-energy physics data tables
  15. NASA SVS         — Space science visualizations & missions

All functions return a standardized dict:
  {"source": str, "indicator": str, "data": list[dict], "error": str|None}
"""

import httpx
import asyncio
from typing import Dict, Any, Optional, List

# SEC EDGAR requires a User-Agent with contact info
_HEADERS = {
    "User-Agent": "EasyCompany/1.0 (research-agent; contact@easycompany.dev)",
    "Accept": "application/json",
}

_TIMEOUT = 20.0


def _result(source: str, indicator: str, data: list, error: str = None) -> Dict[str, Any]:
    """Standardized return envelope."""
    return {
        "source": source,
        "indicator": indicator,
        "data": data,
        "count": len(data),
        "error": error,
    }


# ─────────────────────────────────────────────────────────────────
# 1. SEC EDGAR — Corporate Finance
# ─────────────────────────────────────────────────────────────────

async def sec_edgar(cik: str) -> Dict[str, Any]:
    """
    Fetch SEC filing metadata for a public company.

    Args:
        cik: Central Index Key (e.g. "0000320193" for Apple).
             Leading zeros are padded automatically.
    Returns:
        Company name, recent filings list (form type, date, description).
    """
    cik_padded = cik.strip().zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        company_name = body.get("name", "Unknown")
        recent = body.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        descriptions = recent.get("primaryDocDescription", [])
        accessions = recent.get("accessionNumber", [])

        filings = []
        for i in range(min(len(forms), 20)):
            filings.append({
                "form": forms[i] if i < len(forms) else "",
                "date": dates[i] if i < len(dates) else "",
                "description": descriptions[i] if i < len(descriptions) else "",
                "accession": accessions[i] if i < len(accessions) else "",
            })

        return _result("SEC EDGAR", f"Company: {company_name} (CIK {cik_padded})", filings)

    except Exception as e:
        return _result("SEC EDGAR", f"CIK {cik_padded}", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 2. World Bank — Global Macroeconomics
# ─────────────────────────────────────────────────────────────────

async def world_bank(indicator: str, country: str = "all", date_range: str = "2015:2024",
                     per_page: int = 100) -> Dict[str, Any]:
    """
    Fetch World Bank indicator data.

    Args:
        indicator: Indicator code (e.g. "NY.GDP.MKTP.CD" for GDP).
        country:   ISO2 code or "all" (e.g. "US", "CN", "BR").
        date_range: Year range "YYYY:YYYY".
        per_page:  Results per page (max 500).
    Returns:
        Time-series data points with country, year, value.
    """
    url = (
        f"https://api.worldbank.org/v2/country/{country}"
        f"/indicator/{indicator}"
        f"?format=json&date={date_range}&per_page={per_page}"
    )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        # World Bank returns [metadata, data_array]
        if not isinstance(body, list) or len(body) < 2:
            return _result("World Bank", indicator, [], error="Unexpected response format")

        raw_data = body[1] or []
        data = []
        for entry in raw_data:
            if entry.get("value") is not None:
                data.append({
                    "country": entry.get("country", {}).get("value", ""),
                    "country_code": entry.get("countryiso3code", ""),
                    "year": entry.get("date", ""),
                    "value": entry["value"],
                    "indicator_name": entry.get("indicator", {}).get("value", ""),
                })

        return _result("World Bank", indicator, data)

    except Exception as e:
        return _result("World Bank", indicator, [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 3. IMF SDMX — International Trade & Finance
# ─────────────────────────────────────────────────────────────────

async def imf_data(dataset: str = "IFS", frequency: str = "A",
                   country: str = "US", indicator: str = "PCPI_IX",
                   start_period: str = "2015", end_period: str = "2024") -> Dict[str, Any]:
    """
    Fetch IMF data via SDMX REST API.

    Args:
        dataset:   Dataset code (e.g. "IFS" for International Financial Statistics).
        frequency: "A" (annual), "Q" (quarterly), "M" (monthly).
        country:   ISO2 country code.
        indicator: Series indicator code (e.g. "PCPI_IX" for CPI index).
        start_period / end_period: Time bounds.
    Returns:
        Observations with period and value.
    """
    # SDMX key format: frequency.country.indicator
    key = f"{frequency}.{country}.{indicator}"
    url = (
        f"https://sdmxcentral.imf.org/sdmx/v2/data/dataflow/IMF/{dataset}/"
        f"?key={key}&startPeriod={start_period}&endPeriod={end_period}"
    )

    headers = {**_HEADERS, "Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.json()

        # Navigate SDMX JSON structure
        datasets = body.get("data", {}).get("dataSets", [])
        if not datasets:
            return _result("IMF", f"{dataset}/{key}", [], error="No datasets in response")

        # Extract observations from first dataset
        series_map = datasets[0].get("series", {})
        time_periods = (
            body.get("data", {})
            .get("structure", {})
            .get("dimensions", {})
            .get("observation", [{}])[0]
            .get("values", [])
        )

        data = []
        for series_key, series_val in series_map.items():
            observations = series_val.get("observations", {})
            for obs_idx, obs_val in observations.items():
                idx = int(obs_idx)
                period = time_periods[idx]["id"] if idx < len(time_periods) else obs_idx
                data.append({
                    "period": period,
                    "value": obs_val[0] if obs_val else None,
                    "series_key": series_key,
                })

        return _result("IMF", f"{dataset}/{key}", data)

    except Exception as e:
        return _result("IMF", f"{dataset}/{key}", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 4. WHO GHO — Global Health
# ─────────────────────────────────────────────────────────────────

async def who_gho(indicator_code: str, country: str = None) -> Dict[str, Any]:
    """
    Fetch WHO Global Health Observatory data.

    Args:
        indicator_code: GHO indicator (e.g. "WHOSIS_000001" for life expectancy).
        country:        Optional ISO3 filter (e.g. "USA", "GBR").
    Returns:
        Observations with country, year, value, sex.
    """
    url = f"https://ghoapi.azureedge.net/api/{indicator_code}"
    if country:
        url += f"?$filter=SpatialDim eq '{country}'"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        raw = body.get("value", [])
        data = []
        for entry in raw[:200]:  # Cap to avoid massive payloads
            data.append({
                "country": entry.get("SpatialDim", ""),
                "year": entry.get("TimeDim", ""),
                "value": entry.get("NumericValue"),
                "sex": entry.get("Dim1", ""),
                "indicator": indicator_code,
            })

        return _result("WHO GHO", indicator_code, data)

    except Exception as e:
        return _result("WHO GHO", indicator_code, [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 5. Federal Register — U.S. Policy & Law
# ─────────────────────────────────────────────────────────────────

async def federal_register(search_term: str = None, doc_type: str = None,
                           per_page: int = 20) -> Dict[str, Any]:
    """
    Search the Federal Register for rules, notices, and executive orders.

    Args:
        search_term: Keyword query (e.g. "artificial intelligence").
        doc_type:    Filter by type: "Rule", "Proposed Rule", "Notice", "Presidential Document".
        per_page:    Number of results (max 100).
    Returns:
        Documents with title, type, agency, publication date, abstract.
    """
    params = {"per_page": min(per_page, 100), "order": "newest"}
    if search_term:
        params["conditions[term]"] = search_term
    if doc_type:
        params["conditions[type][]"] = doc_type

    url = "https://www.federalregister.gov/api/v1/documents.json"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        results = body.get("results", [])
        data = []
        for doc in results:
            data.append({
                "title": doc.get("title", ""),
                "type": doc.get("type", ""),
                "document_number": doc.get("document_number", ""),
                "publication_date": doc.get("publication_date", ""),
                "agencies": [a.get("name", "") for a in doc.get("agencies", [])],
                "abstract": (doc.get("abstract") or "")[:300],
                "url": doc.get("html_url", ""),
            })

        label = search_term or "latest"
        return _result("Federal Register", f"Search: {label}", data)

    except Exception as e:
        return _result("Federal Register", search_term or "latest", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 6. U.S. Treasury — Fiscal Data
# ─────────────────────────────────────────────────────────────────

async def treasury_rates(endpoint: str = "rates_of_exchange",
                         currency: str = None,
                         sort: str = "-record_date",
                         page_size: int = 50) -> Dict[str, Any]:
    """
    Fetch U.S. Treasury fiscal data.

    Args:
        endpoint: API endpoint slug. Common options:
            - "rates_of_exchange"          (exchange rates)
            - "avg_interest_rates"         (interest on debt)
            - "debt_to_penny"              (national debt)
        currency: Optional filter for exchange rates (e.g. "Euro Zone-Euro").
        sort:     Sort field (prefix "-" for descending).
        page_size: Results per page.
    Returns:
        Records with date, value, and metadata.
    """
    base = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

    # Map friendly names to full paths
    endpoint_map = {
        "rates_of_exchange": "/v1/accounting/od/rates_of_exchange",
        "avg_interest_rates": "/v2/accounting/od/avg_interest_rates",
        "debt_to_penny": "/v2/accounting/od/debt_to_penny",
    }
    path = endpoint_map.get(endpoint, f"/v1/accounting/od/{endpoint}")
    url = f"{base}{path}"

    params = {"sort": sort, "page[size]": page_size, "format": "json"}
    if currency:
        params["filter"] = f"country_currency_desc:eq:{currency}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        records = body.get("data", [])
        data = []
        for rec in records:
            data.append(rec)  # Treasury data is already flat key-value

        return _result("U.S. Treasury", endpoint, data)

    except Exception as e:
        return _result("U.S. Treasury", endpoint, [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 7. U.S. Census Bureau — Demographics & Economy
# ─────────────────────────────────────────────────────────────────

async def census_acs(variables: str = "NAME,B01001_001E",
                     geo: str = "state:*",
                     year: int = 2023) -> Dict[str, Any]:
    """
    Fetch American Community Survey (ACS) 5-year data.

    Args:
        variables: Comma-separated variable codes.
            Common codes:
              B01001_001E  — Total population
              B19013_001E  — Median household income
              B15003_022E  — Bachelor's degree holders
              B25077_001E  — Median home value
        geo:  Geography level (e.g. "state:*", "county:*&in=state:06").
        year: Survey year (2019-2023 available).
    Returns:
        Rows with variable values per geography.
    """
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": variables, "for": geo}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        if not body or len(body) < 2:
            return _result("U.S. Census", variables, [], error="Empty response")

        headers_row = body[0]
        data = []
        for row in body[1:]:
            entry = {}
            for i, col in enumerate(headers_row):
                entry[col] = row[i] if i < len(row) else None
            data.append(entry)

        return _result("U.S. Census", f"ACS5 {year}: {variables}", data)

    except Exception as e:
        return _result("U.S. Census", variables, [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 8. OECD — Economic Development
# ─────────────────────────────────────────────────────────────────

async def oecd_data(dataset: str, key: str = "all",
                    start_period: str = "2015", end_period: str = "2024") -> Dict[str, Any]:
    """
    Fetch OECD data via SDMX REST API.

    Args:
        dataset: Dataset code (e.g. "QNA" for Quarterly National Accounts,
                 "KEI" for Key Economic Indicators).
        key:     Dimension filter or "all".
        start_period / end_period: Time bounds.
    Returns:
        Observations with dimensions and values.
    """
    url = f"https://sdmx.oecd.org/public/rest/data/{dataset}/{key}"
    params = {"startPeriod": start_period, "endPeriod": end_period}
    headers = {
        **_HEADERS,
        "Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()

        datasets = body.get("data", {}).get("dataSets", [])
        if not datasets:
            return _result("OECD", dataset, [], error="No datasets in response")

        # Extract dimension labels for readable output
        structure = body.get("data", {}).get("structure", {})
        series_dims = structure.get("dimensions", {}).get("series", [])
        obs_dims = structure.get("dimensions", {}).get("observation", [])
        time_values = obs_dims[0].get("values", []) if obs_dims else []

        series_map = datasets[0].get("series", {})
        data = []

        for series_key, series_val in list(series_map.items())[:100]:
            # Decode series dimensions
            dim_indices = series_key.split(":")
            dim_labels = {}
            for i, idx_str in enumerate(dim_indices):
                if i < len(series_dims):
                    dim = series_dims[i]
                    idx = int(idx_str)
                    values = dim.get("values", [])
                    dim_labels[dim.get("id", f"dim_{i}")] = (
                        values[idx].get("name", idx_str) if idx < len(values) else idx_str
                    )

            observations = series_val.get("observations", {})
            for obs_idx, obs_val in observations.items():
                idx = int(obs_idx)
                period = time_values[idx].get("id", obs_idx) if idx < len(time_values) else obs_idx
                data.append({
                    **dim_labels,
                    "period": period,
                    "value": obs_val[0] if obs_val else None,
                })

        return _result("OECD", dataset, data)

    except Exception as e:
        return _result("OECD", dataset, [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 9. NCBI Datasets v2 — Genomics & Gene Records
# ─────────────────────────────────────────────────────────────────

async def ncbi_gene_search(query: str, taxon: str = "human",
                           limit: int = 20) -> Dict[str, Any]:
    """
    Look up gene records from NCBI Datasets v2.

    Supports two modes:
      - Single symbol:    query="BRCA1"
      - Multiple symbols: query="BRCA1,TP53,EGFR" (comma-separated)

    Args:
        query:  Gene symbol(s), comma-separated (e.g. "BRCA1", "TP53,EGFR,MYC").
        taxon:  Organism name or NCBI taxon ID (default "human").
        limit:  Max results to return.
    Returns:
        Gene records with symbol, description, organism, chromosome, type,
        genomic location, and cross-references (UniProt, Ensembl, OMIM).
    """
    symbols = [s.strip().upper() for s in query.split(",") if s.strip()]
    url = "https://api.ncbi.nlm.nih.gov/datasets/v2/gene"

    try:
        payload = {
            "symbols_for_taxon": {
                "symbols": symbols[:limit],
                "taxon": taxon,
            }
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url, json=payload,
                headers={**_HEADERS, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()

        reports = body.get("reports", [])
        data = []
        for report in reports[:limit]:
            gene = report.get("gene", {})

            # Extract primary genomic location
            genomic_location = {}
            annotations = gene.get("annotations", [])
            if annotations:
                locs = annotations[0].get("genomic_locations", [])
                if locs:
                    loc = locs[0]
                    gr = loc.get("genomic_range", {})
                    genomic_location = {
                        "accession": loc.get("genomic_accession_version", ""),
                        "chromosome": loc.get("sequence_name", ""),
                        "begin": gr.get("begin"),
                        "end": gr.get("end"),
                        "orientation": gr.get("orientation", ""),
                        "assembly": annotations[0].get("assembly_name", ""),
                    }

            data.append({
                "gene_id": gene.get("gene_id"),
                "symbol": gene.get("symbol", ""),
                "description": gene.get("description", ""),
                "taxname": gene.get("taxname", ""),
                "tax_id": gene.get("tax_id"),
                "chromosome": gene.get("chromosomes", [""])[0] if gene.get("chromosomes") else "",
                "type": gene.get("type", ""),
                "synonyms": gene.get("synonyms", []),
                "genomic_location": genomic_location,
                "uniprot": gene.get("swiss_prot_accessions", []),
                "ensembl": gene.get("ensembl_gene_ids", []),
                "omim": gene.get("omim_ids", []),
            })

        return _result("NCBI", f"Gene lookup: {query} ({taxon})", data)

    except Exception as e:
        return _result("NCBI", f"Gene lookup: {query}", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 10. USGS Water Data — Real-Time Hydrology
# ─────────────────────────────────────────────────────────────────

async def usgs_water(site_id: str, param_code: str = "00060",
                     period: str = "P7D") -> Dict[str, Any]:
    """
    Fetch real-time water data from USGS monitoring stations.

    Args:
        site_id:    USGS site number (e.g. "01646500" for Potomac River at DC).
        param_code: Parameter code. Common ones:
            00060 — Streamflow/discharge (cubic ft/s)
            00065 — Gage height (feet)
            00010 — Water temperature (C)
        period: ISO 8601 duration for lookback (e.g. "P7D" = past 7 days,
                "P1D" = past 24 hours, "P30D" = past month).
    Returns:
        Time-series observations with timestamp and value.
    """
    url = "https://waterservices.usgs.gov/nwis/iv/"
    params = {
        "format": "json",
        "sites": site_id,
        "parameterCd": param_code,
        "period": period,
        "siteStatus": "active",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        ts_list = body.get("value", {}).get("timeSeries", [])
        if not ts_list:
            return _result("USGS Water", f"Site {site_id}", [], error="No time series found")

        ts = ts_list[0]
        site_name = ts.get("sourceInfo", {}).get("siteName", "")
        variable_name = ts.get("variable", {}).get("variableName", "")
        unit = ts.get("variable", {}).get("unit", {}).get("unitCode", "")
        values_raw = ts.get("values", [{}])[0].get("value", [])

        data = []
        for v in values_raw:
            data.append({
                "datetime": v.get("dateTime", ""),
                "value": v.get("value"),
                "qualifiers": v.get("qualifiers", []),
            })

        indicator = f"{site_name} — {variable_name} ({unit})"
        return _result("USGS Water", indicator, data)

    except Exception as e:
        return _result("USGS Water", f"Site {site_id}", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 11. GBIF — Global Biodiversity Occurrences
# ─────────────────────────────────────────────────────────────────

async def gbif_occurrences(taxon_key: int = None, scientific_name: str = None,
                           country: str = None, limit: int = 50) -> Dict[str, Any]:
    """
    Search GBIF species occurrence records.

    Args:
        taxon_key:       GBIF species key (e.g. 2480498 for Gray Wolf).
        scientific_name: Alternative to taxon_key (e.g. "Canis lupus").
        country:         ISO2 country filter (e.g. "US", "BR").
        limit:           Max records (max 300).
    Returns:
        Occurrence records with coordinates, date, country, and basis of record.
    """
    url = "https://api.gbif.org/v1/occurrence/search"
    params = {"limit": min(limit, 300)}
    if taxon_key:
        params["taxonKey"] = taxon_key
    if scientific_name:
        params["scientificName"] = scientific_name
    if country:
        params["country"] = country

    label = scientific_name or f"taxon:{taxon_key}" or "all"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        results = body.get("results", [])
        total_count = body.get("count", 0)
        data = []
        for occ in results:
            data.append({
                "species": occ.get("species", ""),
                "scientific_name": occ.get("scientificName", ""),
                "latitude": occ.get("decimalLatitude"),
                "longitude": occ.get("decimalLongitude"),
                "country": occ.get("country", ""),
                "event_date": occ.get("eventDate", ""),
                "basis_of_record": occ.get("basisOfRecord", ""),
                "dataset": occ.get("datasetName", ""),
                "year": occ.get("year"),
            })

        result = _result("GBIF", f"Occurrences: {label}", data)
        result["total_available"] = total_count
        return result

    except Exception as e:
        return _result("GBIF", f"Occurrences: {label}", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 12. NWS/NOAA — Weather Observations & Alerts
# ─────────────────────────────────────────────────────────────────

async def nws_observations(station_id: str, limit: int = 24) -> Dict[str, Any]:
    """
    Fetch recent weather observations from a NWS station.

    Args:
        station_id: NWS station identifier (e.g. "KDCA" for DC Reagan,
                    "KJFK" for JFK airport, "KORD" for Chicago O'Hare).
    Returns:
        Observations with temperature, wind, humidity, pressure, description.
    """
    url = f"https://api.weather.gov/stations/{station_id}/observations"
    params = {"limit": limit}
    headers = {**_HEADERS, "Accept": "application/geo+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()

        features = body.get("features", [])
        data = []
        for feat in features:
            props = feat.get("properties", {})
            temp = props.get("temperature", {})
            wind = props.get("windSpeed", {})
            humidity = props.get("relativeHumidity", {})
            pressure = props.get("barometricPressure", {})

            data.append({
                "timestamp": props.get("timestamp", ""),
                "description": props.get("textDescription", ""),
                "temperature_c": temp.get("value"),
                "wind_speed_kmh": wind.get("value"),
                "humidity_pct": humidity.get("value"),
                "pressure_pa": pressure.get("value"),
                "wind_direction_deg": props.get("windDirection", {}).get("value"),
                "precipitation_mm": props.get("precipitationLastHour", {}).get("value"),
            })

        return _result("NWS/NOAA", f"Station: {station_id}", data)

    except Exception as e:
        return _result("NWS/NOAA", f"Station: {station_id}", [], error=str(e))


async def nws_alerts(state: str = None, zone: str = None,
                     severity: str = None) -> Dict[str, Any]:
    """
    Fetch active weather alerts from NWS.

    Args:
        state:    U.S. state code (e.g. "CA", "TX", "FL").
        zone:     NWS zone ID for specific area.
        severity: Filter by severity: "Extreme", "Severe", "Moderate", "Minor".
    Returns:
        Active alerts with headline, description, severity, and affected areas.
    """
    url = "https://api.weather.gov/alerts/active"
    params = {}
    if state:
        params["area"] = state
    if zone:
        params["zone"] = zone
    if severity:
        params["severity"] = severity

    headers = {**_HEADERS, "Accept": "application/geo+json"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()

        features = body.get("features", [])
        data = []
        for feat in features[:50]:
            props = feat.get("properties", {})
            data.append({
                "headline": props.get("headline", ""),
                "event": props.get("event", ""),
                "severity": props.get("severity", ""),
                "urgency": props.get("urgency", ""),
                "areas": props.get("areaDesc", ""),
                "onset": props.get("onset", ""),
                "expires": props.get("expires", ""),
                "description": (props.get("description") or "")[:300],
                "sender": props.get("senderName", ""),
            })

        label = f"Alerts: {state or zone or 'nationwide'}"
        return _result("NWS/NOAA", label, data)

    except Exception as e:
        return _result("NWS/NOAA", "Alerts", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 13. EMBL-EBI Search — Molecular Biology
# ─────────────────────────────────────────────────────────────────

async def ebi_search(domain: str, query: str, limit: int = 20) -> Dict[str, Any]:
    """
    Search the European Bioinformatics Institute databases.

    Args:
        domain: EBI domain to search. Common ones:
            "uniprot"       — Protein sequences & function
            "pdb"           — 3D protein structures
            "chembl_target" — Drug targets
            "emdb"          — Electron microscopy structures
            "ena_sequence"  — Nucleotide sequences
        query:  Search term (e.g. "insulin", "kinase", "SARS-CoV-2").
        limit:  Max results.
    Returns:
        Entries with ID, name, description, organism, and domain-specific fields.
    """
    url = f"https://www.ebi.ac.uk/ebisearch/ws/rest/{domain}"
    params = {
        "query": query,
        "size": min(limit, 100),
        "format": "json",
        "fields": "id,name,description,organism,status,TAXONOMY",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        entries = body.get("entries", [])
        hit_count = body.get("hitCount", 0)
        data = []
        for entry in entries:
            fields = entry.get("fields", {})
            data.append({
                "id": entry.get("id", ""),
                "source": entry.get("source", domain),
                "name": _first(fields.get("name")),
                "description": _first(fields.get("description"), max_len=200),
                "organism": _first(fields.get("organism")),
                "taxonomy": _first(fields.get("TAXONOMY")),
            })

        result = _result("EMBL-EBI", f"{domain}: {query}", data)
        result["total_available"] = hit_count
        return result

    except Exception as e:
        return _result("EMBL-EBI", f"{domain}: {query}", [], error=str(e))


def _first(val, max_len: int = None) -> str:
    """Extract first element if list, else return str. Optionally truncate."""
    if isinstance(val, list):
        val = val[0] if val else ""
    s = str(val) if val else ""
    if max_len and len(s) > max_len:
        s = s[:max_len] + "..."
    return s


# ─────────────────────────────────────────────────────────────────
# 14. CERN HEPData — High-Energy Physics
# ─────────────────────────────────────────────────────────────────

async def hepdata_search(query: str = "higgs", inspire_id: str = None,
                         limit: int = 10) -> Dict[str, Any]:
    """
    Search CERN HEPData for high-energy physics data tables.

    Two modes:
      - Keyword search: query="higgs boson cross section"
      - Direct record:  inspire_id="ins1283842"

    Args:
        query:      Search term for keyword search.
        inspire_id: Direct INSPIRE record ID (overrides query if set).
        limit:      Max results for keyword search.
    Returns:
        Publications with title, collaboration, abstract, data table count,
        and keywords from the publication.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if inspire_id:
                # Direct record lookup
                url = f"https://www.hepdata.net/record/{inspire_id}?format=json"
                resp = await client.get(url, headers=_HEADERS)
                resp.raise_for_status()
                body = resp.json()

                record = body.get("record", {})
                tables = body.get("tables", [])

                table_summaries = []
                for table in tables[:15]:
                    table_summaries.append({
                        "name": table.get("name", ""),
                        "description": (table.get("description") or "")[:200],
                        "doi": table.get("doi", ""),
                        "keywords": [
                            {"name": kw.get("name", ""), "value": kw.get("value", "")}
                            for kw in table.get("keywords", [])[:5]
                        ],
                    })

                collaborations = record.get("collaborations", [])
                data = [{
                    "title": record.get("title", ""),
                    "collaboration": collaborations[0] if collaborations else "",
                    "doi": record.get("doi", ""),
                    "year": record.get("year", ""),
                    "abstract": (record.get("abstract") or "")[:300],
                    "table_count": len(tables),
                    "tables": table_summaries,
                }]
                label = record.get("title", inspire_id)
                return _result("CERN HEPData", label[:80], data)

            else:
                # Keyword search
                url = "https://www.hepdata.net/search/"
                params = {"q": query, "format": "json", "size": min(limit, 30)}
                resp = await client.get(url, params=params, headers=_HEADERS)
                resp.raise_for_status()
                body = resp.json()

                results = body.get("results", [])
                total = body.get("total", 0)
                data = []
                for r in results:
                    data.append({
                        "title": r.get("title", ""),
                        "collaboration": r.get("collaborations", [""])[0] if r.get("collaborations") else "",
                        "inspire_id": r.get("inspire_id", ""),
                        "year": r.get("year", ""),
                        "abstract": (r.get("abstract") or "")[:250],
                        "data_tables": r.get("data_tables", 0),
                        "doi": r.get("doi", ""),
                    })

                result = _result("CERN HEPData", f"Search: {query}", data)
                result["total_available"] = total
                return result

    except Exception as e:
        return _result("CERN HEPData", query or inspire_id or "", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# 15. NASA SVS — Space Science Visualizations
# ─────────────────────────────────────────────────────────────────

async def nasa_svs(search_term: str = None, mission: str = None,
                   limit: int = 20) -> Dict[str, Any]:
    """
    Search NASA's Scientific Visualization Studio.

    Args:
        search_term: Keyword search (e.g. "black hole", "sea level", "Mars").
        mission:     Filter by mission name (e.g. "Hubble", "JWST", "Landsat").
        limit:       Max results.
    Returns:
        Visualizations with title, description, release date, and media links.
    """
    url = "https://svs.gsfc.nasa.gov/api/search/"
    params = {}
    if search_term:
        params["search"] = search_term
    if mission:
        params["missions"] = mission

    label = search_term or mission or "latest"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            body = resp.json()

        # SVS API returns a list of items or a dict with results
        items = []
        if isinstance(body, list):
            items = body
        elif isinstance(body, dict):
            items = body.get("results", body.get("items", []))

        data = []
        for item in items[:limit]:
            if isinstance(item, dict):
                data.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "description": (item.get("description") or "")[:250],
                    "release_date": item.get("release_date", item.get("date", "")),
                    "missions": item.get("missions", []),
                    "keywords": item.get("keywords", [])[:10],
                    "url": item.get("url", ""),
                    "studio": item.get("studio", ""),
                })
            elif isinstance(item, (int, str)):
                # Some endpoints return just IDs
                data.append({"id": str(item)})

        return _result("NASA SVS", f"Search: {label}", data)

    except Exception as e:
        return _result("NASA SVS", f"Search: {label}", [], error=str(e))


# ─────────────────────────────────────────────────────────────────
# UNIFIED DISPATCHER
# ─────────────────────────────────────────────────────────────────

# Registry mapping source names to functions and their required args
SOURCES = {
    # Economics & Policy
    "sec_edgar":         {"fn": sec_edgar,         "required": ["cik"]},
    "world_bank":        {"fn": world_bank,        "required": ["indicator"]},
    "imf":               {"fn": imf_data,          "required": ["dataset"]},
    "who":               {"fn": who_gho,           "required": ["indicator_code"]},
    "federal_register":  {"fn": federal_register,  "required": []},
    "treasury":          {"fn": treasury_rates,    "required": []},
    "census":            {"fn": census_acs,        "required": []},
    "oecd":              {"fn": oecd_data,         "required": ["dataset"]},
    # Science & Environment
    "ncbi":              {"fn": ncbi_gene_search,  "required": ["query"]},
    "usgs_water":        {"fn": usgs_water,        "required": ["site_id"]},
    "gbif":              {"fn": gbif_occurrences,   "required": []},
    "nws_observations":  {"fn": nws_observations,  "required": ["station_id"]},
    "nws_alerts":        {"fn": nws_alerts,        "required": []},
    "ebi":               {"fn": ebi_search,        "required": ["domain", "query"]},
    "hepdata":           {"fn": hepdata_search,    "required": []},
    "nasa_svs":          {"fn": nasa_svs,          "required": []},
}


async def fetch_data(source: str, **kwargs) -> Dict[str, Any]:
    """
    Unified entry point. Routes to the correct API by source name.

    Args:
        source: One of: sec_edgar, world_bank, imf, who,
                federal_register, treasury, census, oecd,
                ncbi, usgs_water, gbif, nws_observations,
                nws_alerts, ebi, hepdata, nasa_svs
        **kwargs: Passed directly to the source function.
    Returns:
        Standardized result dict.
    """
    if source not in SOURCES:
        return _result("Unknown", source, [], error=f"Unknown source '{source}'. Available: {list(SOURCES.keys())}")

    entry = SOURCES[source]
    fn = entry["fn"]
    missing = [r for r in entry["required"] if r not in kwargs]
    if missing:
        return _result(source, "", [], error=f"Missing required args: {missing}")

    return await fn(**kwargs)


async def fetch_multiple(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fetch from multiple sources in parallel.

    Args:
        requests: List of dicts, each with "source" and optional kwargs.
            Example: [
                {"source": "world_bank", "indicator": "NY.GDP.MKTP.CD", "country": "US"},
                {"source": "treasury", "endpoint": "debt_to_penny"},
            ]
    Returns:
        List of result dicts in the same order as requests.
    """
    tasks = [fetch_data(**req) for req in requests]
    return await asyncio.gather(*tasks)
