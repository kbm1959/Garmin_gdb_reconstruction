#!/usr/bin/env python

import argparse

from garmin_analyzer import *


def parse_args():
	parser = argparse.ArgumentParser(description="Analyze a Garmin database file.")
	parser.add_argument("--filename", default="4.7/AllData.gdb", help="Path to the  file")
	parser.add_argument("--log", action='store_true', help="Log record contents (log_records)")
	parser.add_argument("--short", action='store_true', help="Print records in short form")
	parser.add_argument("--page_len", type=int, default=0, help="Number of records per page (0 disables paging)")
	parser.add_argument("--record_type", choices=["T", "W", "R", "F", "I", "all"], default="all", help="Only analyze records of this type (T=Track, W=Waypoint, R=Route, F=Folder, I=Item, all=no filter)")
	parser.add_argument("--version", action="version", version="%(prog)s 1.0")	
	parser.add_argument("--hex_dump", action="store_true", help="Hex Dump of input file")
	parser.add_argument("--hex_length", type=int, default=0, help="Number of bytes to display in hex dump (default: 256)")
	parser.add_argument("--fetch_track", default="", help="return only analysis of this track (by name)")
	return parser.parse_args()


def main():
	args = parse_args()

	if args.hex_dump:
		try:
			with open(args.filename, "rb") as f:
				bytes_data = f.read()
				if args.hex_length and args.hex_length <= len(bytes_data):
					disp_hex_ascii(bytes_data[:args.hex_length])  # Display first N bytes
				else:
					disp_hex_ascii(bytes_data)  # Display all bytes if hex_length is 0 or greater than file size
		except FileNotFoundError:
			print(f"File not found: {args.filename}")
	else:
		gd = GarminAnalyzer(args.filename, log_records=args.log)

		d = gd.records
		if args.record_type != "all":
			d = [r for r in d if r[0] == args.record_type]

		#print(f"Analyzing {len(d)} records of type '{args.record_type}' from {args.filename}...")
		#print(d[0])
		#print(gd.analyze_record(d[0], short=args.short))
		#return

		# array for different Waypoint classes 
		wp_classes = []
		invalid_cat_number_count = 0
		for i, r in enumerate(d):
			analyzed_record = gd.analyze_record(r, short=args.short)
			# collect waypoint classes
			if r[0] == "W" and "wp_class" in analyzed_record:
				wp_class = analyzed_record["wp_class"]
				if wp_class not in wp_classes:
					wp_classes.append(wp_class)
			if args.fetch_track :
				if "track_name" in analyzed_record and analyzed_record["track_name"] == args.fetch_track:
					print(f"Found track: {args.fetch_track}")
					print(analyzed_record)
					break
			else:
				print(f"{i}: {analyzed_record}")
				#print(r)				
				print("-" * 80)
				# break if wp_class == 0 and num_categories > 20
				if r[0] == "W" and "wp_class" in analyzed_record and "num_categories" in analyzed_record:
					if analyzed_record["wp_class"] == 0 and analyzed_record["num_categories"] > 20:
						print(f"Waypoint class 0 with more than 20 categories found. Stopping analysis.")
						print(r)
						invalid_cat_number_count += 1
						# break the loop if more than 1 invalid waypoint is found
						if invalid_cat_number_count > 11:
							print(f"More than 11 invalid waypoints found. Stopping analysis.")
							break

				if args.page_len and (i + 1) % args.page_len == 0:
					answer = input("-- more (Enter to continue, q to quit) --")
					if answer.strip().lower() == "q":
						break
		# print waypoint classes found
		if wp_classes:
			print(f"Waypoint classes found: {wp_classes}")

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



if __name__ == "__main__":
	main()
	

