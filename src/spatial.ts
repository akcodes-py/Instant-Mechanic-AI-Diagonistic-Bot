/**
 * Shared H3 helpers for the mechanic console and supply/demand overlays.
 * Mirrors backend/app/services/spatial.py - see contracts/h3.md.
 */
import {
  cellToLatLng,
  cellToParent,
  getResolution,
  gridDisk,
  isValidCell,
  latLngToCell,
} from 'h3-js';

export const PRESENCE_RESOLUTION = 8;
export const ZONE_RESOLUTION = 7;
export const MAX_RING = 3;

export type LngLat = readonly [lon: number, lat: number];

export function latLngToRes8(lat: number, lon: number): string {
  if (lat < -90 || lat > 90) throw new RangeError('lat must be between -90 and 90');
  if (lon < -180 || lon > 180) throw new RangeError('lon must be between -180 and 180');
  return latLngToCell(lat, lon, PRESENCE_RESOLUTION);
}

export function zoneFor(cell: string): string {
  return cellToParent(cell, ZONE_RESOLUTION);
}

/** Full disk: k=1 -> 7 cells, k=2 -> 19, k=3 -> 37. */
export function ring(origin: string, k: number): string[] {
  if (k < 0) throw new RangeError('ring radius k must be >= 0');
  return gridDisk(origin, k);
}

/** Newly added cells per hop: 7 / 12 / 18 (cumulative 7 / 19 / 37). */
export function cascade(origin: string, maxRing = MAX_RING): Array<[number, string[]]> {
  const seen = new Set<string>();
  const result: Array<[number, string[]]> = [];
  for (let k = 1; k <= maxRing; k += 1) {
    const cells = gridDisk(origin, k).filter((cell) => !seen.has(cell));
    cells.forEach((cell) => seen.add(cell));
    result.push([k, cells]);
  }
  return result;
}

export function center(cell: string): LngLat {
  return cellToLatLng(cell);
}

export function isCellAt(value: string, resolution: number): boolean {
  return isValidCell(value) && getResolution(value) === resolution;
}
