from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, fields
from functools import cached_property
from typing import TYPE_CHECKING, Any, final

from ..utils import EMPTY_FROZEN_DICT, FrozenDict, hash_str

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import ClassVar, Final, TypeVar

    T = TypeVar('T', bound='KAst')
    W = TypeVar('W', bound='WithKAtt')

_LOGGER: Final = logging.getLogger(__name__)


class KAst(ABC):
    @staticmethod
    def version() -> int:
        return 3

    @classmethod
    def from_dict(cls: type[T], d: Mapping[str, Any]) -> T:
        from . import inner, outer

        node = d['node']

        if node == 'KAtt':
            return KAtt.from_dict(d)  # type: ignore

        if node in inner.KInner._INNER_NODES:
            return getattr(inner, node).from_dict(d)

        if node in outer.KOuter._OUTER_NODES:
            return getattr(outer, node).from_dict(d)

        raise ValueError(f'Expected KAst label as "node" value, found: {node}')

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        ...

    @classmethod
    def from_json(cls: type[T], s: str) -> T:
        return cls.from_dict(json.loads(s))

    @final
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @final
    @cached_property
    def hash(self) -> str:
        return hash_str(self.to_json())

    @classmethod
    def _check_node(cls: type[T], d: Mapping[str, Any], expected: str | None = None) -> None:
        expected = expected if expected is not None else cls.__name__
        actual = d['node']
        if actual != expected:
            raise ValueError(f'Expected "node" value: {expected}, got: {actual}')

    def _as_shallow_tuple(self) -> tuple[Any, ...]:
        # shallow copy version of dataclass.astuple.
        return tuple(self.__dict__[field.name] for field in fields(type(self)))  # type: ignore

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, KAst):
            return NotImplemented
        if type(self) == type(other):
            return self._as_shallow_tuple() < other._as_shallow_tuple()
        return type(self).__name__ < type(other).__name__


@final
@dataclass(frozen=True)
class KAtt(KAst, Mapping[str, Any]):
    atts: FrozenDict[str, Any]

    SORT: ClassVar[str] = 'org.kframework.kore.Sort'
    LOCATION: ClassVar[str] = 'org.kframework.attributes.Location'
    SOURCE: ClassVar[str] = 'org.kframework.attributes.Source'

    def __init__(self, atts: Mapping[str, Any] = EMPTY_FROZEN_DICT):
        def _freeze(m: Any) -> Any:
            if isinstance(m, (int, str, tuple, FrozenDict, frozenset)):
                return m
            elif isinstance(m, list):
                return tuple(_freeze(v) for v in m)
            elif isinstance(m, dict):
                return FrozenDict((k, _freeze(v)) for (k, v) in m.items())
            raise ValueError(f"Don't know how to freeze attribute value {m} of type {type(m)}.")

        frozen = _freeze(atts)
        assert isinstance(frozen, FrozenDict)
        object.__setattr__(self, 'atts', frozen)

    def __iter__(self) -> Iterator[str]:
        return iter(self.atts)

    def __len__(self) -> int:
        return len(self.atts)

    def __getitem__(self, key: str) -> Any:
        return self.atts[key]

    @staticmethod
    def of(**atts: Any) -> KAtt:
        return KAtt(atts=atts)

    @classmethod
    def from_dict(cls: type[KAtt], d: Mapping[str, Any]) -> KAtt:
        cls._check_node(d)
        return KAtt(atts=d['att'])

    def to_dict(self) -> dict[str, Any]:
        def _to_dict(m: Any) -> Any:
            if isinstance(m, FrozenDict):
                return {k: _to_dict(v) for (k, v) in m.items()}
            return m

        return {'node': 'KAtt', 'att': _to_dict(self.atts)}

    def let(self, *, atts: Mapping[str, Any] | None = None) -> KAtt:
        atts = atts if atts is not None else self.atts
        return KAtt(atts=atts)

    def update(self, atts: Mapping[str, Any]) -> KAtt:
        return self.let(atts={k: v for k, v in {**self.atts, **atts}.items() if v is not None})

    def remove(self, atts: Iterable[str]) -> KAtt:
        return KAtt({k: v for k, v in self.atts.items() if k not in atts})

    def drop_source(self) -> KAtt:
        new_atts = {key: value for key, value in self.atts.items() if key != self.SOURCE and key != self.LOCATION}
        return KAtt(atts=new_atts)

    @property
    def pretty(self) -> str:
        if len(self) == 0:
            return ''
        att_strs = []
        for k, v in self.items():
            if k == self.LOCATION:
                loc_ids = str(v).replace(' ', '')
                att_strs.append(f'{self.LOCATION}{loc_ids}')
            elif k == self.SOURCE:
                att_strs.append(self.SOURCE + '("' + v + '")')
            else:
                att_strs.append(f'{k}({v})')
        return f'[{", ".join(att_strs)}]'


EMPTY_ATT: Final = KAtt()


class WithKAtt(ABC):
    att: KAtt

    @abstractmethod
    def let_att(self: W, att: KAtt) -> W:
        ...

    def map_att(self: W, f: Callable[[KAtt], KAtt]) -> W:
        return self.let_att(att=f(self.att))

    def update_atts(self: W, atts: Mapping[str, Any]) -> W:
        return self.let_att(att=self.att.update(atts))


# TODO fix typing (maybe just return Mapping)
def kast_term(dct: Mapping[str, Any], cls: type[T] = KAst) -> T:  # type: ignore
    if dct['format'] != 'KAST':
        raise ValueError(f"Invalid format: {dct['format']}")

    if dct['version'] != KAst.version():
        raise ValueError(f"Invalid version: {dct['version']}")

    return cls.from_dict(dct['term'])
