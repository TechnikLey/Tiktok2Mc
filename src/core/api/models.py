from pydantic import BaseModel, Field
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


# ── Plugin models ────────────────────────────────────────────────────


class PluginRegistration(BaseModel):
    """Canonical plugin record stored and served by the API registry."""

    name: str = Field(min_length=1, description="Unique plugin name")
    path: str = Field("", description="Filesystem path to the executable")
    version: str = Field("1.0.0", description="Plugin version string")
    enabled: bool = Field(False, description="Whether the plugin is active")
    level: int = Field(2, ge=1, le=4, description="Visibility level")
    port: int = Field(0, ge=0, description="Web/overlay port, 0=none")
    ics: bool = Field(False, description="Interface Control System flag")
    description: str = Field("", description="Human-readable description")
    registered_at: Optional[float] = Field(
        None, description="Unix timestamp of first registration"
    )
    updated_at: Optional[float] = Field(
        None, description="Unix timestamp of last update"
    )


class PluginRegisterRequest(BaseModel):
    """Request body for ``POST /plugins/register``."""

    name: str = Field(min_length=1)
    path: str = ""
    version: str = "1.0.0"
    enabled: bool = False
    level: int = 2
    port: int = 0
    ics: bool = False
    description: str = ""


class PluginUpdateRequest(BaseModel):
    """Partial-update body for ``PUT /plugins/{name}``."""

    enabled: Optional[bool] = None
    level: Optional[int] = None
    port: Optional[int] = None
    ics: Optional[bool] = None
    path: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None


class PluginListResponse(BaseModel):
    total: int
    enabled: int
    plugins: list[PluginRegistration]


class PluginRegisterResponse(BaseModel):
    status: str
    plugin: PluginRegistration


class ImportLegacyResponse(BaseModel):
    status: str
    imported: int
    total: int


# ── Config models ────────────────────────────────────────────────────


class ConfigResponse(BaseModel):
    path: str
    config: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]
    backup: bool = True


# ── Shared ───────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class WSMessage(BaseModel):
    type: str
    data: dict[str, Any]
