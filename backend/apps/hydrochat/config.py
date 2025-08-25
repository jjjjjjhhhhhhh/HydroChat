from __future__ import annotations
from dataclasses import dataclass, asdict
import os
from typing import Any, Dict

@dataclass(frozen=True)
class HydroConfig:
    base_url: str
    auth_token: str | None = None
    timeout_s: float = 10.0

    def snapshot(self) -> Dict[str, Any]:
        data = asdict(self)
        if data.get('auth_token'):
            token = data['auth_token']
            data['auth_token'] = f"{token[:4]}***" if len(token) >= 4 else '***'
        return data

def load_config() -> HydroConfig:
    base_url = os.getenv('HYDRO_BASE_URL') or os.getenv('BASE_URL') or 'http://localhost:8000'
    auth = os.getenv('HYDRO_AUTH_TOKEN') or os.getenv('AUTH_TOKEN')
    timeout = float(os.getenv('HYDRO_TIMEOUT_S', '10.0'))
    return HydroConfig(base_url=base_url.rstrip('/'), auth_token=auth, timeout_s=timeout)

__all__ = ['HydroConfig', 'load_config']
