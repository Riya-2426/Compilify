"""Map GCC error text to short, beginner-friendly suggestions."""
from __future__ import annotations

import re


def suggestion_for_gcc_error(msg: str) -> str:
    m = msg.lower()

    # Missing semicolon
    if re.search(r"expected.*;", m):
        return (
            "Possible missing semicolon `;` before this line.\n"
            "Example:\n"
            "int x = 10;\n"
            "printf(\"%d\", x);"
        )

    # Missing quotes
    if "missing terminating" in m or "unterminated" in m:
        return (
            "String is missing closing quote `\"`.\n"
            "Example:\n"
            "printf(\"Hello\");"
        )

    # Undeclared variable
    if "undeclared" in m:
        return (
            "Variable used before declaration.\n"
            "Example:\n"
            "int x;\n"
            "x = 10;"
        )

    # Invalid identifier
    if "expected identifier" in m or "invalid suffix" in m:
        return (
            "Invalid variable/function name.\n"
            "Variable names cannot start with numbers or contain special symbols.\n"
            "Example:\n"
            "int num1 = 10;"
        )

    # Parenthesis mismatch
    if re.search(r"expected.*\)", m):
        return (
            "Check matching parentheses `(` and `)`.\n"
            "Example:\n"
            "printf(\"%d\", x);"
        )

    # Opening parenthesis missing
    if re.search(r"expected.*\(", m):
        return (
            "Missing opening parenthesis `(`.\n"
            "Example:\n"
            "if (x > 0)"
        )

    # Brace mismatch
    if re.search(r"expected.*\}", m):
        return (
            "Missing closing brace `}` for block/function."
        )

    # Opening brace missing
    if re.search(r"expected.*\{", m):
        return (
            "Missing opening brace `{`.\n"
            "Example:\n"
            "if (x > 0) {\n"
            "   printf(\"Hi\");\n"
            "}"
        )

    # Invalid initializer
    if "invalid initializer" in m:
        return (
            "Invalid value assigned during initialization.\n"
            "Example:\n"
            "int x = 10;"
        )

    # Too many/few arguments
    if "too many arguments" in m:
        return (
            "Too many arguments passed to function.\n"
            "Check function definition and parameters."
        )

    if "too few arguments" in m:
        return (
            "Missing required function arguments.\n"
            "Example:\n"
            "printf(\"%d\", x);"
        )

    # Invalid operands
    if "invalid operands" in m:
        return (
            "Operator used with incompatible values.\n"
            "Example:\n"
            "Cannot add string and integer directly."
        )

    # Lvalue required
    if "lvalue required" in m:
        return (
            "Left side of assignment must be a variable.\n"
            "Example:\n"
            "x = 10;\n"
            "But `(a+b) = 10` is invalid."
        )

    # Array errors
    if "subscripted value is neither array nor pointer" in m:
        return (
            "Only arrays or pointers can use `[]` indexing.\n"
            "Example:\n"
            "arr[0]"
        )

    # Redeclaration
    if "redefinition" in m or "conflicting types" in m:
        return (
            "Variable/function declared multiple times with different types.\n"
            "Use unique declarations."
        )

    # Invalid character
    if "stray" in m:
        return (
            "Invalid character detected in source code.\n"
            "Use only standard keyboard symbols.\n"
            "Avoid copying code from Word/PDF."
        )

    # Missing include/header
    if "implicit declaration" in m:
        return (
            "Function used without proper header file.\n"
            "Example:\n"
            "#include <stdio.h>"
        )

    # No such file
    if "no such file" in m or "cannot find" in m:
        return (
            "Header file or source file not found.\n"
            "Check file name and include path."
        )

    # Undefined reference
    if "undefined reference" in m:
        return (
            "Function declared but definition/link missing.\n"
            "Example:\n"
            "Compile with required libraries."
        )

    # Return type mismatch
    if "return type" in m:
        return (
            "Returned value does not match function return type.\n"
            "Example:\n"
            "int func() { return 10; }"
        )

    # Break/continue misuse
    if "break statement not within loop" in m:
        return (
            "`break` can only be used inside loops or switch statements."
        )

    if "continue statement not within loop" in m:
        return (
            "`continue` can only be used inside loops."
        )

    # Default fallback
    return (
        "Check syntax near this line:\n"
        "- semicolons\n"
        "- braces\n"
        "- parentheses\n"
        "- quotes\n"
        "- variable names"
    )
