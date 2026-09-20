import type { CSSProperties } from "react";

const paths = {
  clip: "M21 11.5 12.5 20a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.8-2.8l8.5-8.5",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  check: "m5 12 4 4L19 6",
  lock: "M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4",
  bookmark: "M6 3h12v18l-6-4-6 4z",
  key: "M14 3a5 5 0 1 1-3 9l-8 8v-4l7-7a5 5 0 0 1 4-6 M17 7h.01",
  logout: "M9 3H4v18h5 M9 12h12 M17 8l4 4-4 4",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  external: "M14 3h7v7 M21 3 10 14 M10 3H3v18h18v-7",
} as const;

export function Icon({
  name,
  size = 20,
  style,
}: {
  name: keyof typeof paths;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      <path d={paths[name]} />
    </svg>
  );
}

export function Brand() {
  return (
    <span className="brand">
      <span className="brand-mark">
        <Icon name="clip" size={23} />
      </span>
      Clipo<span className="brand-dot">.</span>
    </span>
  );
}
