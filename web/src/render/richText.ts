// AI replies: Markdown (marked) + LaTeX (server SVG, else KaTeX), sanitized with DOMPurify.
// Ported from renderRich() in frontend/index.html; the extraction rules must stay in step with
// src/utils/latex_svg.py so the server's `renders` keys match the snippets found here.
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/contrib/mhchem";
import { marked } from "marked";
import type { Renders } from "../protocol";

marked.setOptions({ gfm: true, breaks: true });
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

// Code spans/blocks (unterminated fences too, while streaming) are left alone
const CODE_RE = /(```[\s\S]*?(?:```|$)|`[^`\n]+`)/g;
// $$…$$ and \[…\] display; \(…\) and $…$ inline. Inline $ needs non-space just inside both
// delimiters and no digit after the closing one, so prices like "$5 and $10" stay text.
const MATH_RE = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g;

// Blocks the streaming cursor may sit at the end of
const CURSOR_BLOCKS = "p, li, h1, h2, h3, h4, td, pre code";

const sanitizeSvg = (svg: string) => DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } });

/**
 * Render a reply to sanitized HTML.
 * `renders` is null while the reply is still streaming: math previews with KaTeX and chemfig shows a
 * placeholder. Snippets missing from the final map fall back to KaTeX / the chemfig source.
 */
export function renderRich(text: string, renders: Renders | null, { cursor = false } = {}): string {
  // Pull math out before Markdown parsing (which would eat its backslashes and underscores),
  // then put KaTeX output back in after sanitizing.
  const math: { tex: string; display: boolean }[] = [];
  const src = text
    .split(CODE_RE)
    .map((part, i) =>
      i % 2
        ? part
        : part.replace(MATH_RE, (_, d1, d2, i1, i2) => {
            math.push({ tex: d1 ?? d2 ?? i1 ?? i2, display: d1 !== undefined || d2 !== undefined });
            return `KTXMATH${math.length - 1}END`;
          }),
    )
    .join("");
  const html = DOMPurify.sanitize(marked.parse(src, { async: false })).replace(/KTXMATH(\d+)END/g, (_, n) => {
    const { tex, display } = math[+n];
    const svg = renders?.[(display ? "D:" : "I:") + tex];
    if (svg) return `<span class="math-svg${display ? " math-display" : ""}">${sanitizeSvg(svg)}</span>`;
    return katex.renderToString(tex, { displayMode: display, throwOnError: false });
  });

  const root = document.createElement("template");
  root.innerHTML = html;
  const el = root.content;
  // Display math is its own block; drop the line breaks Markdown left around it (they double the spacing)
  el.querySelectorAll(".math-display, .katex-display").forEach((block) => {
    for (const sib of [block.previousSibling, block.nextSibling]) {
      if (sib && sib.nodeName === "BR") sib.remove();
    }
  });
  el.querySelectorAll("pre > code.language-chemfig").forEach((code) => {
    const pre = code.parentElement!;
    if (renders === null) {
      const pending = document.createElement("div");
      pending.className = "chemfig-pending";
      pending.textContent = "⌬ Drawing structure…";
      pre.replaceWith(pending);
      return;
    }
    const svg = renders["C:" + (code.textContent ?? "").trim()];
    if (!svg) {
      const note = document.createElement("div");
      note.className = "chemfig-failed";
      note.textContent = "Couldn't draw this structure; showing its chemfig source.";
      pre.after(note);
      return;
    }
    const fig = document.createElement("div");
    fig.className = "chemfig";
    fig.innerHTML = sanitizeSvg(svg);
    pre.replaceWith(fig);
  });
  if (cursor) {
    // Put the cursor at the end of the last text block rather than on a line of its own
    const blocks = el.querySelectorAll(CURSOR_BLOCKS);
    const caret = document.createElement("span");
    caret.className = "stream-cursor";
    (blocks[blocks.length - 1] ?? el).appendChild(caret);
  }
  return root.innerHTML;
}
