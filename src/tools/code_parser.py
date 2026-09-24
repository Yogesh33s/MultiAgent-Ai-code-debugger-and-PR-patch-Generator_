"""
Code parser tool using Tree-sitter and tree-sitter-python.
Provides AST extraction of functions and their exact line ranges.
"""

from typing import List, Optional, Dict, Any, Tuple


class FunctionInfo(dict):
    """
    Dictionary representing extracted function details.
    Supports both key indexing (`info["code"]`) and attribute access (`info.code`).
    """
    def __init__(self, name: str, code: str, line_start: int, line_end: int):
        super().__init__(
            name=name,
            code=code,
            line_start=line_start,
            line_end=line_end,
            lines=(line_start, line_end),
            line_range=(line_start, line_end)
        )
        self.name = name
        self.code = code
        self.line_start = line_start
        self.line_end = line_end
        self.lines = (line_start, line_end)
        self.line_range = (line_start, line_end)


# Initialize Tree-sitter Python parser
_tree_sitter_available = False
_parser = None

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    _py_lang = Language(tspython.language())
    _parser = Parser(_py_lang)
    _tree_sitter_available = True
except Exception:
    _tree_sitter_available = False


def _parse_with_tree_sitter(source_code: str) -> List[FunctionInfo]:
    """Parse python code using Tree-sitter to find all function definitions."""
    if not source_code or not _parser:
        return []

    code_bytes = source_code.encode("utf-8")
    tree = _parser.parse(code_bytes)
    results = []

    def traverse(node):
        if node.type in ("function_definition", "async_function_definition"):
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                # Include decorator lines if function is decorated
                target_node = node.parent if (node.parent and node.parent.type == "decorated_definition") else node
                func_code = code_bytes[target_node.start_byte:target_node.end_byte].decode("utf-8")
                
                # 1-indexed lines
                line_start = target_node.start_point[0] + 1
                line_end = target_node.end_point[0] + 1
                results.append(FunctionInfo(name=func_name, code=func_code, line_start=line_start, line_end=line_end))

        for child in node.children:
            traverse(child)

    traverse(tree.root_node)
    return results


def _parse_with_ast_fallback(source_code: str) -> List[FunctionInfo]:
    """Fallback parser using Python's built-in ast module."""
    import ast
    if not source_code:
        return []

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    lines = source_code.splitlines(keepends=True)
    results = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line)
            func_code = "".join(lines[start_line - 1:end_line])
            results.append(FunctionInfo(name=func_name, code=func_code, line_start=start_line, line_end=end_line))

    return results


def extract_all_functions(source_code: str) -> List[FunctionInfo]:
    """
    Extracts all functions from source code with code snippet and line ranges.
    Uses Tree-sitter if available, with automatic fallback to standard AST.
    """
    if _tree_sitter_available:
        try:
            return _parse_with_tree_sitter(source_code)
        except Exception:
            return _parse_with_ast_fallback(source_code)
    return _parse_with_ast_fallback(source_code)


def list_functions(source_code: str) -> List[str]:
    """
    Returns a list of all function names present in the source code.
    
    Example:
        >>> list_functions("def add(a, b): return a + b")
        ['add']
    """
    funcs = extract_all_functions(source_code)
    return [f.name for f in funcs]


def extract_function(source_code: str, function_name: str) -> Optional[FunctionInfo]:
    """
    Finds and extracts a specific function by name.
    
    Returns:
        FunctionInfo dict containing:
        - code: the source code of the function
        - line_start: 1-indexed starting line
        - line_end: 1-indexed ending line
        Returns None if function is not found.
    """
    funcs = extract_all_functions(source_code)
    for f in funcs:
        if f.name == function_name:
            return f
    return None
