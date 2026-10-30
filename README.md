# Habitat Retreat Guides

Attendee guides for Habitat Retreats, published with GitHub Pages at
https://habitat-dev.github.io/habitat-guides/

| Folder | What it is |
|---|---|
| `<destination>-<year>/index.html` | One guide (web page). Its PDF sits next to it. |
| `_template/guide-template.html` | Starting point for every new guide. |
| `tools/guide_tool.py` | `new`, `check`, `pdf`, `preview` commands. |
| `index.html` | Home page listing every guide. Add a link for each new guide. |

Workflow: `python3 tools/guide_tool.py new kenya-2027` → fill the page from the approved copy →
`check` → `pdf` → commit + push → live in 1 to 2 minutes.
