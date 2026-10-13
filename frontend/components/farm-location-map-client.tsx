"use client";

import { useEffect } from "react";
import L from "leaflet";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import {
  MapContainer,
  Marker,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

import type { FarmCoordinates } from "@/lib/farm-location";

export const BAIS_CITY_CENTER: [number, number] = [9.591111, 123.122778];

const DEFAULT_ZOOM = 13;
const SELECTED_ZOOM = 16;

function imageUrl(image: string | { src: string }): string {
  return typeof image === "string" ? image : image.src;
}

const farmMarkerIcon = L.icon({
  iconUrl: imageUrl(markerIcon),
  iconRetinaUrl: imageUrl(markerIcon2x),
  shadowUrl: imageUrl(markerShadow),
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

type FarmLocationMapClientProps = {
  coordinates: FarmCoordinates | null;
  onSelect: (latitude: number, longitude: number) => void;
};

function MapClickHandler({ onSelect }: Pick<FarmLocationMapClientProps, "onSelect">) {
  useMapEvents({
    click(event) {
      onSelect(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

function SelectedLocationView({ coordinates }: { coordinates: FarmCoordinates | null }) {
  const map = useMap();

  useEffect(() => {
    if (coordinates) {
      map.setView([coordinates.latitude, coordinates.longitude], SELECTED_ZOOM);
    }
  }, [coordinates, map]);

  return null;
}

export default function FarmLocationMapClient({
  coordinates,
  onSelect,
}: FarmLocationMapClientProps) {
  const initialCenter: [number, number] = coordinates
    ? [coordinates.latitude, coordinates.longitude]
    : BAIS_CITY_CENTER;

  return (
    <MapContainer
      center={initialCenter}
      zoom={coordinates ? SELECTED_ZOOM : DEFAULT_ZOOM}
      className="gov-farm-map"
      aria-label="Interactive map for selecting the approximate farm location"
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapClickHandler onSelect={onSelect} />
      <SelectedLocationView coordinates={coordinates} />
      {coordinates && (
        <Marker
          position={[coordinates.latitude, coordinates.longitude]}
          icon={farmMarkerIcon}
          title="Selected approximate farm location"
          alt="Selected approximate farm location"
        />
      )}
    </MapContainer>
  );
}
