import { NavLink } from "react-router-dom";

export function BrandLogoIcon({ className = "", size = 32 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="tns-logo-grad" x1="4" y1="2" x2="32" y2="34" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FF385C" />
          <stop offset="50%" stopColor="#E11D48" />
          <stop offset="100%" stopColor="#BE123C" />
        </linearGradient>
        <filter id="tns-glow" x="-2" y="-2" width="40" height="40" filterUnits="userSpaceOnUse">
          <feDropShadow dx="0" dy="1.5" stdDeviation="2" floodColor="#E11D48" floodOpacity="0.25" />
        </filter>
      </defs>

      {/* Main Outer Flame / Scholar Petal Shape */}
      <g filter="url(#tns-glow)">
        <path
          d="M18 2.5C18.8 3.8 20.4 6.8 23.5 11.2C26.8 15.8 29.5 20.2 29 24.5C28.3 30.1 23.8 34 18 34C12.2 34 7.7 30.1 7 24.5C6.5 20.2 9.2 15.8 12.5 11.2C15.6 6.8 17.2 3.8 18 2.5Z"
          fill="url(#tns-logo-grad)"
        />
        {/* Inner Stylized Loop / Mortarboard Sparkle Contour */}
        <path
          d="M18 9.5C19.8 13.2 24.5 19.8 24 23.8C23.6 27.2 20.8 29.5 18 29.5C15.2 29.5 12.4 27.2 12 23.8C11.5 19.8 16.2 13.2 18 9.5Z"
          fill="#FFFFFF"
          fillOpacity="0.95"
        />
        {/* Center Radiant Core Dot / Beacon */}
        <circle cx="18" cy="22.5" r="3.2" fill="url(#tns-logo-grad)" />
      </g>
    </svg>
  );
}

export function Brand({
  className = "",
  showDomain = false,
  onClick,
}: {
  className?: string;
  showDomain?: boolean;
  onClick?: () => void;
}) {
  return (
    <NavLink
      className={`tns-brand ${className}`}
      to="/"
      aria-label="The Next Scholar home"
      onClick={onClick}
    >
      <span className="tns-brand-icon-wrapper" aria-hidden="true">
        <BrandLogoIcon size={32} />
      </span>
      <span className="tns-brand-text-block">
        <span className="tns-brand-title">The Next Scholar</span>
        {showDomain ? <span className="tns-brand-domain">thenextscholar.com</span> : null}
      </span>
    </NavLink>
  );
}
