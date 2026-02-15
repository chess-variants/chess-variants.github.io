# Chess Variant Hub

Chess Variant Hub is a static GitHub Pages website for chess variant resources, tournaments, books, servers, and GUIs.

The site is built with Jekyll and the Bulma Simple Theme:
- https://pages.github.com/
- https://github.com/ianfab/bulma-simple-theme

Most content is maintained in `_data/` (TSV/YAML files) and rendered into pages.

Local preview:

```bash
bundle exec jekyll serve
```

Local preview without Ruby (Docker Compose):

```bash
docker compose up
```

Then open `http://localhost:4000`.
If you changed Ruby image versions, run `docker compose down -v` once before starting again.
