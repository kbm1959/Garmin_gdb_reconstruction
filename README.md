# Garmin Database reconstruction
This is Python code which reconstructs a Garmin basecamp backup to a local directory structure and extracts Tracks and Waypoints from the database to this local structure.

Up to now it reconstructs only waypoints and tracks but no Routes, Adventures or Birdseye data.

The document
https://www.memotech.franken.de/FileFormats/Garmin_MPS_GDB_and_GFI_Format.pdf from Herbert Oppmann was very helpful when analyzing the .gdb and .gfi file structures.
https://www.memotech.franken.de/FileFormats/Garmin_MPS_GDB_and_GFI_Format.pdf from Herbert Oppmann was very helpful when analyzing the .gdb and .gfi file structures.

This is the first production version of this App
I managed to reconstruct the folder structure and all waypoints and tracks from a Garmin Basecamp V 4.7.5 database 

Version 0.3 (beta)
Date 2026-09-15
- complete reconstruction of folder-structure and tracks and waypoints within folders implemented

- known issues: Routes are not yet handled, since the analysis of their binary structure in the DB is not straightforward

Description of the files:

- analyze_tracksegment.py: experimental to analyze the structure of tracksegemnts in the TrackSegments folder
- basecamp_migration.py: KI generatde code from Oppmans documentation, not usable, will be deleted in final version
- ganalyze.py: experimental code to analyze the .gdb and .gfi data structure
- garmin_analyzer.py: Experimental class used by ganalyze.py
- garmin_tools.py: final class for data reconstruction (beta)
- map_plotter.py: Experimental code to test reconstructed track coordinates from the .gdb file
- reconstruct_garmin_db.py: Application example for garmin_tools (beta)