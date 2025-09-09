import requests
import json
from collections import defaultdict

# --- DBpedia Lookup + SPARQL Tool (Top 3 results, up to 5 props × 5 values) ---
async def dbpedia_lookup(query: str, max_results: int = 3):
    """
    Query DBpedia Lookup API and fetch dbo:abstract + up to 5 relevant properties 
    (each with up to 5 values) for the top 3 entities via SPARQL.
    """
    lookup_url = "https://lookup.dbpedia.org/api/search/KeywordSearch"
    headers = {"Accept": "application/json"}
    params = {"QueryString": query, "MaxHits": max_results}

    try:
        # Step 1: Lookup
        response = requests.get(lookup_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        # checks if the response was turned into a JSON
        try:
            data = response.json()
            print("Lookup JSON keys:", list(data.keys()))
        except Exception as e:
            return json.dumps({
                "error": f"Lookup JSON parse failed (Line 25 in lookup.py): {str(e)}",
                "status_code": response.status_code,
                "raw": response.text[:500]
            })

        if not data.get("docs"):
            return json.dumps({"error": "No DBpedia result."})

        results = []

        # Step 2: Process top entities (up to 3)
        for doc in data.get("docs", [])[:max_results]:
            entity_uri = doc["resource"][0]
            label = doc.get("label", [""])[0]
            description = doc.get("description", [""])[0]

            sparql_url = "https://dbpedia.org/sparql"
            headers_sparql = {"Accept": "application/sparql-results+json"}

            # Query dbo:abstract
            sparql_abstract = f"""
            SELECT ?abstract WHERE {{
                <{entity_uri}> dbo:abstract ?abstract .
                FILTER (lang(?abstract) = 'en')
            }} LIMIT 1
            """
            abstract_resp = requests.get(
                sparql_url,
                params={"query": sparql_abstract, "format": "application/sparql-results+json"},
                headers=headers_sparql,
                timeout=10,
            )
            try:
                abstract_data = abstract_resp.json()
                abstract = (
                    abstract_data["results"]["bindings"][0]["abstract"]["value"]
                    if abstract_data["results"]["bindings"]
                    else ""
                )
            except Exception as e:
                abstract = ""
                print("Turning abstract into a JSON failed.")

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
            props_resp = requests.get(
                sparql_url,
                params={"query": sparql_props, "format": "application/sparql-results+json"},
                headers=headers_sparql,
                timeout=10,
            )
            props = defaultdict(list)
            try:
                props_data = props_resp.json()
                for binding in props_data["results"]["bindings"]:
                    p = binding["p"]["value"]
                    o = binding["o"]["value"]
                    if len(props[p]) < 5:  # keep up to 5 values per property
                        props[p].append(o)
            except Exception as e:
                print(f"Props query failed for {entity_uri}: {str(e)} | Raw: {props_resp.text[:200]}")

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
        return json.dumps({"error": str(e)})
