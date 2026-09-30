from app.adapters.base import NormalizedRawEvent, SourceAdapter


class _StubAdapter(SourceAdapter):
    stub_name: str = "stub"

    def is_enabled(self) -> bool:
        return False

    async def fetch(self, source, since=None) -> list[NormalizedRawEvent]:
        raise NotImplementedError(
            f"{self.stub_name} adapter is not implemented yet (source={getattr(source, 'name', '?')})"
        )


class XAdapter(_StubAdapter):
    name = "x"
    stub_name = "XAdapter"


class DexScreenerAdapter(_StubAdapter):
    name = "dexscreener"
    stub_name = "DexScreenerAdapter"
