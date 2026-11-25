"""Isolated, safe mathematical expression evaluator with constant support."""

import ast
import math
import operator
from typing import Any

from medicare.tools.base import BaseTool

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "log": math.log,
    "exp": math.exp,
}

_ALLOWED_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def _eval_node(node: ast.AST) -> Any:
    """Recursively evaluate an AST node within strict safety boundaries."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise ValueError(f"Undefined variable or constant: {node.id}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Disallowed binary operator: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _ALLOWED_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Disallowed unary operator: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCTIONS:
            func = _ALLOWED_FUNCTIONS[node.func.id]
            args = [_eval_node(arg) for arg in node.args]
            return func(*args)
        raise ValueError(f"Disallowed function call: {getattr(node.func, 'id', 'unknown')}")

    raise ValueError(f"Disallowed expression syntax: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """Tool for verifying and computing mathematical expressions."""

    name = "calculator"
    description = "Compute safe mathematical expressions. Supports arithmetic, constants (pi, e), and functions (sqrt, sin, cos, abs, round)."

    async def execute(self, expression: str = "", **kwargs: Any) -> str:
        if not expression:
            return "Error: Empty expression provided."
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = _eval_node(tree)
            return f"Result: {result}"
        except Exception as err:
            return f"Math Evaluation Error: {err}"
