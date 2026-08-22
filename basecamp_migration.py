#!/usr/bin/env python3
"""
BaseCamp Backup Migration Tool

Liest ein BaseCamp-Backup (AllData.gdb + FolderData.gfi + TrackSegments)
und exportiert Tracks mit Ordnerstruktur als GPX-Dateien.

Basierend auf der Spezifikation:
https://www.memotech.franken.de/FileFormats/Garmin_MPS_GDB_and_GFI_Format.pdf

Voraussetzungen:
- Python 3.8+
- gpxpy (pip install gpxpy)

Verwendung:
    python basecamp_migration.py \
        --gdb path/to/AllData.gdb \
        --gfi path/to/FolderData.gfi \
        --tracksegments path/to/TrackSegments \
        --output path/to/output_dir
"""

import argparse
import struct
import os
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, BinaryIO
from datetime import datetime, timezone

try:
    import gpxpy
    import gpxpy.gpx
except ImportError:
    print("Fehler: gpxpy nicht installiert. Bitte mit 'pip install gpxpy' nachinstallieren.")
    raise


# =============================================================================
# Datenstrukturen
# =============================================================================

@dataclass
class TrackPoint:
    lat: float
    lon: float
    elevation: Optional[float] = None
    time: Optional[datetime] = None
    temperature: Optional[float] = None


@dataclass
class Track:
    track_id: int
    name: str
    color: int
    points: List[TrackPoint] = field(default_factory=list)
    notes: str = ""
    segment_uuids: List[str] = field(default_factory=list)


@dataclass
class Folder:
    folder_id: int
    name: str
    parent_id: Optional[int] = None
    children: List[int] = field(default_factory=list)
    track_ids: List[int] = field(default_factory=list)


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def read_string(f: BinaryIO) -> str:
    """Liest einen null-terminierten String."""
    result = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b'\x00':
            break
        result.append(b[0])
    return result.decode('latin-1', errors='replace')


def read_fstring(f: BinaryIO) -> Optional[str]:
    """Liest einen optionalen String (flag + content)."""
    flag = struct.unpack('<B', f.read(1))[0]
    if flag:
        return read_string(f)
    return None


def read_fdouble(f: BinaryIO) -> Optional[float]:
    """Liest einen optionalen double-Wert."""
    flag = struct.unpack('<B', f.read(1))[0]
    if flag:
        return struct.unpack('<d', f.read(8))[0]
    return None


def read_fint(f: BinaryIO) -> Optional[int]:
    """Liest einen optionalen int-Wert."""
    flag = struct.unpack('<B', f.read(1))[0]
    if flag:
        return struct.unpack('<i', f.read(4))[0]
    return None


def coord_to_degrees(coord: int) -> float:
    """Konvertiert Garmin-Koordinaten in Dezimalgrad."""
    return coord * 360.0 / (2**32)


def unix_time_to_datetime(ts: Optional[int]) -> Optional[datetime]:
    """Konvertiert Unix-Timestamp in datetime."""
    if ts is None or ts == 0:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (OSError, OverflowError):
        return None


# =============================================================================
# GDB-Parser (AllData.gdb)
# =============================================================================

def parse_gdb(gdb_path: str) -> Tuple[Dict[int, Track], int]:
    """
    Parst eine AllData.gdb-Datei und extrahiert Tracks.
    
    Returns:
        Tuple aus (Track-Dictionary, File-Format-Version)
    """
    tracks: Dict[int, Track] = {}
    file_format_version = 0
    track_id_counter = 0
    
    with open(gdb_path, 'rb') as f:
        # Header lesen
        signature = f.read(4)
        if signature != b'MsRc':
            raise ValueError(f"Ungültige GDB-Signatur: {signature!r}")
        
        primary_version = struct.unpack('<H', f.read(2))[0]
        
        # Application field (optional)
        if primary_version > 0x0064:  # > 1.0
            app_field = read_string(f)
        
        # Records lesen
        while True:
            pos_before = f.tell()
            header = f.read(4)
            if len(header) < 4:
                break
            
            record_length = struct.unpack('<I', header[:4])[0]
            record_type = f.read(1)
            
            if len(record_type) == 0:
                break
            
            record_type = record_type[0]
            
            # Record-Inhalt lesen
            record_start = f.tell()
            
            if record_type == ord('D'):
                # File format version record
                file_format_version = struct.unpack('<H', f.read(2))[0]
                
            elif record_type == ord('T'):
                # Track record
                track = parse_track_record(f, track_id_counter, file_format_version)
                if track:
                    tracks[track.track_id] = track
                    track_id_counter += 1
            
            elif record_type == ord('X'):
                # End of file
                break
            
            # Zum nächsten Record springen
            f.seek(record_start + record_length)
    
    return tracks, file_format_version


def parse_track_record(f: BinaryIO, track_id: int, file_format_version: int) -> Optional[Track]:
    """Parst einen einzelnen Track-Record."""
    try:
        track_name = read_string(f)
        track_display = struct.unpack('<B', f.read(1))[0]
        track_color = struct.unpack('<I', f.read(1))[0]
        num_points = struct.unpack('<I', f.read(4))[0]
        
        points: List[TrackPoint] = []
        for _ in range(num_points):
            lat_coord = struct.unpack('<i', f.read(4))[0]
            lon_coord = struct.unpack('<i', f.read(4))[0]
            elevation = read_fdouble(f)
            time_ts = read_fint(f)
            depth = read_fdouble(f)
            temperature = read_fdouble(f)
            
            # Unbekannte Felder bei neueren Versionen
            if file_format_version >= 0x001D:  # >= 1.29
                unknown1 = read_fdouble(f)
                unknown2 = read_fdouble(f)
                flag = struct.unpack('<B', f.read(1))[0]
                if flag:
                    present_flag = struct.unpack('<B', f.read(1))[0]
            
            lat = coord_to_degrees(lat_coord)
            lon = coord_to_degrees(lon_coord)
            time_dt = unix_time_to_datetime(time_ts)
            
            points.append(TrackPoint(
                lat=lat,
                lon=lon,
                elevation=elevation,
                time=time_dt,
                temperature=temperature
            ))
        
        # Links (ab Version 1.9)
        if file_format_version >= 0x0019:  # >= 1.9
            num_links = struct.unpack('<I', f.read(4))[0]
            for _ in range(num_links):
                link = read_string(f)
        
        # Notes (ab Version 1.15)
        if file_format_version >= 0x001F:  # >= 1.15
            notes = read_string(f)
        else:
            notes = ""
        
        return Track(
            track_id=track_id,
            name=track_name,
            color=track_color,
            points=points,
            notes=notes
        )
        
    except Exception as e:
        print(f"Fehler beim Parsen eines Track-Records: {e}")
        return None


# =============================================================================
# GFI-Parser (FolderData.gfi)
# =============================================================================

def parse_gfi(gfi_path: str) -> Tuple[Dict[int, Folder], Dict[int, List[int]]]:
    """
    Parst eine FolderData.gfi-Datei und extrahiert Ordnerstruktur.
    
    Returns:
        Tuple aus (Folder-Dictionary, Track-zu-Ordner-Mapping)
    """
    folders: Dict[int, Folder] = {}
    track_to_folders: Dict[int, List[int]] = {}
    
    with open(gfi_path, 'rb') as f:
        # Header lesen
        signature = f.read(4)
        if signature != b'DifG':
            raise ValueError(f"Ung�ltige GFI-Signatur: {signature!r}")
        
        primary_version = struct.unpack('<H', f.read(2))[0]
        
        # Application field (optional)
        if primary_version > 0x0064:
            app_field = read_string(f)
        
        # Records lesen
        while True:
            header = f.read(4)
            if len(header) < 4:
                break
            
            record_length = struct.unpack('<I', header[:4])[0]
            record_type = f.read(1)
            
            if len(record_type) == 0:
                break
            
            record_type = record_type[0]
            record_start = f.tell()
            
            if record_type == ord('F'):
                # Folder record
                folder = parse_folder_record(f)
                if folder:
                    folders[folder.folder_id] = folder
            
            elif record_type == ord('I'):
                # Item record (Verweis auf Track in Ordner)
                folder_id, item_type, item_id = parse_item_record(f)
                if item_type == 'T' and folder_id is not None:
                    if item_id not in track_to_folders:
                        track_to_folders[item_id] = []
                    track_to_folders[item_id].append(folder_id)
                    
                    # Track zum Ordner hinzuf�gen
                    if folder_id in folders:
                        folders[folder_id].track_ids.append(item_id)
            
            elif record_type == ord('X'):
                break
            
            f.seek(record_start + record_length)
    
    # Ordnerhierarchie aufbauen
    build_folder_hierarchy(folders)
    
    return folders, track_to_folders


def parse_folder_record(f: BinaryIO) -> Optional[Folder]:
    """Parst einen Folder-Record."""
    try:
        folder_id = struct.unpack('<I', f.read(4))[0]
        folder_name = read_string(f)
        parent_id_raw = struct.unpack('<I', f.read(4))[0]
        parent_id = parent_id_raw if parent_id_raw != 0xFFFFFFFF else None
        
        return Folder(
            folder_id=folder_id,
            name=folder_name,
            parent_id=parent_id
        )
    except Exception as e:
        print(f"Fehler beim Parsen eines Folder-Records: {e}")
        return None


def parse_item_record(f: BinaryIO) -> Tuple[Optional[int], str, int]:
    """Parst einen Item-Record (Verweis auf Track/Route/Waypoint in Ordner)."""
    try:
        folder_id_raw = struct.unpack('<I', f.read(4))[0]
        folder_id = folder_id_raw if folder_id_raw != 0xFFFFFFFF else None
        
        item_type_byte = f.read(1)
        item_type = item_type_byte.decode('latin-1') if item_type_byte else '?'
        
        item_id = struct.unpack('<I', f.read(4))[0]
        
        return folder_id, item_type, item_id
    except Exception as e:
        print(f"Fehler beim Parsen eines Item-Records: {e}")
        return None, '?', 0


def build_folder_hierarchy(folders: Dict[int, Folder]):
    """Baut die Kinder-Listen der Ordner auf."""
    for folder in folders.values():
        if folder.parent_id is not None and folder.parent_id in folders:
            folders[folder.parent_id].children.append(folder.folder_id)


# =============================================================================
# TrackSegments-Parser
# =============================================================================

def parse_track_segments(tracksegments_path: str, track: Track) -> List[TrackPoint]:
    """
    Parst TrackSegment-Dateien für einen Track.
    
    Achtung: Das genaue Format der TrackSegment-Dateien ist nicht vollständig
    dokumentiert. Diese Funktion ist ein Platzhalter und müsste ggf. angepasst
    werden, basierend auf Reverse-Engineering.
    """
    enhanced_points: List[TrackPoint] = []
    
    for seg_uuid in track.segment_uuids:
        seg_file = os.path.join(tracksegments_path, seg_uuid)
        if not os.path.exists(seg_file):
            continue
        
        try:
            with open(seg_file, 'rb') as f:
                # Format ist nicht offiziell dokumentiert
                # Hier müsste das tatsächliche Format implementiert werden
                pass
        except Exception as e:
            print(f"Fehler beim Lesen von TrackSegment {seg_uuid}: {e}")
    
    return enhanced_points if enhanced_points else track.points


# =============================================================================
# GPX-Export
# =============================================================================

def export_tracks_to_gpx(
    tracks: Dict[int, Track],
    folders: Dict[int, Folder],
    output_dir: str
):
    """
    Exportiert Tracks mit Ordnerstruktur als GPX-Dateien.
    
    Erstellt für jeden Ordner eine GPX-Datei mit allen darin enthaltenen Tracks.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Ordner ohne Parent (Root-Ordner) finden
    root_folders = [f for f in folders.values() if f.parent_id is None]
    
    for root_folder in root_folders:
        export_folder_recursive(root_folder, folders, tracks, output_dir, "")


def export_folder_recursive(
    folder: Folder,
    folders: Dict[int, Folder],
    tracks: Dict[int, Track],
    output_dir: str,
    path_prefix: str
):
    """Exportiert einen Ordner und seine Unterordner rekursiv."""
    folder_path = os.path.join(output_dir, path_prefix, folder.name)
    os.makedirs(folder_path, exist_ok=True)
    
    # GPX für diesen Ordner erstellen
    if folder.track_ids:
        gpx = create_gpx_for_folder(folder, folders, tracks)
        gpx_filename = os.path.join(folder_path, f"{sanitize_filename(folder.name)}.gpx")
        
        with open(gpx_filename, 'w', encoding='utf-8') as f:
            f.write(gpx.to_xml())
        
        print(f"Exportiert: {gpx_filename} ({len(folder.track_ids)} Tracks)")
    
    # Unterordner rekursiv exportieren
    for child_id in folder.children:
        if child_id in folders:
            child_folder = folders[child_id]
            export_folder_recursive(
                child_folder,
                folders,
                tracks,
                output_dir,
                os.path.join(path_prefix, folder.name)
            )


def create_gpx_for_folder(
    folder: Folder,
    folders: Dict[int, Folder],
    tracks: Dict[int, Track]
) -> gpxpy.gpx.GPX:
    """Erstellt ein GPX-Objekt für alle Tracks in einem Ordner."""
    gpx = gpxpy.gpx.GPX()
    gpx.creator = "BaseCamp Migration Tool"
    
    for track_id in folder.track_ids:
        if track_id not in tracks:
            continue
        
        track = tracks[track_id]
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx_track.name = track.name
        gpx_track.type = "BaseCamp Track"
        
        if track.points:
            gpx_segment = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)
            
            for point in track.points:
                gpx_point = gpxpy.gpx.GPXTrackPoint(
                    latitude=point.lat,
                    longitude=point.lon,
                    elevation=point.elevation,
                    time=point.time
                )
                gpx_segment.points.append(gpx_point)
        
        gpx.tracks.append(gpx_track)
    
    return gpx


def sanitize_filename(name: str) -> str:
    """Entfernt ungültige Zeichen für Dateinamen."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip()


# =============================================================================
# Hauptprogramm
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="BaseCamp Backup Migration Tool - Exportiert Tracks mit Ordnerstruktur als GPX"
    )
    parser.add_argument(
        "--gdb",
        required=True,
        help="Pfad zur AllData.gdb-Datei"
    )
    parser.add_argument(
        "--gfi",
        required=True,
        help="Pfad zur FolderData.gfi-Datei"
    )
    parser.add_argument(
        "--tracksegments",
        required=False,
        help="Pfad zum TrackSegments-Verzeichnis (optional)"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Ausgabeverzeichnis für GPX-Dateien"
    )
    
    args = parser.parse_args()
    
    # GDB parsen
    print(f"Parsing GDB: {args.gdb}")
    tracks, file_format_version = parse_gdb(args.gdb)
    print(f"  Gefunden: {len(tracks)} Tracks (File Format Version: {file_format_version})")
    
    # GFI parsen
    print(f"Parsing GFI: {args.gfi}")
    folders, track_to_folders = parse_gfi(args.gfi)
    print(f"  Gefunden: {len(folders)} Ordner")
    
    # TrackSegments (optional)
    if args.tracksegments and os.path.isdir(args.tracksegments):
        print(f"TrackSegments-Verzeichnis: {args.tracksegments}")
        # Hier könnte die TrackSegment-Integration implementiert werden
    
    # GPX exportieren
    print(f"Exportiere GPX-Dateien nach: {args.output}")
    export_tracks_to_gpx(tracks, folders, args.output)
    
    print("Fertig!")


if __name__ == "__main__":
    main()
