"""
Module 2: Geospatial & Drift Modeling - Map Visualizer
Plots Contract B output (backtrack line, estimated origin, +6h & +24h forecast polygons)
over coastline using GeoPandas + Matplotlib.
"""

import os
import sys
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.ticker as mticker
import geopandas as gpd
from shapely.geometry import shape, Point, Polygon, LineString
import cartopy.feature as cfeature


def plot_drift_contract(
    contract_json_path: str = "contracts/sample_drift_output.json",
    output_png: str = "module2_drift/plots/drift_visualization.png",
    bbox: tuple = (71.0, 73.5, 18.0, 20.0)
):
    """
    Renders the backtrack trajectory, estimated origin, and forecast envelopes onto a map.
    """
    if not os.path.exists(contract_json_path):
        # Fallback to root sample output if running from different working directories
        alt_path = os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "sample_drift_output.json")
        if os.path.exists(alt_path):
            contract_json_path = alt_path
        else:
            raise FileNotFoundError(f"Contract output not found at: {contract_json_path}")

    with open(contract_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slick_id = data.get("slick_id", "SLICK-DEMO")
    origin_pt = data["estimated_origin"]["point"]
    origin_time = data["estimated_origin"]["time_utc"]

    backtrack_geom = shape(data["backtrack_track"])
    forecast_6h_geom = shape(data["forecast_polygons"][0]["geometry"])
    forecast_24h_geom = shape(data["forecast_polygons"][1]["geometry"])
    det_lon, det_lat = data["backtrack_track"]["coordinates"][-1]

    gdf_backtrack = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[backtrack_geom])
    gdf_origin = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[Point(origin_pt[0], origin_pt[1])])
    gdf_det = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[Point(det_lon, det_lat)])
    gdf_fore_6h = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[forecast_6h_geom])
    gdf_fore_24h = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[forecast_24h_geom])

    # Extract Coastline and Land
    land_feature = cfeature.NaturalEarthFeature('physical', 'land', '10m')
    land_geoms = list(land_feature.intersecting_geometries((bbox[0]-0.5, bbox[2]-0.5, bbox[1]+0.5, bbox[3]+0.5)))
    gdf_land = gpd.GeoDataFrame(geometry=land_geoms, crs="EPSG:4326") if land_geoms else None

    coast_feature = cfeature.NaturalEarthFeature('physical', 'coastline', '10m')
    coast_geoms = list(coast_feature.intersecting_geometries((bbox[0]-0.5, bbox[2]-0.5, bbox[1]+0.5, bbox[3]+0.5)))
    gdf_coast = gpd.GeoDataFrame(geometry=coast_geoms, crs="EPSG:4326") if coast_geoms else None

    # Setup Plot
    fig, ax = plt.subplots(figsize=(13, 10), dpi=200, facecolor='#09111e')
    ax.set_facecolor('#0f1e33')
    ax.set_xlim(bbox[0], bbox[1])
    ax.set_ylim(bbox[2], bbox[3])

    if gdf_land is not None and not gdf_land.empty:
        gdf_land.plot(ax=ax, facecolor='#1b2838', edgecolor='#3a506b', linewidth=1.0, zorder=2)
    if gdf_coast is not None and not gdf_coast.empty:
        gdf_coast.plot(ax=ax, color='#64dfdf', linewidth=1.4, zorder=3)

    # Reference Assets
    ref_points = [
        {"name": "Bombay High Offshore Oil Field", "lon": 71.35, "lat": 19.40, "color": "#f72585", "marker": "s"},
        {"name": "Mumbai Harbour Entrance", "lon": 72.83, "lat": 18.92, "color": "#4895ef", "marker": "D"},
        {"name": "JNPT Port Approach", "lon": 72.95, "lat": 18.94, "color": "#4cc9f0", "marker": "p"},
    ]
    for pt in ref_points:
        if bbox[0] <= pt["lon"] <= bbox[1] and bbox[2] <= pt["lat"] <= bbox[3]:
            ax.scatter(pt["lon"], pt["lat"], color=pt["color"], s=110, marker=pt["marker"], edgecolors='white', zorder=8)
            ax.annotate(f" {pt['name']}", (pt["lon"], pt["lat"]), xytext=(10, 8), textcoords="offset points",
                        color='#ffffff', fontsize=8.5, fontweight='bold',
                        bbox=dict(boxstyle="round,pad=0.3", fc="#08121f", ec=pt["color"], alpha=0.9), zorder=9)

    # Forecast Envelopes
    gdf_fore_24h.plot(ax=ax, facecolor='#e63946', edgecolor='#e63946', linewidth=2.0, alpha=0.35, zorder=4)
    gdf_fore_6h.plot(ax=ax, facecolor='#f4a261', edgecolor='#f4a261', linewidth=2.0, alpha=0.55, zorder=5)

    # Backtrack Track
    gdf_backtrack.plot(ax=ax, color='#00f5d4', linewidth=2.5, linestyle='--', zorder=6)
    bx, by = backtrack_geom.xy
    ax.scatter(bx, by, color='#00f5d4', s=30, zorder=7)

    # Detection & Origin Points
    ax.scatter(det_lon, det_lat, color='#ffbe0b', s=160, marker='o', edgecolors='black', linewidth=1.5, zorder=8)
    ax.scatter(origin_pt[0], origin_pt[1], color='#ff0054', s=240, marker='*', edgecolors='white', linewidth=1.5, zorder=9)

    # Formatting
    ax.xaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, pos: f"{x:.1f}°E"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, pos: f"{y:.1f}°N"))
    ax.tick_params(colors='#caf0f8')
    ax.grid(True, color='#253852', linestyle='-', linewidth=0.7, alpha=0.6)

    ax.set_title(f"OIL SPILL DRIFT & ATTRIBUTION MAP — {slick_id}", color='#ffffff', fontsize=12, fontweight='bold', pad=12)

    legend_elements = [
        Line2D([0], [0], marker='*', color='#ff0054', label='Estimated Origin (T-12h)', markersize=12, linestyle='none'),
        Line2D([0], [0], marker='o', color='#ffbe0b', label='SAR Detection (T0)', markersize=9, linestyle='none'),
        Line2D([0], [0], color='#00f5d4', lw=2.5, linestyle='--', label='Backtrack Track'),
        mpatches.Patch(facecolor='#f4a261', edgecolor='#f4a261', alpha=0.55, label='Forecast (+6h Polygon)'),
        mpatches.Patch(facecolor='#e63946', edgecolor='#e63946', alpha=0.35, label='Forecast (+24h Polygon)'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=8.5, facecolor='#060e1a', edgecolor='#48cae4', labelcolor='#ffffff')

    os.makedirs(os.path.dirname(output_png), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_png, dpi=200, facecolor=fig.get_facecolor())
    plt.close()
    print(f"[Map Visualizer] Saved sanity-check plot to: {output_png}")
    return output_png


if __name__ == '__main__':
    in_file = sys.argv[1] if len(sys.argv) > 1 else "contracts/sample_drift_output.json"
    plot_drift_contract(contract_json_path=in_file)
