#!/usr/bin/env python3

"""
Uses the GarminAnalyzer Class to reconstruct a Garmin database from Garmin Basecamp Version 4.7. 
By default it uses the files Alldata.gdb and FolderData.gfi from the directory path given in the --filename argument.
it follows the following steps:
1. It reconstructs a directory structure of the Garmin database using the F and I records in the FolderData.gfi file.
   It treats the F records as well as the I records as folders and subfolders.  
   It creates the directory structure in the current working directory if the --dir argument is not provided.
2. It reconstructs the tracks and waypoints in the Garmin database using the T and W records in the AllData.gdb file.
   It places the tracks and waypoints in the directory structure created in step 1 using the T and W records in the FolderData.gfi file.

It is tested and works with Basecamp Version 4.7 databases (primary version 1.2, file format version 1.88).

To write the GarminAnalyzer Class, the document of Herbert Oppmann was very helpful, 
though it is not complete and has some errors. 
The document can be found at: https://www.memotech.franken.de/FileFormats/Garmin_MPS_GDB_and_GFI_Format.pdf

This is a work in progress and will be updated as more information is discovered about the Garmin database file format.

Code Version: 0.3
date: 2026-09-15s
"""

from garmin_tools import GarminAnalyzer

# read AllData.gdb and FolderData.gfi from the directory path given
db = GarminAnalyzer('4.7/')

# reconstruct the directory structure of the Garmin database
# using the F and I records in the FolderData.gfi file to build the folder tree
db.build_folder_tree(db.gfi_f_records['root'], folder_path='./waypoints/', build_tree=True)

print("Directory structure built successfully.")
# restore waypoints from the W records in the AllData.gdb and the FolderData.gfi file
# create the gpx xml structure of the waypoints from the W records in the AllData.gdb file
# save the waypoints in the folderstructure using the W records in the FolderData.gfi file
count = db.restore_waypoints()
print(f"Restored {count} waypoints.")

# store the tracks in a different folder
db.build_folder_tree(db.gfi_f_records['root'], folder_path='./tracks/', build_tree=True)

# restore tracks from the T records in the AllData.gdb and the FolderData.gfi file
# create the gpx xml structure of the tracks from the T records in the AllData.gdb file and the track segments in the TrackSegments directory
# save the tracks in the folderstructure using the T records in the FolderData.gfi file
count = db.restore_tracks()
print(f"Restored {count} tracks.")