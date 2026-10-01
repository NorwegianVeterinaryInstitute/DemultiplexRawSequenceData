# Partial stub: only the MultipartEncoder API that demux uses (step07_05, #226).
# requests-toolbelt 1.0.0 ships no type information.
from collections.abc import Mapping, Sequence
from typing import Any

class MultipartEncoder:
    boundary_value: str
    boundary: str
    encoding: str
    finished: bool
    def __init__( self, fields: Mapping[ str, Any ] | Sequence[ tuple[ str, Any ] ], boundary: str | None = None, encoding: str = "utf-8" ) -> None: ...
    @property
    def len( self ) -> int: ...
    @property
    def content_type( self ) -> str: ...
    def to_string( self ) -> bytes: ...
    def read( self, size: int = -1 ) -> bytes: ...
