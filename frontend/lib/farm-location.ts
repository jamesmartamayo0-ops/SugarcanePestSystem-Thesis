export type FarmCoordinates = {
  latitude: number;
  longitude: number;
};

export type FarmLocationChange =
  | { kind: "unchanged" }
  | { kind: "selected"; coordinates: FarmCoordinates }
  | { kind: "cleared" };

function assertCoordinate(value: number, minimum: number, maximum: number, name: string) {
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new RangeError(`${name} is outside the valid coordinate range.`);
  }
}

export function normalizeFarmCoordinates(
  latitude: number,
  longitude: number,
): FarmCoordinates {
  assertCoordinate(latitude, -90, 90, "Latitude");
  assertCoordinate(longitude, -180, 180, "Longitude");

  return {
    latitude: Number(latitude.toFixed(6)),
    longitude: Number(longitude.toFixed(6)),
  };
}

export function createCoordinatePayload(
  coordinates: FarmCoordinates | null,
): FarmCoordinates | Record<string, never> {
  return coordinates
    ? normalizeFarmCoordinates(coordinates.latitude, coordinates.longitude)
    : {};
}

export function updateCoordinatePayload(
  change: FarmLocationChange,
): FarmCoordinates | { latitude: null; longitude: null } | Record<string, never> {
  if (change.kind === "unchanged") {
    return {};
  }
  if (change.kind === "cleared") {
    return { latitude: null, longitude: null };
  }
  return normalizeFarmCoordinates(
    change.coordinates.latitude,
    change.coordinates.longitude,
  );
}
