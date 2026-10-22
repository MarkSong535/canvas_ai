"""
Render the LaTeX in agent answers to SVG on the server: inline math, display math, and ```chemfig structures.

Pipeline: one LaTeX document per answer with one page per snippet -> DVI -> dvisvgm -> one SVG per page.
Each snippet goes into a box whose width/height/depth is logged and used as the page size, so the SVG keeps
the box's baseline: inline math is sized in em and vertically aligned like text. If the batch fails to
compile, snippets are rendered one by one so a single bad formula doesn't take the others down.

Needs `latex` (amsmath, mhchem, chemfig) and `dvisvgm` on PATH (installed in the Docker image). When they are
missing nothing is rendered and front ends fall back to client-side KaTeX / the chemfig source.

The LaTeX comes from model output, so it is treated as untrusted:
- LaTeX runs with shell escape disabled and paranoid file access (no absolute paths, no parent dirs, no
  dotfiles) in an empty temporary directory, with a timeout.
- Snippets that use file I/O, raw specials, catcode/macro tricks or document-level commands are refused.
- The SVG is checked for active content here, and front ends sanitize it again before inserting it.

Snippet keys ("I:<tex>", "D:<tex>", "C:<code>") use the exact text the answer contains, so front ends that
extract math with the same rules (see frontend/index.html) can look renders up directly.
"""

import asyncio
import hashlib
import os
import re
import shutil
import tempfile
from collections import OrderedDict
from dataclasses import dataclass

# Same extraction rules as the web UI: code is skipped; $$..$$ and \[..\] are display; \(..\) and $..$ inline
CODE_RE = re.compile(r"(```[\s\S]*?(?:```|$)|`[^`\n]+`)")
MATH_RE = re.compile(r"\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)")
CHEMFIG_BLOCK_RE = re.compile(r"```chemfig[ \t]*\n(.*?)```", re.S)

MAX_SNIPPETS = 40
MAX_TEX_CHARS = 4000
TIMEOUT_S = 25
CACHE_SIZE = 1024
PT_PER_EM = 10.0  # LaTeX 10pt font: 1em of math == 1em of surrounding text
PAD_PT = 1.5  # room for ink that pokes out of the TeX box (italic overhangs, accents)
SCALE = {"inline": 1.05, "display": 1.05, "chemfig": 1.25}

_FORBIDDEN_RE = re.compile(
    r"\\(?:input|include|includeonly|openin|openout|read|readline|write|message|immediate|newread|newwrite"
    r"|special|catcode|csname|def|edef|gdef|xdef|let|futurelet|expandafter|makeatletter|makeatother"
    r"|scantokens|everyeof|everyjob|endinput|directlua|shipout|usepackage|RequirePackage|documentclass"
    r"|loop|jobname|pgfsys\w*|tikzset|pgfkeys|hoffset|voffset|newcommand|renewcommand|providecommand)(?![A-Za-z])"
    r"|document\}"
)  # `@` stays allowed (chemfig's @{name} atom labels); without \makeatletter it can't reach internal macros
_ACTIVE_SVG_RE = re.compile(r"<script|<foreignObject|\son\w+\s*=|javascript:", re.I)
_BLACK_RE = re.compile(r"""(fill|stroke)=(['"])(?:#000|#000000|black)\2""")
_BOX_RE = re.compile(r"::SNIP (\d+) ([\d.]+)pt,([\d.]+)pt,([\d.]+)pt::")
_ERROR_RE = re.compile(r"^! (.+)$", re.M)


@dataclass(frozen=True)
class Snippet:
    kind: str  # "inline" | "display" | "chemfig"
    tex: str  # exactly as written in the answer

    @property
    def key(self) -> str:
        return {"inline": "I", "display": "D", "chemfig": "C"}[self.kind] + ":" + self.tex


def available() -> bool:
    return bool(shutil.which("latex") and shutil.which("dvisvgm"))


def extract(text: str) -> list[Snippet]:
    """All renderable snippets in an answer, in order, without duplicates."""
    found: list[Snippet] = []
    for match in CHEMFIG_BLOCK_RE.finditer(text):
        found.append(Snippet("chemfig", match.group(1).strip()))
    for i, part in enumerate(CODE_RE.split(text)):
        if i % 2:  # code span / block
            continue
        for match in MATH_RE.finditer(part):
            d1, d2, i1, i2 = match.groups()
            if d1 is not None or d2 is not None:
                found.append(Snippet("display", d1 if d1 is not None else d2))
            else:
                found.append(Snippet("inline", i1 if i1 is not None else i2))
    unique = list(dict.fromkeys(s for s in found if s.tex.strip()))
    return unique[:MAX_SNIPPETS]


async def render_answer(text: str) -> dict[str, str]:
    """Render every snippet in an answer. Returns {snippet key: svg} for the ones that rendered."""
    if not available():
        return {}
    snippets = extract(text)
    results = await render_many(snippets)
    return {s.key: svg for s, (svg, _) in zip(snippets, results) if svg}


async def render_many(snippets: list[Snippet]) -> list[tuple[str | None, str | None]]:
    """Render snippets; each result is (svg, None) or (None, error message)."""
    results: dict[Snippet, tuple[str | None, str | None]] = {}
    todo = []
    for s in snippets:
        if s in _cache:
            _cache.move_to_end(s)
            results[s] = _cache[s]
        else:
            refusal = _refusal(s)
            if refusal:
                results[s] = (None, refusal)
            else:
                todo.append(s)
    if todo:
        async with _get_semaphore():
            batch = await _compile(todo)
        if batch is None:  # the batch didn't compile: isolate the bad snippet(s)
            batch = {}
            for s in todo:
                async with _get_semaphore():
                    batch.update(await _compile([s]) or {})
        for s in todo:
            results[s] = batch.get(s, (None, "LaTeX error"))
            _cache[s] = results[s]
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return [results[s] for s in snippets]


_cache: "OrderedDict[Snippet, tuple[str | None, str | None]]" = OrderedDict()
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(2)
    return _semaphore


def _refusal(s: Snippet) -> str | None:
    if len(s.tex) > MAX_TEX_CHARS:
        return f"Too long (over {MAX_TEX_CHARS} characters)."
    bad = _FORBIDDEN_RE.search(s.tex)
    if bad:
        return f"'{bad.group(0)}' is not allowed; use only math / chemfig commands."
    return None


_DISPLAY_ENVS = [
    (re.compile(r"\\(begin|end)\{(?:align|alignat|flalign|eqnarray)\*?\}"), r"\\\1{aligned}"),
    (re.compile(r"\\(begin|end)\{(?:gather|multline)\*?\}"), r"\\\1{gathered}"),
    (re.compile(r"\\(?:begin|end)\{(?:equation|displaymath)\*?\}"), ""),
    (re.compile(r"\\(?:label|tag\*?)\{[^{}]*\}|\\(?:nonumber|notag)(?![A-Za-z])"), ""),
]


_ARROW_RE = re.compile(r"\\arrow\s*(?:\([^)]*\))?\s*\{")
_CHEMNAME_RE = re.compile(r"\\chemname\*?\s*\{")
_MATH_ONLY_CMD = (
    r"\\(?:[vV]ar)?(?:alpha|beta|[gG]amma|[dD]elta|epsilon|zeta|eta|[tT]heta|iota|kappa|[lL]ambda|mu|nu|[xX]i"
    r"|[pP]i|rho|[sS]igma|tau|[uU]psilon|[pP]hi|chi|[pP]si|[oO]mega|pm|mp|times|cdot|circ|to|infty|approx|sim"
    r"|leq?|geq?|neq|[lL]eftarrow|[rR]ightarrow|[lL]eftrightarrow|rightleftharpoons|uparrow|downarrow)(?![A-Za-z])"
)
# A word that needs math mode: has a sub/superscript or a math-only command
_SCRIPT_WORD_RE = re.compile(r"[^\s,;]*(?:[_^]|%s)[^\s,;]*" % _MATH_ONLY_CMD)
_PROTECTED_RE = re.compile(r"\\ce\s*\{|\$|\\\(|\\ensuremath\s*\{")


def _matching_brace(text: str, open_index: int) -> int | None:
    """Index of the `}` closing the `{` at open_index."""
    depth = 0
    for i in range(open_index, len(text)):
        if text[i] == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif text[i] == "}" and (i == 0 or text[i - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return i
    return None


def _math_safe_text(text: str) -> str:
    """Text-mode label -> formula words (CH_3I, Fe^{3+}, \\Delta) wrapped in upright math.

    chemfig typesets arrow labels and \\chemname captions in text mode, where `_`, `^` and math-only commands
    are LaTeX errors. Parts already in math or \\ce{...} are left as written.
    """
    if "$" in text or "\\(" in text:  # the label manages math itself
        return text
    out, pos = [], 0
    for match in _PROTECTED_RE.finditer(text):
        if match.start() < pos:
            continue
        close = _matching_brace(text, match.end() - 1) if match.group(0).endswith("{") else None
        if close is None:
            continue
        out.append(_wrap_formula_words(text[pos:match.start()]))
        out.append(text[match.start():close + 1])
        pos = close + 1
    out.append(_wrap_formula_words(text[pos:]))
    return "".join(out)


def _wrap_formula_words(text: str) -> str:
    return _SCRIPT_WORD_RE.sub(lambda m: "\\ensuremath{\\mathrm{%s}}" % m.group(0), text)


def _fix_bracket_labels(arg: str) -> str:
    """Apply _math_safe_text to each top-level [...] label inside an \\arrow{...} argument."""
    out, depth, i, n = [], 0, 0, len(arg)
    while i < n:
        ch = arg[i]
        if ch == "[" and depth == 0:
            j, inner = i + 1, 0
            while j < n and not (arg[j] == "]" and inner == 0):
                inner += {"{": 1, "}": -1}.get(arg[j], 0)
                j += 1
            if j >= n:  # unterminated label: leave the rest as written
                out.append(arg[i:])
                break
            out.append("[" + _math_safe_text(arg[i + 1:j]) + "]")
            i = j + 1
            continue
        depth += {"{": 1, "}": -1}.get(ch, 0)
        out.append(ch)
        i += 1
    return "".join(out)


def _fix_chemfig_labels(code: str) -> str:
    """Make text-mode labels in a chemfig scheme safe for formulas (arrow labels, \\chemname captions)."""
    for pattern, fix_arg_index in ((_ARROW_RE, 0), (_CHEMNAME_RE, 1)):
        result, pos = [], 0
        for match in pattern.finditer(code):
            if match.start() < pos:
                continue
            open_i = match.end() - 1
            close_i = _matching_brace(code, open_i)
            if close_i is None:
                break
            if fix_arg_index == 0:
                result.append(code[pos:open_i + 1] + _fix_bracket_labels(code[open_i + 1:close_i]))
                pos = close_i
                continue
            # \chemname{<structure>}{<caption>}: fix the second argument
            second_open = code.find("{", close_i + 1)
            if second_open == -1 or code[close_i + 1:second_open].strip():
                continue
            second_close = _matching_brace(code, second_open)
            if second_close is None:
                break
            result.append(code[pos:second_open + 1] + _math_safe_text(code[second_open + 1:second_close]))
            pos = second_close
        result.append(code[pos:])
        code = "".join(result)
    return code


def _body(s: Snippet) -> str:
    if s.kind == "chemfig":
        code = s.tex.strip()
        # Models sometimes write just the molecule (`*6(=-=-=-)`) without the \chemfig{...} wrapper
        code = code if code.startswith("\\") else "\\chemfig{%s}" % code
        return _fix_chemfig_labels(code)
    if s.kind == "inline":
        return "$%s$" % s.tex
    tex = s.tex.strip()
    for pattern, repl in _DISPLAY_ENVS:  # equation-style environments only work in vertical mode; use inner forms
        tex = pattern.sub(repl, tex)
    if "\\\\" in tex and "{aligned}" not in tex and "{gathered}" not in tex:
        tex = ("\\begin{aligned}%s\\end{aligned}" if "&" in tex else "\\begin{gathered}%s\\end{gathered}") % tex
    return "$\\displaystyle %s$" % tex


def _document(snippets: list[Snippet]) -> str:
    joined = " ".join(s.tex for s in snippets)
    packages = ["\\usepackage{amsmath,amssymb}"]
    if "\\ce" in joined or "\\pu" in joined or any(s.kind == "chemfig" for s in snippets):
        packages.append("\\usepackage[version=4]{mhchem}")
    if any(s.kind == "chemfig" for s in snippets) or "\\chemfig" in joined:
        packages.insert(0, "\\def\\pgfsysdriver{pgfsys-dvisvgm.def}")
        packages.append("\\usepackage{chemfig}")
    pages = "\n".join("\\snip{%d}{%s}" % (i + 1, _body(s)) for i, s in enumerate(snippets))
    pad, pad2 = f"{PAD_PT}pt", f"{2 * PAD_PT}pt"
    return (
        "\\documentclass[10pt]{article}\n" + "\n".join(packages) + "\n\\pagestyle{empty}\n"
        "\\hoffset=-1in \\voffset=-1in\n"
        "\\newsavebox\\snipbox\n"
        # One page per snippet, exactly the size of its box plus padding; log the box metrics for alignment
        "\\newcommand\\snip[2]{\\sbox\\snipbox{#2}%\n"
        "\\typeout{::SNIP #1 \\the\\wd\\snipbox,\\the\\ht\\snipbox,\\the\\dp\\snipbox::}%\n"
        "\\shipout\\hbox{\\special{papersize=\\the\\dimexpr\\wd\\snipbox+" + pad2 + "\\relax,"
        "\\the\\dimexpr\\ht\\snipbox+\\dp\\snipbox+" + pad2 + "\\relax}%\n"
        "\\vbox{\\kern" + pad + "\\hbox{\\kern" + pad + "\\usebox\\snipbox}\\kern" + pad + "}}}\n"
        "\\begin{document}\n" + pages + "\n\\end{document}\n"
    )


async def _compile(snippets: list[Snippet]) -> dict[Snippet, tuple[str | None, str | None]] | None:
    """Compile snippets in one document. None if LaTeX failed (with one snippet: that snippet's error)."""
    with tempfile.TemporaryDirectory(prefix="latex-svg-") as tmp:
        with open(os.path.join(tmp, "doc.tex"), "w", encoding="utf-8") as f:
            f.write(_document(snippets))
        env = {**os.environ, "openin_any": "p", "openout_any": "p", "shell_escape": "f"}
        latex = ["latex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"]
        if not await _run(latex, tmp, env):
            if len(snippets) == 1:
                return {snippets[0]: (None, _latex_error(tmp))}
            return None
        # --no-fonts=1: glyphs as inline <path>s (no <use> references, which front-end sanitizers strip)
        dvisvgm = ["dvisvgm", "--no-fonts=1", "--bbox=papersize", "--page=1-", "-o", "page-%p.svg", "doc.dvi"]
        if not await _run(dvisvgm, tmp, env):
            return {s: (None, "SVG conversion failed") for s in snippets}
        boxes = {int(n): (float(w), float(h), float(d)) for n, w, h, d in _BOX_RE.findall(_read(tmp, "doc.log"))}
        pages = {}
        for name in os.listdir(tmp):
            match = re.fullmatch(r"page-0*(\d+)\.svg", name)
            if match:
                pages[int(match.group(1))] = _read(tmp, name)
        if len(snippets) == 1 and not pages and os.path.exists(os.path.join(tmp, "page.svg")):
            pages[1] = _read(tmp, "page.svg")
        results = {}
        for i, s in enumerate(snippets, start=1):
            svg = _finish_svg(pages.get(i), boxes.get(i), s.kind)
            results[s] = (svg, None) if svg else (None, "SVG conversion failed")
        return results


def _finish_svg(svg: str | None, box: tuple[float, float, float] | None, kind: str) -> str | None:
    if not svg or not box:
        return None
    start = svg.find("<svg")
    if start == -1 or _ACTIVE_SVG_RE.search(svg):
        return None
    svg = svg[start:]
    width, height, depth = box
    scale = SCALE[kind] / PT_PER_EM
    w_em = (width + 2 * PAD_PT) * scale
    h_em = (height + depth + 2 * PAD_PT) * scale
    valign = -(depth + PAD_PT) * scale
    # Size in em so it scales with the text; inline math sits on the text baseline
    svg = re.sub(r"\swidth=(['\"])[^'\"]*\1", f" width='{w_em:.3f}em'", svg, count=1)
    svg = re.sub(r"\sheight=(['\"])[^'\"]*\1", f" height='{h_em:.3f}em'", svg, count=1)
    # Draw in the page's text color: explicit black -> currentColor; implicit (default black) fills inherit it
    svg = _BLACK_RE.sub(r"\1=\2currentColor\2", svg)
    style = f"vertical-align:{valign:.3f}em;overflow:visible"
    return svg.replace("<svg ", f"<svg fill='currentColor' style='{style}' ", 1)


def _latex_error(tmp: str) -> str:
    log = _read(tmp, "doc.log")
    match = _ERROR_RE.search(log)
    if not match:
        return "LaTeX error"
    if "File ended while scanning use of \\snip" in match.group(0) or "Runaway argument" in log:
        return "unbalanced braces: a '{' is never closed"
    # The error line plus the context line(s) TeX prints after it ("l.12 ...")
    tail = log[match.start():].splitlines()[:4]
    return " ".join(line.strip() for line in tail if line.strip())[:500]


def _read(tmp: str, name: str) -> str:
    try:
        with open(os.path.join(tmp, name), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


async def _run(cmd: list[str], cwd: str, env: dict) -> bool:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, env=env,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.wait(), TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False
    return proc.returncode == 0
