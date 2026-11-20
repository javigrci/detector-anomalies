"""Seudonimización del usuario e identificadores derivados con HMAC (FR-001-23, FR-001-24).

El nombre de usuario nunca sale del módulo en claro. Los identificadores del adaptador también se
derivan con la clave (separación de dominio): un hash sin clave permitiría confirmar un usuario
adivinado probando candidatos (research R6).
"""

import hashlib
import hmac
import os
import unicodedata
from collections.abc import Mapping
from typing import Self

from pydantic import SecretStr

from security_anomaly.core.config import ConfigError
from security_anomaly.ingestion.errors import PseudonymKeyMissing

ENV_VAR = "PSEUDONYM_KEY"
MIN_KEY_LENGTH = 32
_PLACEHOLDER = "change-me"
_HEX_LENGTH = 32


class Pseudonymizer:
    """Deriva seudónimos e identificadores con HMAC-SHA256 y una clave secreta."""

    __slots__ = ("_key",)

    def __init__(self, key: SecretStr | str | None) -> None:
        if key is None:
            self._key: SecretStr | None = None
            return
        raw = key.get_secret_value() if isinstance(key, SecretStr) else key
        if len(raw) < MIN_KEY_LENGTH or _PLACEHOLDER in raw.lower():
            raise ConfigError(
                f"{ENV_VAR}: valor inválido (clave de menos de {MIN_KEY_LENGTH} caracteres "
                "o marcador de ejemplo del repositorio)"
            )
        self._key = SecretStr(raw)

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Lee ``PSEUDONYM_KEY``; vacía o ausente significa sin clave."""
        source = os.environ if environ is None else environ
        value = source.get(ENV_VAR)
        return cls(value.strip() if value is not None and value.strip() else None)

    @property
    def has_key(self) -> bool:
        return self._key is not None

    def derive_id(self, domain: str, *parts: str | int) -> str:
        """HMAC (32 caracteres hexadecimales) de ``parts`` bajo el dominio indicado."""
        if self._key is None:
            raise PseudonymKeyMissing
        message = "\x00".join([domain, *(str(part) for part in parts)]).encode("utf-8")
        digest = hmac.new(self._key.get_secret_value().encode("utf-8"), message, hashlib.sha256)
        return digest.hexdigest()[:_HEX_LENGTH]

    def pseudonym(self, username: str) -> str:
        """Seudónimo estable ``usr_`` + 32 hex; distingue mayúsculas y normaliza NFC y espacios."""
        normalized = unicodedata.normalize("NFC", username.strip())
        return "usr_" + self.derive_id("user", normalized)

    def __repr__(self) -> str:
        return f"Pseudonymizer(key={'<set>' if self._key is not None else '<unset>'})"

    __str__ = __repr__
