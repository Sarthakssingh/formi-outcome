import httpx


class SimulatorClient:
    def __init__(self, base_url: str, timeout_seconds: int = 30):
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
        )

    def state(self) -> dict:
        response = self._client.get("/sim/state")
        response.raise_for_status()
        return response.json()

    def workflows(self) -> list[dict]:
        response = self._client.get("/workflows")
        response.raise_for_status()
        return response.json()

    def workflow(self, workflow_id: str) -> dict:
        response = self._client.get(f"/workflows/{workflow_id}")
        response.raise_for_status()
        return response.json()

    def workflow_config(self, workflow_id: str) -> dict:
        response = self._client.get(f"/workflows/{workflow_id}/config")
        response.raise_for_status()
        return response.json()

    def event_chunks(self, kind: str, after: int) -> list[dict]:
        response = self._client.get(
            "/events/chunks",
            params={"kind": kind, "after": after},
        )
        response.raise_for_status()
        return response.json()

    def event_chunk(self, chunk_number: int) -> str:
        response = self._client.get(f"/events/chunks/{chunk_number}")
        response.raise_for_status()
        return response.text

    def advance(self, minutes: int) -> dict:
        response = self._client.post(
            "/sim/advance",
            json={"minutes": minutes},
        )
        response.raise_for_status()
        return response.json()