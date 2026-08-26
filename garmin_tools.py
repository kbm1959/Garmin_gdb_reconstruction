"""
This module contains the GarminAnalyzer class, which was developed to analyse Garmin databases in .gdb format.
The class provides functions for reading and interpreting the file, including the extraction of header information, 
record types and their contents. It supports the analysis of waypoints, routes, tracks and other relevant data 
contained in Garmin files.

The class can handle the following file types:
- Garmin .gdb database file
- garmin .gfi folder information file
- Garmin TrackSegment files (usually in the subfolder TrackSegments of the Garmin database folder)

It is based on the specification in:
https://www.memotech.franken.de/FileFormats/Garmin_MPS_GDB_and_GFI_Format.pdf
Thanks to Herbert Oppmann for his work and the document, which was very helpful in writing this class.

Example:

"""
import struct
import datetime
import os
import re
from datetime import datetime
import pytz
from typing import List, Optional
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

# define custom data classes for Folder, Item, Trackpoint, Track, and Waypoint to store the analyzed data
@dataclass
class Folder:
    name: str
    parent_id: Optional[int] = None
    children: List[tuple] = field(default_factory=list)

@dataclass
class Item: # this is a Basecamp List element, will be treated like a folder
    name: str
    parent_id: Optional[int] = None
    created_by: Optional[int] = None
    folder_path: Optional[str] = None

@dataclass
class Trackpoint:
    latitude: float
    longitude: float
    elevation: Optional[float] = None
    timestamp: Optional[str] = None
@dataclass
class Track:
    name: str
    parent_item_id: Optional[int] = None
    trackpoints: List[Trackpoint] = field(default_factory=list)
    display_mode: Optional[int] = None
    color: Optional[str] = None
    links: List[str] = field(default_factory=list)
    note: Optional[str] = None
    area: Optional[float] = None
    latitude_max: Optional[float] = None
    latitude_min: Optional[float] = None
    longitude_max: Optional[float] = None
    longitude_min: Optional[float] = None
    duration: Optional[float] = None
    length: Optional[float] = None
    start_time: Optional[str] = None
    track_segments: List[Trackpoint] = field(default_factory=list)
    uuid: Optional[str] = None

@dataclass
class Waypoint:
    name: str
    parent_item_id: Optional[int] = None
    wp_class: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    comment: Optional[str] = None
    proximity: Optional[float] = None
    display_mode: Optional[int] = None
    icon: Optional[int] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zip_code: Optional[str] = None
    altitude: Optional[float] = None
    depth: Optional[float] = None
    num_links: Optional[int] = None
    links: List[str] = field(default_factory=list)
    temperature: Optional[float] = None
    modification_date: Optional[str] = None
    creation_date: Optional[str] = None
    num_categories: Optional[int] = None
    categories: List[str] = field(default_factory=list)

class GarminAnalyzer:

    def __init__(self, db_path, log_records=False):
        """
        Initializes the GarminAnalyzer with the specified database file path:
        - checks for the presence of AllData.gdb, FolderData.gfi, and TrackSegments folder in db_path
        - opens and reads the header information from AllData.gdb and FolderData.gfi to extract the signature, primary version, file format version and author information
        - reads the application string
        - reads all remaining records 
        Args:
            db_path (str): File path to the Garmin database file (.gdb, .gfi or TrackSegment file)
            log_records (bool): Whether to log the contents of the records
        """
        try:
            # check if AllData.gdb exists in db_path
            all_data_path = os.path.join(db_path, "AllData.gdb")
            if not os.path.exists(all_data_path):
                print("AllData.gdb not found in the specified db_path")
                return
            else:
                print(f"AllData.gdb found in {db_path}")

            # check if FolderData.gfi exists in db_path
            folder_data_path = os.path.join(db_path, "FolderData.gfi")
            if not os.path.exists(folder_data_path):
                print("FolderData.gfi not found in the specified db_path")
                return
            else:
                print(f"FolderData.gfi found in {db_path}")

            # check if TrackSegments directory exists in db_path
            track_segments_path = os.path.join(db_path, "TrackSegments")
            if not os.path.exists(track_segments_path):
                print("TrackSegments directory not found in the specified db_path")
                return
            else:
                print(f"TrackSegments directory found in {db_path}")

            # set logging flag
            self.log = log_records

            # read header and records from AllData.gdb
            with open(all_data_path, 'rb') as file:
                print("-"*50)
                print(f"Reading header of: {all_data_path}")
                self.header = self.read_garmin_header(file)
                for key, value in self.header.items():
                    print(f"{key}: {value}")
                print("=" * 50)

                # now read all the remaining records from the file until the 'X' (EndOfFile) record is reached
                # keep only 'T' (track) and 'W' recordsof class 0 (user Waypoints). 'R' (route) records will be treated in a later version
                self.gdb_t_records = {} # Track records
                self.gdb_w_records = {} # Waypoint records
                # read next record:
                record_type, _, record_content = self.read_record(file)
                while record_type != 'X':  # 'X' indicates EndOfFile
                    if record_type in ['T', 'W']:
                        record_name, record_content = self.get_string(record_content)
                        if record_type == 'T':
                            self.gdb_t_records[record_name] = record_content
                        elif record_type == 'W':
                            wp_class, record_content = self.get_uint(record_content)
                            if wp_class == 0 or wp_class == 1:  # only keep user waypoints (class 0) and class 1 waypoints (user defined)
                                self.gdb_w_records[record_name] = record_content
                    record_type, _, record_content = self.read_record(file)
            
                print(f"{len(self.gdb_t_records)} Track + {len(self.gdb_w_records)} Waypoint records successfully loaded.")

        # now read header and all the records from FolderData.gfi
            with open(folder_data_path, 'rb') as file:
                print("-"*50)
                print(f"Reading header of: {folder_data_path}")
                self.header_gfi = self.read_garmin_header(file)
                for key, value in self.header_gfi.items():
                    print(f"{key}: {value}")
                print("=" * 50)

                # now read all the remaining records from the file 
                # keep only 'F' (Folder), 'I' (Item), 'T' (Track) and 'W' (Waypoint) records
                self.gfi_f_records = {} # Folder records
                self.gfi_i_records = {} # Item records
                self.gfi_t_records = [] # Track records
                self.gfi_w_records = [] # Waypoint records
                # read next record:
                record_type, _, record_content = self.read_record(file)
                while record_type :  # None indicates EndOfFile
                    if record_type in ['F', 'I', 'T', 'W']:
                        if record_type == 'F':
                            folder_id, folder = self.analyze_gfi_record_F(record_content)
                            self.gfi_f_records[folder_id] = folder
                        elif record_type == 'I':
                            item_id, item = self.analyze_gfi_record_I(record_content)
                            self.gfi_i_records[item_id] = item
                        elif record_type == 'T':
                            self.gfi_t_records.append(self.analyze_gfi_record_T(record_content))
                        elif record_type == 'W':
                            self.gfi_w_records.append(self.analyze_gfi_record_W(record_content))
                    record_type, _, record_content = self.read_record(file)
            
                print(f"{len(self.gfi_f_records)} Folder + {len(self.gfi_i_records)} Item records successfully loaded.")
        except PermissionError:
            print(f"Fehler: Keine Berechtigung zum Zugriff auf '{all_data_path}'.")

    def read_garmin_header(self, file_handle):
        """
        Reads the Garmin header from the given file handle.
        The header consists of:
        - Signature (4 bytes)
        - Primary Version (2 bytes, little-endian)
        - File Format Version (Record 'D')
        - Author Information (Record 'A')
        - Application String (null-terminated)
        
        Args:
            file_handle: A file object opened in binary mode.
        
        Returns:
            dict: A dictionary containing the signature, primary version, file format version, author information, and application string.
        """
        header_info = {}
        
        # Read Signature (4 bytes)
        signature_bytes = file_handle.read(4)
        header_info['signature'] = signature_bytes.decode('utf-8', errors='ignore')
        
        # Read Primary Version (2 bytes, little-endian)
        primary_version_bytes = file_handle.read(2)
        primary_version = int.from_bytes(primary_version_bytes, byteorder='little')
        major = primary_version // 100
        minor = primary_version % 100
        header_info['primary_version'] = f"{major}.{minor}"
        
        # Read File Format Version (Record 'D')
        record_type, record_length, record_content = self.read_record(file_handle)
        if record_type == 'D':
            file_format_version = int.from_bytes(record_content, byteorder='little')
            major_ffv = file_format_version // 100
            minor_ffv = file_format_version % 100
            header_info['file_format_version'] = f"{major_ffv}.{minor_ffv}"
        else:
            print("Fehler: Erwarteter Record-Typ 'D' für Dateiformatversion nicht gefunden.")
        
        # Read Author Information (Record 'A')
        record_type, record_length, record_content = self.read_record(file_handle)
        if record_type == 'A':
            # read program version from file
        # Lese Programm Version (2 Byte, little-endian)
            version = int.from_bytes(record_content[0:2], byteorder='little')
            major = version // 100
            minor = version % 100
            program_version_gdb = f"{major}.{minor}"

            # Extrahiere die null-terminierten Strings
            
            # Builder (null terminated string)
            builder, record_content = self.get_string(record_content)
            
            # Build date (null terminated string)
            build_date, record_content = self.get_string(record_content)
            
            # Build time (null terminated string)
            build_time, record_content = self.get_string(record_content)

            header_info['program_version'] = program_version_gdb
            header_info['builder'] = builder
            header_info['build_date'] = build_date
            header_info['build_time'] = build_time
        else:
            print("Fehler: Erwarteter Record-Typ 'A' für Autorinformationen nicht gefunden.")

        # Read Application String (null-terminated)
        header_info['application'] = self.read_string(file_handle)
        
        return header_info
    
    def read_string(self, file_handle):
        """
        Reads a null-terminated string from the given file handle.
        
        Args:
            file_handle: A file object opened in binary mode.

        Returns:
            str: The decoded string.
        """
        string_bytes = bytearray()
        while True:
            byte = file_handle.read(1)
            if not byte or byte == b'\x00':
                break
            string_bytes.extend(byte)
        return string_bytes.decode('utf-8', errors='ignore')
    
    def read_record(self, file_handle=None):
        """
        Liest einen einzelnen Record aus dem übergebenen file_handle.
                
        Returns:
            tuple: (record_type, record_length, record_content)
        """
        # Lese Record-Länge (4 Byte, little-endian)
        record_length_bytes = file_handle.read(4)
        if record_length_bytes == b'':
            return None, 0, b''  # End of file reached
        else:
            record_length = int.from_bytes(record_length_bytes, byteorder='little')
        
            # Lese Record-Type (1 Byte)
            record_type = file_handle.read(1).decode('ascii', errors='ignore')
            
            # Lese Record-Inhalt
            record_content = file_handle.read(record_length)
                    
            return record_type, record_length, record_content
        
    def analyze_record(self, record, short = False):
        """
        Dispatches analysis to appropriate handler based on record type.
        Handles Garmin GDB .gdb as well as GFI .gfi files.
        Initializes the record index (record_pos).
        
        Args:
            record: A tuple of format (record_type, record_length, record_content)
                    where record_type is an uppercase letter
            short: a flag to shorten the analysys
        
        Returns:
            The result of the specific analysis function
        """
        # get record type and content
        record_type, record_length, record_content = record

        # get function prefix from application signature
        if self.signature == 'DifG':
            f_prefix = 'gfi_'
        else:
            f_prefix = ''
        # Construct the function name
        function_name = f"analyze_{f_prefix}record_{record_type}"
        
        # Check if the function exists as a method
        if hasattr(self, function_name):
            # initialize the record counter
            self.record_pos = 0
            # Get the method and call it with record_content
            method = getattr(self, function_name)
            return method(record_content, short)
        else:
            raise ValueError(f"No analysis method found for record type: {record_type}")

    def analyze_gfi_record_F(self, rec_content):
        """
        Analysiert den Inhalt eines Record-Typs 'F' (Folder Information) für GFI-Dateien.
        Analyzes the content of a record of type 'F' (Folder Information) for GFI files.
                
        Args:
            rec_content (bytes): The content of the record

        Returns:
            tuple: A tuple containing the Folder ID and a Folder dataclass object.
        """

        record = rec_content
        root_not_found = True
        folder_id, record = self.get_uint(record)
        if self.log: 
            print(f"Folder ID: {folder_id}")

        folder_name, record = self.get_string(record)
        if self.log: 
            print(f"Folder Name: {folder_name}")
        # initialize new folder dataclass
        folder = Folder(name=folder_name)

        folder.parent_id, record = self.get_uint(record)
        if self.log: 
            print(f"Parent Folder ID: {folder.parent_id}")
        # check for root folder
        if root_not_found and folder.parent_id == folder_id:
            root_not_found = False
            if self.log: 
                print(f"Root folder found: {folder_name} (ID={folder_id})")
            self.root_folder_id = folder_id
            folder_id = 'root'

        n_subordinated, record = self.get_uint(record)
        if self.log: 
            print(f"Number of Subordinated Folders: {n_subordinated}")

        folder.children = []
        for i in range(n_subordinated):
            sub_item_type, record = self.get_uint(record)
            sub_item_id, record = self.get_uint(record)
            folder.children.append((sub_item_id, sub_item_type))
            if self.log: 
                print(f"Subordinated Folder {i+1}: ID={sub_item_id}, Type={sub_item_type}")

        return folder_id, folder

    def analyze_gfi_record_I(self, rec_content):
        """
        Analyzes the content of a record of type 'I' (Item Information) for GFI files.
        
        Args:
            rec_content (bytes): The content of the record
        Returns:
            tuple: A tuple containing the Item ID and an Item dataclass object.
        """
        record = rec_content
        item_id, record = self.get_uint(record)
        if self.log: 
            print(f"Item ID: {item_id}")

        item_name, record = self.get_string(record)
        if self.log: 
            print(f"Item Name: {item_name}")
        item = Item(name=item_name)

        item.created_by, record = self.get_uint(record)
        if self.log: 
            print(f"Created By: {item.created_by}")

        item.parent_id, record = self.get_uint(record)
        if self.log: 
            print(f"Parent Folder ID: {item.parent_id}")

        return item_id, item

    def analyze_gfi_record_R(self, rec_content):
        """
        Analysiert den Inhalt eines Record-Typs 'R' (Route) für GFI-Dateien.
        
        Args:
            rec_content (bytes): The content of the record
        """
        result = {}
        parent_item_id, record = self.get_uint(rec_content)
        if self.log: 
            print(f"Parent Item ID: {parent_item_id}")
        result['parent_item_id'] = parent_item_id

        route_name = self.get_string(rec_content)
        if self.log: 
            print(f"Route name: {route_name}")
        result["route_name"] = route_name

        route_origin = rec_content[self.record_pos]
        if route_origin == 0:
            route_origin_str = "user-defined"
        elif route_origin == 1:
            route_origin_str = "auto-generated"
        else:
            route_origin_str = "unknown"
        if self.log: 
            print(f"Route origin: {route_origin_str} ({route_origin})")
        result["route_origin"] = route_origin_str
        result["route_origin_value"] = route_origin
        
        return result
    
    def analyze_gfi_record_T(self, rec_content):
        """
        Analyzes the content of a record of type 'T' (Track) for GFI files.
        
        Args:
            rec_content (bytes): The content of the record
        Returns:
            tuple: A tuple containing the Parent Item ID and the Track Name.
        """
        record = rec_content

        parent_item_id, record = self.get_uint(record)
        if self.log: 
            print(f"Parent Item ID: {parent_item_id}")
        
        track_name, record = self.get_string(record)
        if self.log: 
            print(f"Track Name: {track_name}")

        return parent_item_id, track_name

    def analyze_gfi_record_W(self, rec_content):
        """
        Analyzes the content of a record of type 'W' (Waypoint) for GFI files.
        
        Args:
            rec_content (bytes): The content of the record
        Returns:
            tuple: A tuple containing the Parent Item ID, Waypoint Name, and Waypoint Class.
        """
        record = rec_content

        parent_item_id, record = self.get_uint(record)
        if self.log: 
            print(f"Parent Item ID: {parent_item_id}")

        waypoint_name, record = self.get_string(record)
        if self.log: 
            print(f"Waypoint Name: {waypoint_name}")

        waypoint_class, record = self.get_uint(record)
        if self.log: 
            print(f"Waypoint Class: {waypoint_class}")

        return parent_item_id, waypoint_name, waypoint_class

    def analyze_record_W(self, rec_content):
        """
        Analyzes the content of a record of type 'W' (Waypoint).
        
        Record Typ "W": Waypoint
        string Waypoint name
        uint Waypoint class
        position Position
        string Comment
        fdouble Proximity in meter
        uint Display mode
        uint Icon
        uint Color
        byte Unknown1=0
        flag Subclass1 present
        Subclass1 (only present if Subclass1 present flag set)
        flag Subclass2 present
        Subclass2 (only present if Subclass2 present flag set)
        fdouble Altitude in meter
        byte Unknown2=0
        uint Number of links
        Number of links x string Link
        fdouble Temperature in °C
        fint Creation time (Unix time, seconds since 1970-01-01)
        byte Unknown3=0
        flag Thumbnail present
        The next fields are only present when Thumbnail present flag is set:
        string Origin
        string UUID in format "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        8 x byte Unknown4=0
        
        Args:
            rec_content (bytes): the content of the record where the name (string) has already been read
        """        
        result = {}

        record = rec_content
        # Waypoint name (string) has already been read and removed by the __init__ function, so we do not read it again here
        #wp_name, record = self.get_string(record)
        # if self.log: 
        #     print(f"Waypoint name: {wp_name}")
        # result["wp_name"] = wp_name
        
        # Waypoint class (uint, 4 bytes) has already been read and removed by the __init__ function, so we do not read it again here
        #wp_class, record = self.get_uint(record)
        # if self.log: 
        #     print(f"Waypoint Class: {wp_class}")
        # result["wp_class"] = wp_class

        # latitude (4 bytes int)
        latitude, record = self.get_coord(record)
        if self.log: 
            print(f"Breitengrad: {latitude:.6f}°")
        result["latitude"] = latitude
 
        # longitude (4 bytes int)
        longitude, record = self.get_coord(record)
        if self.log: 
            print(f"Längengrad: {longitude:.6f}°")
        result["longitude"] = longitude

        # Comment (null terminated string)
        comment, record = self.get_string(record)
        if len(comment) > 1:
            if self.log: 
                print(f"Comment: {comment}")
            result["comment"] = comment

        # Proximity in meter (fdouble, 1+8 bytes)
        proximity, record = self.get_fdouble(record)
        if proximity is not None:
            if self.log: 
                print(f"Proximity: {proximity} m")
            result["proximity"] = proximity

        # Display mode (uint, 4 bytes)
        display_mode, record = self.get_displaymode(record)
        if display_mode is not None:
            if self.log: 
                print(f"Display mode: {display_mode}")
            result["display_mode"] = display_mode
        
        # Icon (uint, 4 bytes)
        icon, record = self.get_icon(record)
        if self.log: 
            print(f"Icon: {icon}")
        result["icon"] = icon

        # street (string null terminated)
        street, record = self.get_string(record)
        if len(street) > 1:
            if self.log: 
                print(f"Street: {street}")
            result["street"] = street

        # city (string null terminated)
        city, record = self.get_string(record)
        if len(city) > 1:
            if self.log: 
                print(f"City: {city}")
            result["city"] = city

        # state (string null terminated)
        state, record = self.get_string(record)
        if len(state) > 1:
            if self.log: 
                print(f"State: {state}")
            result["state"] = state

        # country (string null terminated)
        country, record = self.get_string(record)
        if len(country) > 1:
            if self.log: 
                print(f"Country: {country}")
            result["country"] = country

        # ZIP (string null terminated)
        zip_code, record = self.get_string(record)
        if len(zip_code) > 1:
            if self.log: 
                print(f"ZIP: {zip_code}")
            result["zip"] = zip_code

        # if the next byte is 0x01, then Subclass is present
        # skip subclass if present, because it is not known what it is (in total 24 bytes)
        if record[0] == 0x01:
            if self.log: 
                print(f"Subclass present, skipping 24 bytes")
            record = record[25:]  # skip the flag byte and the 24 bytes of subclass
        else:
            record = record[2:]  # skip the flag and the stop byte

        # altitude in meter (fdouble, 1+8 bytes)
        altitude, record = self.get_fdouble(record)
        if altitude is not None:
            if self.log: 
                print(f"Altitude: {altitude} m")
            result["altitude"] = altitude

        # depth in meter (fdouble, 1+8 bytes)
        depth, record = self.get_fdouble(record)
        if depth is not None:
            if self.log: 
                print(f"Depth: {depth} m")
            result["depth"] = depth

        # number of links (uint, 4 bytes)
        num_links, record = self.get_uint(record)
        if self.log: 
            print(f"Number of links: {num_links}")
        
        # read all links (null terminated strings)
        links = []
        for i in range(num_links):
            link, record = self.get_string(record)
            if self.log: 
                print(f"Link {i+1}: {link}")
            links.append(link)
        if len(links) > 0:
            result["links"] = links

        # temperature in °C (fdouble, 1+8 bytes)
        temperature, record = self.get_fdouble(record)
        if temperature is not None:
            if self.log: 
                print(f"Temperature: {temperature} °C")
            result["temperature"] = temperature

        # modification_date (fint, 1+4 bytes)
        modification_date_unix, record = self.get_fint(record)
        if type(modification_date_unix) == int:
            modification_date = self.unix_to_mez_iso8601(modification_date_unix)
            if self.log: 
                print(f"Modification date: {modification_date} ")
            result["modification_date"] = modification_date

        # skip 6 bytes (unknown)
        record = record[6:]

        # number of phone numbers (uint, 4 bytes)
        num_phone_numbers, record = self.get_uint(record)
        if self.log: 
            print(f"?Number of phone numbers?: {num_phone_numbers}")

        # read phone number (null terminated strings)
        # there is only one phone number, even if num_phone_numbers > 1, so we read only one phone number
        if num_phone_numbers > 0:
            phone_number, record = self.get_string(record)
            if self.log: 
                print(f"Phone number: {phone_number}")
            result["phone_numbers"] = phone_number
        
        # skip additional byte if num_phone_numbers > 0
        if num_phone_numbers > 0:
            record = record[1:]

        # creation_date (fint, 1+4 bytes)
        creation_date_unix, record = self.get_fint(record)
        if type(creation_date_unix) == int:
            creation_date = self.unix_to_mez_iso8601(creation_date_unix)
            if self.log: 
                print(f"Creation date: {creation_date} ")
            result["creation_date"] = creation_date

        # skip 3 bytes (unknown)
        record = record[3:]
        
        # number of categories (uint, 4 bytes)
        num_categories, record = self.get_uint(record)
        if self.log: 
            print(f"Number of categories: {num_categories}")
        
        # read all categories (null terminated strings)
        categories = []
        for i in range(num_categories):
            category, record = self.get_string(record)
            if self.log: 
                print(f"Category {i+1}: {category}")
            categories.append(category)
        if len(categories) > 0:
            result["categories"] = categories

        return result

    def analyze_record_R(self, rec_content):

        result = {}
        
        # Route name (string null terminated)
        rt_name = self.get_string(rec_content)
        if self.log: 
            print(f"Route name: {rt_name}")
        result["route_name"] = rt_name
        return result

    def analyze_record_T(self, rec_content):
        """
        Analysiert den Inhalt eines Record-Typs 'T' (Track).
        """
        result = {}
        
        # string Track name
        tr_name = self.get_string(rec_content)
        if self.log: 
            print(f"Track name: {tr_name}")
        result["track_name"] = tr_name

        # Track display (byte)
        tr_display = rec_content[self.record_pos]
        if self.log: 
            print(f"Track display: {tr_display}")
        result["track_display"] = tr_display
        self.record_pos += 1

        # skip next 4 bytes (unknown)
        self.record_pos += 4

        # track color (4 bytes  uint)
        tr_color = self.get_color(rec_content)
        if self.log: 
            print(f"Track color: {tr_color}")
        result["track_color"] = tr_color

        # number of links (4 bytes uint)
        num_links = self.get_uint(rec_content)
        if self.log: 
            print(f"Number of links: {num_links}")
        result["num_links"] = num_links

        # if num_links > 1 read num_links x string Link
        links = []
        for i in range(num_links):
            link = self.get_string(rec_content)
            if self.log: 
                print(f"Link {i+1}: {link}")
            links.append(link)
        result["links"] = links

        # read note string (null terminated)
        note = self.get_string(rec_content)
        if self.log: 
            print(f"Note: {note}")
        result["note"] = note

        # area in m² (double 8 bytes)
        area = self.get_double(rec_content)
        if self.log: 
            print(f"Area: {area} m²")
        result["area"] = area / 1000000  # convert to km²

        # fdouble, meaning not known, but seems to be a flag (byte) followed by a double value if true, otherwise empty
        unknown_fdouble = self.get_fdouble(rec_content)
        if self.log: 
            print(f"Unknown double value: {unknown_fdouble}")
        result["unknown_fdouble"] = unknown_fdouble

        # skip unknown byte 
        self.record_pos += 1

        # latitude max (4 bytes int)
        lat_max = self.get_coord(rec_content)
        if self.log: 
            print(f"Latitude max: {lat_max:.6f}°")
        result["latitude_max"] = lat_max

        # longitude max (4 bytes int)
        lon_max = self.get_coord(rec_content)
        if self.log: 
            print(f"Longitude max: {lon_max:.6f}°")
        result["longitude_max"] = lon_max

        # latitide min (4 bytes int)
        lat_min = self.get_coord(rec_content)
        if self.log: 
            print(f"Latitude min: {lat_min:.6f}°")
        result["latitude_min"] = lat_min

        # longitude min (4 bytes int)
        lon_min = self.get_coord(rec_content)
        if self.log: 
            print(f"Longitude min: {lon_min:.6f}°")
        result["longitude_min"] = lon_min

        # duration in seconds (fdouble 9 bytes)
        duration = self.get_fdouble(rec_content)
        if self.log: 
            print(f"Duration: {duration} seconds")
        result["duration"] = duration

        # length in meters (double 8 bytes)
        length = self.get_double(rec_content)
        if self.log: 
            print(f"Length: {length/1000} km")
        result["length"] = length / 1000  # convert to km

        # start time (unix time, seconds since 1970-01-01) (fint 5 bytes)
        start_time_unix = self.get_fint(rec_content)
        if type(start_time_unix) == int:
            start_time = self.unix_to_mez_iso8601(start_time_unix)
        else:
            start_time = 'not defined'
        if self.log: 
            print(f"Start time: {start_time} ")
        result["start_time"] = start_time

        # unknown 4 bytes
        unknown1 = self.get_uint(rec_content)
        if self.log: 
            print(f"Unknown 4 bytes: {unknown1}")
        result["unknown1"] = unknown1

        # number of track segments (uint 4 bytes)
        num_segments = self.get_uint(rec_content)
        if self.log: 
            print(f"Number of track segments: {num_segments}")
        result["num_segments"] = num_segments

        # read all track segments
        track_segments = []
        for i in range(num_segments):
            segment_bound, segment = self.get_track_segment(rec_content)
            if self.log: 
                print(f"Track segment {i+1}: {len(segment)} points")
            track_segments.append(segment)

        result["track_segments"] = track_segments

        # total number of points (uint 4 bytes)
        total_points = self.get_uint(rec_content)
        if self.log: 
            print(f"Total number of points: {total_points}")
        result["total_points"] = total_points

        # track uuid (null terminated string)
        track_uuid = self.get_string(rec_content)
        if self.log: 
            print(f"Track UUID: {track_uuid}")
        result["track_uuid"] = track_uuid

        #remaining_bytes = len(rec_content) - self.record_pos
        #print(f"remaining length: {remaining_bytes} bytes")
        #print(rec_content[self.record_pos:])

        return result

    def analyze_record_V(self, content):
        # string Map set name
        # Suche null-terminator
        result={}
        name_end = content.find(b'\x00')
        if name_end == -1:
            print("Fehler: Kein null-terminierter String für Mapset name gefunden")
            return
        ms_name = content[:name_end].decode('utf-8', errors='replace')
        if self.log: 
            print(f"Waypoint name: {ms_name}")
        result["mapset_name"] = ms_name
        if content[name_end+1] == 0:
            result["Name_flag"] = "user-named"
        else:
            result["Name_flag"] = "auto-named"
        return result

    def analyze_record_E(self, content):
        return {"E":len(content)}

    def analyze_record_X(self, content):
        return content[:-1].decode('utf-8', errors='replace')

    def build_folder_tree(self, folder, folder_path='./', build_tree=False):
        """
        Recursively builds the folder tree for a given folder downwards.
        Relies on the gfi_f_records and gfi_i_records dictionaries to find child folders and items.
        Adds the folder path to the Item Class objects for easier access to the full path of each item.
        
        Args:
            folder (Folder): The folder object to build the tree for.
            folder_path (str): The path folder where to build the folder structure. Default is local Folder './'.
        """

        path = folder_path + folder.name + '/'
        # create folder path if build_tree is True
        if build_tree:
            os.makedirs(path, exist_ok=True)
        for child in folder.children:
            print(child)
            child_id, child_type = child
            if child_type == 1:  # Folder
                self.build_folder_tree(self.gfi_f_records[child_id], path, build_tree=build_tree)
            elif child_type == 0:  # Item
                item = self.gfi_i_records[child_id] # get the item object
                # add the folder path to the item object
                item.folder_path = path + item.name + '/'
                # create destination folder if build_tree is True
                if build_tree:
                    os.makedirs(item.folder_path, exist_ok=True)
        return

    def get_string(self, data_bytes):
        """
        Reads a null-terminated string from the byte sequence data_bytes starting at the beginning of the sequence. The string is expected to be encoded in UTF-8.
        The function returns the extracted string and the remaining byte sequence after the null terminator.
        
        Args:
        data_bytes (bytes): The byte sequence containing the string
        
        Returns:
        str: The extracted string
        bytes: The remaining byte sequence after the string
        """
        end_pos = data_bytes.find(b'\x00')
        if end_pos == -1:
            print("Fehler: Kein null-terminierter String gefunden")
            return '', data_bytes

        result = data_bytes[:end_pos].decode('utf-8', errors='ignore')
        return result, data_bytes[end_pos + 1:]
    
    def get_double(self, data_bytes):
        """
        Converts the first 8 bytes of the byte sequence data_bytes into a floating-point number (double) using little-endian representation.
        
        Args:
        data_bytes (bytes): The byte sequence to be converted.

        Returns:
        float: the corresponding floating-point number
        bytes: the remaining byte sequence after the double
        """
        result = struct.unpack('<d', data_bytes[:8])[0]
        return result, data_bytes[8:]

    def get_fdouble(self, data_bytes):
        """
        Converts the first 9 bytes of the byte sequence data_bytes into a floating-point number (double) using little-endian representation.
        The first byte is interpreted as a flag indicating whether the following 8 bytes represent a valid double.
        
        Parameter:
        data_bytes (bytes): The byte sequence to be converted.
        
        Rückgabe:
        float:  The corresponding floating-point number, or None if the flag is not set
        """
        flag = data_bytes[0]
        if flag:
            return self.get_double(data_bytes[1:])
        else:
            return None, data_bytes[1:]
        
    def get_uint(self, data_bytes):
        """
        Converts the next 4 bytes of the byte sequence data_bytes into an unsigned integer using little-endian representation.
        
        Args:
        data_bytes (bytes): The byte sequence to be converted.

        Returns:
        int: The corresponding integer.
        bytes: The remaining byte sequence after the integer.
        """
        if len(data_bytes) < 4:
            print("Error: byte sequence too short for Uint conversion")
            return
        result = int.from_bytes(data_bytes[:4], byteorder='little', signed=False)
        return result, data_bytes[4:] if len(data_bytes) > 4 else b''

    def get_int(self, data_bytes):
        """
        Converts the first 4 bytes of the byte sequence data_bytes into a signed integer using little-endian representation.

        Parameter:
        data_bytes (bytes): The byte sequence to be converted.

        Returns:
        int: The corresponding integer.
        bytes: The remaining byte sequence after the integer.
        """
        if len(data_bytes) < 4:
            print("Error: byte sequence too short for Int conversion")
            return
        result = int.from_bytes(data_bytes[:4], byteorder='little', signed=True)
        return result, data_bytes[4:] if len(data_bytes) > 4 else b''

    def get_fint(self, data_bytes):
        """
        Converts the first 5 bytes of the byte sequence data_bytes into a signed integer using little-endian representation.
        The first byte is interpreted as a flag indicating whether the following 4 bytes represent a valid integer.
        
        Args:
        data_bytes (bytes): The byte sequence to be converted.
        
        Returns:
        int: The corresponding integer, or None if the flag is not set.
        bytes: The remaining byte sequence after the integer.
        """
        flag = data_bytes[0]
        if flag:
            if len(data_bytes) < 5:
                print("Error: byte sequence too short for FInt conversion")
                return
            result = int.from_bytes(data_bytes[1:5], byteorder='little', signed=True)
            return result, data_bytes[5:]
        else:
            return None, data_bytes[1:]

    def get_coord(self, data_bytes):
        """
        Konvertiert die ersten 4 Byte der Byte-Sequenz data_bytes in eine Koordinate (latitude oder longitude) unter Verwendung der little-endian-Darstellung.
        
        Parameter:
        data_bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        float: Die entsprechende Koordinate in Grad
        """
        position, remaining_bytes = self.get_int(data_bytes)
        return position * 360.0 / (2**32), remaining_bytes
    
    def get_displaymode(self, data_bytes):
        """
        Returns the meaning of the Displaymode ID.

        Parameter:
        data_bytes (bytes): The byte sequence containing the ID

        Returns:
        str: The corresponding meaning as a string
        """
        meaning_map = {
            0: "Symbol",
            1: "Symbol & Name",
            2: "Symbol & Comment",
            3: "Image",
            4: "Image & Name"
        }

        value, remaining_bytes = self.get_uint(data_bytes)
        if value in meaning_map:
            return meaning_map[value], remaining_bytes
        else:
            return f"invalid Displaymode ID: {value}. Valid IDs are 0 to 4.", remaining_bytes

    def get_color(self, data_bytes):
        """
        Returns the color of a given ID.
        
        Parameter:
        data_bytes (bytes): The byte sequence containing the ID
        
        Returns:
        str: The corresponding color as a string
        
        """
        color_map = [
            "Default",
            "Black",
            "Dark red",
            "Dark green",
            "Dark yellow",
            "Dark blue",
            "Dark magenta",
            "Dark cyan",
            "Light grey",
            "Dark grey",
            "Red",
            "Green",
            "Yellow",
            "Blue",
            "Magenta",
            "Cyan",
            "White",
            "Transparent"
        ]
        
        id, remaining_bytes = self.get_uint(data_bytes)
        if 0 <= id < len(color_map):
            return color_map[id], remaining_bytes
        else:
            return f"invalid ID: {id}", remaining_bytes
            
    def get_icon(self, data_bytes):
        """
        Returns the name of an icon based on its ID.
        
        Parameter:
        data_bytes (bytes): The byte sequence containing the ID
        
        Returns:
        str: The name of the icon as a string
        """
        icon_list = [
            "Anchor", "Bell", "DiamondGrn", "DiamondRed", "Dive1", "Dive2", "Dollar", "Fish", "Fuel", "Horn",
            "House", "Knife", "Light", "Mug", "Skull", "SquareGrn", "SquareRed", "Wbuoy", "WptDot", "Wreck",
            "Mob", "BuoyAmbr", "BuoyBlck", "BuoyBlue", "BuoyGrn", "BuoyGrnRed", "BuoyGrnWht", "BuoyOrng", "BuoyRed",
            "BuoyRedGrn", "BuoyRedWht", "BuoyViolet", "BuoyWht", "BuoyWhtGrn", "BuoyWhtRed", "Dot", "Rbcn", "BoatRamp",
            "Camp", "Restrooms", "Showers", "DrinkingWtr", "Phone", "1stAid", "Info", "Parking", "Park", "Picnic",
            "Scenic", "Skiing", "Swimming", "Dam", "Controlled", "Danger", "Restricted", "Ball", "Car", "Deer",
            "ShpngCart", "Lodging", "Mine", "TrailHead", "TruckStop", "UserExit", "Flag", "CircleX", "MiMrkr", "Trcbck",
            "Golf", "SmlCty", "MedCty", "LrgCty", "CapCty", "AmusePk", "Bowling", "CarRental", "CarRepair", "Fastfood",
            "Fitness", "Movie", "Museum", "Pharmacy", "Pizza", "PostOfc", "RvPark", "School", "Stadium", "Store", "Zoo",
            "GasPlus", "Faces", "WeighSttn", "TollBooth", "Bridge", "Building", "Cemetery", "Church", "Civil", "Crossing",
            "HistTown", "Levee", "Military", "OilField", "Tunnel", "Beach", "Forest", "Summit", "Airport", "Heliport",
            "Private", "SoftFld", "TallTower", "ShortTower", "Glider", "Ultralight", "Parachute", "Seaplane", "Geocache",
            "GeocacheFound", "ContactAfro", "ContactAlien", "ContactBalCap", "ContactBigEar", "ContactBiker", "ContactBug",
            "ContactCat", "ContactDog", "ContactDreads", "ContactFem1", "ContactFem2", "ContactFem3", "ContactGoatee",
            "ContactKungFu", "ContactPig", "ContactPirate", "ContactRanger", "ContactSmiley", "ContactSpike", "ContactSumo",
            "WaterHydrant", "FlagRed", "FlagBlue", "FlagGreen", "PinRed", "PinBlue", "PinGreen", "BlockRed", "BlockBlue",
            "BlockGreen", "BikeTrail", "FHSFacility", "PoliceStation", "SkiResort", "IceSkating", "Wrecker", "NoAnchor",
            "Beacon", "CoastGuard", "Reef", "WeedBed", "DropOff", "Dock", "Marina", "BaitTackle", "Stump", "CircleRed",
            "CircleGreen", "CircleBlue", "DiamondBlue", "OvalRed", "OvalGreen", "OvalBlue", "RectRed", "RectGreen", "RectBlue",
            "SquareBlue", "LetterARed", "LetterAGreen", "LetterABlue", "LetterBRed", "LetterBGreen", "LetterBBlue", "LetterCRed",
            "LetterCGreen", "LetterCBlue", "LetterDRed", "LetterDGreen", "LetterDBlue", "Number0Red", "Number0Green", "Number0Blue",
            "Number1Red", "Number1Green", "Number1Blue", "Number2Red", "Number2Green", "Number2Blue", "Number3Red", "Number3Green",
            "Number3Blue", "Number4Red", "Number4Green", "Number4Blue", "Number5Red", "Number5Green", "Number5Blue", "Number6Red",
            "Number6Green", "Number6Blue", "Number7Red", "Number7Green", "Number7Blue", "Number8Red", "Number8Green", "Number8Blue",
            "Number9Red", "Number9Green", "Number9Blue", "TriangleBlue", "TriangleGreen", "TriangleRed", "ContactBlonde", "ContactClown",
            "ContactGlasses", "ContactPanda", "MultiCache", "LetterboxCache", "PuzzleCache", "Library", "BusStation", "CityHall",
            "Winery", "ATV", "BigGame", "Blind", "BloodTrail", "Cover", "Covey", "FoodSource", "Furbearer", "Lodge", "SmallGame",
            "AnimalTracks", "TreedQuarry", "TreeStand", "Truck", "UplandGame", "Waterfowl", "WaterSource"
        ]
        
        id, remaining_bytes = self.get_uint(data_bytes)
        if 0 <= id < len(icon_list):
            return icon_list[id], remaining_bytes
        else:
            return "Default", remaining_bytes

    def get_track_segment(self, data_bytes):
        """
        Return the track points.
        
        Parameter:
        data_bytes (bytes): The byte sequence containing the ID
        
        Returns:
        tuple: A tuple containing the track bounds dictionary, a list of track points, and the remaining bytes.
        """
        # track starts with an unknown byte, so we skip that
        self.record_pos += 1

        # get max / min position
        latitude_max, remaining_bytes = self.get_coord(data_bytes)
        longitude_max, remaining_bytes = self.get_coord(remaining_bytes)
        latitude_min, remaining_bytes = self.get_coord(remaining_bytes)
        longitude_min, remaining_bytes = self.get_coord(remaining_bytes)

        track_bounds = {
            "latitude_max": latitude_max,
            "longitude_max": longitude_max,
            "latitude_min": latitude_min,
            "longitude_min": longitude_min
        }
        #print(f"Track segment bounds: lat {latitude_min:.6f} to {latitude_max:.6f}, lon {longitude_min:.6f} to {longitude_max:.6f}")

        num_points, remaining_bytes = self.get_uint(remaining_bytes)
        #print(f"Number of track points: {num_points}")

        # read all track points
        track_points = []
        for i in range(num_points):
            latitude, remaining_bytes = self.get_coord(remaining_bytes)
            longitude, remaining_bytes = self.get_coord(remaining_bytes)
            track_points.append((latitude, longitude))

        return track_bounds, track_points, remaining_bytes

    def analyze_recordtypes(self, records):
        record_types = {}
        for r in records:
            if r[0] in record_types:
                record_types[r[0]] += 1
            else:
                record_types[r[0]] = 1
        return record_types
                
    @staticmethod
    def unix_to_mez_iso8601(timestamp):
        """
        Convert a Unix timestamp to ISO 8601 format (yyyy-mm-ddThh:mm:ssZ) in MEZ/CEST timezone.
        
        Args:
            timestamp: Unix timestamp (seconds since 1970-01-01 00:00:00 UTC)
        
        Returns:
            String in format: yyyy-mm-ddThh:mm:ssZ (with Z representing MEZ/CEST)
        
        Note: The 'Z' suffix is used here to indicate the time is in the MEZ/CEST timezone,
        though strictly speaking 'Z' means UTC in ISO 8601. For proper timezone indication,
        consider using '+01:00' or '+02:00' instead of 'Z'.
        
        Examples:
            >>> unix_to_mez_iso8601(0)
            '1970-01-01T01:00:00Z'  # CET (MEZ in winter)
            >>> unix_to_mez_iso8601(1625097600)  # 2021-06-30 00:00:00 UTC
            '2021-06-30T02:00:00Z'  # CEST (MEZ in summer)
        """
        # Define the MEZ/CEST timezone (Europe/Berlin covers this)
        mezeastern = pytz.timezone('Europe/Berlin')
        
        # Convert Unix timestamp to datetime in UTC first, then convert to MEZ/CEST
        utc_dt = datetime.fromtimestamp(timestamp, tz=pytz.utc)
        mezeastern_dt = utc_dt.astimezone(mezeastern)
        
        # Format as ISO 8601 string with 'Z' suffix (though technically should be offset)
        # Using 'Z' as requested, but note that it's not strictly correct for non-UTC time
        return mezeastern_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    @staticmethod
    def dict_to_gpx_waypoint(data_dict, waypoint_name="Waypoint"):
        """
        Convert a dictionary to Garmin GPX waypoint XML with extensions.
        
        Args:
            data_dict: Dictionary containing waypoint data
            waypoint_name: Name for the waypoint (default: "Waypoint")
        
        Returns:
            String containing the GPX XML
        """
        
        # Define namespaces
        namespaces = {
            'gpx': 'http://www.topografix.com/GPX/1/1',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'wptx1': 'http://www.garmin.com/xmlschemas/WaypointExtension/v1',
            'gpxtrx': 'http://www.garmin.com/xmlschemas/GpxExtensions/v3',
            'gpxtpx': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1',
            'gpxx': 'http://www.garmin.com/xmlschemas/GpxExtensions/v3',
            'trp': 'http://www.garmin.com/xmlschemas/TripExtensions/v1',
            'adv': 'http://www.garmin.com/xmlschemas/AdventuresExtensions/v1',
            'prs': 'http://www.garmin.com/xmlschemas/PressureExtension/v1',
            'tmd': 'http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1',
            'vptm': 'http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1',
            'ctx': 'http://www.garmin.com/xmlschemas/CreationTimeExtension/v1',
            'gpxacc': 'http://www.garmin.com/xmlschemas/AccelerationExtension/v1',
            'gpxpx': 'http://www.garmin.com/xmlschemas/PowerExtension/v1',
            'vidx1': 'http://www.garmin.com/xmlschemas/VideoExtension/v1'
        }
        
        # Register namespaces for proper prefix handling
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)
        
        # Create root GPX element with all required attributes
        gpx = ET.Element('gpx', {
            'creator': 'Garmin Desktop App',
            'version': '1.1',
            'xsi:schemaLocation': 'http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/WaypointExtension/v1 http://www8.garmin.com/xmlschemas/WaypointExtensionv1.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www8.garmin.com/xmlschemas/TrackPointExtensionv1.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www8.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/ActivityExtension/v1 http://www8.garmin.com/xmlschemas/ActivityExtensionv1.xsd http://www.garmin.com/xmlschemas/AdventuresExtensions/v1 http://www8.garmin.com/xmlschemas/AdventuresExtensionv1.xsd http://www.garmin.com/xmlschemas/PressureExtension/v1 http://www8.garmin.com/xmlschemas/PressureExtensionv1.xsd http://www.garmin.com/xmlschemas/TripExtensions/v1 http://www.garmin.com/xmlschemas/TripExtensionsv1.xsd http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1 http://www.garmin.com/xmlschemas/TripMetaDataExtensionsv1.xsd http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1 http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensionsv1.xsd http://www.garmin.com/xmlschemas/CreationTimeExtension/v1 http://www.garmin.com/xmlschemas/CreationTimeExtensionsv1.xsd http://www.garmin.com/xmlschemas/AccelerationExtension/v1 http://www.garmin.com/xmlschemas/AccelerationExtensionv1.xsd http://www.garmin.com/xmlschemas/PowerExtension/v1 http://www.garmin.com/xmlschemas/PowerExtensionv1.xsd http://www.garmin.com/xmlschemas/VideoExtension/v1 http://www.garmin.com/xmlschemas/VideoExtensionv1.xsd',
            'xmlns': 'http://www.topografix.com/GPX/1/1',
            'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xmlns:wptx1': 'http://www.garmin.com/xmlschemas/WaypointExtension/v1',
            'xmlns:gpxtrx': 'http://www.garmin.com/xmlschemas/GpxExtensions/v3',
            'xmlns:gpxtpx': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1',
            'xmlns:gpxx': 'http://www.garmin.com/xmlschemas/GpxExtensions/v3',
            'xmlns:trp': 'http://www.garmin.com/xmlschemas/TripExtensions/v1',
            'xmlns:adv': 'http://www.garmin.com/xmlschemas/AdventuresExtensions/v1',
            'xmlns:prs': 'http://www.garmin.com/xmlschemas/PressureExtension/v1',
            'xmlns:tmd': 'http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1',
            'xmlns:vptm': 'http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1',
            'xmlns:ctx': 'http://www.garmin.com/xmlschemas/CreationTimeExtension/v1',
            'xmlns:gpxacc': 'http://www.garmin.com/xmlschemas/AccelerationExtension/v1',
            'xmlns:gpxpx': 'http://www.garmin.com/xmlschemas/PowerExtension/v1',
            'xmlns:vidx1': 'http://www.garmin.com/xmlschemas/VideoExtension/v1'
        })
        
        # Create metadata
        metadata = ET.SubElement(gpx, 'metadata')
        link = ET.SubElement(metadata, 'link', {'href': 'http://www.garmin.com'})
        text = ET.SubElement(link, 'text')
        text.text = 'Garmin International'
        
        # Current time for metadata time element
        current_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        time_elem = ET.SubElement(metadata, 'time')
        time_elem.text = current_time
        
        # Bounds element (using the waypoint coordinates)
        lat = data_dict.get('latitude', 0)
        lon = data_dict.get('longitude', 0)
        bounds = ET.SubElement(metadata, 'bounds', {
            'maxlat': str(lat),
            'maxlon': str(lon),
            'minlat': str(lat),
            'minlon': str(lon)
        })
        
        # Create waypoint element
        wpt = ET.SubElement(gpx, 'wpt', {
            'lat': str(lat),
            'lon': str(lon)
        })
        
        # Elevation
        if 'altitude' in data_dict:
            ele = ET.SubElement(wpt, 'ele')
            ele.text = str(data_dict['altitude'])
        
        # Time (using creation_date if available, otherwise current time)
        if 'creation_date' in data_dict:
            time_elem = ET.SubElement(wpt, 'time')
            time_elem.text = data_dict['creation_date']
        
        # Name
        name = ET.SubElement(wpt, 'name')
        name.text = waypoint_name
        
        # Comment and Description (handle multi-line comments)
        if 'comment' in data_dict:
            cmt = ET.SubElement(wpt, 'cmt')
            cmt.text = data_dict['comment'].replace('\r\n', '\n')
            
            desc = ET.SubElement(wpt, 'desc')
            desc.text = data_dict['comment'].replace('\r\n', '\n')
        
        # Links
        if 'links' in data_dict and isinstance(data_dict['links'], list):
            for link_url in data_dict['links']:
                link_elem = ET.SubElement(wpt, 'link', {'href': str(link_url)})
        
        # Symbol (convert icon to Garmin symbol format)
        if 'icon' in data_dict:
            sym = ET.SubElement(wpt, 'sym')
            # Map common icons to Garmin symbols
            icon_map = {
                'House': 'Residence',
                'Car': 'Gas Station',
                'Tree': 'Campground',
                'Flag': 'Flag',
                'Star': 'Star',
                'Camera': 'Camera',
                'Phone': 'Telephone',
                'Medical': 'Medical Facility'
            }
            sym.text = icon_map.get(data_dict['icon'], data_dict['icon'])
        
        # Type
        type_elem = ET.SubElement(wpt, 'type')
        type_elem.text = 'user'
        
        # Create extensions
        extensions = ET.SubElement(wpt, 'extensions')
        
        # Garmin GPX Extensions (gpxx:WaypointExtension)
        gpxx_ext = ET.SubElement(extensions, 'gpxx:WaypointExtension')
        
        # Proximity
        if 'proximity' in data_dict:
            proximity = ET.SubElement(gpxx_ext, 'gpxx:Proximity')
            proximity.text = str(int(data_dict['proximity']))
        
        # Temperature
        if 'temperature' in data_dict:
            temperature = ET.SubElement(gpxx_ext, 'gpxx:Temperature')
            temperature.text = str(int(data_dict['temperature']))
        
        # Depth
        if 'depth' in data_dict:
            depth = ET.SubElement(gpxx_ext, 'gpxx:Depth')
            depth.text = str(int(data_dict['depth']))
        
        # Display Mode
        if 'display_mode' in data_dict:
            display_mode = ET.SubElement(gpxx_ext, 'gpxx:DisplayMode')
            # Convert "Symbol & Comment" to "SymbolAndDescription"
            mode_map = {
                'Symbol & Comment': 'SymbolAndDescription',
                'Symbol Only': 'SymbolOnly',
                'Comment Only': 'DescriptionOnly'
            }
            display_mode.text = mode_map.get(data_dict['display_mode'], data_dict['display_mode'])
        
        # Categories
        if 'categories' in data_dict and isinstance(data_dict['categories'], list):
            categories = ET.SubElement(gpxx_ext, 'gpxx:Categories')
            for category in data_dict['categories']:
                cat_elem = ET.SubElement(categories, 'gpxx:Category')
                cat_elem.text = category
        
        # Address
        address_fields = ['street', 'city', 'state', 'country', 'zip']
        if any(field in data_dict for field in address_fields):
            address = ET.SubElement(gpxx_ext, 'gpxx:Address')
            
            if 'street' in data_dict:
                street = ET.SubElement(address, 'gpxx:StreetAddress')
                street.text = data_dict['street']
            
            if 'city' in data_dict:
                city = ET.SubElement(address, 'gpxx:City')
                city.text = data_dict['city']
            
            if 'state' in data_dict:
                state = ET.SubElement(address, 'gpxx:State')
                state.text = data_dict['state']
            
            if 'country' in data_dict:
                country = ET.SubElement(address, 'gpxx:Country')
                country.text = data_dict['country']
            
            if 'zip' in data_dict:
                postal_code = ET.SubElement(address, 'gpxx:PostalCode')
                postal_code.text = data_dict['zip']
        
        # Phone Number
        if 'phone_numbers' in data_dict:
            phone = ET.SubElement(gpxx_ext, 'gpxx:PhoneNumber')
            phone.text = data_dict['phone_numbers']
        
        # WaypointExtension (wptx1)
        wptx1_ext = ET.SubElement(extensions, 'wptx1:WaypointExtension')
        
        # Same fields for wptx1 extension
        if 'proximity' in data_dict:
            proximity = ET.SubElement(wptx1_ext, 'wptx1:Proximity')
            proximity.text = str(int(data_dict['proximity']))
        
        if 'temperature' in data_dict:
            temperature = ET.SubElement(wptx1_ext, 'wptx1:Temperature')
            temperature.text = str(int(data_dict['temperature']))
        
        if 'depth' in data_dict:
            depth = ET.SubElement(wptx1_ext, 'wptx1:Depth')
            depth.text = str(int(data_dict['depth']))
        
        if 'display_mode' in data_dict:
            display_mode = ET.SubElement(wptx1_ext, 'wptx1:DisplayMode')
            mode_map = {
                'Symbol & Comment': 'SymbolAndDescription',
                'Symbol Only': 'SymbolOnly',
                'Comment Only': 'DescriptionOnly'
            }
            display_mode.text = mode_map.get(data_dict['display_mode'], data_dict['display_mode'])
        
        if 'categories' in data_dict and isinstance(data_dict['categories'], list):
            categories = ET.SubElement(wptx1_ext, 'wptx1:Categories')
            for category in data_dict['categories']:
                cat_elem = ET.SubElement(categories, 'wptx1:Category')
                cat_elem.text = category
        
        if any(field in data_dict for field in address_fields):
            address = ET.SubElement(wptx1_ext, 'wptx1:Address')
            
            if 'street' in data_dict:
                street = ET.SubElement(address, 'wptx1:StreetAddress')
                street.text = data_dict['street']
            
            if 'city' in data_dict:
                city = ET.SubElement(address, 'wptx1:City')
                city.text = data_dict['city']
            
            if 'state' in data_dict:
                state = ET.SubElement(address, 'wptx1:State')
                state.text = data_dict['state']
            
            if 'country' in data_dict:
                country = ET.SubElement(address, 'wptx1:Country')
                country.text = data_dict['country']
            
            if 'zip' in data_dict:
                postal_code = ET.SubElement(address, 'wptx1:PostalCode')
                postal_code.text = data_dict['zip']
        
        if 'phone_numbers' in data_dict:
            phone = ET.SubElement(wptx1_ext, 'wptx1:PhoneNumber')
            phone.text = data_dict['phone_numbers']
        
        # CreationTimeExtension
        if 'creation_date' in data_dict:
            ctx_ext = ET.SubElement(extensions, 'ctx:CreationTimeExtension')
            creation_time = ET.SubElement(ctx_ext, 'ctx:CreationTime')
            creation_time.text = data_dict['creation_date']
        
        # Convert to string with proper formatting
        xml_string = ET.tostring(gpx, encoding='unicode')
        
        # Add XML declaration and pretty print
        final_xml = '<?xml version="1.0" encoding="utf-8"?>' + xml_string
        
        # Optional: pretty print (requires xml.dom.minidom)
        try:
            from xml.dom import minidom
            dom = minidom.parseString(final_xml)
            final_xml = dom.toprettyxml(indent="  ")
        except:
            pass  # Use the non-pretty version if minidom fails
        
        return final_xml

    def write_waypoint(self, file_path, waypoint_name, waypoint_dict):
        """
        Write a waypoint to a GPX file.
        Uses the dict_to_gpx_waypoint method to convert the waypoint dictionary to GPX format and writes it to the specified file path.
        Needs to be called with a valid waypoint dictionary containing at least latitude and longitude.
        Mapping the waypoint dictionary to the GPX format is handled by the dict_to_gpx_waypoint method, which also includes Garmin-specific extensions.
        
        Args:
            file_path: The path to the GPX file to write.
            waypoint_name: The name of the waypoint.
            waypoint_dict: A dictionary containing waypoint data.
        """
        gpx_data = self.dict_to_gpx_waypoint(waypoint_dict, waypoint_name=waypoint_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(gpx_data)
        if self.log:
            print(f"Waypoint '{waypoint_name}' written to {file_path}")

    def restore_waypoints(self, base_dir='./'):
        """
        Restore waypoints from the Garmin device to GPX files.
        This method iterates through the waypoints stored in the Garmin device, converts each waypoint to GPX format using the dict_to_gpx_waypoint method, and writes them to individual GPX files in a specified directory.
        The directory structure is created based on the folder hierarchy of the Garmin device, and each waypoint is saved with its name as the filename.
        """
        # Create the directory tree from the gfi_frcords and the gfi_i_records
        self.build_folder_tree(self.gfi_f_records['root'], folder_path=base_dir, build_tree=True)

        # Iterate through all waypoints in the Garmin device
        for Item_id, waypoint_name, _ in self.gfi_w_records:
            print(f"Restoring waypoint: {waypoint_name} (ID: {Item_id})")

            # replace ocurence of '/' in waypoint_name with '_' to avoid issues with file paths
            valid_waypoint_name = waypoint_name.replace('/', '_')   

            # Get corresponding Item (= destination folder) for the waypoint from gfi_i_records
            Item = self.gfi_i_records[Item_id]

            # create the file path for the waypoint GPX file
            file_path = Item.folder_path + f"{valid_waypoint_name}.gpx"

            # convert to dictionary using analyze_record_W
            wp_dict = self.analyze_record_W(self.gdb_w_records[waypoint_name])

            # Convert waypoint to GPX and write to file
            self.write_waypoint(file_path, valid_waypoint_name, wp_dict)
