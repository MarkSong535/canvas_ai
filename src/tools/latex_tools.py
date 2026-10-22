"""
LaTeX check tool: lets the agent compile a formula or chemfig structure with the same server-side renderer
that draws its final answer (src/utils/latex_svg.py), and read the LaTeX error if it doesn't compile.
"""

from src.tools import AsyncTool, ToolResult
from src.utils import latex_svg


class CheckLatex(AsyncTool):
    """Compile LaTeX the way the student's screen will render it."""

    name = "check_latex"
    description = (
        "Compile a LaTeX math expression or a chemfig structure exactly the way it will be rendered for the "
        "student, and report whether it renders or the LaTeX error. Use it to check complex formulas, "
        "multi-line derivations, or chemfig structures before putting them in the final answer; simple math "
        "does not need checking."
    )

    parameters = {
        "type": "object",
        "properties": {
            "latex": {
                "type": "string",
                "description": "The LaTeX without delimiters, e.g. '\\frac{a}{b}' or '\\chemfig{*6(=-=-=-)}'",
            },
            "kind": {
                "type": "string",
                "description": "'inline' or 'display' for math, 'chemfig' for a chemfig block (default 'display')",
                "nullable": True,
            },
        },
        "required": ["latex"],
        "additionalProperties": False,
    }

    output_type = "any"

    async def forward(self, latex: str, kind: str = "display") -> ToolResult:
        kind = kind if kind in ("inline", "display", "chemfig") else "display"
        if not latex_svg.available():
            return ToolResult(output="The renderer is not available here; the student's browser will render math itself.")
        [(svg, error)] = await latex_svg.render_many([latex_svg.Snippet(kind, latex)])
        if svg:
            return ToolResult(output="OK: this compiles and will render correctly.")
        return ToolResult(output=f"Does not compile: {error.rstrip('.')}. Fix the LaTeX and check again, or simplify it.")
