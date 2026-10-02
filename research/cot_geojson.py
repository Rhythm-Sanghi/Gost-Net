"""
Cursor-on-Target (CoT 2.0 XML) and GeoJSON (RFC 7946) interoperability engine.
Provides tactical geospatial translation for ATAK, QGIS, and off-grid mapping.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Union, Any


COT_TYPE_MAP = {
    "user": "a-f-G-u-C",       # Own position
    "peer": "a-f-G-u-C",       # Friendly ground unit combatant
    "sos": "b-m-p-s-m",        # Emergency / distress beacon
    "waypoint": "b-m-p-w",      # Standard waypoint
    "rally": "b-m-p-w-R",      # Rally point
    "hazard": "b-m-o-O",       # Hazard / obstacle
    "cache": "b-m-p-s-c",      # Supply cache
    "checkpoint": "b-m-p-c",   # Checkpoint
    "medical": "b-m-p-m",      # Medical aid station
}

REVERSE_COT_MAP = {v: k for k, v in COT_TYPE_MAP.items()}



def _iso_utc(dt: datetime) -> str:
    """Format datetime as UTC ISO 8601 string (e.g. 2026-10-01T08:30:00Z)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(iso_str: str) -> Optional[datetime]:
    """Parse ISO 8601 UTC timestamp."""
    try:
        iso_str = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None


def export_cot_xml(data: Dict[str, Any]) -> str:
    """
    Export a geospatial item (peer, SOS, waypoint) to Cursor-on-Target (CoT 2.0) XML.
    
    Expected keys in data:
      - uid: Unique event ID (str)
      - cot_type / marker_type / type: (str)
      - lat / latitude: (float)
      - lon / longitude: (float)
      - hae / altitude: (float, optional)
      - callsign / title / sender_name: (str, optional)
      - remarks / description: (str, optional)
      - ttl_seconds: (int, optional, default 3600)
      - timestamp: (float or str, optional)
    """
    uid = str(data.get("uid") or data.get("waypoint_id") or data.get("sos_id") or data.get("peer_id") or "cot-unknown")
    marker_type = data.get("cot_type") or data.get("marker_type") or data.get("waypoint_type") or data.get("type", "waypoint")
    cot_type = COT_TYPE_MAP.get(marker_type, marker_type)
    
    lat = float(data.get("lat") or data.get("latitude") or 0.0)
    lon = float(data.get("lon") or data.get("longitude") or 0.0)
    hae = float(data.get("hae") or data.get("altitude") or 0.0)
    ce = float(data.get("ce") or data.get("accuracy") or 10.0)
    le = float(data.get("le") or 10.0)
    
    callsign = str(data.get("callsign") or data.get("title") or data.get("sender_name") or data.get("username") or uid)
    remarks = str(data.get("remarks") or data.get("description") or data.get("message") or "")
    
    ttl_seconds = int(data.get("ttl_seconds") or data.get("ttl") or 3600)
    
    ts = data.get("timestamp")
    if isinstance(ts, (int, float)):
        now_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    elif isinstance(ts, str):
        parsed = _parse_iso(ts)
        now_dt = parsed if parsed else datetime.now(timezone.utc)
    else:
        now_dt = datetime.now(timezone.utc)
        
    stale_dt = now_dt + timedelta(seconds=ttl_seconds)
    
    root = ET.Element("event", {
        "version": "2.0",
        "uid": uid,
        "type": cot_type,
        "how": "m-g",
        "time": _iso_utc(now_dt),
        "start": _iso_utc(now_dt),
        "stale": _iso_utc(stale_dt)
    })
    
    ET.SubElement(root, "point", {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "hae": f"{hae:.1f}",
        "ce": f"{ce:.1f}",
        "le": f"{le:.1f}"
    })
    
    detail = ET.SubElement(root, "detail")
    ET.SubElement(detail, "contact", {
        "callsign": callsign
    })
    
    if remarks:
        ET.SubElement(detail, "remarks").text = remarks
        
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def parse_cot_xml(cot_xml: str) -> Optional[Dict[str, Any]]:
    """
    Parse a Cursor-on-Target (CoT 2.0) XML string into a structured dictionary.
    Returns None if XML is invalid or missing required point coordinates.
    """
    try:
        root = ET.fromstring(cot_xml.strip())
        if root.tag != "event":
            return None
            
        uid = root.get("uid", "")
        cot_type = root.get("type", "b-m-p-w")
        time_str = root.get("time", "")
        start_str = root.get("start", "")
        stale_str = root.get("stale", "")
        
        point_elem = root.find("point")
        if point_elem is None:
            return None
            
        lat = float(point_elem.get("lat", 0.0))
        lon = float(point_elem.get("lon", 0.0))
        hae = float(point_elem.get("hae", 0.0))
        ce = float(point_elem.get("ce", 10.0))
        
        callsign = uid
        remarks = ""
        detail = root.find("detail")
        if detail is not None:
            contact = detail.find("contact")
            if contact is not None:
                callsign = contact.get("callsign", uid)
            rem = detail.find("remarks")
            if rem is not None and rem.text:
                remarks = rem.text.strip()
                
        resolved_type = REVERSE_COT_MAP.get(cot_type, cot_type)
        
        return {
            "uid": uid,
            "cot_type": cot_type,
            "marker_type": resolved_type,
            "callsign": callsign,
            "lat": lat,
            "lon": lon,
            "hae": hae,
            "ce": ce,
            "time": time_str,
            "start": start_str,
            "stale": stale_str,
            "remarks": remarks
        }
    except Exception as e:
        print(f"[CoT Engine] Error parsing CoT XML: {e}")
        return None


def export_geojson(items: List[Dict[str, Any]]) -> str:
    """
    Export a list of markers, waypoints, or peer locations as RFC 7946 GeoJSON FeatureCollection.
    """
    features = []
    for item in items:
        lat = float(item.get("lat") or item.get("latitude") or 0.0)
        lon = float(item.get("lon") or item.get("longitude") or 0.0)
        alt = float(item.get("alt") or item.get("altitude") or 0.0)
        
        coords = [lon, lat]
        if alt != 0.0:
            coords.append(alt)
            
        properties = {
            "id": item.get("uid") or item.get("waypoint_id") or item.get("sos_id") or item.get("peer_id", ""),
            "title": item.get("title") or item.get("callsign") or item.get("sender_name") or item.get("username", "Unnamed"),
            "description": item.get("description") or item.get("remarks") or item.get("message", ""),
            "waypoint_type": item.get("waypoint_type") or item.get("marker_type") or item.get("type", "waypoint"),
            "created_by": item.get("created_by") or item.get("sender_id", "local"),
            "timestamp": item.get("timestamp") or item.get("created_at") or datetime.now(timezone.utc).isoformat()
        }
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": coords
            },
            "properties": properties
        }
        features.append(feature)
        
    collection = {
        "type": "FeatureCollection",
        "features": features
    }
    return json.dumps(collection, indent=2)


def import_geojson(geojson_input: Union[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Import GeoJSON FeatureCollection or Features and validate coordinates.
    Returns normalized marker dictionary list.
    """
    if isinstance(geojson_input, str):
        try:
            data = json.loads(geojson_input)
        except Exception as e:
            print(f"[GeoJSON Engine] JSON parse error: {e}")
            return []
    elif isinstance(geojson_input, dict):
        data = geojson_input
    else:
        return []
        
    markers = []
    features = []
    
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
        
    for feat in features:
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
            
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
            
        lon, lat = float(coords[0]), float(coords[1])
        alt = float(coords[2]) if len(coords) >= 3 else 0.0
        
        # Coordinate sanity bounds check
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            print(f"[GeoJSON Engine] Rejecting out-of-bounds coordinates: ({lat}, {lon})")
            continue
            
        props = feat.get("properties", {})
        marker = {
            "waypoint_id": props.get("id") or props.get("waypoint_id") or f"wp_{len(markers)+1}",
            "title": props.get("title") or props.get("name") or "Imported Waypoint",
            "description": props.get("description") or "",
            "waypoint_type": props.get("waypoint_type") or props.get("type") or "waypoint",
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "created_by": props.get("created_by") or "imported",
            "created_at": props.get("timestamp") or datetime.now(timezone.utc).isoformat()
        }
        markers.append(marker)
        
    return markers
