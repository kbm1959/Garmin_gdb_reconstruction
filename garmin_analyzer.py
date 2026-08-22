"""
Dieses Modul enthält die Klasse GarminAnalyzer, die für die Analyse von Garmin Datenbanken im .gdb-Format entwickelt wurde.
Die Klasse bietet Funktionen zum Lesen und Interpretieren der Datei, einschließlich der Extraktion von Header-Informationen, 
Record-Typen und deren Inhalte. Sie unterstützt die Analyse von Waypoints, Routen, Tracks und anderen relevanten Daten, 
die in Garmin-Dateien enthalten sind.
Die Klasse ist so konzipiert, dass sie robust gegenüber verschiedenen Dateiformaten und -strukturen ist und bietet detaillierte Ausgaben zur Unterstützung der Analyse.

Basierend auf der Spezifikation:
https://www.memotech.franken.de/FileFormats/Garmin_MPS_GDB_and_GFI_Format.pdf

Beispiel:
    analyzer = GarminAnalyzer("example.gdb", log_records=True)
    analyzer.analyze_recordtypes(analyzer.records)

"""
import struct
import datetime
import sys
from datetime import datetime
import pytz

class GarminAnalyzer:

    def __init__(self, filename, log_records=False, read_all_records=True):
        """
        Öffnet eine Datei und analysiert ihre Struktur gemäß dem angegebenen Format.
        
        Args:
            filename (str): Pfad zur Datei
            log_records (bool): Ob die Record-Inhalte ausgegeben werden sollen
            read_all_records (bool): Ob alle Records gelesen werden sollen
        """
        try:
            with open(filename, 'rb') as file:
                self.data = file.read()
                print(f"Analyse der Datei: {filename}")
                print(f"Gesamtgröße: {len(self.data)} Bytes")
                print("=" * 50)

                self.log = log_records
                self.filename = filename
                #data_pos is tracked by function get_data (see below)
                self.data_pos = 0
                
                if len(self.data) < 12:  # Mindestlänge für erste Record-Struktur
                    print("Daten zu kurz für gültige Struktur")
                    return
                
                # Analyze Header
                # Byte 1-4: Signature (string)
                self.signature = self.get_bytes(4).decode('utf-8', errors='ignore')
                print(f"Signature: {self.signature}")
                
                # Byte 5-6: Primary Version (unsigned short, little-endian)
                version = int.from_bytes(self.get_bytes(2), byteorder='little')
                # Berechnung von Major und Minor mit Modulo 100
                major = version // 100
                minor = version % 100
                print(f"Primary version: {major}.{minor} (0x{version:04x})")

                # read the first two records
                #record_1: Record 'D' – File format version
                self.analyze_record(self.read_record())

                #record_2: Record 'A' – File author information
                self.analyze_record(self.read_record())

                # read the application string
                self.application = self.read_rstring()
                print(f"Application: {self.application} ")

                # now read all the remaining records
                self.records = []
                if read_all_records:
                    while self.data_pos < len(self.data):
                        self.records.append(self.read_record())
                
                    # analyze the record types
                    self.record_types = self.analyze_recordtypes(self.records)    
                    print(f"\n{len(self.record_types)} unterschiedliche Record-Typen gefunden.")
                    print("-" * 40)
                    for i, (record_type, count) in enumerate(sorted(self.record_types.items()), 1):
                        print(f"{i:2d}. '{record_type}' - {count} mal")

                    print(f"{len(self.records)} records successfully loaded.")
                else:
                    print("Records wurden nicht geladen, da read_all_records auf False gesetzt ist.")

        except FileNotFoundError:
            print(f"Fehler: Die Datei '{filename}' wurde nicht gefunden.")
        except PermissionError:
            print(f"Fehler: Keine Berechtigung zum Zugriff auf '{filename}'.")
#        except Exception as e:
#            exc_type, exc_value, exc_tb = sys.exc_info()
#            print("Fehler:", e)
#            print("Datei:", exc_tb.tb_frame.f_code.co_filename)
#            print("Zeile:", exc_tb.tb_lineno)

    def get_bytes(self, n_bytes):
        """
        returns n_bytes bytes from self.data starting at position self.data_pos
        and increments the data position
        """
        self.data_pos += n_bytes
        return self.data[self.data_pos - n_bytes : self.data_pos]
        
    def read_record(self):
        """
        Liest einen einzelnen Record aus den Daten self.data ab der Position self.data_pos.
                
        Returns:
            tuple: (record_type, record_length, record_content)
        """
        if self.data_pos + 4 > len(self.data):
            return 'n', 0, b''
        
        # Lese Record-Länge (4 Byte, little-endian)
        record_length = int.from_bytes(self.get_bytes(4), byteorder='little')
        
        # Prüfen, ob genug Bytes für den Record vorhanden sind
        if self.data_pos + 1 + record_length > len(self.data):
            return 'n', 0, b''
        
        # Lese Record-Type (1 Byte)
        record_type = self.get_bytes(1).decode('ascii', errors='ignore')
        
        # Lese Record-Inhalt
        record_content = self.get_bytes(record_length)
                
        return record_type, record_length, record_content

    def read_rstring(self):
        """
        reads a null terminated string from the bytestream self.data starting at self.data_pos
        """
        pos = self.data_pos
        data_len = len(self.data)
        while  pos < data_len and self.data[pos] != 0:
            pos += 1
            
        string_data = self.get_bytes(pos - self.data_pos)
        # data_pos was incremented by get_bytes, but increment self.data_pos to skip string termination 0 byte
        self.data_pos += 1
        
        return string_data.decode('utf-8', errors='ignore')
        
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

    def analyze_gfi_record_A(self, rec_content, short = False):
        """
        Identisch mit analyze_record_A, aber für GFI-Dateien.

        Args:
            content (bytes): Der Inhalt des Records
        """
        return self.analyze_record_A(rec_content, short)
    
    def analyze_gfi_record_D(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'D' (File format) für GFI-Dateien.
        
        Identisch mit analyze_record_D, aber für GFI-Dateien.
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        return self.analyze_record_D(rec_content, short)

    def analyze_gfi_record_F(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'F' (Folder Information) für GFI-Dateien.
                
        Args:
            content (bytes): Der Inhalt des Records
        """
        result = {}
        folder_id = self.get_uint(rec_content)
        if self.log: 
            print(f"Folder ID: {folder_id}")
        result['folder_id'] = folder_id

        folder_name = self.get_string(rec_content)
        if self.log: 
            print(f"Folder Name: {folder_name}")
        result['folder_name'] = folder_name

        parent_folder_id = self.get_uint(rec_content)
        if self.log: 
            print(f"Parent Folder ID: {parent_folder_id}")
        result['parent_folder_id'] = parent_folder_id

        n_subordinated = self.get_uint(rec_content)
        if self.log: 
            print(f"Number of Subordinated Folders: {n_subordinated}")
        result['n_subordinated_folders'] = n_subordinated

        sub_items = {}
        for i in range(n_subordinated):
            sub_item_type = self.get_uint(rec_content)
            sub_item_id = self.get_uint(rec_content)
            if self.log: 
                print(f"Subordinated Folder {i+1}: ID={sub_item_id}, Type={sub_item_type}")
            sub_items[sub_item_id] = sub_item_type
        result['sub_items'] = sub_items

        return result

    def analyze_gfi_record_I(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'I' (Item Information) für GFI-Dateien.
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        result = {}
        item_id = self.get_uint(rec_content)
        if self.log: 
            print(f"Item ID: {item_id}")
        result['item_id'] = item_id

        item_name = self.get_string(rec_content)
        if self.log: 
            print(f"Item Name: {item_name}")
        result['item_name'] = item_name

        created_by = self.get_uint(rec_content)
        if self.log: 
            print(f"Created By: {created_by}")
        result['created_by'] = created_by

        parent_folder_id = self.get_uint(rec_content)
        if self.log: 
            print(f"Parent Folder ID: {parent_folder_id}")
        result['parent_folder_id'] = parent_folder_id

        return result

    def analyze_gfi_record_R(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'R' (Route) für GFI-Dateien.
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        result = {}
        parent_item_id = self.get_uint(rec_content)
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
    
    def analyze_gfi_record_T(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'T' (Track) für GFI-Dateien.
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        result = {}

        parent_item_id = self.get_uint(rec_content)
        if self.log: 
            print(f"Parent Item ID: {parent_item_id}")
        result['parent_item_id'] = parent_item_id

        track_name = self.get_string(rec_content)
        if self.log: 
            print(f"Track Name: {track_name}")
        result['track_name'] = track_name

        return result

    def analyze_gfi_record_W(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'W' (Waypoint) für GFI-Dateien.
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        result = {}

        parent_item_id = self.get_uint(rec_content)
        if self.log: 
            print(f"Parent Item ID: {parent_item_id}")
        result['parent_item_id'] = parent_item_id

        waypoint_name = self.get_string(rec_content)
        if self.log: 
            print(f"Waypoint Name: {waypoint_name}")
        result['waypoint_name'] = waypoint_name

        waypoint_class = self.get_uint(rec_content)
        if self.log: 
            print(f"Waypoint Class: {waypoint_class}")
        result['waypoint_class'] = waypoint_class

        return result

    def analyze_record_A(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'A' (Author Information).
        
        Record Typ "A": Author information.
        2 byte: Programm Version (major/minor wie primäre Version berechnen)
        string (0 terminated): Builder
        string (0 terminated): Build date
        string (0 terminated): Build time
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        if len(rec_content) < 2:
            print("Fehler: Ungültige Länge für Record-Typ 'A'")
            return None
        
        # Lese Programm Version (2 Byte, little-endian)
        version = int.from_bytes(rec_content[0:2], byteorder='little')
        major = version // 100
        minor = version % 100
        print(f"Programm version: {major}.{minor} (0x{version:04x})")
        self.program_version = f"{major}.{minor}"
        self.record_pos += 2
        
        # Extrahiere die null-terminierten Strings
        
        # Builder (null terminated string)
        self.builder = self.get_string(rec_content)
        print(f"Builder: {self.builder}")
        
        # Build date (null terminated string)
        self.build_date = self.get_string(rec_content)
        print(f"Build date: {self.build_date}")
        
        # Build time (null terminated string)
        self.build_time = self.get_string(rec_content)
        print(f"Build time: {self.build_time}")

    def analyze_record_D(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'D' (File format).
        
        Record Typ "D": File format
        version   File format (two bytes)
        
        Args:
            content (bytes): Der Inhalt des Records
        """
        if len(rec_content) != 2:
            print("Fehler: Ungültige Länge für Record-Typ 'D'")
            return
        
        # version File format (2 bytes)
        version = int.from_bytes(rec_content, byteorder='little')
        major = version // 100
        minor = version % 100
        print(f"File format version: {major}.{minor} (0x{version:04x})")
        self.file_version = f"{major}.{minor}" 

    def analyze_record_W(self, rec_content, short = False):
        """
        Analysiert den Inhalt eines Record-Typs 'W' (Waypoint).
        
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
            content (bytes): Der Inhalt des Records
        """        
        result = {}
        
        # Waypoint name (string)
        # Suche null-terminator
        wp_name = self.get_string(rec_content)
        if self.log: 
            print(f"Waypoint name: {wp_name}")
        result["wp_name"] = wp_name
        
        # Waypoint class (uint, 4 bytes)
        wp_class = self.get_uint(rec_content)
        if self.log: 
            print(f"Waypoint Class: {wp_class}")
        result["wp_class"] = wp_class

        if wp_class > 0:
            return result

        # latitude (4 bytes int)
        latitude = self.get_coord(rec_content)
        if self.log: 
            print(f"Breitengrad: {latitude:.6f}°")
        result["latitude"] = latitude
 
        # longitude (4 bytes int)
        longitude = self.get_coord(rec_content)
        if self.log: 
            print(f"Längengrad: {longitude:.6f}°")
        result["longitude"] = longitude

        # Comment (null terminated string)
        comment = self.get_string(rec_content)
        if len(comment) > 1:
            if self.log: 
                print(f"Comment: {comment}")
            result["comment"] = comment
        else:
            result["comment"] = "no comment"

        # Proximity in meter (fdouble, 1+8 bytes)
        proximity = self.get_fdouble(rec_content)
        if self.log: 
            print(f"Proximity: {proximity} m")
        result["proximity"] = proximity

        # Display mode (uint, 4 bytes)
        display_mode = self.get_displaymode(rec_content)
        if self.log: 
            print(f"Display mode: {display_mode}")
        result["display_mode"] = display_mode
        
        # Icon (uint, 4 bytes)
        icon = self.get_icon(rec_content)
        if self.log: 
            print(f"Icon: {icon}")
        result["icon"] = icon

        # street (string null terminated)
        street = self.get_string(rec_content)
        if self.log: 
            print(f"Street: {street}")
        result["street"] = street

        # city (string null terminated)
        city = self.get_string(rec_content)
        if self.log: 
            print(f"City: {city}")
        result["city"] = city

        # state (string null terminated)
        state = self.get_string(rec_content)
        if self.log: 
            print(f"State: {state}")
        result["state"] = state

        # country (string null terminated)
        country = self.get_string(rec_content)
        if self.log: 
            print(f"Country: {country}")
        result["country"] = country

        # ZIP (string null terminated)
        zip_code = self.get_string(rec_content)
        if self.log: 
            print(f"ZIP: {zip_code}")
        result["zip"] = zip_code

        # if the next byte is 0x01, then Subclass is present
        # skip subclass if present, because it is not known what it is (in total 24 bytes)
        if rec_content[self.record_pos] == 0x01:
            if self.log: 
                print(f"Subclass present, skipping 24 bytes")
            self.record_pos += 25  # skip the flag byte and the 24 bytes of subclass
        else:
            self.record_pos += 2  # skip the flag and the stop byte

        # altitude in meter (fdouble, 1+8 bytes)
        altitude = self.get_fdouble(rec_content)
        if self.log: 
            print(f"Altitude: {altitude} m")
        result["altitude"] = altitude

        # depth in meter (fdouble, 1+8 bytes)
        depth = self.get_fdouble(rec_content)
        if self.log: 
            print(f"Depth: {depth} m")
        result["depth"] = depth

        # number of links (uint, 4 bytes)
        num_links = self.get_uint(rec_content)
        if self.log: 
            print(f"Number of links: {num_links}")
        result["num_links"] = num_links

        if num_links > 20:
            print(f"Number of links exceeds 20: {num_links}")
            return result
        
        # read all links (null terminated strings)
        links = []
        for i in range(num_links):
            link = self.get_string(rec_content)
            if self.log: 
                print(f"Link {i+1}: {link}")
            links.append(link)
        result["links"] = links

        # temperature in °C (fdouble, 1+8 bytes)
        temperature = self.get_fdouble(rec_content)
        if self.log: 
            print(f"Temperature: {temperature} °C")
        result["temperature"] = temperature

        # modification_date (fint, 1+4 bytes)
        modification_date_unix = self.get_fint(rec_content)
        if type(modification_date_unix) == int:
            modification_date = self.unix_to_mez_iso8601(modification_date_unix)
        else:
            modification_date = 'not defined'
        if self.log: 
            print(f"Modification date: {modification_date} ")
        result["modification_date"] = modification_date

        # skip 6 bytes (unknown)
        self.record_pos += 6

        # number of phone numbers (uint, 4 bytes)
        num_phone_numbers = self.get_uint(rec_content)
        if self.log: 
            print(f"Number of phone numbers: {num_phone_numbers}")
        result["num_phone_numbers"] = num_phone_numbers

        # read phone number (null terminated strings)
        # there is only one phone number, even if num_phone_numbers > 1, so we read only one phone number
        if num_phone_numbers > 0:
            phone_number = self.get_string(rec_content)
            if self.log: 
                print(f"Phone number: {phone_number}")
            result["phone_numbers"] = phone_number
        else:
            result["phone_numbers"] = "no phone number"
        
        # skip additional byte if num_phone_numbers > 0
        if num_phone_numbers > 0:
            self.record_pos += 1

        # creation_date (fint, 1+4 bytes)
        creation_date_unix = self.get_fint(rec_content)
        if type(creation_date_unix) == int:
            creation_date = self.unix_to_mez_iso8601(creation_date_unix)
        else:
            creation_date = 'not defined'
        if self.log: 
            print(f"Creation date: {creation_date} ")
        result["creation_date"] = creation_date

        # skip 3 bytes (unknown)
        self.record_pos += 3
        
        # number of categories (uint, 4 bytes)
        num_categories = self.get_uint(rec_content)
        if self.log: 
            print(f"Number of categories: {num_categories}")
        result["num_categories"] = num_categories

        if num_categories > 20:
            print(f"Number of categories exceeds 20: {num_categories}")
            return result
        
        # read all categories (null terminated strings)
        categories = []
        for i in range(num_categories):
            category = self.get_string(rec_content)
            if self.log: 
                print(f"Category {i+1}: {category}")
            categories.append(category)
        result["categories"] = categories

        # remaining bytes
        print(f"remaining length: {len(rec_content[self.record_pos:])} bytes")
        print(rec_content[self.record_pos:])

        return result

    def analyze_record_R(self, rec_content, short = False):

        result = {}
        
        # Route name (string null terminated)
        rt_name = self.get_string(rec_content)
        if self.log: 
            print(f"Route name: {rt_name}")
        result["route_name"] = rt_name
        return result

    def analyze_record_T(self, rec_content, short = False):
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

    def analyze_record_V(self, content, short = False):
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

    def analyze_record_E(self, content, short = False):
        return {"E":len(content)}

    def analyze_record_X(self, content, short = False):
        return content[:-1].decode('utf-8', errors='replace')

    def get_string(self, bytes):
        """
        Liest einen null-terminierten String aus der Byte-Sequenz bytes ab der aktuellen Position self.record_pos.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die den String enthält
        
        Rückgabe:
        str: Der extrahierte String
        """
        end_pos = bytes.find(b'\x00', self.record_pos)
        if end_pos == -1:
            print("Fehler: Kein null-terminierter String gefunden")
            return 
        
        result = bytes[self.record_pos:end_pos].decode('utf-8', errors='ignore')
        self.record_pos = end_pos + 1  # Move past the null terminator
        return result
    
    def get_double(self, bytes):
        """
        Konvertiert die nächsten 8 Byte der Byte-Sequenz bytes in eine Gleitkommazahl (double) unter Verwendung der little-endian-Darstellung.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        float: Die entsprechende Gleitkommazahl
        """
        if self.record_pos + 8 > len(bytes):
            print("Fehler: byte sequenz zur kurz für Double Konversion")
            return 
        result = struct.unpack('<d', bytes[self.record_pos:self.record_pos+8])[0]
        self.record_pos += 8
        return result

    def get_fdouble(self, bytes):
        """
        Konvertiert die nächsten 9 Byte der Byte-Sequenz bytes in eine Gleitkommazahl (double) unter Verwendung der little-endian-Darstellung.
        Das erste Byte wird als Flag interpretiert, das angibt, ob die folgenden 8 Byte eine gültige double-Zahl darstellen.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        float: Die entsprechende Gleitkommazahl, oder None, wenn das Flag nicht gesetzt ist
        """
        if self.record_pos + 1 > len(bytes):
            print("Fehler: byte sequenz zur kurz für FDouble Konversion")
            return 
        flag = bytes[self.record_pos]
        self.record_pos += 1
        if flag:
            return self.get_double(bytes)
        else:
            return 'not present'
        
    def get_uint(self, bytes):
        """
        Konvertiert die ersten 4 Byte der Byte-Sequenz bytes in eine Ganzzahl (unsigned int) unter Verwendung der little-endian-Darstellung.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        int: Die entsprechende Ganzzahl
        """
        if self.record_pos + 4 > len(bytes):
            print("Fehler: byte sequenz zur kurz für Uint Konversion")
            return 
        result = int.from_bytes(bytes[self.record_pos:self.record_pos+4], byteorder='little', signed=False)
        self.record_pos += 4
        return result

    def get_int(self, bytes):
        """
        Konvertiert die ersten 4 Byte der Byte-Sequenz bytes in eine Ganzzahl (signed int) unter Verwendung der little-endian-Darstellung.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        int: Die entsprechende Ganzzahl
        """
        if self.record_pos + 4 > len(bytes):
            print("Fehler: byte sequenz zur kurz für Uint Konversion")
            return 
        result = int.from_bytes(bytes[self.record_pos:self.record_pos+4], byteorder='little', signed=True)
        self.record_pos += 4
        return result

    def get_fint(self, bytes):
        """
        Konvertiert die ersten 5 Byte der Byte-Sequenz bytes in eine Ganzzahl (signed int) unter Verwendung der little-endian-Darstellung.
        Das erste Byte wird als Flag interpretiert, das angibt, ob die folgenden 4 Byte eine gültige Ganzzahl darstellen.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        int: Die entsprechende Ganzzahl, oder None, wenn das Flag nicht gesetzt ist
        """
        if self.record_pos + 1 > len(bytes):
            print("Fehler: byte sequenz zur kurz für FInt Konversion")
            return 
        flag = bytes[self.record_pos]
        self.record_pos += 1
        if flag:
            result = int.from_bytes(bytes[self.record_pos:self.record_pos+4], byteorder='little', signed=True)
            self.record_pos += 4
            return result
        else:
            return 'not present'

    def get_coord(self, bytes):
        """
        Konvertiert die ersten 4 Byte der Byte-Sequenz bytes in eine Koordinate (latitude oder longitude) unter Verwendung der little-endian-Darstellung.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die konvertiert werden soll
        
        Rückgabe:
        float: Die entsprechende Koordinate in Grad
        """
        position = self.get_int(bytes)
        return position * 360.0 / (2**32)
    
    def get_displaymode(self, bytes):
        """
        Gibt die Bedeutung Displaymode ID zurück.

        Parameter:
        bytes (bytes): Die Byte-Sequenz, die die ID enthält

        Rückgabe:
        str: Die zugehörige Bedeutung als Zeichenkette

        Raises:
        ValueError: Wenn die ID außerhalb des gültigen Bereichs liegt
        """
        meaning_map = {
            0: "Symbol",
            1: "Symbol & Name",
            2: "Symbol & Comment",
            3: "Image",
            4: "Image & Name"
        }

        value = self.get_uint(bytes)
        if value in meaning_map:
            return meaning_map[value]
        else:
            return f"Ungültige Displaymode ID: {value}. Gültige IDs sind 0 bis 4."

    def get_color(self, bytes):
        """
        Gibt die Farbe einer gegebenen ID zurück.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die die ID enthält
        
        Rückgabe:
        str: Die zugehörige Farbe als Zeichenkette
        
        Raises:
        ValueError: Wenn die ID außerhalb des gültigen Bereichs liegt
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
        
        id = self.get_uint(bytes)
        if 0 <= id < len(color_map):
            return color_map[id]
        else:
            return f"Ungültige ID: {id}"
            
    def get_icon(self, bytes):
        """
        Gibt den Namen eines Icons anhand der ID zurück.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die die ID enthält
        
        Rückgabe:
        str: Der Name des Icons als Zeichenkette
        
        Raises:
        ValueError: Wenn die ID außerhalb des gültigen Bereichs liegt
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
        
        id = self.get_uint(bytes)
        if 0 <= id < len(icon_list):
            return icon_list[id]
        else:
            return f"Unknown Icon ID {id}"

    def get_track_segment(self, bytes):
        """
        Gibt die Track-Punkte zurück.
        
        Parameter:
        bytes (bytes): Die Byte-Sequenz, die die ID enthält
        
        Rückgabe:
        str: Die zugehörige Track-Information als Zeichenkette
        """
        # track starts with an unknown byte, so we skip that
        self.record_pos += 1

        # get max / min position
        latitude_max = self.get_coord(bytes)
        longitude_max = self.get_coord(bytes)
        latitude_min = self.get_coord(bytes)
        longitude_min = self.get_coord(bytes)

        track_bounds = {
            "latitude_max": latitude_max,
            "longitude_max": longitude_max,
            "latitude_min": latitude_min,
            "longitude_min": longitude_min
        }
        #print(f"Track segment bounds: lat {latitude_min:.6f} to {latitude_max:.6f}, lon {longitude_min:.6f} to {longitude_max:.6f}")

        num_points = self.get_uint(bytes)
        #print(f"Number of track points: {num_points}")

        # read all track points
        track_points = []
        for i in range(num_points):
            latitude = self.get_coord(bytes)
            longitude = self.get_coord(bytes)
            track_points.append((latitude, longitude))

        return track_bounds, track_points

    def analyze_recordtypes(self, records):
        record_types = {}
        for r in records:
            if r[0] in record_types:
                record_types[r[0]] += 1
            else:
                record_types[r[0]] = 1
        return record_types
                
    def unix_to_mez_iso8601(self, timestamp):
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
