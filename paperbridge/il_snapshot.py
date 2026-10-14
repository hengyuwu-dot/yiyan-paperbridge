"""Copy the PDF layout graph without Python recursion or shared mutable state."""
from dataclasses import fields, is_dataclass


_ATOMS = (str, bytes, int, float, bool, type(None))


def snapshot_graph(root):
    """Snapshot BabelDOC's dataclasses/lists, including aliases and cycles.

    Nested PDF forms can exceed deepcopy's call-stack depth. Work on an explicit
    stack instead; never change the interpreter recursion limit or share boxes
    that the typesetter can later mutate.
    """
    memo = {}
    holder = [None]
    tasks = [(root, holder, 0)]

    def assign(parent, key, value):
        if isinstance(parent, (list, dict)):
            parent[key] = value
        else:
            setattr(parent, key, value)

    while tasks:
        value, parent, key = tasks.pop()
        if (type(value).__name__ == "LazyPassthroughInstruction"
                and type(value).__module__.startswith("babeldoc.")):
            # This string wrapper retains the full linked history of PDF paint
            # commands. Materialize its immutable string through BabelDOC's
            # iterative renderer instead of copying that history recursively.
            assign(parent, key, str(value))
            continue
        if isinstance(value, _ATOMS):
            assign(parent, key, value)
            continue
        if id(value) in memo:
            assign(parent, key, memo[id(value)])
            continue
        if is_dataclass(value) and not isinstance(value, type):
            copied = object.__new__(type(value))
            children = [(getattr(value, field.name), copied, field.name)
                        for field in fields(value)]
        elif isinstance(value, list):
            copied = [None] * len(value)
            children = [(item, copied, index) for index, item in enumerate(value)]
        elif isinstance(value, dict):
            if not all(isinstance(k, _ATOMS) for k in value):
                raise TypeError("PDF snapshot dictionary keys must be scalar")
            copied = {}
            children = [(item, copied, k) for k, item in value.items()]
        elif isinstance(value, tuple) and all(isinstance(item, _ATOMS) for item in value):
            copied, children = value, []  # immutable coordinate tuple
        else:
            raise TypeError(f"Unsupported PDF snapshot field: {type(value).__name__}")
        memo[id(value)] = copied
        assign(parent, key, copied)
        tasks.extend(children)
    return holder[0]
