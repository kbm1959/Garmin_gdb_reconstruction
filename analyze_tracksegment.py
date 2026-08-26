#!/usr/bin/env python

import argparse

from garmin_analyzer import *

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze a Garmin tracksegment file.")
    parser.add_argument("--filename", default="4.7/TrackSegments/df8d7d0f-6a88-4077-aa38-2ccff64a5425", help="Path to the  file")
    parser.add_argument("--log", action='store_true', help="Log record contents (log_records)")
    return parser.parse_args()

def main():
    args = parse_args()
    gd = GarminAnalyzer(args.filename, log_records=args.log, read_all_records=False)

    rec_length = int.from_bytes(gd.data[gd.data_pos:gd.data_pos + 4], byteorder='little')
    print(f"Record length: {rec_length} bytes")
    gd.data_pos += 4  # Move past the length field
    rec_type = gd.data[gd.data_pos:gd.data_pos + 1]
    print(f"Record type: {rec_type}")
    print(f"Data position: {gd.data_pos}")
    print(f"Remaining data length: {len(gd.data) - gd.data_pos}")

    # now scan the record data for valid unix timestamps
    timestamps = []
    for i in range(gd.data_pos, len(gd.data) - 4):
        potential_timestamp = int.from_bytes(gd.data[i:i + 4], byteorder='little')
        if 1777392278 <= potential_timestamp <= 1777393478:  # Between Jan 1, 2000 and Jan 1, 2100
            timestamps.append((i, potential_timestamp))
    print("Timestamps found:")
    for pos, ts in timestamps:
        print(f"Position: {pos}, Timestamp: {gd.unix_to_mez_iso8601(ts)}")
        print(f"Data at position: {gd.data[pos-9:pos -1].hex()}")
        check_for_double(gd.data[pos-9:pos-1])

def disp_hex_ascii(bytes_data):
	
	# Verarbeite die Bytes in 16-Byte-Blöcken
	for i in range(0, len(bytes_data), 16):
		# Adresse (4-stellige Hex-Zahl)
		address = f"{i:04x}"
		
		# Hole 16 Bytes oder weniger, wenn Ende erreicht
		block = bytes_data[i:i+16]
		
		# Hex-Darstellung (32 Zeichen, mit Leerzeichen zwischen jedem Byte)
		hex_part = ' '.join(f'{byte:02x}' for byte in block)
		# Fülle auf 47 Zeichen (für 16 Bytes mit Leerzeichen)
		hex_part = hex_part.ljust(47)
		
		# ASCII-Darstellung
		ascii_part = ''
		for byte in block:
			if 32 <= byte <= 126:  # Druckbare ASCII-Zeichen
				ascii_part += chr(byte)
			else:
				ascii_part += '.'
		
		print(f"{address}   | {hex_part} | {ascii_part}")

def check_for_uint(bytes_data):
    # Prüfe, ob die Bytes ein gültiges uint32 darstellen
    for i in range(len(bytes_data) - 3):
        potential_uint = int.from_bytes(bytes_data[i:i + 4], byteorder='little')
        print(f"Position: {i}, Potential uint32: {potential_uint}")

def check_for_double(bytes_data):
    # Prüfe, ob die Bytes ein gültiges double darstellen
    for i in range(len(bytes_data) - 7):
        potential_double = struct.unpack('<d', bytes_data[i:i + 8])[0]
        print(f"Position: {i}, Potential double: {potential_double}")   

if __name__ == "__main__":
    main()