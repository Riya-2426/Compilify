<<<<<<< HEAD
## C Compiler GUI

A PyQt5 GUI for editing, compiling (via `gcc`), running C programs, and showing:

- Line-numbered code editor with basic C syntax highlighting
- Tokens table (Keyword / Identifier / Operator / Constant)
- Lexical, semantic, and GCC syntax errors (colored + line highlighting)
- Output panel for compiler messages and program output

### Requirements

- Python 3.9+
- `gcc` available on PATH (e.g., MinGW-w64)

Install Python deps:

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

# CD PBL – Mini C Compiler

This project contains:

- **Java backend** (`src/minicompiler/`): lexer + parser + simple executor (generates output for `print(...)`).
- **Python GUI** (`python_gui/`): advanced editor UI that saves `.c` files, compiles via the Java backend, and shows friendly errors with line highlighting and per-error visualization.

## Run the Python GUI

Requirements:

- Python 3.10+ (recommended)
- Java JDK (so `javac` and `java` are available in PATH)

From the project root (`CD PBL`):

```bash
python python_gui/run_gui.py
```

On first compile, the GUI will automatically build the Java backend into `build/java/`.

## Supported language (mini C-like)

- Variable declaration: `int x = 10;`
- Assignment: `x = x + 1;`
- Print: `print(x);`
- Expressions: `+ - * /` with parentheses

=======
# Compilify
A Mini C compiler which on correct code compilation give output and show different phases of compiler and if any error occur it tells the error in easy or friendly manner along with that tell the category of error occured.
>>>>>>> 9a4abf558a34b21bea08f7144ffd6a34df48a126
