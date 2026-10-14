"""Preserve image transform precision in the pinned BabelDOC renderer.

Six decimal places can produce a visible seam between adjacent image strips,
even though each original image object's bytes are unchanged.
"""
import math


def matrix_bytes(matrix):
    values = [getattr(matrix, key) for key in "abcdef"] if hasattr(matrix, "a") else list(matrix)
    if len(values) != 6 or not all(math.isfinite(value) for value in values):
        raise ValueError("无效的 PDF 变换矩阵")
    # Fixed notation is required by PDF; exponent notation is not a PDF number.
    return (" " + " ".join(f"{value:.12f}".rstrip("0").rstrip(".") or "0" for value in values) + " cm ").encode()


def install():
    from babeldoc.format.pdf.document_il.backend import pdf_creater
    from babeldoc.format.pdf.document_il.utils import matrix_helper
    pdf_creater.matrix_to_bytes = matrix_bytes
    matrix_helper.matrix_to_bytes = matrix_bytes
