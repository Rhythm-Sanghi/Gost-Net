"""
Ghost Net - Android Permissions Module
Runtime permission request and checking for Android API 33+ compliance.
Implements permission group management, request dialogs, and graceful
fallback for denied permissions.

Permissions Required:
- NEARBY_WIFI_DEVICES (API 33+): Wi-Fi Direct peer discovery
- BLUETOOTH_SCAN (API 31+): Bluetooth device discovery
- BLUETOOTH_CONNECT (API 31+): Bluetooth connections
- ACCESS_FINE_LOCATION: Precise location for Wi-Fi Direct
- ACCESS_COARSE_LOCATION: Network-based location
- CHANGE_WIFI_STATE: Wi-Fi Direct control
- ACCESS_WIFI_STATE: Wi-Fi state monitoring
- BLUETOOTH: Classic Bluetooth (API 30 and earlier)
- BLUETOOTH_ADMIN: Bluetooth device pairing
"""

import logging
from typing import List, Optional, Callable, Dict
from enum import Enum
from dataclasses import dataclass
import sys

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Conditional pyjnius imports
try:
    from jnius import autoclass, PythonJavaClass, java_method
    PYJNIUS_AVAILABLE = True
except ImportError:
    PYJNIUS_AVAILABLE = False
    autoclass = None
    class PythonJavaClass:
        pass
    def java_method(signature):
        def decorator(f):
            return f
        return decorator
    logger.warning("[Permissions] pyjnius not available - Android permissions disabled")


class PermissionStatus(Enum):
    """Permission status states."""
    GRANTED = "granted"
    DENIED = "denied"
    PENDING = "pending"
    NOT_AVAILABLE = "not_available"


class PermissionGroup(Enum):
    """Android permission groups for API 33+ runtime request logic."""
    WIFI_P2P = "wifi_p2p"
    BLUETOOTH = "bluetooth"
    LOCATION = "location"
    STORAGE = "storage"


@dataclass
class PermissionConfig:
    """Configuration for a single permission."""
    name: str
    min_api: int = 1
    group: Optional[PermissionGroup] = None
    critical: bool = False  # If denied, should disable feature
    fallback_message: str = ""


# Permission definitions with API levels and group assignments
PERMISSION_DEFINITIONS = {
    # Wi-Fi Direct Permissions (API 33+)
    'NEARBY_WIFI_DEVICES': PermissionConfig(
        name='android.permission.NEARBY_WIFI_DEVICES',
        min_api=33,
        group=PermissionGroup.WIFI_P2P,
        critical=True,
        fallback_message="Wi-Fi Direct discovery unavailable - nearby device permission denied"
    ),
    
    # Bluetooth Permissions
    'BLUETOOTH_SCAN': PermissionConfig(
        name='android.permission.BLUETOOTH_SCAN',
        min_api=31,
        group=PermissionGroup.BLUETOOTH,
        critical=True,
        fallback_message="Bluetooth device discovery unavailable - scan permission denied"
    ),
    'BLUETOOTH_CONNECT': PermissionConfig(
        name='android.permission.BLUETOOTH_CONNECT',
        min_api=31,
        group=PermissionGroup.BLUETOOTH,
        critical=True,
        fallback_message="Bluetooth connections unavailable - connect permission denied"
    ),
    'BLUETOOTH': PermissionConfig(
        name='android.permission.BLUETOOTH',
        min_api=1,
        group=PermissionGroup.BLUETOOTH,
        critical=False,
        fallback_message="Bluetooth unavailable"
    ),
    'BLUETOOTH_ADMIN': PermissionConfig(
        name='android.permission.BLUETOOTH_ADMIN',
        min_api=1,
        group=PermissionGroup.BLUETOOTH,
        critical=False,
        fallback_message="Bluetooth pairing unavailable"
    ),
    
    # Location Permissions (required for Wi-Fi Direct and Bluetooth on some APIs)
    'ACCESS_FINE_LOCATION': PermissionConfig(
        name='android.permission.ACCESS_FINE_LOCATION',
        min_api=1,
        group=PermissionGroup.LOCATION,
        critical=True,
        fallback_message="Fine location unavailable - precise location permission denied"
    ),
    'ACCESS_COARSE_LOCATION': PermissionConfig(
        name='android.permission.ACCESS_COARSE_LOCATION',
        min_api=1,
        group=PermissionGroup.LOCATION,
        critical=False,
        fallback_message="Coarse location unavailable"
    ),
    
    # Wi-Fi State Permissions
    'ACCESS_WIFI_STATE': PermissionConfig(
        name='android.permission.ACCESS_WIFI_STATE',
        min_api=1,
        group=PermissionGroup.WIFI_P2P,
        critical=False,
        fallback_message="Wi-Fi state monitoring unavailable"
    ),
    'CHANGE_WIFI_STATE': PermissionConfig(
        name='android.permission.CHANGE_WIFI_STATE',
        min_api=1,
        group=PermissionGroup.WIFI_P2P,
        critical=True,
        fallback_message="Wi-Fi Direct control unavailable - state change permission denied"
    ),
}


class PermissionRequestDialog(PythonJavaClass):
    """
    Callback interface for Android permission request results.
    Implements ActivityCompat.OnRequestPermissionsResultCallback.
    """
    __javainterfaces__ = ['androidx/core/app/ActivityCompat$OnRequestPermissionsResultCallback']
    __javacontext__ = 'app'

    def __init__(self, callback_queue):
        """Initialize dialog with result callback."""
        super().__init__()
        self.callback_queue = callback_queue

    @java_method('(I[Ljava/lang/String;[I)V')
    def onRequestPermissionsResult(self, request_code: int, permissions: list, 
                                    grant_results: list):
        """
        Handle permission request results from Android dialog.
        
        Args:
            request_code: Request code identifying which permission group
            permissions: Array of requested permission strings
            grant_results: Array of grant results (PackageManager.PERMISSION_GRANTED=0)
        """
        try:
            result_dict = {
                'type': 'permission_result',
                'request_code': request_code,
                'permissions': list(permissions),
                'results': list(grant_results)
            }
            self.callback_queue.put(result_dict)
            logger.debug(f"[Permissions] Result callback: {request_code} - {len(permissions)} perms")

        except Exception as e:
            logger.error(f"[Permissions] Callback error: {e}", exc_info=True)


class PermissionManager:
    """
    High-level manager for Android runtime permissions.
    
    Handles:
    - API level checking for per-permission minimum requirements
    - Batch permission requests by group
    - Permission status checking
    - Graceful fallback for denied permissions
    - Dialog display and result handling
    """

    # Request codes for permission groups
    REQUEST_CODE_WIFI_P2P = 1001
    REQUEST_CODE_BLUETOOTH = 1002
    REQUEST_CODE_LOCATION = 1003

    def __init__(self, on_permissions_result: Optional[Callable] = None,
                 on_error: Optional[Callable] = None):
        """
        Initialize Permission Manager.
        
        Args:
            on_permissions_result: Callback(group, granted, denied) on result
            on_error: Callback(error_msg) on errors
        """
        self.context = None
        self.activity = None

        self.on_permissions_result = on_permissions_result
        self.on_error = on_error

        self.permission_dialog = None
        self.permission_queue = None
        self.event_thread = None
        self.running = False

        self.request_code_map: Dict[int, PermissionGroup] = {
            self.REQUEST_CODE_WIFI_P2P: PermissionGroup.WIFI_P2P,
            self.REQUEST_CODE_BLUETOOTH: PermissionGroup.BLUETOOTH,
            self.REQUEST_CODE_LOCATION: PermissionGroup.LOCATION,
        }

        self.cached_status: Dict[str, PermissionStatus] = {}

        if PYJNIUS_AVAILABLE:
            self._initialize()
        else:
            logger.warning("[Permissions] Initialization skipped - pyjnius unavailable")

    def _initialize(self):
        """Initialize Android context and permission dialog."""
        try:
            # Get activity context
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.activity = PythonActivity.mActivity
            self.context = self.activity

            # Get API level
            VERSION = autoclass('android.os.Build$VERSION')
            self.api_level = VERSION.SDK_INT
            logger.info(f"[Permissions] Android API Level: {self.api_level}")

            # Initialize event queue and callback dialog
            from queue import Queue
            self.permission_queue = Queue()

            self.permission_dialog = PermissionRequestDialog(self.permission_queue)

            # Start event processing thread
            self.running = True
            import threading
            self.event_thread = threading.Thread(
                target=self._process_permission_events,
                daemon=True,
                name="PermissionEventLoop"
            )
            self.event_thread.start()

            logger.info("[Permissions] Manager initialized")

        except Exception as e:
            logger.error(f"[Permissions] Initialization failed: {e}", exc_info=True)
            self._notify_error(f"Init failed: {e}")

    def _get_api_level(self) -> int:
        """Get Android API level."""
        if not PYJNIUS_AVAILABLE:
            return 1

        try:
            VERSION = autoclass('android.os.Build$VERSION')
            return VERSION.SDK_INT
        except:
            return 1

    def check_permission(self, permission_key: str) -> PermissionStatus:
        """
        Check if a permission is granted.
        
        Args:
            permission_key: Key from PERMISSION_DEFINITIONS
            
        Returns:
            PermissionStatus indicating grant state
        """
        if permission_key not in PERMISSION_DEFINITIONS:
            return PermissionStatus.NOT_AVAILABLE

        config = PERMISSION_DEFINITIONS[permission_key]

        # Check minimum API level
        if self._get_api_level() < config.min_api:
            logger.debug(f"[Permissions] {permission_key} not available on API {self._get_api_level()}")
            return PermissionStatus.NOT_AVAILABLE

        # Check cached status
        if permission_key in self.cached_status:
            return self.cached_status[permission_key]

        if not PYJNIUS_AVAILABLE:
            return PermissionStatus.DENIED

        try:
            Context = autoclass('android.content.Context')
            ContextCompat = autoclass('androidx.core.content.ContextCompat')
            PackageManager = autoclass('android.content.pm.PackageManager')

            result = ContextCompat.checkSelfPermission(
                self.context,
                config.name
            )

            status = (PermissionStatus.GRANTED 
                     if result == PackageManager.PERMISSION_GRANTED 
                     else PermissionStatus.DENIED)

            self.cached_status[permission_key] = status
            return status

        except Exception as e:
            logger.error(f"[Permissions] Check error: {e}")
            return PermissionStatus.DENIED

    def check_permissions(self, permission_keys: List[str]) -> Dict[str, PermissionStatus]:
        """
        Check multiple permissions.
        
        Args:
            permission_keys: List of permission keys
            
        Returns:
            Dict mapping permission key to status
        """
        return {
            key: self.check_permission(key)
            for key in permission_keys
        }

    def request_permission_group(self, group: PermissionGroup) -> bool:
        """
        Request all permissions in a group.
        
        Args:
            group: PermissionGroup enum value
            
        Returns:
            bool: True if request started, False otherwise
        """
        if not self.activity:
            self._notify_error("Activity not initialized")
            return False

        try:
            # Collect permissions for this group that need requesting
            perms_to_request = []

            for key, config in PERMISSION_DEFINITIONS.items():
                if config.group == group:
                    # Skip if API level too low
                    if self._get_api_level() < config.min_api:
                        continue

                    # Skip if already granted
                    if self.check_permission(key) == PermissionStatus.GRANTED:
                        continue

                    perms_to_request.append(config.name)

            if not perms_to_request:
                logger.debug(f"[Permissions] All {group.value} permissions already granted")
                if self.on_permissions_result:
                    self.on_permissions_result(group, [], [])
                return True

            # Request permissions via ActivityCompat
            ActivityCompat = autoclass('androidx.core.app.ActivityCompat')

            request_code = {
                PermissionGroup.WIFI_P2P: self.REQUEST_CODE_WIFI_P2P,
                PermissionGroup.BLUETOOTH: self.REQUEST_CODE_BLUETOOTH,
                PermissionGroup.LOCATION: self.REQUEST_CODE_LOCATION,
            }.get(group, 1000)

            logger.info(f"[Permissions] Requesting {len(perms_to_request)} {group.value} permissions")

            # Convert Python list to Java String array
            PythonJavaClass_str_array = autoclass('[Ljava/lang/String;')
            java_perms = PythonJavaClass_str_array(len(perms_to_request))
            for i, perm in enumerate(perms_to_request):
                java_perms[i] = perm

            ActivityCompat.requestPermissions(
                self.activity,
                java_perms,
                request_code
            )

            return True

        except Exception as e:
            logger.error(f"[Permissions] Request error: {e}", exc_info=True)
            self._notify_error(f"Request failed: {e}")
            return False

    def request_wifi_direct_permissions(self) -> bool:
        """Request all Wi-Fi Direct required permissions."""
        return self.request_permission_group(PermissionGroup.WIFI_P2P)

    def request_bluetooth_permissions(self) -> bool:
        """Request all Bluetooth required permissions."""
        return self.request_permission_group(PermissionGroup.BLUETOOTH)

    def request_location_permissions(self) -> bool:
        """Request all location permissions."""
        return self.request_permission_group(PermissionGroup.LOCATION)

    def check_critical_permissions(self) -> tuple[bool, List[str]]:
        """
        Check if all critical permissions are granted.
        
        Returns:
            Tuple of (all_granted: bool, denied_critical_perms: List[str])
        """
        denied = []

        for key, config in PERMISSION_DEFINITIONS.items():
            if not config.critical:
                continue

            if self._get_api_level() < config.min_api:
                continue

            if self.check_permission(key) != PermissionStatus.GRANTED:
                denied.append(key)

        return len(denied) == 0, denied

    def check_feature_available(self, feature: str) -> tuple[bool, str]:
        """
        Check if a P2P feature is available based on permissions.
        
        Args:
            feature: 'wifi_direct', 'bluetooth', or 'location'
            
        Returns:
            Tuple of (available: bool, reason: str)
        """
        feature_map = {
            'wifi_direct': [
                'NEARBY_WIFI_DEVICES',
                'CHANGE_WIFI_STATE',
                'ACCESS_FINE_LOCATION'
            ],
            'bluetooth': [
                'BLUETOOTH_SCAN',
                'BLUETOOTH_CONNECT',
                'ACCESS_FINE_LOCATION'
            ],
            'location': [
                'ACCESS_FINE_LOCATION',
                'ACCESS_COARSE_LOCATION'
            ]
        }

        if feature not in feature_map:
            return False, "Unknown feature"

        for perm_key in feature_map[feature]:
            status = self.check_permission(perm_key)

            if status == PermissionStatus.NOT_AVAILABLE:
                # Not critical - skip
                continue

            if status == PermissionStatus.DENIED:
                config = PERMISSION_DEFINITIONS[perm_key]
                return False, config.fallback_message

        return True, "Available"

    def _process_permission_events(self):
        """Background thread processing permission request results."""
        while self.running:
            try:
                if self.permission_queue:
                    event = self.permission_queue.get(timeout=1)
                    self._handle_permission_result(event)
            except:
                continue

    def _handle_permission_result(self, event: dict):
        """Process permission request result."""
        try:
            request_code = event.get('request_code')
            permissions = event.get('permissions', [])
            results = event.get('results', [])

            if request_code not in self.request_code_map:
                return

            group = self.request_code_map[request_code]

            # Clear cached status for these permissions
            for perm in permissions:
                for key, config in PERMISSION_DEFINITIONS.items():
                    if config.name == perm:
                        self.cached_status.pop(key, None)

            # Categorize results
            granted = []
            denied = []

            for perm, result in zip(permissions, results):
                PackageManager = autoclass('android.content.pm.PackageManager')
                if result == PackageManager.PERMISSION_GRANTED:
                    granted.append(perm)
                else:
                    denied.append(perm)

            logger.info(f"[Permissions] {group.value}: {len(granted)} granted, {len(denied)} denied")

            if self.on_permissions_result:
                self.on_permissions_result(group, granted, denied)

        except Exception as e:
            logger.error(f"[Permissions] Result handling error: {e}", exc_info=True)

    def _notify_error(self, error_msg: str):
        """Thread-safe error notification."""
        logger.error(f"[Permissions] Error: {error_msg}")
        if self.on_error:
            self.on_error(error_msg)

    def shutdown(self):
        """Clean up resources."""
        self.running = False
        if self.event_thread:
            self.event_thread.join(timeout=2)
        logger.info("[Permissions] Manager shut down")


def get_system_version() -> int:
    """Get Android API level."""
    if not PYJNIUS_AVAILABLE:
        return 1

    try:
        VERSION = autoclass('android.os.Build$VERSION')
        return VERSION.SDK_INT
    except:
        return 1
