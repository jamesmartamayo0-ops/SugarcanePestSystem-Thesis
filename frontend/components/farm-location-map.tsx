"use client";

import { Component, type ReactNode } from "react";
import dynamic from "next/dynamic";

import type { FarmCoordinates } from "@/lib/farm-location";

const FarmLocationMapClient = dynamic(
  () => import("@/components/farm-location-map-client"),
  {
    ssr: false,
    loading: () => (
      <div className="gov-map-message" role="status">
        Loading map...
      </div>
    ),
  },
);

type FarmLocationMapProps = {
  coordinates: FarmCoordinates | null;
  onSelect: (latitude: number, longitude: number) => void;
};

type MapErrorBoundaryProps = {
  children: ReactNode;
};

type MapErrorBoundaryState = {
  failed: boolean;
};

class MapErrorBoundary extends Component<
  MapErrorBoundaryProps,
  MapErrorBoundaryState
> {
  state: MapErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): MapErrorBoundaryState {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="gov-map-message" role="alert">
          The map is unavailable. You can still use the rest of the farm form.
        </div>
      );
    }
    return this.props.children;
  }
}

export default function FarmLocationMap(props: FarmLocationMapProps) {
  return (
    <MapErrorBoundary>
      <FarmLocationMapClient {...props} />
    </MapErrorBoundary>
  );
}
