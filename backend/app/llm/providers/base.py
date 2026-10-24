from abc import ABC, abstractmethod


class BaseProvider(ABC):
    @abstractmethod
    async def complete_json(
        self,
        system: str,
        user: str,
        model: str,
        timeout: float,
    ) -> str:
        raise NotImplementedError
