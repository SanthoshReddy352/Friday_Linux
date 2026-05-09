"""Helpers for cleaning local model output before it reaches users or files."""

from __future__ import annotations

import re
from typing import Any

# Translation table for converting digit strings to Unicode subscript characters.
_DIGIT_TO_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


THINK_BLOCK_PATTERN = re.compile(
    r"<think\b[^>]*>.*?(?:</think>|$)",
    re.IGNORECASE | re.DOTALL,
)
NO_THINK_SUFFIX = "/no_think"


def strip_model_artifacts(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = THINK_BLOCK_PATTERN.sub("", text)
    cleaned = re.sub(r"(?im)^\s*/(?:no_)?think\s*$", "", cleaned)
    return cleaned.strip()


def with_no_think_user_message(messages: list[dict]) -> list[dict]:
    patched = [dict(message) for message in messages]
    for message in reversed(patched):
        if message.get("role") == "user":
            content = str(message.get("content", "")).rstrip()
            recent_lines = content.splitlines()[-2:]
            if NO_THINK_SUFFIX not in recent_lines:
                message["content"] = f"{content}\n\n{NO_THINK_SUFFIX}".strip()
            break
    return patched


def extract_fenced_code(text: str) -> str:
    if not isinstance(text, str):
        return ""
    match = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


# ---------------------------------------------------------------------------
# LaTeX / chemistry / biology equation → human-readable conversions
#
# Substitution lists: (pattern, replacement) applied left-to-right.
# Longer / more-specific patterns must come before shorter overlapping ones.
#
# Pipeline stages (same for _SPEECH_SUBS and _DISPLAY_SUBS):
#   0. Pre-processing:  strip letter-subscript braces; insert spaces
#   1. Text wrappers:   \text{} → plain content
#   2. Fractions/roots: after braces are gone, [^{}]+ can match cleanly
#   3. Reaction arrows: chem/bio equilibrium, forward, backward
#   4. Named subscripts: chemistry & biology constants (pH, pKa, Vmax, Km…)
#   5. Ion charges:     ^{2+}, ^-, ^+ → spoken/unicode form
#   6. Concentration:   [A], [OH^-], [S] → "concentration of X"
#   7. Greek letters
#   8. Math/chem operators
#   9. Generic super/subscripts
#  10. Strip remaining scaffolding; normalise whitespace
# ---------------------------------------------------------------------------

_SPEECH_SUBS: list[tuple] = [

    # ── 0. Pre-processing ────────────────────────────────────────────────────
    # Remove braces from letter-only subscripts so \frac can parse them.
    # e.g. V_{max} → V_max  (no {} inside \frac arguments)
    (re.compile(r"_\{([A-Za-z][A-Za-z0-9]*)\}"), r"_\1"),
    # Insert a space between a word character and a LaTeX command so that
    # T\Delta S → T \Delta S → "T delta S" (not "Tdelta S")
    (re.compile(r"(\w)(\\[A-Za-z])"), r"\1 \2"),

    # ── 1. Text wrappers ─────────────────────────────────────────────────────
    (re.compile(r"\\(?:text|mathrm|mathit|mathbf|mathsf|operatorname)\{([^{}]+)\}"),
     r"\1"),

    # ── 2. Fractions / roots ─────────────────────────────────────────────────
    (re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}"), r"\1 over \2"),
    (re.compile(r"\\sqrt\{([^{}]+)\}"), r"square root of \1"),
    (re.compile(r"\\sqrt\b"), "square root of "),

    # ── 2.5. Re-insert spaces after frac expansion (e.g. nF\ln → nF \ln) ────
    (re.compile(r"([a-zA-Z])(\\[A-Za-z])"), r"\1 \2"),

    # ── 3. Reaction arrows ───────────────────────────────────────────────────
    (re.compile(r"\\(?:rightleftharpoons|leftrightharpoons|rightleftarrows)\b|[⇌⇋]"),
     " is in equilibrium with "),
    (re.compile(r"\\xrightarrow\{([^{}]+)\}"), r" yields, \1, "),
    (re.compile(r"\\(?:longrightarrow|Rightarrow)\b|[⟶⇒]"), " yields "),
    (re.compile(r"\\(?:rightarrow|to)\b|→"), " yields "),
    (re.compile(r"\\(?:longleftarrow|Leftarrow)\b|[⟵⇐]"), " reverses to give "),
    (re.compile(r"\\(?:leftarrow|gets)\b|←"), " reverses to give "),

    # ── 4. Named subscripts — chemistry / biology (no "sub" word) ────────────
    # pH / pK (before generic \Delta and subscript handlers)
    (re.compile(r"\bpK_?[Aa]\b"), "p K a "),
    (re.compile(r"\bpK_?[Bb]\b"), "p K b "),
    (re.compile(r"\bpK_?[Ww]\b"), "p K w "),
    (re.compile(r"\bpOH\b"), "p O H "),
    (re.compile(r"\bpH\b"), "p H "),
    # Equilibrium / solubility constants
    (re.compile(r"\b[Kk]_?eq\b"), "K equilibrium "),
    (re.compile(r"\b[Kk]_?sp\b"), "K s p "),
    (re.compile(r"\b[Kk]_?[Aa]\b"), "K a "),
    (re.compile(r"\b[Kk]_?[Bb]\b"), "K b "),
    (re.compile(r"\b[Kk]_?[Ww]\b"), "K w "),
    # Michaelis-Menten / kinetics
    (re.compile(r"\b[Vv]_?max\b"), "V max "),
    (re.compile(r"\b[Kk]_?m\b"), "K m "),
    (re.compile(r"\b[Kk]_?[Dd]\b"), "K d "),
    (re.compile(r"\b[Kk]_?[Ii]\b"), "K i "),
    (re.compile(r"\bk_?cat\b"), "k cat "),

    # ── 4b. Inline fraction: a/b → a over b (variable names, not URLs) ─────────
    # \s* absorbs trailing spaces that stage 4 may have added to named constants.
    (re.compile(r"(\w)\s*/\s*(\w)"), r"\1 over \2"),

    # ── 4c. Chemical-formula subscripts: CH_4 → "CH 4"  (not "CH sub 4") ────
    # Matches element-like token (uppercase + optional lowercase) before a digit.
    (re.compile(r"([A-Z][a-z]?)_\{?(\d+)\}?"), r"\1 \2"),

    # ── 5. Ion / oxidation-state charges ─────────────────────────────────────
    (re.compile(r"\^\{(\d+)\+\}"), r"\1 positive "),
    (re.compile(r"\^\{(\d+)-\}"), r"\1 negative "),
    (re.compile(r"\^\{\+\}|\^\+"), " positive "),
    (re.compile(r"\^\{-\}|\^\-"), " negative "),

    # ── 6. Concentration brackets  [X], [H^+], [OH^-] ────────────────────────
    # Leading space prevents "\logconcentration" merging with previous command
    (re.compile(r"\[([A-Z][A-Za-z0-9\s]*)\](?!\d)"), r" concentration of \1 "),

    # ── 7. Greek letters ──────────────────────────────────────────────────────
    (re.compile(r"\\hbar\b"), "h bar "),
    (re.compile(r"\\Delta\b"), "delta "),
    (re.compile(r"\\delta\b"), "delta "),
    (re.compile(r"\\Sigma\b"), "sigma "),
    (re.compile(r"\\sigma\b"), "sigma "),
    (re.compile(r"\\rho\b"), "rho "),
    (re.compile(r"\\mu\b"), "mu "),
    (re.compile(r"\\Pi\b"), "pi "),
    (re.compile(r"\\pi\b"), "pi "),
    (re.compile(r"\\alpha\b"), "alpha "),
    (re.compile(r"\\beta\b"), "beta "),
    (re.compile(r"\\Gamma\b"), "gamma "),
    (re.compile(r"\\gamma\b"), "gamma "),
    (re.compile(r"\\Theta\b"), "theta "),
    (re.compile(r"\\theta\b"), "theta "),
    (re.compile(r"\\Omega\b"), "omega "),
    (re.compile(r"\\omega\b"), "omega "),
    (re.compile(r"\\epsilon\b"), "epsilon "),
    (re.compile(r"\\varepsilon\b"), "epsilon "),
    (re.compile(r"\\Lambda\b"), "lambda "),
    (re.compile(r"\\lambda\b"), "lambda "),
    (re.compile(r"\\tau\b"), "tau "),
    (re.compile(r"\\Phi\b"), "phi "),
    (re.compile(r"\\phi\b"), "phi "),
    (re.compile(r"\\varphi\b"), "phi "),
    (re.compile(r"\\Psi\b"), "psi "),
    (re.compile(r"\\psi\b"), "psi "),
    (re.compile(r"\\eta\b"), "eta "),
    (re.compile(r"\\chi\b"), "chi "),
    (re.compile(r"\\xi\b"), "xi "),
    (re.compile(r"\\Xi\b"), "xi "),
    (re.compile(r"\\zeta\b"), "zeta "),
    (re.compile(r"\\nu\b"), "nu "),
    (re.compile(r"\\kappa\b"), "kappa "),

    # ── 8. Math / chemistry / biology operators ───────────────────────────────
    (re.compile(r"\^\\circ\b"), " standard"),   # E^\circ → "E standard"
    (re.compile(r"\\circ\b"), ""),               # standalone \circ stripped
    (re.compile(r"\\ln\b"), "log of "),
    (re.compile(r"\\log\b"), "log "),
    (re.compile(r"\\exp\b"), "e to the power of "),
    (re.compile(r"\\approx\b"), "approximately "),
    (re.compile(r"\\times\b"), " times "),
    (re.compile(r"\\cdot\b"), " times "),
    (re.compile(r"\\div\b"), " divided by "),
    (re.compile(r"\\pm\b"), " plus or minus "),
    (re.compile(r"\\mp\b"), " minus or plus "),
    (re.compile(r"\\neq\b"), " not equal to "),
    (re.compile(r"\\leq\b"), " less than or equal to "),
    (re.compile(r"\\geq\b"), " greater than or equal to "),
    (re.compile(r"\\le\b"), " less than or equal to "),
    (re.compile(r"\\ge\b"), " greater than or equal to "),
    (re.compile(r"\\infty\b"), " infinity"),
    (re.compile(r"\\sum\b"), "the sum of "),
    (re.compile(r"\\int\b"), "the integral of "),
    (re.compile(r"\\partial\b"), "partial "),
    (re.compile(r"\\nabla\b"), "nabla "),
    (re.compile(r"\\propto\b"), " is proportional to "),
    (re.compile(r"\\equiv\b"), " is equivalent to "),
    (re.compile(r"\\uparrow\b|↑"), " increases "),
    (re.compile(r"\\downarrow\b|↓"), " decreases "),

    # ── 9. Generic super / subscripts ────────────────────────────────────────
    (re.compile(r"\^\{([^{}]+)\}"), r" to the power of \1"),
    (re.compile(r"\^(\w)"), r" to the power of \1"),
    (re.compile(r"_\{([^{}]+)\}"), r" sub \1"),
    (re.compile(r"_(\w)"), r" sub \1"),

    # ── 10. Strip scaffolding, normalise ──────────────────────────────────────
    (re.compile(r"\\[a-zA-Z]+\*?"), ""),
    (re.compile(r"[{}]"), ""),
    (re.compile(r"\${1,2}"), ""),
    (re.compile(r" {2,}"), " "),
]


_DISPLAY_SUBS: list[tuple] = [

    # ── 0. Pre-processing ────────────────────────────────────────────────────
    (re.compile(r"_\{([A-Za-z][A-Za-z0-9]*)\}"), r"_\1"),
    (re.compile(r"(\w)(\\[A-Za-z])"), r"\1 \2"),

    # ── 1. Text wrappers ─────────────────────────────────────────────────────
    (re.compile(r"\\(?:text|mathrm|mathit|mathbf|mathsf|operatorname)\{([^{}]+)\}"),
     r"\1"),

    # ── 2. Fractions / roots ─────────────────────────────────────────────────
    (re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}"), r"(\1)/(\2)"),
    (re.compile(r"\\sqrt\{([^{}]+)\}"), r"√(\1)"),
    (re.compile(r"\\sqrt\b"), "√"),

    # ── 3. Reaction arrows → Unicode ─────────────────────────────────────────
    (re.compile(r"\\(?:rightleftharpoons|leftrightharpoons|rightleftarrows)\b|[⇌⇋]"),
     "⇌"),
    (re.compile(r"\\xrightarrow\{([^{}]+)\}"), r"→[\1]"),
    (re.compile(r"\\(?:longrightarrow|Rightarrow)\b|[⟶⇒]"), "⟶"),
    (re.compile(r"\\(?:rightarrow|to)\b|→"), "→"),
    (re.compile(r"\\(?:longleftarrow|Leftarrow)\b|[⟵⇐]"), "⟵"),
    (re.compile(r"\\(?:leftarrow|gets)\b|←"), "←"),

    # ── 4. Named subscripts — chemistry / biology ────────────────────────────
    (re.compile(r"\bpK_?[Aa]\b"), "pKₐ"),
    (re.compile(r"\bpK_?[Bb]\b"), "pK_b"),
    (re.compile(r"\bpK_?[Ww]\b"), "pK_w"),
    (re.compile(r"\b[Vv]_?max\b"), "V_max"),
    (re.compile(r"\b[Kk]_?m\b"), "K_m"),
    (re.compile(r"\b[Kk]_?[Dd]\b"), "K_d"),
    (re.compile(r"\b[Kk]_?eq\b"), "K_eq"),
    (re.compile(r"\b[Kk]_?sp\b"), "K_sp"),
    (re.compile(r"\bk_?cat\b"), "k_cat"),

    # ── 5. Ion charges → Unicode superscripts ────────────────────────────────
    (re.compile(r"\^\{(\d+)\+\}"), r"^\1⁺"),
    (re.compile(r"\^\{(\d+)-\}"), r"^\1⁻"),
    (re.compile(r"\^\{\+\}|\^\+"), "⁺"),
    (re.compile(r"\^\{-\}|\^\-"), "⁻"),

    # ── 6. Greek letters → Unicode ───────────────────────────────────────────
    (re.compile(r"\\hbar\b"), "ℏ"),
    (re.compile(r"\\Delta\b"), "Δ"),
    (re.compile(r"\\delta\b"), "δ"),
    (re.compile(r"\\Sigma\b"), "Σ"),
    (re.compile(r"\\sigma\b"), "σ"),
    (re.compile(r"\\rho\b"), "ρ"),
    (re.compile(r"\\mu\b"), "μ"),
    (re.compile(r"\\Pi\b"), "Π"),
    (re.compile(r"\\pi\b"), "π"),
    (re.compile(r"\\alpha\b"), "α"),
    (re.compile(r"\\beta\b"), "β"),
    (re.compile(r"\\Gamma\b"), "Γ"),
    (re.compile(r"\\gamma\b"), "γ"),
    (re.compile(r"\\Theta\b"), "Θ"),
    (re.compile(r"\\theta\b"), "θ"),
    (re.compile(r"\\Omega\b"), "Ω"),
    (re.compile(r"\\omega\b"), "ω"),
    (re.compile(r"\\epsilon\b"), "ε"),
    (re.compile(r"\\varepsilon\b"), "ε"),
    (re.compile(r"\\Lambda\b"), "Λ"),
    (re.compile(r"\\lambda\b"), "λ"),
    (re.compile(r"\\tau\b"), "τ"),
    (re.compile(r"\\Phi\b"), "Φ"),
    (re.compile(r"\\phi\b"), "φ"),
    (re.compile(r"\\varphi\b"), "φ"),
    (re.compile(r"\\Psi\b"), "Ψ"),
    (re.compile(r"\\psi\b"), "ψ"),
    (re.compile(r"\\eta\b"), "η"),
    (re.compile(r"\\chi\b"), "χ"),
    (re.compile(r"\\xi\b"), "ξ"),
    (re.compile(r"\\Xi\b"), "Ξ"),
    (re.compile(r"\\zeta\b"), "ζ"),
    (re.compile(r"\\nu\b"), "ν"),
    (re.compile(r"\\kappa\b"), "κ"),

    # ── 7. Math / chemistry / biology operators → Unicode ─────────────────────
    (re.compile(r"\^\\circ\b"), "°"),    # E^\circ → E°  (standard state)
    (re.compile(r"\\circ\b"), "°"),      # standalone \circ → degree symbol
    (re.compile(r"\\approx\b"), "≈"),
    (re.compile(r"\\times\b"), "×"),
    (re.compile(r"\\cdot\b"), "·"),
    (re.compile(r"\\div\b"), "÷"),
    (re.compile(r"\\pm\b"), "±"),
    (re.compile(r"\\mp\b"), "∓"),
    (re.compile(r"\\neq\b"), "≠"),
    (re.compile(r"\\leq\b"), "≤"),
    (re.compile(r"\\geq\b"), "≥"),
    (re.compile(r"\\le\b"), "≤"),
    (re.compile(r"\\ge\b"), "≥"),
    (re.compile(r"\\infty\b"), "∞"),
    (re.compile(r"\\sum\b"), "Σ"),
    (re.compile(r"\\int\b"), "∫"),
    (re.compile(r"\\partial\b"), "∂"),
    (re.compile(r"\\nabla\b"), "∇"),
    (re.compile(r"\\propto\b"), "∝"),
    (re.compile(r"\\equiv\b"), "≡"),
    (re.compile(r"\\ln\b"), "ln"),
    (re.compile(r"\\log\b"), "log"),
    (re.compile(r"\\exp\b"), "exp"),
    (re.compile(r"\\uparrow\b"), "↑"),
    (re.compile(r"\\downarrow\b"), "↓"),

    # ── 8. Generic super / subscripts ────────────────────────────────────────
    (re.compile(r"\^\{?2\}?"), "²"),
    (re.compile(r"\^\{?3\}?"), "³"),
    (re.compile(r"\^\{?4\}?"), "⁴"),
    (re.compile(r"\^\{?n\}?"), "ⁿ"),
    (re.compile(r"\^\{([^{}]+)\}"), r"^\1"),
    (re.compile(r"\^(\w)"), r"^\1"),
    # Braced digit subscript: _{12} → ₁₂  (handles multi-digit like C₆H₁₂O₆)
    (re.compile(r"_\{(\d+)\}"),
     lambda m: m.group(1).translate(_DIGIT_TO_SUB)),
    # Unbraced single digit: _2 → ₂
    (re.compile(r"_(\d)"),
     lambda m: m.group(1).translate(_DIGIT_TO_SUB)),
    # Special letter subscript: _{e} or _e → ₑ (not followed by more alphanumerics)
    (re.compile(r"_\{?e\}?(?![a-zA-Z0-9])"), "ₑ"),
    # Generic braced subscript: _{abc} → _abc
    (re.compile(r"_\{([^{}]+)\}"), r"_\1"),
    # Generic unbraced subscript: _x → _x (leave as-is)
    (re.compile(r"_(\w)"), r"_\1"),

    # ── 9. Strip scaffolding, normalise ──────────────────────────────────────
    (re.compile(r"\\[a-zA-Z]+\*?"), ""),
    (re.compile(r"[{}]"), ""),
    (re.compile(r"\${1,2}"), ""),
    (re.compile(r" {2,}"), " "),
]


def _apply_subs(text: str, subs: list[tuple]) -> str:
    for pattern, replacement in subs:
        text = pattern.sub(replacement, text)
    return text.strip()


def _has_latex(text: str) -> bool:
    """True if the text likely contains LaTeX math or chemistry notation."""
    return bool(re.search(
        r"\$|\\[a-zA-Z]|_\{|\^\{|\^\+|\^\-"
        r"|→|←|⇌|⇋|⟶|⟵"
        r"|\[(?:[A-Z][A-Za-z0-9]*)\]",
        text,
    ))


def math_to_speech(text: str) -> str:
    """Convert LaTeX / equation notation in *text* to a TTS-friendly spoken form.

    Covers physics (Greek, fractions, integrals), chemistry (reaction arrows,
    concentration brackets, equilibrium / pH / pKa constants), and biology
    (Michaelis-Menten Vmax / Km / Kd, catalytic rate k_cat, Beer-Lambert).
    Non-math text is returned unchanged.
    """
    if not isinstance(text, str) or not _has_latex(text):
        return text
    return _apply_subs(text, _SPEECH_SUBS)


def math_to_display(text: str) -> str:
    """Convert LaTeX / equation notation in *text* to Unicode for GUI display.

    Translates Greek letters (Δ, σ…), operators (≈, ×, ÷…), reaction arrows
    (→, ⇌), ion charges (⁺, ⁻), and strips $ delimiters.
    Non-math text is returned unchanged.
    """
    if not isinstance(text, str) or not _has_latex(text):
        return text
    return _apply_subs(text, _DISPLAY_SUBS)
