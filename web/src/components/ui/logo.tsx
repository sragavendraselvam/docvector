interface LogoProps {
  className?: string;
  size?: number;
  showText?: boolean;
  variant?: "gradient" | "mono" | "white" | "dark";
}

/**
 * DocVector Logo
 *
 * Design concept: A typographic logo where the "o" in DocVector is stylized
 * as a magnifying glass/search symbol, directly communicating the product's
 * purpose as a documentation search tool.
 *
 * The icon version is the stylized "o" search symbol that can stand alone.
 */
export function Logo({
  className = "",
  size = 32,
  showText = true,
  variant = "gradient"
}: LogoProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <LogoMark size={size} variant={variant} />
      {showText && <LogoWordmark variant={variant} />}
    </div>
  );
}

export function LogoMark({
  size = 32,
  variant = "gradient",
  className = ""
}: Omit<LogoProps, "showText">) {
  // Use a stable ID based on size and variant to prevent hydration errors
  const gradientId = `vectorD-${size}-${variant}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`flex-shrink-0 ${className}`}
      aria-label="DocVector logo"
    >
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>

      {/* Rounded square background */}
      <rect
        x="2"
        y="2"
        width="44"
        height="44"
        rx="10"
        fill={variant === "gradient" ? `url(#${gradientId})` :
              variant === "white" ? "#ffffff" :
              variant === "dark" ? "#0f172a" :
              "currentColor"}
      />

      {/* Bold D shape */}
      <path
        d="M14 12h8c7.732 0 14 6.268 14 14s-6.268 14-14 14h-8V12z"
        fill={variant === "white" ? "#0f172a" : "#ffffff"}
      />
      <path
        d="M18 16h4c5.523 0 10 4.477 10 10s-4.477 10-10 10h-4V16z"
        fill={variant === "gradient" ? `url(#${gradientId})` :
              variant === "white" ? "#ffffff" :
              variant === "dark" ? "#0f172a" :
              "currentColor"}
      />

      {/* Vector arrow pointing right */}
      <path
        d="M20 26h12m0 0l-4-4m4 4l-4 4"
        stroke={variant === "white" ? "#0f172a" : "#ffffff"}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Wordmark - full "DocVector" text
export function LogoWordmark({
  className = "",
  variant = "gradient"
}: Pick<LogoProps, "className" | "variant">) {
  const textColor = variant === "white"
    ? "text-white"
    : variant === "dark"
    ? "text-gray-900"
    : variant === "mono"
    ? "text-gray-900 dark:text-white"
    : "";

  const gradientClass = variant === "gradient"
    ? "bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent"
    : textColor;

  return (
    <span className={`text-xl font-bold tracking-tight ${gradientClass} ${className}`}>
      DocVector
    </span>
  );
}

// The stylized "o" as inline search symbol for the wordmark
function SearchO({ variant = "gradient", className = "" }: { variant?: LogoProps["variant"]; className?: string }) {
  // Use a stable ID based on variant to prevent hydration errors
  const gradientId = `searchO-${variant}`;

  const strokeColor = variant === "gradient" ? `url(#${gradientId})` :
                     variant === "white" ? "#ffffff" :
                     variant === "dark" ? "#0f172a" :
                     "currentColor";

  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`inline-block ${className}`}
      style={{ verticalAlign: "middle", margin: "0 1px", transform: "translateY(-1px)" }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>

      {/* Circle (the o) - sized to match text x-height */}
      <circle
        cx="6"
        cy="6"
        r="4.5"
        stroke={strokeColor}
        strokeWidth="2"
        fill="none"
      />

      {/* Handle - simple diagonal */}
      <path
        d="M9.5 9.5L14 14"
        stroke={strokeColor}
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Icon-only export for convenience
export function LogoIcon({ className = "", size = 24, variant = "gradient" }: Omit<LogoProps, "showText">) {
  return <LogoMark className={className} size={size} variant={variant} />;
}

// Full logo component with all variations
export function LogoFull({
  className = "",
  variant = "gradient",
  size = "default"
}: {
  className?: string;
  variant?: LogoProps["variant"];
  size?: "small" | "default" | "large";
}) {
  const sizeMap = {
    small: { icon: 24, text: "text-lg" },
    default: { icon: 32, text: "text-xl" },
    large: { icon: 48, text: "text-3xl" },
  };

  const { icon, text } = sizeMap[size];

  const textColor = variant === "white"
    ? "text-white"
    : variant === "dark"
    ? "text-gray-900"
    : variant === "mono"
    ? "text-gray-900 dark:text-white"
    : "";

  const gradientClass = variant === "gradient"
    ? "bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent"
    : textColor;

  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <LogoMark size={icon} variant={variant} />
      <span className={`font-bold tracking-tight ${text} ${gradientClass}`}>
        DocVector
      </span>
    </div>
  );
}
