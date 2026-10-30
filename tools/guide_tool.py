#!/usr/bin/env python3
"""Habitat retreat guide tool.

Usage (run from the root of the habitat-guides repo):
  python3 tools/guide_tool.py new <slug>        copy the template to <slug>/index.html
  python3 tools/guide_tool.py check <slug>      copy + layout checks (run before every publish)
  python3 tools/guide_tool.py pdf <slug>        build <slug>/<PDF named in the Download button>
  python3 tools/guide_tool.py preview <slug>    screenshots at desktop + phone into <slug>/.preview/

Needs: playwright (Python) with Chromium, and pypdf.
  pip install playwright pypdf --break-system-packages   (Chromium is usually preinstalled)
"""
import asyncio, os, re, shutil, subprocess, sys, urllib.request

ROOT = os.getcwd()
TEMPLATE = os.path.join(ROOT, "_template", "guide-template.html")
PRINT_VIEWPORT = 691          # Letter page width minus margins, in CSS px. Do not change.
CHECK_WIDTHS = (1440, 768, 390, 360)

BANNED = [
    (r"\{\{", "unfilled {{TOKEN}}"),
    (r"\[(TIME|TBD|TBC|BOOK|FILM|HOW|WHEN|DATE|PRICE|NAME)[^\]]*\]", "bracket placeholder"),
    (r"GUIDE:", "leftover GUIDE comment"),
    (r"—|–", "em/en dash (use a period or |)"),
    (r"docs\.google\.com/forms/[^\"']*/edit", "form /edit link (must be /viewform)"),
    (r"usp=publish-editor", "editor-style form link, use the clean /viewform URL"),
    (r"the magic of", "cliche 'the magic of' (allowed only if Kennon/partner wrote it)"),
    (r"show your driver", "'show your driver' (removed by request)"),
    (r"Straight Talk", "section is called Housekeeping now"),
    (r"WhatsApp group", "say 'group message', not WhatsApp group"),
    (r"\+1 939 233 5835|939-233-5835", "old inactive Habitat WhatsApp number"),
    (r"45 days before", "balance is due 30 days before, not 45"),
    (r"lorem|ipsum|TODO", "placeholder text"),
]


def read(slug):
    p = os.path.join(ROOT, slug, "index.html")
    if not os.path.exists(p):
        sys.exit(f"Not found: {p}")
    return p, open(p, encoding="utf-8").read()


def paper_color(html):
    m = re.search(r"--paper:\s*(#[0-9A-Fa-f]{6})", html)
    return m.group(1) if m else "#FFFFFF"


def pdf_name(slug, html):
    m = re.search(r'href="([^"]+\.pdf)"\s+download', html)
    if m:
        return m.group(1)
    return f"Habitat_{slug.replace('-', '_').title()}_Retreat_Guide.pdf"


def visible_text(html):
    body = html[html.find("<body"):]
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"<style.*?</style>|<script.*?</script>", " ", body, flags=re.S)
    return body


async def layout_checks(path):
    from playwright.async_api import async_playwright
    problems = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w in CHECK_WIDTHS:
            pg = await b.new_page(viewport={"width": w, "height": 900})
            await pg.goto("file://" + path, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            sw = await pg.evaluate("document.documentElement.scrollWidth")
            if sw > w + 1:
                wide = await pg.evaluate(f"""()=>[...document.querySelectorAll('body *')]
                  .filter(e=>e.getBoundingClientRect().right>{w}+1 && !e.closest('.tw,.ctw'))
                  .slice(0,3).map(e=>e.tagName.toLowerCase()+'.'+e.className+' :: '+(e.textContent||'').trim().slice(0,50))""")
                problems.append(f"{w}px: page scrolls sideways ({sw}px). Culprits: {wide}")
            cut = await pg.evaluate("""()=>[...document.querySelectorAll('.toc nav a')]
                .filter(a=>a.scrollWidth>a.clientWidth+1).map(a=>a.textContent.trim())""")
            if cut:
                problems.append(f"{w}px: section-link labels cut off: {cut}")
            ids = await pg.evaluate("""()=>[...document.querySelectorAll('a[href^="#"]')]
                .map(a=>a.getAttribute('href').slice(1)).filter(id=>id && !document.getElementById(id))""")
            if ids and w == CHECK_WIDTHS[0]:
                problems.append(f"anchor links point to missing sections: {sorted(set(ids))}")
            await pg.close()
        await b.close()
    return problems


def link_checks(html):
    out = []
    urls = sorted(set(re.findall(r'<a\s[^>]*href="(https?://[^"]+)"', html)))
    for u in urls:
        try:
            req = urllib.request.Request(u, method="GET", headers={"User-Agent": "Mozilla/5.0"})
            code = urllib.request.urlopen(req, timeout=15).getcode()
        except Exception as e:
            code = getattr(e, "code", str(e)[:40])
        flag = "" if code == 200 else "   <-- check"
        if code == 403:
            flag = "   <-- site blocks automated checks, open it by hand once"
        if code == 401 and "docs.google.com/forms" in u:
            flag = "   <-- form asks for sign-in (file-upload question or org-only setting)"
        out.append(f"  {code}  {u}{flag}")
    return out


def cmd_check(slug):
    path, html = read(slug)
    text = visible_text(html)
    issues = []
    for pat, why in BANNED:
        for m in re.finditer(pat, text, flags=re.I if pat.startswith("lorem") else 0):
            line = text.count("\n", 0, m.start()) + 1
            snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text[max(0, m.start()-60):m.end()+60]))
            issues.append(f"  [{why}] ...{snippet.strip()}...")
    # every mention of a form should be a link
    for name in ("Flight + Info Form", "Roommate Matching Quiz", "Anonymous Feedback Form"):
        plain = re.findall(rf"(?<!>){re.escape(name)}(?!</a>)", re.sub(r"<a [^>]*>[^<]*</a>", "", text))
        plain = [x for x in plain if x]
        if plain:
            issues.append(f"  [unlinked mention] '{name}' appears {len(plain)}x without a link")
    print(f"\nCOPY CHECKS ({slug})")
    print("\n".join(issues) if issues else "  OK")
    print("\nLAYOUT CHECKS")
    lp = asyncio.run(layout_checks(path))
    print("\n".join("  " + x for x in lp) if lp else "  OK at " + ", ".join(f"{w}px" for w in CHECK_WIDTHS))
    print("\nLINKS")
    print("\n".join(link_checks(html)))
    if issues or lp:
        sys.exit(1)


async def print_pdf(path, out, paper):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": PRINT_VIEWPORT, "height": 900})
        await pg.goto("file://" + path, wait_until="networkidle")
        await pg.evaluate("document.fonts.ready")
        await pg.pdf(path=out, prefer_css_page_size=True, print_background=True)
        bg = await b.new_page()
        await bg.set_content(f"<style>@page{{size:8.5in 11in;margin:0}}html,body{{margin:0;height:100%;background:{paper}}}</style><body></body>")
        await bg.pdf(path=out + ".bg.pdf", print_background=True, width="8.5in", height="11in")
        await b.close()


def cmd_pdf(slug):
    from pypdf import PdfReader, PdfWriter
    path, html = read(slug)
    name = pdf_name(slug, html)
    out = os.path.join(ROOT, slug, name)
    raw = out + ".raw.pdf"
    asyncio.run(print_pdf(path, raw, paper_color(html)))
    w = PdfWriter()
    for page in PdfReader(raw).pages:          # full-bleed paper color behind every page
        bgp = PdfReader(raw + ".bg.pdf").pages[0]
        bgp.merge_page(page)
        w.add_page(bgp)
    w.write(out)
    for f in (raw, raw + ".bg.pdf"):
        os.remove(f)
    r = PdfReader(out)
    links = sum(len(pg.get("/Annots") or []) for pg in r.pages)
    print(f"Built {out}\n  {len(r.pages)} pages, {links} clickable links, background {paper_color(html)}")
    if shutil.which("pdftoppm"):
        prev = os.path.join(ROOT, slug, ".preview")
        os.makedirs(prev, exist_ok=True)
        subprocess.run(["pdftoppm", "-r", "30", "-png", out, os.path.join(prev, "pdf")], check=False)
        print(f"  page thumbnails in {prev}/ (look at them: no heading alone at a page bottom, no near-empty pages)")


async def shots(path, outdir):
    from playwright.async_api import async_playwright
    os.makedirs(outdir, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w, h in ((1440, 900), (390, 844)):
            pg = await b.new_page(viewport={"width": w, "height": h})
            await pg.goto("file://" + path, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            await pg.screenshot(path=os.path.join(outdir, f"top-{w}.png"))
            await pg.evaluate("document.getElementById('contents').scrollIntoView()")
            await pg.screenshot(path=os.path.join(outdir, f"contents-{w}.png"))
        await b.close()


def cmd_preview(slug):
    path, _ = read(slug)
    outdir = os.path.join(ROOT, slug, ".preview")
    asyncio.run(shots(path, outdir))
    print(f"Screenshots in {outdir}/")


def cmd_new(slug):
    d = os.path.join(ROOT, slug)
    if os.path.exists(os.path.join(d, "index.html")):
        sys.exit(f"{slug}/index.html already exists. Edit it instead.")
    os.makedirs(d, exist_ok=True)
    shutil.copy(TEMPLATE, os.path.join(d, "index.html"))
    print(f"Created {slug}/index.html from the template. Fill every {{{{TOKEN}}}}, then run check.")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("new", "check", "pdf", "preview"):
        sys.exit(__doc__)
    {"new": cmd_new, "check": cmd_check, "pdf": cmd_pdf, "preview": cmd_preview}[sys.argv[1]](sys.argv[2])
