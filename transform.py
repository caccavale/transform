import re
from typing import Callable, Union, Dict


class TransformationException(Exception):
    pass


class TransformationTypeMismatch(TransformationException):
    pass


class TransformationFieldMissing(TransformationException):
    pass


class TransformationMalformed(TransformationException):
    pass


def _transform_dict(transformation, data: dict, nullable=False) -> dict[str]:
    if not isinstance(data, dict):
        raise TransformationTypeMismatch(transformation, data, "dict")

    accumulator = {}
    for k, v in transformation.items():
        accumulator.update(transform(v, transform(k, data, nullable)[k], nullable))

    return accumulator


def _transform_list(transformation, data: list, nullable=False) -> dict[str]:
    if not isinstance(data, dict):
        raise TransformationTypeMismatch(transformation, data, "dict")

    accumulator = {}
    for extract in transformation:
        accumulator.update(transform(extract, data, nullable))

    return accumulator


def _transform_string(transformation, data: str, nullable=False) -> dict[str]:
    if "." in transformation:
        steps = transformation.split(".")
        for step in steps:
            if not isinstance(data, dict):
                raise TransformationTypeMismatch(step, data, "dict")
            if step not in data:
                if nullable:
                    return {transformation: None}
                raise TransformationFieldMissing(step, data)
            data = data[step]

        return {transformation: data}

    if transformation not in data:
        if nullable:
            return {transformation: None}
        raise TransformationFieldMissing(transformation, data)

    return {transformation: data[transformation]}


def transform(transformation, data, nullable=False) -> dict[str]:
    if isinstance(transformation, dict):  # todo: convert to match case
        return _transform_dict(transformation, data, nullable)
    elif isinstance(transformation, list):
        return _transform_list(transformation, data, nullable)
    elif isinstance(transformation, str):
        return _transform_string(transformation, data, nullable)
    # elif isnstance(transformation, int):  # TODO support indexing
    #     return _transform_int(transformation, data, nullable)
    elif callable(transformation):  # callable
        return transformation(data)
    else:
        raise TransformationMalformed(transformation)


Atom = Union[str, int]
Extractable = Union[dict, list, str, int]
Extractor = Callable[[Extractable], Dict[str, Union[Atom, list[Atom]]]]  # suppose this can nest


def rename(old, new) -> Extractor:
    def _rename(data):
        return {new: transform(old, data)[old]}
    return _rename


def split(field, delimiter) -> Extractor:
    def _split(data):
        return {field: transform(field, data)[field].split(delimiter)}
    return _split


def mask(field, pattern, replace) -> Extractor:
    def _mask(data):
        value = transform(field, data)[field]
        return {field: re.sub(pattern, replace, value)}
    return _mask


def nullable(field, nullable=True) -> Extractor:
    def _nullable(data):
        return transform(field, data, nullable=nullable)
    return _nullable


if __name__ == "__main__":
    def check(function, args, expected):
        actual = function(*args)
        if actual != expected:
            print(f"{actual} != {expected}")
        assert (actual == expected)

    def apply(extractor, args, data):
        return extractor(*args)(data)

    def raises(function, args, exception):
        try:
            function(*args)
        except exception:
            return
        print(f"Expected {exception} to be raised.")
        assert False

    API_KEY_PATTERN = r"pk\_(\w{4})\w{26}(\w{4})"
    API_KEY_REPLACE = r"pk_\1##########################\2"

    # Strings
    check(transform, ("a", {"a": 1}), {"a": 1})
    check(transform, ("a.b", {"a": {"b": 1}}), {"a.b": 1})
    check(transform, ("a.b.c", {"a": {"b": {"c": 1}}}), {"a.b.c": 1})

    # Lists
    check(transform, (["a"], {"a": 1}), {"a": 1})
    check(transform, (["a", "b"], {"a": 1, "b": 2}), {"a": 1, "b": 2})
    check(transform, (["a", "b", "c.d"], {"a": 1, "b": 2, "c": {"d": 3}}), {"a": 1, "b": 2, "c.d": 3})

    # Dicts (and dots)
    check(transform, ({"a": "b"}, {"a": {"b": 1}}), {"b": 1})
    check(transform, ({"a": "b.c"}, {"a": {"b": {"c": 1}}}), {"b.c": 1})
    check(transform, ({"a.b": "c"}, {"a": {"b": {"c": 1}}}), {"c": 1})
    check(transform, ({"a.b": "c.d"}, {"a": {"b": {"c": {"d": 1}}}}), {"c.d": 1})

    # Nullability
    check(transform, ({"a": "b"}, {"a": {"b": 1}}, True), {"b": 1})
    check(transform, (["a", "b"], {"a": 1}, True), {"a": 1, "b": None})

    # Callables
    # ## Rename
    check(apply, (rename, ("a", "b"), {"a": 1}), {"b": 1})
    check(transform, (rename("a.b", "c"), {"a": {"b": 1}}), {"c": 1})
    check(transform, (["a", rename("b", "a")], {"a": 1, "b": 2}), {"a": 2})
    # ## Split
    check(apply, (split, ("a", ","), {"a": "1,2,3"}), {"a": ["1", "2", "3"]})
    check(transform, (split("a", ","), {"a": "1,2,3"}), {"a": ["1", "2", "3"]})
    # ## Mask
    check(apply, (mask, ("a", r"\d", "#"), {"a": "123"}), {"a": "###"})
    check(transform, (mask("a", API_KEY_PATTERN, API_KEY_REPLACE), {"a": "pk_1234567890123456789012345678901234"}), {"a": "pk_1234##########################1234"})
    # ## Nullable
    check(apply, (nullable, ("a", True), {"a": 1}), {"a": 1})
    check(apply, (nullable, ("a", True), {}), {"a": None})
    raises(apply, (nullable, ("a", False), {}), TransformationFieldMissing)
    check(transform, (nullable("a", True), {}), {"a": None})
    raises(transform, (nullable("a", False), {}, True), TransformationFieldMissing)  # override

