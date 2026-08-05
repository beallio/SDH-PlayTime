class AddGameChecksumDTO:
    game_id: str
    checksum: str
    algorithm: str
    chunk_size: int
    created_at: str | None
    updated_at: str | None

    __slots__ = (
        "game_id",
        "checksum",
        "algorithm",
        "chunk_size",
        "created_at",
        "updated_at",
    )

    def __init__(self, **kwargs):
        self.game_id = self._required_string(
            "game_id", kwargs.get("game_id"), '"game_id" can not be null'
        )
        self.checksum = self._required_string(
            "checksum", kwargs.get("checksum"), '"checksum" can not be null'
        )
        self.algorithm = self._required_string(
            "algorithm",
            kwargs.get("algorithm"),
            "\"algorithm\" must be: 'SHA224', 'SHA256', 'SHA384', 'SHA512', 'SHA3_224', 'SHA3_256', 'SHA3_384', 'SHA3_512'",
        )
        self.chunk_size = self._required_integer(
            "chunk_size",
            kwargs.get("chunk_size"),
            '"chunk_size" must be a valid integer',
        )
        self.created_at = self._optional_string("created_at", kwargs.get("created_at"))
        self.updated_at = self._optional_string("updated_at", kwargs.get("updated_at"))

    def _required_string(
        self, field_name: str, field_value: object, custom_message: str
    ) -> str:
        if not isinstance(field_value, str):
            raise ValueError(f'"{field_name}" {custom_message}')
        return field_value

    def _required_integer(
        self, field_name: str, field_value: object, custom_message: str
    ) -> int:
        if not isinstance(field_value, int):
            raise ValueError(f'"{field_name}" {custom_message}')
        return field_value

    def _optional_string(self, field_name: str, field_value: object) -> str | None:
        if field_value is not None and not isinstance(field_value, str):
            raise ValueError(f'"{field_name}" must be a string or null')
        return field_value

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, dict_obj):
        return cls(**dict_obj)
