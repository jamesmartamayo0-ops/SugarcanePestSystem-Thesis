"use client";

import { useEffect } from "react";
import { latLngBounds } from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";

import {
  formatArea,
  markerPresentation,
  type FarmMapFarm,
} from "@/lib/farm-map";
import { pestLabel } from "@/lib/presentation";

const BAIS_MONITORING_CENTER: [number, number] = [9.591111, 123.122778];
const SINGLE_FARM_ZOOM = 15;

function FitFarmBounds({ farms }: { farms: FarmMapFarm[] }) {
  const map = useMap();

  useEffect(() => {
    const locations = farms.flatMap((farm) =>
      farm.location ? [[farm.location.latitude, farm.location.longitude] as [number, number]] : [],
    );
    if (locations.length === 1) {
      map.setView(locations[0], SINGLE_FARM_ZOOM);
    } else if (locations.length > 1) {
      map.fitBounds(latLngBounds(locations), { padding: [32, 32], maxZoom: SINGLE_FARM_ZOOM });
    }
  }, [farms, map]);

  return null;
}

export default function FarmMonitoringMapClient({ farms }: { farms: FarmMapFarm[] }) {
  return (
    <MapContainer
      center={BAIS_MONITORING_CENTER}
      zoom={13}
      className="gov-monitoring-map"
      aria-label="Farm monitoring map"
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitFarmBounds farms={farms} />
      {farms.map((farm) => {
        if (farm.location === null) {
          return null;
        }
        const presentation = markerPresentation(farm.marker_state);
        return (
          <CircleMarker
            key={farm.id}
            center={[farm.location.latitude, farm.location.longitude]}
            radius={9}
            pathOptions={{
              color: "#ffffff",
              weight: 2,
              fillColor: presentation.color,
              fillOpacity: 0.95,
            }}
          >
            <Tooltip sticky className="gov-map-tooltip-shell">
              <div className="gov-map-tooltip">
                <strong>{farm.plot_identifier}</strong>
                <span>Farmer: {farm.farmer.full_name}</span>
                <span>Area: {formatArea(farm.area_hectares)}</span>
                <span className="gov-map-tooltip-status">
                  <span
                    className="gov-map-legend-dot"
                    style={{ backgroundColor: presentation.color }}
                    aria-hidden="true"
                  />
                  {presentation.label}
                </span>
                {farm.case && <span>Pest: {pestLabel(farm.case.pest_name)}</span>}
              </div>
            </Tooltip>
            <Popup maxWidth={320} minWidth={230} className="gov-map-popup-shell">
              <div className="gov-map-popup">
                <h3>{farm.plot_identifier}</h3>
                <dl>
                  <div><dt>Farmer</dt><dd>{farm.farmer.full_name}</dd></div>
                  <div><dt>Barangay</dt><dd>{farm.barangay}</dd></div>
                  <div><dt>Farm area</dt><dd>{formatArea(farm.area_hectares)}</dd></div>
                  <div>
                    <dt>Workflow state</dt>
                    <dd>
                      <span className="gov-map-status-chip">
                        <span
                          className="gov-map-legend-dot"
                          style={{ backgroundColor: presentation.color }}
                          aria-hidden="true"
                        />
                        {presentation.label}
                      </span>
                    </dd>
                  </div>
                  {farm.case && (
                    <>
                      <div><dt>Pest</dt><dd>{pestLabel(farm.case.pest_name)}</dd></div>
                      <div><dt>Case status</dt><dd>{markerPresentation(farm.case.status).label}</dd></div>
                      <div><dt>Reported affected area</dt><dd>{formatArea(farm.case.reported_area_hectares)}</dd></div>
                      <div><dt>Validated affected area</dt><dd>{formatArea(farm.case.validated_area_hectares)}</dd></div>
                    </>
                  )}
                </dl>
                <p className="gov-map-popup-note">
                  Approximate farm location for monitoring reference only.
                </p>
                {farm.case && (
                  <div className="gov-map-popup-actions">
                    <a href={`/pest-cases/${farm.case.id}#case-summary`}>View case</a>
                    <a href={`/pest-cases/${farm.case.id}#timeline`}>View timeline</a>
                  </div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
