"""
Dieses Modul enthält die Klasse MapPlotter, die eine Liste von Koordinaten
(Breitengrad, Längengrad) in Dezimalgrad entgegennimmt und diese auf einer
OpenStreetMap-Karte darstellt.

Die Karte wird mit der Bibliothek folium erzeugt und als HTML-Datei gespeichert,
die in jedem Webbrowser geöffnet werden kann.

Beispiel:
    coords = [(47.3769, 8.5417), (46.9480, 7.4474)]
    plotter = MapPlotter(coords)
    plotter.save("karte.html")
"""
import folium


class MapPlotter:

    def __init__(self, coordinates, zoom_start=13):
        """
        Args:
            coordinates (list[tuple[float, float]]): Liste von (Breitengrad, Längengrad) in Dezimalgrad
            zoom_start (int): Anfänglicher Zoom-Level der Karte
        """
        if not coordinates:
            raise ValueError("coordinates darf nicht leer sein")

        self.coordinates = list(coordinates)
        center = self._compute_center(self.coordinates)

        self.map = folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap")

        for lat, lon in self.coordinates:
            folium.Marker(location=(lat, lon)).add_to(self.map)

        if len(self.coordinates) > 1:
            folium.PolyLine(locations=self.coordinates, color="blue").add_to(self.map)

    @staticmethod
    def _compute_center(coordinates):
        lat_avg = sum(lat for lat, _ in coordinates) / len(coordinates)
        lon_avg = sum(lon for _, lon in coordinates) / len(coordinates)
        return (lat_avg, lon_avg)

    def save(self, filename="map.html"):
        """
        Speichert die Karte als HTML-Datei.

        Args:
            filename (str): Zieldateiname der HTML-Datei
        """
        self.map.save(filename)
        print(f"Karte gespeichert unter: {filename}")


if __name__ == "__main__":
    coords = [(47.3769, 8.5417), (46.9480, 7.4474), (46.2044, 6.1432)]
    plotter = MapPlotter(coords)
    plotter.save("map.html")
