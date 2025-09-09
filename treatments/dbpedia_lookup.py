import requests
import json
import xml.etree.ElementTree as ET
from collections import defaultdict

# --- DBpedia Lookup + SPARQL Tool (Top 3 results, up to 5 props × 5 values) ---
async def dbpedia_lookup(query: str, max_results: int = 3):
    """
    Query DBpedia Lookup API (XML) and fetch dbo:abstract + up to 5 relevant properties 
    (each with up to 5 values) for the top 3 entities via SPARQL.
    """
    lookup_url = "https://lookup.dbpedia.org/api/search/KeywordSearch"
    params = {"QueryString": query, "MaxHits": max_results}

    try:
        # Step 1: Lookup (XML response)
        response = requests.get(lookup_url, params=params, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        docs = []
        for result in root.findall(".//Result"):
            uri = result.findtext("URI")
            label = result.findtext("Label")
            description = result.findtext("Description")
            if uri:
                docs.append({
                    "resource": [uri],
                    "label": [label if label else ""],
                    "description": [description if description else ""]
                })

        if not docs:
            return json.dumps({"error": "No DBpedia result."})

        # 🔎 Debug: Show what DBpedia returned
        print("[DEBUG] Lookup returned the following entities:")
        for d in docs[:max_results]:
            print(f" - {d['label'][0]} ({d['resource'][0]})")

        results = []

        # Step 2: Process top entities (up to 3)
        for doc in docs[:max_results]:
            entity_uri = doc["resource"][0]
            label = doc.get("label", [""])[0]
            description = doc.get("description", [""])[0]

            sparql_url = "https://dbpedia.org/sparql"
            headers_sparql = {"Accept": "application/sparql-results+json"}

            # Query dbo:abstract (English)
            sparql_abstract = f"""
            SELECT ?abstract WHERE {{
                <{entity_uri}> dbo:abstract ?abstract .
                FILTER (lang(?abstract) = 'en')
            }} LIMIT 1
            """
            try:
                abstract_resp = requests.get(
                    sparql_url,
                    params={"query": sparql_abstract, "format": "application/sparql-results+json"},
                    headers=headers_sparql,
                    timeout=10,
                )
                abstract_data = abstract_resp.json()
                abstract = (
                    abstract_data["results"]["bindings"][0]["abstract"]["value"]
                    if abstract_data["results"]["bindings"]
                    else ""
                )
            except Exception as e:
                abstract = ""
                print(f"[ERROR] Abstract query failed for {entity_uri}: {str(e)}")

            # Query ontology/resource properties
            sparql_props = f"""
            SELECT ?p ?o WHERE {{
                <{entity_uri}> ?p ?o .
                FILTER (
                    STRSTARTS(STR(?p), "http://dbpedia.org/ontology/") ||
                    STRSTARTS(STR(?p), "http://dbpedia.org/resource/")
                )
            }} LIMIT 50
            """
            props = defaultdict(list)
            try:
                props_resp = requests.get(
                    sparql_url,
                    params={"query": sparql_props, "format": "application/sparql-results+json"},
                    headers=headers_sparql,
                    timeout=10,
                )
                props_data = props_resp.json()
                for binding in props_data["results"]["bindings"]:
                    p = binding["p"]["value"]
                    o = binding["o"]["value"]
                    if len(props[p]) < 5:  # keep up to 5 values per property
                        props[p].append(o)
            except Exception as e:
                print(f"[ERROR] Props query failed for {entity_uri}: {str(e)}")

            # Select up to 5 properties
            selected_props = dict(list(props.items())[:5])

            results.append(
                {
                    "entity": entity_uri,
                    "label": label,
                    "description": description,
                    "abstract": abstract,
                    "properties": selected_props,
                }
            )

        return json.dumps(results, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Lookup request failed: {str(e)}"})
