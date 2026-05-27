from pydantic import BaseModel
from typing import Any, Optional


class HealthResponse(BaseModel):
    status: str
    version: str
    api_version: str


class StatusDetail(BaseModel):
    server: str
    plugins_active: int
    plugins_total: int
    config_loaded: bool
    uptime_seconds: float


class PluginInfo(BaseModel):
    name: str
    enabled: bool
    level: int
    port: int
    ics: bool
    path: str


class PluginListResponse(BaseModel):
    total: int
    enabled: int
    plugins: list[PluginInfo]


class ConfigResponse(BaseModel):
    path: str
    config: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]
    backup: bool = True


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class WSMessage(BaseModel):
    type: str
    data: dict[str, Any]
