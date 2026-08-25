type VehicleType = "car" | "bus" | "truck" | "motorcycle";

const PATHS: Record<VehicleType, string> = {
  car: "M3 12.5l1.2-3.6A2 2 0 0 1 6.1 7.5h7.8a2 2 0 0 1 1.9 1.4L17 12.5M3 12.5h14M3 12.5v2a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1v-1M17 12.5v2a1 1 0 0 0-1 1h-1a1 1 0 0 1-1-1v-1M6 9.8h8",
  bus: "M4 4.5h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1zM3 8.5h14M6 6.5v2M14 6.5v2M6 15.5v1.2M14 15.5v1.2",
  truck: "M2.5 6.5h8v6.5h-8zM10.5 9h3.5l2.5 2v2h-1M2.5 13h10.5M12.5 15.3a1.3 1.3 0 1 0 0-2.6 1.3 1.3 0 0 0 0 2.6zM5 15.3a1.3 1.3 0 1 0 0-2.6 1.3 1.3 0 0 0 0 2.6z",
  motorcycle: "M3 15a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM13 15a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM5 15h2l2.5-5h3l1 2M8 8.5h3l1.5 2.5M11 8.5l1-2h2.5",
};

interface Props {
  type: string;
  size?: number;
}

/** Minimal line icon for a vehicle class; falls back to a generic dot for
 * anything YOLO reports that isn't one of the four known classes. */
export function VehicleIcon({ type, size = 14 }: Props) {
  const path = PATHS[type as VehicleType];
  if (!path) {
    return <span className="vehicle-icon-fallback" style={{ width: size, height: size }} />;
  }
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor"
         strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}
