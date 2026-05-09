"use client";

import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    google: any;
  }
}

interface MarkerData {
  id: string;
  lat: number;
  lng: number;
  title: string;
  type?: "donor" | "ngo" | "gap";
}

interface MapViewerProps {
  markers: MarkerData[];
  center?: { lat: number; lng: number };
  zoom?: number;
  routePath?: Array<{ lat: number; lng: number }>;
}

export function MapViewer({ markers, center = { lat: 17.385, lng: 78.4867 }, zoom = 11, routePath = [] }: MapViewerProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<any>(null);
  const [googleMapsLoaded, setGoogleMapsLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const markersRef = useRef<any[]>([]);
  const routeRef = useRef<any>(null);
  const mapId = process.env.NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID || "";
  const isMapsReady = () =>
    Boolean(window.google && window.google.maps && typeof window.google.maps.Map === "function");

  useEffect(() => {
    // Load Google Maps script
    if (isMapsReady()) {
      setGoogleMapsLoaded(true);
      return;
    }
    
    if (document.querySelector('script[src^="https://maps.googleapis.com/maps/api/js"]')) {
      // script already injected
      const checkInterval = setInterval(() => {
        if (isMapsReady()) {
          setGoogleMapsLoaded(true);
          clearInterval(checkInterval);
        }
      }, 100);
      return () => clearInterval(checkInterval);
    }

    const script = document.createElement("script");
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      setMapError("Google Maps API key is missing.");
      return;
    }
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places,marker&loading=async`;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      let attempts = 0;
      const maxAttempts = 80;
      const checkReady = setInterval(() => {
        attempts += 1;
        if (isMapsReady()) {
          setGoogleMapsLoaded(true);
          clearInterval(checkReady);
          return;
        }
        if (attempts >= maxAttempts) {
          setMapError("Google Maps failed to initialize.");
          clearInterval(checkReady);
        }
      }, 100);
    };
    script.onerror = () => setMapError("Failed to load Google Maps.");
    document.head.appendChild(script);
  }, []);

  useEffect(() => {
    if (!googleMapsLoaded || !mapRef.current || !isMapsReady()) return;

    if (!map) {
      const newMap = new window.google.maps.Map(mapRef.current, {
        center,
        zoom,
        styles: [
          { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] }
        ],
        mapTypeControl: false,
        streetViewControl: false,
        ...(mapId ? { mapId } : {}),
      });
      setMap(newMap);
    }
  }, [googleMapsLoaded, mapRef, center, zoom, map]);

  useEffect(() => {
    if (!map || !window.google) return;

    // Clear old markers
    markersRef.current.forEach((m) => {
      if (typeof m.setMap === "function") {
        m.setMap(null);
      } else {
        m.map = null;
      }
    });
    markersRef.current = [];

    // Add new markers
    markers.forEach((marker) => {
      let iconUrl = "https://maps.google.com/mapfiles/ms/icons/green-dot.png";
      let pinColor = "#16a34a";
      if (marker.type === "ngo") {
        iconUrl = "https://maps.google.com/mapfiles/ms/icons/orange-dot.png";
        pinColor = "#f97316";
      }
      if (marker.type === "gap") {
        iconUrl = "https://maps.google.com/mapfiles/ms/icons/red-dot.png";
        pinColor = "#dc2626";
      }

      let gMarker: any;
      const advancedMarkerCtor = window.google?.maps?.marker?.AdvancedMarkerElement;
      const useAdvancedMarker = Boolean(mapId && advancedMarkerCtor);
      if (useAdvancedMarker) {
        const pin = document.createElement("div");
        pin.style.width = "14px";
        pin.style.height = "14px";
        pin.style.borderRadius = "9999px";
        pin.style.background = pinColor;
        pin.style.border = "2px solid white";
        pin.style.boxShadow = "0 0 0 1px rgba(0,0,0,0.2)";
        gMarker = new advancedMarkerCtor({
          map,
          position: { lat: marker.lat, lng: marker.lng },
          title: marker.title,
          content: pin,
        });
      } else {
        gMarker = new window.google.maps.Marker({
          position: { lat: marker.lat, lng: marker.lng },
          map,
          title: marker.title,
          icon: iconUrl,
        });
      }
      
      let typeLabel = "Donor";
      if (marker.type === "ngo") typeLabel = "NGO";
      if (marker.type === "gap") typeLabel = "Coverage Gap";

      const infoWindow = new window.google.maps.InfoWindow({
        content: `<div><strong>${marker.title}</strong><br/>${typeLabel}</div>`
      });

      const onMarkerClick = () => {
        if (useAdvancedMarker) {
          infoWindow.open({ map, anchor: gMarker });
        } else {
          infoWindow.open(map, gMarker);
        }
      };
      gMarker.addListener(useAdvancedMarker ? "gmp-click" : "click", onMarkerClick);

      markersRef.current.push(gMarker);
    });

    if (routeRef.current) {
      routeRef.current.setMap(null);
      routeRef.current = null;
    }
    if (routePath.length >= 2) {
      routeRef.current = new window.google.maps.Polyline({
        path: routePath,
        geodesic: true,
        strokeColor: "#15803d",
        strokeOpacity: 0.9,
        strokeWeight: 4,
      });
      routeRef.current.setMap(map);
    }
  }, [map, markers, routePath]);

  return (
    <>
      {mapError ? (
        <div className="flex min-h-[300px] items-center justify-center rounded-2xl bg-field p-4 text-sm text-paper/80">
          {mapError}
        </div>
      ) : (
        <div
          ref={mapRef}
          className="h-full w-full rounded-2xl bg-field"
          style={{ minHeight: "300px" }}
        />
      )}
    </>
  );
}
