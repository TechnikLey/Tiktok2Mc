"""Structured error code system for TikTok2Mc.

Every error in the application receives a stable, documented error code.
Codes are prefixed by subsystem and never collide.

Code Format
-----------
    {SUBSYSTEM}-{NNNN}

Subsystem prefixes:
    CORE       Core runtime / generic infrastructure
    PLUGIN     Plugin system
    GUI        Graphical user interface
    API        REST API / FastAPI
    NETWORK    Network / HTTP / WebSocket
    CONFIG     Configuration loading / validation
    OVERLAY    Overlay subsystem
    LIFECYCLE  Process lifecycle / supervisor
    MC         Minecraft server / RCON
    TIKTOK     TikTok Live connection / events
    HOOK       Hook system
    WATCHER    File / directory watchers
    WORKER     Background worker threads / tasks
    VALIDATE   Validation subsystem
    DIAG       Diagnostics / health
    SHUTDOWN   Shutdown procedures
    STARTUP    Startup procedures
    SECURITY   Authentication / sandbox
    BACKUP     Backup subsystem
    UPDATE     Update subsystem
    SANDBOX    Plugin sandbox
    HEARTBEAT  Heartbeat monitoring

Severity levels:
    0  DEBUG    - Diagnostic detail, no action needed
    1  INFO     - Normal operation, informational
    2  NOTICE   - Normal but significant condition
    3  WARNING  - Potential issue, should be reviewed
    4  ERROR    - Functionality impaired, action required
    5  CRITICAL - Severe failure, immediate attention needed
    6  FATAL    - Process will terminate
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(enum.IntEnum):
    DEBUG = 0
    INFO = 1
    NOTICE = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5
    FATAL = 6

    def label(self) -> str:
        return self.name

    @classmethod
    def from_string(cls, s: str) -> Severity:
        try:
            return cls[s.upper()]
        except KeyError:
            return cls.WARNING


class Subsystem(str, enum.Enum):
    CORE = "CORE"
    PLUGIN = "PLUGIN"
    GUI = "GUI"
    API = "API"
    NETWORK = "NETWORK"
    CONFIG = "CONFIG"
    OVERLAY = "OVERLAY"
    LIFECYCLE = "LIFECYCLE"
    MC = "MC"
    TIKTOK = "TIKTOK"
    HOOK = "HOOK"
    WATCHER = "WATCHER"
    WORKER = "WORKER"
    VALIDATE = "VALIDATE"
    DIAG = "DIAG"
    SHUTDOWN = "SHUTDOWN"
    STARTUP = "STARTUP"
    SECURITY = "SECURITY"
    BACKUP = "BACKUP"
    UPDATE = "UPDATE"
    SANDBOX = "SANDBOX"
    HEARTBEAT = "HEARTBEAT"

    @classmethod
    def from_string(cls, s: str) -> Subsystem:
        try:
            return cls[s.upper()]
        except KeyError:
            return cls.CORE


@dataclass
class ErrorCode:
    code: str
    subsystem: Subsystem
    severity: Severity
    message: str
    description: str = ""
    recovery_hint: str = ""
    impact: str = ""

    def format(self, detail: str = "", context: dict[str, Any] | None = None) -> str:
        parts = [self.code, self.message]
        if detail:
            parts.append("")
            parts.append(detail)
        if context:
            parts.append("")
            parts.append(f"Context: {context}")
        if self.recovery_hint:
            parts.append("")
            parts.append(f"Recovery: {self.recovery_hint}")
        return "\n".join(parts)

    def with_context(self, **ctx: Any) -> ErrorInstance:
        return ErrorInstance(
            code=self.code,
            subsystem=self.subsystem,
            severity=self.severity,
            message=self.message,
            description=self.description,
            recovery_hint=self.recovery_hint,
            impact=self.impact,
            context=ctx,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "subsystem": self.subsystem.value,
            "severity": self.severity.label(),
            "message": self.message,
            "description": self.description,
            "recovery_hint": self.recovery_hint,
            "impact": self.impact,
        }


@dataclass
class ErrorInstance:
    code: str
    subsystem: Subsystem
    severity: Severity
    message: str
    description: str = ""
    recovery_hint: str = ""
    impact: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    root_exception: BaseException | None = None
    timestamp: float = 0.0
    recovery_status: str = "none"

    def with_exception(self, exc: BaseException) -> ErrorInstance:
        self.root_exception = exc
        return self

    def format(self) -> str:
        parts = [
            self.code,
            self.message,
        ]
        if self.root_exception:
            parts.append(
                f"Reason: {type(self.root_exception).__name__}: {self.root_exception}"
            )
        if self.impact:
            parts.append(f"Impact: {self.impact}")
        if self.recovery_hint:
            parts.append(f"Recovery: {self.recovery_hint}")
        if self.context:
            parts.append(f"Context: {self.context}")
        return "\n".join(parts)


# ==============================================================================
# Error Code Registry — ALL error codes must be defined here
# ==============================================================================

# ------------------------------------------------------------------- CORE ----
CORE_0001 = ErrorCode(
    code="CORE-0001",
    subsystem=Subsystem.CORE,
    severity=Severity.FATAL,
    message="Unhandled exception in main thread.",
    description="An unexpected exception propagated to the top-level exception hook.",
    recovery_hint="Check crash report and stack trace. This is a bug that must be fixed.",
    impact="Application will terminate.",
)
CORE_0002 = ErrorCode(
    code="CORE-0002",
    subsystem=Subsystem.CORE,
    severity=Severity.CRITICAL,
    message="Unhandled exception in worker thread.",
    description="An unexpected exception propagated from a background thread.",
    recovery_hint="Check crash report and restart the component.",
    impact="The affected background worker has stopped.",
)
CORE_0003 = ErrorCode(
    code="CORE-0003",
    subsystem=Subsystem.CORE,
    severity=Severity.ERROR,
    message="Resource not found.",
    description="A required file, directory, or resource was not found.",
    recovery_hint="Verify the resource path and ensure it exists.",
    impact="Operation cannot proceed.",
)
CORE_0004 = ErrorCode(
    code="CORE-0004",
    subsystem=Subsystem.CORE,
    severity=Severity.WARNING,
    message="Operation timed out.",
    description="A blocking operation exceeded its time limit.",
    recovery_hint="Retry the operation. Consider increasing timeout if the condition persists.",
    impact="The operation was aborted.",
)
CORE_0005 = ErrorCode(
    code="CORE-0005",
    subsystem=Subsystem.CORE,
    severity=Severity.WARNING,
    message="Failed to clean up resource.",
    description="Cleanup of a resource during shutdown or error handling failed.",
    recovery_hint="Manual cleanup may be required.",
    impact="Resource may not have been released properly.",
)
CORE_0006 = ErrorCode(
    code="CORE-0006",
    subsystem=Subsystem.CORE,
    severity=Severity.WARNING,
    message="Event bus queue full, dropping event.",
    description="An EventBus subscriber queue reached capacity and an event was dropped.",
    recovery_hint="Increase subscriber queue size or reduce event publishing rate.",
    impact="Some subscribers may have missed events.",
)
CORE_0007 = ErrorCode(
    code="CORE-0007",
    subsystem=Subsystem.CORE,
    severity=Severity.CRITICAL,
    message="State machine invalid transition.",
    description="A component attempted an illegal state transition.",
    recovery_hint="Check the state machine logic. This indicates a programming error.",
    impact="The component may be in an inconsistent state.",
)
CORE_0008 = ErrorCode(
    code="CORE-0008",
    subsystem=Subsystem.CORE,
    severity=Severity.ERROR,
    message="Heartbeat timeout detected.",
    description="A monitored component failed to report a heartbeat within the expected interval.",
    recovery_hint="The component may be hung or crashed. Initiate recovery if possible.",
    impact="Component may be unresponsive.",
)
CORE_0009 = ErrorCode(
    code="CORE-0009",
    subsystem=Subsystem.CORE,
    severity=Severity.DEBUG,
    message="Component health state changed.",
    description="A subsystem changed health state.",
    recovery_hint="Monitor the component for further degradation.",
    impact="None if transition is expected.",
)

# ---------------------------------------------------------------- PLUGIN ----
PLUGIN_0001 = ErrorCode(
    code="PLUGIN-0001",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Failed to initialize plugin.",
    description="A plugin failed during its initialization phase.",
    recovery_hint="Check the plugin configuration and logs. Restart the plugin.",
    impact="Plugin will remain disabled.",
)
PLUGIN_0002 = ErrorCode(
    code="PLUGIN-0002",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin process crashed.",
    description="A plugin child process exited unexpectedly.",
    recovery_hint="Auto-restart is attempted. Check plugin logs for details.",
    impact="Plugin functionality is unavailable until restarted.",
)
PLUGIN_0003 = ErrorCode(
    code="PLUGIN-0003",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.WARNING,
    message="Plugin tick handler failed.",
    description="A plugin's on_tick() method raised an exception.",
    recovery_hint="Check the plugin code. The tick loop continues.",
    impact="The current tick was skipped.",
)
PLUGIN_0004 = ErrorCode(
    code="PLUGIN-0004",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.WARNING,
    message="Plugin command handler failed.",
    description="A plugin's command handler raised an exception.",
    recovery_hint="Check the plugin code and the command being processed.",
    impact="The command was not handled.",
)
PLUGIN_0005 = ErrorCode(
    code="PLUGIN-0005",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin directory not found.",
    description="The plugins directory does not exist or is inaccessible.",
    recovery_hint="Ensure the plugins directory exists and has correct permissions.",
    impact="No plugins can be loaded.",
)
PLUGIN_0006 = ErrorCode(
    code="PLUGIN-0006",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin manifest invalid.",
    description="A plugin.json file is missing, unreadable, or has invalid content.",
    recovery_hint="Verify the plugin manifest file and format.",
    impact="Plugin cannot be loaded.",
)
PLUGIN_0007 = ErrorCode(
    code="PLUGIN-0007",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.WARNING,
    message="Plugin disabled by configuration.",
    description="A plugin is present but disabled in the registry or config.",
    recovery_hint="Enable the plugin from the GUI or configuration.",
    impact="Plugin will not start.",
)
PLUGIN_0008 = ErrorCode(
    code="PLUGIN-0008",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.CRITICAL,
    message="Plugin sandbox violation detected.",
    description="A plugin exceeded its sandbox limits (memory, CPU, files, processes).",
    recovery_hint="Adjust sandbox limits or fix the plugin.",
    impact="Plugin may be terminated.",
)
PLUGIN_0009 = ErrorCode(
    code="PLUGIN-0009",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin executable not found.",
    description="The compiled plugin executable file does not exist at the expected path.",
    recovery_hint="Rebuild the plugin or check the registry entry.",
    impact="Plugin cannot start.",
)
PLUGIN_0010 = ErrorCode(
    code="PLUGIN-0010",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin discovery failed.",
    description="Plugin discovery process encountered an error.",
    recovery_hint="Check the plugins directory and registry.",
    impact="Some plugins may not be discovered.",
)
PLUGIN_0011 = ErrorCode(
    code="PLUGIN-0011",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.WARNING,
    message="Plugin health check failed.",
    description="A plugin's process died or became unresponsive.",
    recovery_hint="Auto-restart will be attempted if enabled.",
    impact="Plugin marked as failed in registry.",
)
PLUGIN_0012 = ErrorCode(
    code="PLUGIN-0012",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin failed to register overlay.",
    description="A plugin could not register its overlay HTML with the API.",
    recovery_hint="Check API connectivity and plugin configuration.",
    impact="Overlay may not display.",
)
PLUGIN_0013 = ErrorCode(
    code="PLUGIN-0013",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.WARNING,
    message="Plugin state push failed.",
    description="A plugin failed to push its state to the API.",
    recovery_hint="Check API connectivity.",
    impact="Dashboard may show stale state.",
)
PLUGIN_0014 = ErrorCode(
    code="PLUGIN-0014",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.WARNING,
    message="Plugin command fetch failed.",
    description="A plugin failed to fetch pending commands from the API.",
    recovery_hint="Check API connectivity. Command polling continues.",
    impact="Commands may be delayed.",
)
PLUGIN_0015 = ErrorCode(
    code="PLUGIN-0015",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.CRITICAL,
    message="Plugin heartbeat missing.",
    description="A plugin stopped sending heartbeat pings.",
    recovery_hint="Check if plugin process is alive. Restart recommended.",
    impact="Plugin may be hung or crashed.",
)
PLUGIN_0016 = ErrorCode(
    code="PLUGIN-0016",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin failed to stop gracefully.",
    description="A plugin did not stop within the expected timeout.",
    recovery_hint="Force stop may be required.",
    impact="Plugin may be in an inconsistent state.",
)
PLUGIN_0017 = ErrorCode(
    code="PLUGIN-0017",
    subsystem=Subsystem.PLUGIN,
    severity=Severity.ERROR,
    message="Plugin command queue full.",
    description="A plugin's command queue reached maximum capacity.",
    recovery_hint="Commands will be dropped until queue drains.",
    impact="Some commands to the plugin may be lost.",
)

# ------------------------------------------------------------------- GUI ----
GUI_0001 = ErrorCode(
    code="GUI-0001",
    subsystem=Subsystem.GUI,
    severity=Severity.FATAL,
    message="pywebview not installed — cannot open GUI window.",
    description="The pywebview library is required to display the GUI window.",
    recovery_hint="Install pywebview: pip install pywebview.",
    impact="GUI window cannot be displayed.",
)
GUI_0002 = ErrorCode(
    code="GUI-0002",
    subsystem=Subsystem.GUI,
    severity=Severity.WARNING,
    message="Multiple GUI instances detected.",
    description="An attempt was made to start a second GUI instance.",
    recovery_hint="Only one GUI instance is allowed.",
    impact="The new instance will exit.",
)
GUI_0003 = ErrorCode(
    code="GUI-0003",
    subsystem=Subsystem.GUI,
    severity=Severity.ERROR,
    message="Launcher HTML not found.",
    description="The launcher HTML file for the GUI splash screen is missing.",
    recovery_hint="Ensure the templates/gui/ directory is intact.",
    impact="Launcher page cannot be displayed.",
)
GUI_0004 = ErrorCode(
    code="GUI-0004",
    subsystem=Subsystem.GUI,
    severity=Severity.WARNING,
    message="Failed to destroy GUI window.",
    description="An error occurred while closing the pywebview window.",
    recovery_hint="Process may need to be force-terminated.",
    impact="None — process will exit anyway.",
)
GUI_0005 = ErrorCode(
    code="GUI-0005",
    subsystem=Subsystem.GUI,
    severity=Severity.WARNING,
    message="GUI file save failed.",
    description="The GUI could not save a file (e.g. log export).",
    recovery_hint="Check disk space and permissions.",
    impact="File was not saved.",
)

# ------------------------------------------------------------------- API ----
API_0001 = ErrorCode(
    code="API-0001",
    subsystem=Subsystem.API,
    severity=Severity.ERROR,
    message="API endpoint returned 500 Internal Server Error.",
    description="An unhandled exception occurred in an API route handler.",
    recovery_hint="Check API logs for the exception details.",
    impact="The request failed.",
)
API_0002 = ErrorCode(
    code="API-0002",
    subsystem=Subsystem.API,
    severity=Severity.WARNING,
    message="API endpoint returned 404 Not Found.",
    description="An API route was requested but does not exist.",
    recovery_hint="Verify the URL path.",
    impact="Resource not found.",
)
API_0003 = ErrorCode(
    code="API-0003",
    subsystem=Subsystem.API,
    severity=Severity.ERROR,
    message="API server failed to start.",
    description="The FastAPI/uvicorn server could not bind to the configured address.",
    recovery_hint="Check if the port is already in use. Ensure permissions are correct.",
    impact="API server is unavailable.",
)
API_0004 = ErrorCode(
    code="API-0004",
    subsystem=Subsystem.API,
    severity=Severity.WARNING,
    message="API server task cancelled.",
    description="The API server asyncio task was cancelled unexpectedly.",
    recovery_hint="Restart the API server.",
    impact="API endpoints are unavailable.",
)
API_0005 = ErrorCode(
    code="API-0005",
    subsystem=Subsystem.API,
    severity=Severity.WARNING,
    message="API server not reachable.",
    description="Health check poll failed to reach the API server.",
    recovery_hint="Verify the API server process is running.",
    impact="Dependent components may not function.",
)
API_0006 = ErrorCode(
    code="API-0006",
    subsystem=Subsystem.API,
    severity=Severity.WARNING,
    message="WebSocket connection error.",
    description="A WebSocket connection encountered an error or disconnected unexpectedly.",
    recovery_hint="Reconnect will be attempted automatically.",
    impact="Real-time updates may be delayed.",
)
API_0007 = ErrorCode(
    code="API-0007",
    subsystem=Subsystem.API,
    severity=Severity.ERROR,
    message="Dashboard publisher SSE connection failed.",
    description="The dashboard publisher could not send an SSE event to a client.",
    recovery_hint="Client should reconnect automatically.",
    impact="Dashboard client may miss updates.",
)
API_0008 = ErrorCode(
    code="API-0008",
    subsystem=Subsystem.API,
    severity=Severity.WARNING,
    message="Event publication failed.",
    description="An attempt to publish an event to the EventBus failed.",
    recovery_hint="This may be transient. Retry the operation.",
    impact="Event was lost.",
)

# --------------------------------------------------------------- NETWORK ----
NETWORK_0001 = ErrorCode(
    code="NETWORK-0001",
    subsystem=Subsystem.NETWORK,
    severity=Severity.ERROR,
    message="HTTP request failed.",
    description="An HTTP request to an external or internal service failed.",
    recovery_hint="Check network connectivity and service availability.",
    impact="Operation failed.",
)
NETWORK_0002 = ErrorCode(
    code="NETWORK-0002",
    subsystem=Subsystem.NETWORK,
    severity=Severity.WARNING,
    message="Webhook request failed.",
    description="A webhook POST request failed (e.g. MinecraftServerAPI webhook).",
    recovery_hint="Check that the webhook target is running and reachable.",
    impact="Webhook event was not delivered.",
)
NETWORK_0003 = ErrorCode(
    code="NETWORK-0003",
    subsystem=Subsystem.NETWORK,
    severity=Severity.WARNING,
    message="Comment handler HTTP dispatch failed.",
    description="Dispatching a comment command via HTTP failed.",
    recovery_hint="Check the target URL and network connectivity.",
    impact="Comment command was not dispatched.",
)

# --------------------------------------------------------------- CONFIG ----
CONFIG_0001 = ErrorCode(
    code="CONFIG-0001",
    subsystem=Subsystem.CONFIG,
    severity=Severity.FATAL,
    message="Configuration file not found.",
    description="The main config.yaml file does not exist at the expected path.",
    recovery_hint="Ensure config.yaml exists in the config/ directory.",
    impact="Application cannot start without configuration.",
)
CONFIG_0002 = ErrorCode(
    code="CONFIG-0002",
    subsystem=Subsystem.CONFIG,
    severity=Severity.ERROR,
    message="Configuration file has invalid YAML syntax.",
    description="The config file could not be parsed as valid YAML.",
    recovery_hint="Check the config file for YAML syntax errors.",
    impact="Configuration cannot be loaded.",
)
CONFIG_0003 = ErrorCode(
    code="CONFIG-0003",
    subsystem=Subsystem.CONFIG,
    severity=Severity.WARNING,
    message="Configuration key missing, using default.",
    description="A required configuration key was not found and a default value was used.",
    recovery_hint="Add the key to the configuration file to customize its value.",
    impact="Default value applied.",
)
CONFIG_0004 = ErrorCode(
    code="CONFIG-0004",
    subsystem=Subsystem.CONFIG,
    severity=Severity.WARNING,
    message="Configuration validation warning.",
    description="A configuration value did not pass validation.",
    recovery_hint="Check the config.yaml file for invalid values.",
    impact="May cause unexpected behavior.",
)
CONFIG_0005 = ErrorCode(
    code="CONFIG-0005",
    subsystem=Subsystem.CONFIG,
    severity=Severity.WARNING,
    message="Runtime configuration reload failed.",
    description="An attempt to reload configuration at runtime failed.",
    recovery_hint="Check config file syntax. Previous configuration remains active.",
    impact="Configuration changes were not applied.",
)
CONFIG_0006 = ErrorCode(
    code="CONFIG-0006",
    subsystem=Subsystem.CONFIG,
    severity=Severity.ERROR,
    message="Duplicate command keys detected in config.",
    description="Duplicate keys were found in commands_config sections.",
    recovery_hint="Remove duplicate entries from the configuration.",
    impact="Application may not start.",
)
CONFIG_0007 = ErrorCode(
    code="CONFIG-0007",
    subsystem=Subsystem.CONFIG,
    severity=Severity.ERROR,
    message="Comment command prefix collision.",
    description="Multiple command groups use the same prefix.",
    recovery_hint="Ensure each comment command group has a unique prefix.",
    impact="Only the first group with the prefix will be active.",
)
CONFIG_0008 = ErrorCode(
    code="CONFIG-0008",
    subsystem=Subsystem.CONFIG,
    severity=Severity.WARNING,
    message="Plugin configuration missing or invalid.",
    description="A plugin's config.yaml could not be loaded.",
    recovery_hint="Check the plugin configuration file.",
    impact="Plugin defaults will be used.",
)

# -------------------------------------------------------------- OVERLAY ----
OVERLAY_0001 = ErrorCode(
    code="OVERLAY-0001",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.ERROR,
    message="Overlay not found.",
    description="The specified overlay name does not exist.",
    recovery_hint="Check the overlay configuration for available overlays.",
    impact="Overlay message not displayed.",
)
OVERLAY_0002 = ErrorCode(
    code="OVERLAY-0002",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.WARNING,
    message="Overlay circuit breaker active.",
    description="An overlay is in cooldown due to repeated failures.",
    recovery_hint="Wait for the cooldown period to expire.",
    impact="Overlay messages are being suppressed.",
)
OVERLAY_0003 = ErrorCode(
    code="OVERLAY-0003",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.WARNING,
    message="Overlay dispatch failed.",
    description="Publishing overlay text to the event bus failed.",
    recovery_hint="Check event bus connectivity.",
    impact="Overlay message not shown.",
)
OVERLAY_0004 = ErrorCode(
    code="OVERLAY-0004",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.ERROR,
    message="Overlay config file failed to load.",
    description="The global config file could not be loaded for overlay settings.",
    recovery_hint="Check config.yaml exists and is valid.",
    impact="Overlay defaults will be used.",
)
OVERLAY_0005 = ErrorCode(
    code="OVERLAY-0005",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.WARNING,
    message="Overlay SSE stream error.",
    description="A client's overlay SSE stream encountered an error.",
    recovery_hint="Client should reconnect.",
    impact="Real-time overlay updates may be interrupted.",
)
OVERLAY_0006 = ErrorCode(
    code="OVERLAY-0006",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.ERROR,
    message="Overlay HTML rendering failed.",
    description="The overlay HTML template could not be rendered.",
    recovery_hint="Check overlay template and theme configuration.",
    impact="Overlay page may not display correctly.",
)
OVERLAY_0007 = ErrorCode(
    code="OVERLAY-0007",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.WARNING,
    message="Overlay config section missing.",
    description="No 'overlay' section found in the global config.",
    recovery_hint="Add an overlay section to config.yaml or use defaults.",
    impact="Default overlay settings will be used.",
)
OVERLAY_0008 = ErrorCode(
    code="OVERLAY-0008",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.WARNING,
    message="Overlay registered without HTML.",
    description="A plugin registered an overlay with empty or invalid HTML.",
    recovery_hint="Check the plugin's get_overlay_html() implementation.",
    impact="Overlay may display incorrectly.",
)
OVERLAY_0009 = ErrorCode(
    code="OVERLAY-0009",
    subsystem=Subsystem.OVERLAY,
    severity=Severity.ERROR,
    message="Overlay overlay_name mismatch.",
    description="A plugin overlay was dispatched to a non-matching named overlay.",
    recovery_hint="Ensure overlay names are consistent between plugin and config.",
    impact="Message may appear on the wrong overlay target.",
)

# ------------------------------------------------------------- LIFECYCLE ----
LIFECYCLE_0001 = ErrorCode(
    code="LIFECYCLE-0001",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.FATAL,
    message="Failed to load configuration at startup.",
    description="The supervisor could not load the configuration file.",
    recovery_hint="Fix the config.yaml file.",
    impact="Application cannot start.",
)
LIFECYCLE_0002 = ErrorCode(
    code="LIFECYCLE-0002",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.ERROR,
    message="Process failed to start.",
    description="A managed child process exited immediately or could not be spawned.",
    recovery_hint="Check the process executable path and requirements.",
    impact="Process is not running.",
)
LIFECYCLE_0003 = ErrorCode(
    code="LIFECYCLE-0003",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.WARNING,
    message="Process readiness check failed.",
    description="A managed process passed its startup but failed the readiness check.",
    recovery_hint="Check logs from the child process for startup errors.",
    impact="Process may not be fully functional.",
)
LIFECYCLE_0004 = ErrorCode(
    code="LIFECYCLE-0004",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.ERROR,
    message="Process failed to stop gracefully.",
    description="A managed process did not respond to graceful shutdown signals.",
    recovery_hint="Force kill was used. Check why the process did not exit.",
    impact="Process was terminated forcefully.",
)
LIFECYCLE_0005 = ErrorCode(
    code="LIFECYCLE-0005",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.WARNING,
    message="API server stop incomplete.",
    description="The API server task did not cancel within the timeout.",
    recovery_hint="Increase the timeout or investigate stuck connections.",
    impact="API port may not be released immediately.",
)
LIFECYCLE_0006 = ErrorCode(
    code="LIFECYCLE-0006",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.WARNING,
    message="Port still in use after process stop.",
    description="A port was not freed within the expected time after process shutdown.",
    recovery_hint="Check for lingering processes.",
    impact="Next bind may fail.",
)
LIFECYCLE_0007 = ErrorCode(
    code="LIFECYCLE-0007",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.ERROR,
    message="Plugin process died unexpectedly.",
    description="A plugin subprocess exited without being stopped by the supervisor.",
    recovery_hint="Auto-restart is attempted if configured.",
    impact="Plugin functionality temporarily unavailable.",
)
LIFECYCLE_0008 = ErrorCode(
    code="LIFECYCLE-0008",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.WARNING,
    message="Shutdown countdown cancelled.",
    description="An active shutdown countdown was cancelled by the user.",
    recovery_hint="No action needed.",
    impact="System continues running.",
)
LIFECYCLE_0009 = ErrorCode(
    code="LIFECYCLE-0009",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.CRITICAL,
    message="Illegal state transition attempted.",
    description="A lifecycle command was issued in an invalid supervisor state.",
    recovery_hint="Wait for the current operation to complete.",
    impact="Command was rejected.",
)
LIFECYCLE_0010 = ErrorCode(
    code="LIFECYCLE-0010",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.ERROR,
    message="File watcher runtime error.",
    description="The signal file watcher encountered an unexpected error.",
    recovery_hint="Check the watcher logs for details.",
    impact="Signal detection may be delayed.",
)
LIFECYCLE_0011 = ErrorCode(
    code="LIFECYCLE-0011",
    subsystem=Subsystem.LIFECYCLE,
    severity=Severity.WARNING,
    message="Plugin auto-restart signal failed.",
    description="Writing the restart signal file for a dead plugin failed.",
    recovery_hint="Check runtime directory permissions.",
    impact="Plugin may not auto-restart.",
)

# ------------------------------------------------------------------- MC ----
MC_0001 = ErrorCode(
    code="MC-0001",
    subsystem=Subsystem.MC,
    severity=Severity.ERROR,
    message="Minecraft server JAR not found.",
    description="The server.jar file is missing from the instance directory.",
    recovery_hint="Place a valid server.jar in the instance directory.",
    impact="Minecraft server cannot start.",
)
MC_0002 = ErrorCode(
    code="MC-0002",
    subsystem=Subsystem.MC,
    severity=Severity.FATAL,
    message="Java runtime not available.",
    description="No suitable Java runtime (17+) was found.",
    recovery_hint="Install Java 17 or later, or ensure bundled Java is available.",
    impact="Minecraft server cannot start.",
)
MC_0003 = ErrorCode(
    code="MC-0003",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="Minecraft server exited with non-zero code.",
    description="The Minecraft server process exited with an error code.",
    recovery_hint="Check server logs for crash details.",
    impact="Server is stopped.",
)
MC_0004 = ErrorCode(
    code="MC-0004",
    subsystem=Subsystem.MC,
    severity=Severity.ERROR,
    message="RCON connection failed.",
    description="The RCON client could not connect to the Minecraft server.",
    recovery_hint="Ensure RCON is enabled in server.properties and the password is correct.",
    impact="Commands will not be sent to the server.",
)
MC_0005 = ErrorCode(
    code="MC-0005",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="RCON command failed.",
    description="An RCON command execution returned an error.",
    recovery_hint="Check the command syntax and server state.",
    impact="Command may not have executed.",
)
MC_0006 = ErrorCode(
    code="MC-0006",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="RCON command dropped after retries.",
    description="An RCON command failed multiple times and was dropped.",
    recovery_hint="Check RCON connectivity and server state.",
    impact="Command was not executed.",
)
MC_0007 = ErrorCode(
    code="MC-0007",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="RCON queue full.",
    description="The RCON command queue reached capacity and a command was dropped.",
    recovery_hint="Reduce command rate or increase queue size.",
    impact="Command was lost.",
)
MC_0008 = ErrorCode(
    code="MC-0008",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="RCON password not set.",
    description="RCON is enabled but no password is configured.",
    recovery_hint="Set an RCON password in config.yaml.",
    impact="RCON will be disabled.",
)
MC_0009 = ErrorCode(
    code="MC-0009",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="MinecraftServerAPI plugin disabled.",
    description="The MinecraftServerAPI plugin is enabled in config but could not be activated.",
    recovery_hint="Check plugins directory and file permissions.",
    impact="Webhook integration may not work.",
)
MC_0010 = ErrorCode(
    code="MC-0010",
    subsystem=Subsystem.MC,
    severity=Severity.WARNING,
    message="MinecraftServerAPI config failed to write.",
    description="Writing the default MinecraftServerAPI config file failed.",
    recovery_hint="Check file permissions.",
    impact="Defaults may not be applied.",
)
MC_0011 = ErrorCode(
    code="MC-0011",
    subsystem=Subsystem.MC,
    severity=Severity.ERROR,
    message="Minecraft server properties update failed.",
    description="Writing server.properties failed.",
    recovery_hint="Check file permissions.",
    impact="Server settings may not be applied.",
)

# --------------------------------------------------------------- TIKTOK ----
TIKTOK_0001 = ErrorCode(
    code="TIKTOK-0001",
    subsystem=Subsystem.TIKTOK,
    severity=Severity.ERROR,
    message="TikTok Live connection failed.",
    description="The TikTok Live client could not connect to the stream.",
    recovery_hint="Check the username and TikTok Live availability. Auto-reconnect will attempt.",
    impact="TikTok events are not received.",
)
TIKTOK_0002 = ErrorCode(
    code="TIKTOK-0002",
    subsystem=Subsystem.TIKTOK,
    severity=Severity.WARNING,
    message="TikTok Live disconnected.",
    description="The TikTok Live client disconnected from the stream.",
    recovery_hint="Auto-reconnect is active. Check network stability.",
    impact="Events are temporarily not received.",
)
TIKTOK_0003 = ErrorCode(
    code="TIKTOK-0003",
    subsystem=Subsystem.TIKTOK,
    severity=Severity.WARNING,
    message="TikTok event handler failed.",
    description="Handling a TikTok event (gift, follow, like, etc.) raised an exception.",
    recovery_hint="Check the event handler implementation.",
    impact="Event was not processed.",
)
TIKTOK_0004 = ErrorCode(
    code="TIKTOK-0004",
    subsystem=Subsystem.TIKTOK,
    severity=Severity.WARNING,
    message="TikTok event publishing failed.",
    description="Publishing a TikTok event to the EventBus failed.",
    recovery_hint="Check the event bus health.",
    impact="Plugins may not receive the event.",
)
TIKTOK_0005 = ErrorCode(
    code="TIKTOK-0005",
    subsystem=Subsystem.TIKTOK,
    severity=Severity.ERROR,
    message="TikTok bridge worker crashed.",
    description="A background worker (trigger, RCON, event bridge) crashed.",
    recovery_hint="Restart the bridge process.",
    impact="Event processing stopped.",
)

# ------------------------------------------------------------------ HOOK ----
HOOK_0001 = ErrorCode(
    code="HOOK-0001",
    subsystem=Subsystem.HOOK,
    severity=Severity.ERROR,
    message="Hook manifest missing or invalid.",
    description="The hook.json file for a hook is missing, unreadable, or invalid.",
    recovery_hint="Check the hook manifest file.",
    impact="Hook cannot be loaded.",
)
HOOK_0002 = ErrorCode(
    code="HOOK-0002",
    subsystem=Subsystem.HOOK,
    severity=Severity.ERROR,
    message="Hook main.py not found.",
    description="A hook directory does not contain a main.py entry point.",
    recovery_hint="Ensure the hook has a main.py file.",
    impact="Hook cannot be loaded.",
)
HOOK_0003 = ErrorCode(
    code="HOOK-0003",
    subsystem=Subsystem.HOOK,
    severity=Severity.ERROR,
    message="Hook imports disallowed module.",
    description="A hook attempted to import a module not in the allowed list.",
    recovery_hint="Remove the disallowed import from the hook code.",
    impact="Hook is skipped.",
)
HOOK_0004 = ErrorCode(
    code="HOOK-0004",
    subsystem=Subsystem.HOOK,
    severity=Severity.WARNING,
    message="Hook failed to load.",
    description="A hook's main.py raised an exception during loading.",
    recovery_hint="Check the hook code for syntax or runtime errors.",
    impact="Hook is not available.",
)
HOOK_0005 = ErrorCode(
    code="HOOK-0005",
    subsystem=Subsystem.HOOK,
    severity=Severity.WARNING,
    message="Hook registration failed.",
    description="A hook's register() function raised an exception.",
    recovery_hint="Check the register() implementation in the hook.",
    impact="Hook is not loaded.",
)
HOOK_0006 = ErrorCode(
    code="HOOK-0006",
    subsystem=Subsystem.HOOK,
    severity=Severity.ERROR,
    message="Hook script action failed.",
    description="A hook script action raised an exception during execution.",
    recovery_hint="Check the hook action implementation.",
    impact="Action was not completed.",
)
HOOK_0007 = ErrorCode(
    code="HOOK-0007",
    subsystem=Subsystem.HOOK,
    severity=Severity.ERROR,
    message="Hook has no register() function.",
    description="A hook's main.py does not define a register() function.",
    recovery_hint="Add a register(api) function to the hook.",
    impact="Hook is skipped.",
)

# -------------------------------------------------------------- WATCHER ----
WATCHER_0001 = ErrorCode(
    code="WATCHER-0001",
    subsystem=Subsystem.WATCHER,
    severity=Severity.WARNING,
    message="Plugin watcher sync error.",
    description="The plugin directory watcher encountered an error during sync.",
    recovery_hint="This will be retried on the next poll cycle.",
    impact="Plugin state may be out of date.",
)
WATCHER_0002 = ErrorCode(
    code="WATCHER-0002",
    subsystem=Subsystem.WATCHER,
    severity=Severity.WARNING,
    message="Plugin watcher auto-register failed.",
    description="The watcher could not auto-register a newly discovered plugin.",
    recovery_hint="Check the plugin's manifest file.",
    impact="New plugin may not appear in registry.",
)
WATCHER_0003 = ErrorCode(
    code="WATCHER-0003",
    subsystem=Subsystem.WATCHER,
    severity=Severity.WARNING,
    message="Plugin watcher directory not found.",
    description="The plugins directory to watch does not exist.",
    recovery_hint="Ensure the plugins directory exists.",
    impact="Watcher will be inactive.",
)
WATCHER_0004 = ErrorCode(
    code="WATCHER-0004",
    subsystem=Subsystem.WATCHER,
    severity=Severity.WARNING,
    message="Signal file watcher file error.",
    description="An error occurred while reading or removing a signal file.",
    recovery_hint="Check runtime directory permissions.",
    impact="Signal may not be processed.",
)

# --------------------------------------------------------------- WORKER ----
WORKER_0001 = ErrorCode(
    code="WORKER-0001",
    subsystem=Subsystem.WORKER,
    severity=Severity.WARNING,
    message="Trigger worker processing error.",
    description="The trigger queue worker encountered an error processing an event.",
    recovery_hint="Check the trigger configuration.",
    impact="The specific event was not processed.",
)
WORKER_0002 = ErrorCode(
    code="WORKER-0002",
    subsystem=Subsystem.WORKER,
    severity=Severity.ERROR,
    message="Trigger queue loop crashed.",
    description="The trigger worker while-loop raised an unexpected exception.",
    recovery_hint="Worker will be restarted automatically.",
    impact="Event processing is temporarily interrupted.",
)
WORKER_0003 = ErrorCode(
    code="WORKER-0003",
    subsystem=Subsystem.WORKER,
    severity=Severity.WARNING,
    message="Datapack generation failed.",
    description="Building the Minecraft datapack files encountered an error.",
    recovery_hint="Check actions.mca and configuration.",
    impact="Datapack was not updated.",
)
WORKER_0004 = ErrorCode(
    code="WORKER-0004",
    subsystem=Subsystem.WORKER,
    severity=Severity.WARNING,
    message="Shell command execution failed.",
    description="A shell action command exited with a non-zero code.",
    recovery_hint="Check the shell command syntax.",
    impact="Shell command may not have completed.",
)
WORKER_0005 = ErrorCode(
    code="WORKER-0005",
    subsystem=Subsystem.WORKER,
    severity=Severity.WARNING,
    message="Follow tracking file write failed.",
    description="Writing the followed_users.txt file failed.",
    recovery_hint="Check file permissions.",
    impact="Follow tracking may lose data.",
)

# ------------------------------------------------------------- SHUTDOWN ----
SHUTDOWN_0001 = ErrorCode(
    code="SHUTDOWN-0001",
    subsystem=Subsystem.SHUTDOWN,
    severity=Severity.CRITICAL,
    message="Failed to stop all processes during shutdown.",
    description="The supervisor could not stop all managed processes.",
    recovery_hint="Manual process termination may be required.",
    impact="Some child processes may still be running.",
)
SHUTDOWN_0002 = ErrorCode(
    code="SHUTDOWN-0002",
    subsystem=Subsystem.SHUTDOWN,
    severity=Severity.ERROR,
    message="Shutdown signal write failed.",
    description="Writing the shutdown status file failed.",
    recovery_hint="Check runtime directory permissions.",
    impact="Shutdown progress is not visible.",
)
SHUTDOWN_0003 = ErrorCode(
    code="SHUTDOWN-0003",
    subsystem=Subsystem.SHUTDOWN,
    severity=Severity.WARNING,
    message="Shutdown request rejected (already pending).",
    description="A second shutdown was requested while one was already pending or running.",
    recovery_hint="No action needed — the first request is being processed.",
    impact="The second request is ignored.",
)
SHUTDOWN_0004 = ErrorCode(
    code="SHUTDOWN-0004",
    subsystem=Subsystem.SHUTDOWN,
    severity=Severity.ERROR,
    message="Unclean shutdown detected at startup.",
    description="The previous run did not exit cleanly. The shutdown state file indicates an incomplete shutdown.",
    recovery_hint="Check logs for the previous shutdown ID. The application restarts normally.",
    impact="Previous shutdown was not clean; child processes may have been orphaned.",
)
SHUTDOWN_0005 = ErrorCode(
    code="SHUTDOWN-0005",
    subsystem=Subsystem.SHUTDOWN,
    severity=Severity.CRITICAL,
    message="Exception during shutdown cleanup.",
    description="An exception occurred while the shutdown controller was performing cleanup.",
    recovery_hint="Review the exception details. Manual cleanup may be needed.",
    impact="Shutdown may be incomplete.",
)

# ------------------------------------------------------------- STARTUP ----
STARTUP_0001 = ErrorCode(
    code="STARTUP-0001",
    subsystem=Subsystem.STARTUP,
    severity=Severity.FATAL,
    message="Startup validation failed.",
    description="One or more startup validation checks failed.",
    recovery_hint="Review the validation errors above.",
    impact="Application cannot start.",
)
STARTUP_0002 = ErrorCode(
    code="STARTUP-0002",
    subsystem=Subsystem.STARTUP,
    severity=Severity.WARNING,
    message="Port scan conflict detected.",
    description="One or more required ports are already in use.",
    recovery_hint="Configure auto_resolve or free the required ports.",
    impact="Application may not function correctly.",
)
STARTUP_0003 = ErrorCode(
    code="STARTUP-0003",
    subsystem=Subsystem.STARTUP,
    severity=Severity.ERROR,
    message="Required port not free and auto-resolve disabled.",
    description="A required port is in use and auto-resolution is disabled.",
    recovery_hint="Free the port or enable auto_resolve in config.",
    impact="Application cannot start.",
)

# ------------------------------------------------------------- VALIDATE ----
VALIDATE_0001 = ErrorCode(
    code="VALIDATE-0001",
    subsystem=Subsystem.VALIDATE,
    severity=Severity.WARNING,
    message="Configuration validation issue.",
    description="A configuration value does not meet validation criteria.",
    recovery_hint="Review the validation message and fix the configuration.",
    impact="May cause runtime issues.",
)

# ---------------------------------------------------------------- DIAG ----
DIAG_0001 = ErrorCode(
    code="DIAG-0001",
    subsystem=Subsystem.DIAG,
    severity=Severity.WARNING,
    message="Diagnostics collection failed.",
    description="An error occurred while collecting diagnostics data.",
    recovery_hint="This may indicate a deeper issue.",
    impact="Diagnostics report may be incomplete.",
)
DIAG_0002 = ErrorCode(
    code="DIAG-0002",
    subsystem=Subsystem.DIAG,
    severity=Severity.DEBUG,
    message="Diagnostics report generated.",
    description="A runtime diagnostics report was generated.",
    recovery_hint="No action needed.",
    impact="None.",
)

# -------------------------------------------------------------- SANDBOX ----
SANDBOX_0001 = ErrorCode(
    code="SANDBOX-0001",
    subsystem=Subsystem.SANDBOX,
    severity=Severity.WARNING,
    message="Plugin sandbox resource limit hit.",
    description="A plugin hit a sandbox limit (memory, CPU, files, or processes).",
    recovery_hint="Increase sandbox limits or optimize the plugin.",
    impact="Plugin may be restricted or terminated.",
)

# ------------------------------------------------------------- SECURITY ----
SECURITY_0001 = ErrorCode(
    code="SECURITY-0001",
    subsystem=Subsystem.SECURITY,
    severity=Severity.WARNING,
    message="API authentication failed.",
    description="An API request failed authentication.",
    recovery_hint="Check the API key.",
    impact="Request was rejected.",
)
SECURITY_0002 = ErrorCode(
    code="SECURITY-0002",
    subsystem=Subsystem.SECURITY,
    severity=Severity.WARNING,
    message="Secure storage operation failed.",
    description="An encrypted storage operation failed.",
    recovery_hint="Check the encryption key and storage file.",
    impact="Data may not be accessible.",
)

# --------------------------------------------------------------- BACKUP ----
BACKUP_0001 = ErrorCode(
    code="BACKUP-0001",
    subsystem=Subsystem.BACKUP,
    severity=Severity.WARNING,
    message="Backup creation failed.",
    description="Creating a backup of a file or directory failed.",
    recovery_hint="Check disk space and permissions.",
    impact="Backup was not created.",
)
BACKUP_0002 = ErrorCode(
    code="BACKUP-0002",
    subsystem=Subsystem.BACKUP,
    severity=Severity.WARNING,
    message="Backup restoration failed.",
    description="Restoring from a backup failed.",
    recovery_hint="Check backup file integrity.",
    impact="Data was not restored.",
)

# --------------------------------------------------------------- UPDATE ----
UPDATE_0001 = ErrorCode(
    code="UPDATE-0001",
    subsystem=Subsystem.UPDATE,
    severity=Severity.WARNING,
    message="Update check failed.",
    description="Checking for updates failed due to a network or parsing error.",
    recovery_hint="Check network connectivity.",
    impact="Update information may not be available.",
)
UPDATE_0002 = ErrorCode(
    code="UPDATE-0002",
    subsystem=Subsystem.UPDATE,
    severity=Severity.ERROR,
    message="Update download failed.",
    description="Downloading an update failed.",
    recovery_hint="Check network connectivity and disk space.",
    impact="Update could not be installed.",
)
UPDATE_0003 = ErrorCode(
    code="UPDATE-0003",
    subsystem=Subsystem.UPDATE,
    severity=Severity.WARNING,
    message="Updater process returned unexpected exit code.",
    description="The updater subprocess exited with an unexpected code.",
    recovery_hint="Check updater logs for details.",
    impact="Update may not have been applied.",
)

# ------------------------------------------------------------ HEARTBEAT ----
HEARTBEAT_0001 = ErrorCode(
    code="HEARTBEAT-0001",
    subsystem=Subsystem.HEARTBEAT,
    severity=Severity.WARNING,
    message="Heartbeat subsystem check failed.",
    description="A subsystem health check within a heartbeat returned a failure status.",
    recovery_hint="Check the subsystem status for details.",
    impact="Component may be degraded.",
)
HEARTBEAT_0002 = ErrorCode(
    code="HEARTBEAT-0002",
    subsystem=Subsystem.HEARTBEAT,
    severity=Severity.DEBUG,
    message="Heartbeat alive signal.",
    description="Periodic heartbeat indicating the process is alive.",
    recovery_hint="No action needed.",
    impact="None.",
)

# ==============================================================================
# Lookup helpers
# ==============================================================================

_CODE_MAP: dict[str, ErrorCode] = {}


def _build_map() -> None:
    for _obj in globals().values():
        if isinstance(_obj, ErrorCode):
            _CODE_MAP[_obj.code] = _obj


_build_map()


def get_error_code(code: str) -> ErrorCode | None:
    """Look up an error code by its string identifier, e.g. ``CORE-0001``."""
    return _CODE_MAP.get(code)


def list_all_codes() -> list[ErrorCode]:
    """Return all registered error codes sorted by code."""
    return [_CODE_MAP[k] for k in sorted(_CODE_MAP.keys())]
