# Member 1 Synthetic Demo Fixtures

This directory contains deterministic demo and test fixtures for Member 1 of SIH-26143.

## Notice

> **IMPORTANT:**
> This fixture is synthetic demonstration/test data. It is not output from the trained Member 1 U-Net model.
> It does not claim or represent a real detected oil spill.

## Purpose

The demo fixtures allow end-to-end integration and pipeline testing across Member 1 (Detection), Member 2 (Drift Simulation), and Member 3 (AIS Attribution) without relying on trained U-Net model weights or real Sentinel-1 SAR GeoTIFF scenes.

## Fixture Specification (`demo_contract_a.json`)

- **Schema**: Member 2 Contract A (`module2_drift.api.ContractARequest`)
- **Slick ID**: `DEMO-SLICK-001`
- **Detection Timestamp**: `2026-09-04T12:00:00Z` (Fixed UTC; never dynamic)
- **Region**: Arabian Sea (Offshore Bombay High / Maharashtra coastal corridor)
  - Coordinates: `[longitude, latitude]`
  - Bounding Box: `~71.85°E, 19.27°N` to `~71.87°E, 19.29°N` (open ocean)
  - Shape: Closed GeoJSON Polygon with 5 coordinate pairs (4 unique vertices + 1 closing vertex)
- **Estimated Area**: `2.45 km²`
- **Detection Confidence**: `0.92`
