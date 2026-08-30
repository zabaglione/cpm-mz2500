#!/usr/bin/env python3
"""Mechanically convert the vendored CP/M 2.2 sources to z80asm 1.8 syntax.

Input: vendor/cpm22/src/{ccp,bdos}.asm - Macro Assembler AS syntax, 8080
mnemonics (brouhaha/cpm22 reformatting of the DRI originals).
Output: Z80-mnemonic source that Bas Wijnen z80asm 1.8 assembles to the
same bytes (every 8080 instruction maps 1:1 onto the identical Z80 opcode).

The conversion is fully mechanical - no hand edits. Correctness is enforced
by tests/test_vendor_match.py, which byte-compares the assembled
output against the vendored CPM.SYS reference (serial bytes masked).

What is handled (validated against the actual vendored sources):
- conditional assembly: ifdef/ifndef are resolved here (z80asm has no
  ifdef); plain `if` expressions are evaluated against equ constants.
- `label equ` gains the colon z80asm requires; `label:mnemonic` splits.
- db/dw/ds -> defb/defw/defs; title/.cpu -> comments.
- the full 8080 mnemonic set -> Z80 equivalents.
- a validation pass rejects any leftover 8080 mnemonic or AS-only operator
  (and/or/xor/not/shl/shr/mod as words) so nothing misassembles silently -
  z80asm treats some of these as garbage without erroring.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REG8 = {"a": "a", "b": "b", "c": "c", "d": "d", "e": "e", "h": "h", "l": "l",
        "m": "(hl)"}
PAIR = {"b": "bc", "d": "de", "h": "hl", "sp": "sp"}
PUSH_PAIR = {"b": "bc", "d": "de", "h": "hl", "psw": "af"}
COND = {"nz": "nz", "z": "z", "nc": "nc", "c": "c", "po": "po", "pe": "pe",
        "p": "p", "m": "m"}

WORD_OPERATORS = {"and": "&", "or": "|", "xor": "^", "not": "~",
                  "shl": "<<", "shr": ">>"}
FORBIDDEN_WORDS = set(WORD_OPERATORS) | {"mod"}

EIGHTY80_MNEMONICS = {
    "mov", "mvi", "lxi", "lda", "sta", "lhld", "shld", "ldax", "stax",
    "xchg", "xthl", "sphl", "pchl", "add", "adc", "sub", "sbb", "ana",
    "xra", "ora", "cmp", "adi", "aci", "sui", "sbi", "ani", "xri", "ori",
    "cpi", "inr", "dcr", "inx", "dcx", "dad", "jmp", "jnz", "jz", "jnc",
    "jc", "jpo", "jpe", "jp", "jm", "call", "cnz", "cz", "cnc", "cc",
    "cpo", "cpe", "cp", "cm", "ret", "rnz", "rz", "rnc", "rc", "rpo",
    "rpe", "rp", "rm", "rlc", "rrc", "ral", "rar", "cma", "stc", "cmc",
    "daa", "nop", "hlt", "ei", "di", "in", "out", "push", "pop", "rst",
}


QUOTED_SEGMENT = r"(\"[^\"]*\"|'[^']*')"


def split_comment(line: str) -> tuple[str, str]:
    """Split at the first ';' outside single- or double-quoted text."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == ";":
            return line[:i], line[i:]
    return line, ""


def fix_operators(expr: str) -> str:
    """Replace AS word operators outside quoted text; error on mod."""
    out = []
    for i, seg in enumerate(re.split(QUOTED_SEGMENT, expr)):
        if i % 2 == 1:  # quoted segment, untouched
            out.append(seg)
            continue
        if re.search(r"\bmod\b", seg, re.IGNORECASE):
            raise ValueError(f"mod operator needs a manual mapping: {expr!r}")
        for word, sym in WORD_OPERATORS.items():
            seg = re.sub(rf"\b{word}\b", sym, seg, flags=re.IGNORECASE)
        out.append(seg)
    return "".join(out)


class Evaluator:
    """Evaluate AS constant expressions for `if` and symbol tracking."""

    def __init__(self) -> None:
        self.symbols: dict[str, int] = {}

    def value(self, expr: str) -> int | None:
        text = fix_operators(expr)
        # numbers: 0abcdh / 101b / 123 ; identifiers from the table
        tokens = []
        for tok in re.finditer(r"\"[^\"]\"|'[^']'|[A-Za-z_$][\w$]*"
                               r"|[0-9][0-9A-Fa-f]*[hH]\b"
                               r"|[01]+[bB]\b|\d+|<<|>>|[~&|^()+\-*/]|\s+|.",
                               text):
            t = tok.group(0)
            if not t.strip():
                continue
            if len(t) == 3 and t[0] == t[2] and t[0] in "\"'":
                tokens.append(str(ord(t[1])))
            elif re.fullmatch(r"[0-9][0-9A-Fa-f]*[hH]", t):
                tokens.append(str(int(t[:-1], 16)))
            elif re.fullmatch(r"[01]+[bB]", t):
                tokens.append(str(int(t[:-1], 2)))
            elif re.fullmatch(r"\d+", t):
                tokens.append(t)
            elif re.fullmatch(r"[A-Za-z_$][\w$]*", t):
                if t == "$" or t not in self.symbols:
                    return None  # location counter / forward ref: not constant
                tokens.append(str(self.symbols[t]))
            elif t in {"<<", ">>", "~", "&", "|", "^", "(", ")", "+", "-",
                       "*", "/"}:
                tokens.append(t)
            else:
                return None
        try:
            return int(eval("".join(tokens), {"__builtins__": {}}, {})) & 0xFFFF
        except Exception:
            return None


def strip_outer_parens(expr: str) -> str:
    """Drop parens that enclose the whole expression.

    8080 immediates like `lxi b,(reccnt-extnum)` are plain values, but the
    same spelling in Z80 syntax means a memory operand (`ld bc,(nn)` is the
    4-byte ED 4B form, `ld hl,(nn)` silently becomes the 2A opcode), so
    immediates and jump targets must never stay fully parenthesized.
    """
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    return expr  # parens close early: not fully enclosed
        expr = expr[1:-1].strip()
    return expr


def immediate(expr: str) -> str:
    return strip_outer_parens(fix_operators(expr))


def translate_instruction(mnem: str, ops: str) -> str:
    """8080 mnemonic + operand field -> one Z80 instruction line body."""
    ops = ops.strip()
    parts = [p.strip() for p in ops.split(",")] if ops else []

    def r8(name: str) -> str:
        return REG8[name.lower()]

    if mnem == "mov":
        return f"ld {r8(parts[0])},{r8(parts[1])}"
    if mnem == "mvi":
        return f"ld {r8(parts[0])},{immediate(parts[1])}"
    if mnem == "lxi":
        return f"ld {PAIR[parts[0].lower()]},{immediate(parts[1])}"
    if mnem == "lda":
        return f"ld a,({fix_operators(ops)})"
    if mnem == "sta":
        return f"ld ({fix_operators(ops)}),a"
    if mnem == "lhld":
        return f"ld hl,({fix_operators(ops)})"
    if mnem == "shld":
        return f"ld ({fix_operators(ops)}),hl"
    if mnem == "ldax":
        return f"ld a,({PAIR[ops.lower()]})"
    if mnem == "stax":
        return f"ld ({PAIR[ops.lower()]}),a"
    if mnem == "xchg":
        return "ex de,hl"
    if mnem == "xthl":
        return "ex (sp),hl"
    if mnem == "sphl":
        return "ld sp,hl"
    if mnem == "pchl":
        return "jp (hl)"
    if mnem in {"add", "adc", "sub", "sbb", "ana", "xra", "ora", "cmp"}:
        z80 = {"add": "add a,", "adc": "adc a,", "sub": "sub ",
               "sbb": "sbc a,", "ana": "and ", "xra": "xor ",
               "ora": "or ", "cmp": "cp "}[mnem]
        return f"{z80}{r8(ops)}"
    if mnem in {"adi", "aci", "sui", "sbi", "ani", "xri", "ori", "cpi"}:
        z80 = {"adi": "add a,", "aci": "adc a,", "sui": "sub ",
               "sbi": "sbc a,", "ani": "and ", "xri": "xor ",
               "ori": "or ", "cpi": "cp "}[mnem]
        return f"{z80}{immediate(ops)}"
    if mnem == "inr":
        return f"inc {r8(ops)}"
    if mnem == "dcr":
        return f"dec {r8(ops)}"
    if mnem == "inx":
        return f"inc {PAIR[ops.lower()]}"
    if mnem == "dcx":
        return f"dec {PAIR[ops.lower()]}"
    if mnem == "dad":
        return f"add hl,{PAIR[ops.lower()]}"
    if mnem == "jmp":
        return f"jp {immediate(ops)}"
    if mnem in {"jnz", "jz", "jnc", "jc", "jpo", "jpe", "jp", "jm"}:
        return f"jp {COND[mnem[1:]]},{immediate(ops)}"
    if mnem == "call":
        return f"call {immediate(ops)}"
    if mnem in {"cnz", "cz", "cnc", "cc", "cpo", "cpe", "cp", "cm"}:
        return f"call {COND[mnem[1:]]},{immediate(ops)}"
    if mnem == "ret":
        return "ret"
    if mnem in {"rnz", "rz", "rnc", "rc", "rpo", "rpe", "rp", "rm"}:
        return f"ret {COND[mnem[1:]]}"
    if mnem == "rlc":
        return "rlca"
    if mnem == "rrc":
        return "rrca"
    if mnem == "ral":
        return "rla"
    if mnem == "rar":
        return "rra"
    if mnem == "cma":
        return "cpl"
    if mnem == "stc":
        return "scf"
    if mnem == "cmc":
        return "ccf"
    if mnem in {"daa", "nop", "ei", "di"}:
        return mnem
    if mnem == "hlt":
        return "halt"
    if mnem == "in":
        return f"in a,({fix_operators(ops)})"
    if mnem == "out":
        return f"out ({fix_operators(ops)}),a"
    if mnem == "push":
        return f"push {PUSH_PAIR[ops.lower()]}"
    if mnem == "pop":
        return f"pop {PUSH_PAIR[ops.lower()]}"
    if mnem == "rst":
        return f"rst {int(ops, 0) * 8}"
    raise ValueError(f"unhandled 8080 mnemonic {mnem!r}")


def validate(code: str, source_line: str) -> None:
    """Reject anything z80asm would swallow silently."""
    body, _ = split_comment(code)
    # Peel the label and the (Z80) mnemonic: word-operator checks only make
    # sense in the operand field - `or a` is a legitimate output instruction.
    operand = re.sub(r"^\s*(?:[A-Za-z_?@][\w$]*:)?\s*\.?[A-Za-z]+\b", "", body, count=1)
    for i, seg in enumerate(re.split(QUOTED_SEGMENT, operand)):
        if i % 2 == 1:
            continue
        for word in re.findall(r"[A-Za-z_][\w]*", seg):
            lw = word.lower()
            if lw in FORBIDDEN_WORDS:
                raise ValueError(f"leftover operator {word!r} in {source_line!r}")
    first = re.match(r"\s*(?:[A-Za-z_?@][\w$]*:)?\s*([A-Za-z_.][\w.]*)", body)
    if first and first.group(1).lower() in EIGHTY80_MNEMONICS - {
            "add", "adc", "sub", "cp", "call", "ret", "push", "pop", "in",
            "out", "jp", "rst", "ei", "di", "nop", "daa"}:
        raise ValueError(f"leftover 8080 mnemonic in {source_line!r}")


def convert(text: str, defines: dict[str, int]) -> str:
    evaluator = Evaluator()
    evaluator.symbols.update(defines)
    out: list[str] = []
    for name, value in defines.items():
        out.append(f"{name}:\tequ 0{value:04x}h")
    # conditional stack entries: True=emit, False=skip, None=skip (dead else)
    stack: list[bool | None] = []

    def active() -> bool:
        return all(state is True for state in stack)

    for raw in text.splitlines():
        code, comment = split_comment(raw)
        stripped = code.strip()
        lower = stripped.lower()

        # --- conditional directives are always interpreted ---
        m = re.match(r"(ifdef|ifndef|if|else|endif)\b\s*(.*)$", lower)
        if m and not re.match(r"^[A-Za-z_][\w]*:", stripped):
            directive, rest = m.group(1), stripped[len(m.group(1)):].strip()
            if directive == "ifdef":
                stack.append(active() and rest.lower() in evaluator.symbols)
            elif directive == "ifndef":
                stack.append(active() and rest.lower() not in evaluator.symbols)
            elif directive == "if":
                if active():
                    value = evaluator.value(rest)
                    if value is None:
                        raise ValueError(f"cannot evaluate: {raw!r}")
                    stack.append(value != 0)
                else:
                    stack.append(None)
            elif directive == "else":
                top = stack.pop()
                enclosing = active()
                stack.append(None if top is None or not enclosing
                             else (not top))
            elif directive == "endif":
                stack.pop()
            out.append(f";[cond] {raw}" if raw.strip() else "")
            continue
        if not active():
            out.append(f";[skip] {raw}")
            continue

        if not stripped:
            out.append(comment if comment else raw)
            continue

        # --- label peeling ---
        label = ""
        rest = stripped
        lm = re.match(r"([A-Za-z_?@][\w$]*)\s*:\s*(.*)$", stripped)
        if lm:
            label, rest = lm.group(1), lm.group(2)
        else:
            em = re.match(r"([A-Za-z_?@][\w$]*)\s+(equ|set)\b\s*(.*)$", stripped,
                          re.IGNORECASE)
            if em:
                # AS `set` is a redefinable equ; the vendored sources only
                # ever define each such symbol once, so equ is equivalent.
                label, rest = em.group(1), "equ " + em.group(3)

        mnem_match = re.match(r"(\.?[A-Za-z]+)\b\s*(.*)$", rest)
        mnem = mnem_match.group(1).lower() if mnem_match else ""
        ops = mnem_match.group(2) if mnem_match else ""

        if mnem in {"title", ".cpu", "page"}:
            out.append(f";[meta] {raw}")
            continue

        prefix = f"{label}:" if label else ""
        pad = "\t" if label else "\t"

        if mnem == "equ":
            if label and label.lower() in defines:
                # Symbol supplied via --define (emitted at the top): the
                # in-file definition would either duplicate it or - worse -
                # be a forward reference z80asm silently resolves to 0
                # (`bios` is defined at the END of bdos.asm but used at the
                # top; z80asm emits 0 for such equ chains without an error).
                out.append(f";[defined] {raw}")
                continue
            expr = fix_operators(ops)
            value = evaluator.value(ops)
            if value is not None and label:
                evaluator.symbols[label.lower()] = value
            out.append(f"{prefix}{pad}equ {expr}{comment and ' ' + comment}")
        elif mnem == "org":
            out.append(f"{prefix}{pad}org {fix_operators(ops)}".rstrip()
                       + (" " + comment if comment else ""))
        elif mnem == "end":
            # AS `end <start>` carries a start address; z80asm's end takes no
            # operand and rejects even a trailing comment on the same line.
            out.append(f";[was] end {ops}".rstrip())
            out.append(f"{prefix}{pad}end")
        elif mnem in {"db", "dw", "ds"}:
            directive = {"db": "defb", "dw": "defw", "ds": "defs"}[mnem]
            out.append(f"{prefix}{pad}{directive} {fix_operators(ops)}"
                       + (" " + comment if comment else ""))
        elif mnem in EIGHTY80_MNEMONICS:
            body = translate_instruction(mnem, ops)
            out.append(f"{prefix}{pad}{body}" + (" " + comment if comment else ""))
        elif not mnem and label:
            out.append(f"{prefix}" + (" " + comment if comment else ""))
        else:
            raise ValueError(f"unrecognized line: {raw!r}")

        validate(out[-1], raw)

    if stack:
        raise ValueError("unbalanced conditional at end of file")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--origin", required=True,
                        help="value for the `origin` symbol, e.g. 0xDC00")
    parser.add_argument("--define", action="append", default=[],
                        metavar="NAME=VALUE",
                        help="predefine a symbol; suppresses its in-file "
                             "definition (needed for forward-defined ones "
                             "like bdos.asm's `bios`)")
    args = parser.parse_args()

    origin = int(args.origin, 0)
    defines = {"origin": origin}
    for item in args.define:
        name, _, value = item.partition("=")
        defines[name.strip().lower()] = int(value, 0)
    source = pathlib.Path(args.input).read_text()
    converted = convert(source, defines)
    header = (f"; GENERATED by convert_cpm22.py from {pathlib.Path(args.input).name}"
              f" (origin={origin:04x}h) - DO NOT EDIT\n")
    pathlib.Path(args.output).write_text(header + converted)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"convert_cpm22: {exc}", file=sys.stderr)
        raise SystemExit(1)
