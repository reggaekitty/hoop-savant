# Hoop Savant
Static site (index.html + data/*.json). `update_data.py` refreshes the current season's data;
a GitHub Action runs it daily and commits the result, and GitHub Pages serves the site.
Test locally: `python update_data.py` then `python -m http.server` and open http://localhost:8000
