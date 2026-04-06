# AnonyInfo

AnonyInfo is now a CLI-first investigation tool built around one seed input that expands into multiple entities, enrichment modules, and a saved case dossier.

## Features

- Canonical entity normalization for emails, usernames, domains, IPs, URLs, phone numbers, and image URLs
- Plugin-style module registry for social discovery, network intel, phone intel, image metadata, web search, fingerprinting, exposure checks, ports, and relationship leads
- Recursive entity expansion plus certificate-transparency-backed subdomain discovery
- Registration intel for domains and IPs using public RDAP data
- Saved investigation store with `cases`, `entities`, `findings`, `relationships`, `artifacts`, `module_runs`, and per-module cache
- Console, JSON, HTML dossier, Mermaid graph, and CSV evidence export paths
- Case comparison plus investigation scoring and module-health summaries
- Dashboard viewer with case graph preview and lead inspection
- Backward-compatible legacy CLI support

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Legacy compatibility
python anonyinfo.py example.com
python anonyinfo.py example.com --report

# New investigation flow
python anonyinfo.py investigate example.com
python anonyinfo.py investigate someone@example.com --full
python anonyinfo.py investigate https://example.com --format html --output dossier.html
python anonyinfo.py investigate example.com --format graph --output graph.mmd
python anonyinfo.py investigate user123 --modules social,web,links --depth deep

# Read saved cases
python anonyinfo.py case show <case_id> --format console --full
python anonyinfo.py case export <case_id> --format json --output case.json
python anonyinfo.py case export <case_id> --format csv --output findings.csv
python anonyinfo.py case export <case_id> --format graph --output graph.mmd
python anonyinfo.py case compare <case_a> <case_b>
```

## Dashboard

```bash
python dashboard.py
```

Then open `http://localhost:5000`.
