export function UKLandmarkSvg({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 120" fill="currentColor" className={className} aria-hidden="true">
      {/* Big Ben & London Skyline Silhouette */}
      <path d="M10 120 L10 95 L25 95 L25 120 Z" opacity="0.4" />
      <path d="M30 120 L30 85 L45 85 L45 120 Z" opacity="0.5" />
      <path d="M50 120 L50 40 L54 36 L54 18 L58 10 L62 18 L62 36 L66 40 L66 120 Z" opacity="0.9" />
      <path d="M56 46 L60 46 L60 50 L56 50 Z" fill="#ffffff" opacity="0.8" />
      <path d="M70 120 L70 70 L85 70 L85 120 Z" opacity="0.6" />
      <path d="M90 120 L90 80 L105 80 L105 120 Z" opacity="0.4" />
      <path d="M110 120 C110 100 140 100 140 120 Z" opacity="0.35" />
      <path d="M145 120 L145 60 L155 60 L155 120 Z" opacity="0.5" />
      <path d="M160 120 L160 75 L175 75 L175 120 Z" opacity="0.4" />
      <path d="M180 120 L180 90 L195 90 L195 120 Z" opacity="0.3" />
      <line x1="0" y1="118" x2="200" y2="118" stroke="currentColor" strokeWidth="3" opacity="0.6" />
    </svg>
  );
}

export function USLandmarkSvg({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 120" fill="currentColor" className={className} aria-hidden="true">
      {/* Statue of Liberty & Skyline Silhouette */}
      <path d="M15 120 L15 80 L30 80 L30 120 Z" opacity="0.35" />
      <path d="M35 120 L35 60 L50 60 L50 120 Z" opacity="0.45" />
      <path d="M55 120 L55 35 L60 25 L65 35 L65 120 Z" opacity="0.5" />
      <path d="M70 120 L70 75 L85 75 L85 120 Z" opacity="0.4" />
      <g opacity="0.95" transform="translate(110, 10) scale(0.75)">
        {/* Statue of Liberty Torch & Crown */}
        <path d="M30 140 L20 80 L25 60 L22 45 L25 35 L30 35 L33 45 L30 60 L35 80 Z" />
        <path d="M22 35 L12 28 L16 35 L10 35 L16 40 L20 40 Z" />
        <path d="M20 30 L18 10 L22 10 L24 25 Z" />
        <circle cx="20" cy="8" r="4" fill="#FFE4E6" />
        <path d="M10 140 L50 140 L45 90 L15 90 Z" />
      </g>
      <path d="M155 120 L155 50 L170 50 L170 120 Z" opacity="0.4" />
      <path d="M175 120 L175 70 L190 70 L190 120 Z" opacity="0.3" />
      <line x1="0" y1="118" x2="200" y2="118" stroke="currentColor" strokeWidth="3" opacity="0.6" />
    </svg>
  );
}

export function GermanyLandmarkSvg({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 120" fill="currentColor" className={className} aria-hidden="true">
      {/* Brandenburg Gate Silhouette */}
      <path d="M10 120 L10 90 L30 90 L30 120 Z" opacity="0.3" />
      <g opacity="0.9" transform="translate(45, 30)">
        {/* Quadriga on top */}
        <path d="M48 10 L52 2 L56 10 L50 12 Z" />
        <path d="M40 12 L64 12 L64 16 L40 16 Z" />
        {/* Attic */}
        <rect x="10" y="16" width="84" height="14" rx="2" />
        {/* Columns & Archways */}
        <rect x="12" y="30" width="8" height="60" />
        <rect x="26" y="30" width="8" height="60" />
        <rect x="40" y="30" width="8" height="60" />
        <rect x="56" y="30" width="8" height="60" />
        <rect x="70" y="30" width="8" height="60" />
        <rect x="84" y="30" width="8" height="60" />
      </g>
      <path d="M160 120 L160 85 L180 85 L180 120 Z" opacity="0.35" />
      <line x1="0" y1="118" x2="200" y2="118" stroke="currentColor" strokeWidth="3" opacity="0.6" />
    </svg>
  );
}

export function CanadaLandmarkSvg({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 120" fill="currentColor" className={className} aria-hidden="true">
      {/* CN Tower & Toronto Skyline Silhouette */}
      <path d="M15 120 L15 85 L35 85 L35 120 Z" opacity="0.4" />
      <path d="M40 120 L40 70 L60 70 L60 120 Z" opacity="0.5" />
      {/* CN Tower */}
      <g opacity="0.95">
        <path d="M86 120 L92 35 L96 35 L102 120 Z" />
        <ellipse cx="94" cy="48" rx="14" ry="6" />
        <rect x="91" y="42" width="6" height="12" rx="1" />
        <line x1="94" y1="35" x2="94" y2="8" stroke="currentColor" strokeWidth="2.5" />
      </g>
      {/* Rogers Centre Dome & Skyline */}
      <path d="M108 120 C108 95 138 95 138 120 Z" opacity="0.55" />
      <path d="M142 120 L142 65 L160 65 L160 120 Z" opacity="0.45" />
      <path d="M165 120 L165 80 L185 80 L185 120 Z" opacity="0.3" />
      <line x1="0" y1="118" x2="200" y2="118" stroke="currentColor" strokeWidth="3" opacity="0.6" />
    </svg>
  );
}

export function AustraliaLandmarkSvg({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 120" fill="currentColor" className={className} aria-hidden="true">
      {/* Sydney Opera House & Harbour Bridge Silhouette */}
      {/* Harbour Bridge Arch */}
      <path d="M10 120 C10 60 70 60 70 120 C62 80 18 80 10 120 Z" opacity="0.4" />
      {/* Sydney Opera House Shells */}
      <g opacity="0.9" transform="translate(65, 45)">
        <path d="M10 75 C12 40 32 30 40 75 Z" />
        <path d="M28 75 C30 25 55 15 65 75 Z" />
        <path d="M52 75 C54 35 75 25 85 75 Z" />
        <path d="M72 75 C74 48 92 40 100 75 Z" />
        <rect x="0" y="70" width="110" height="8" rx="2" />
      </g>
      <path d="M165 120 L165 80 L185 80 L185 120 Z" opacity="0.3" />
      <line x1="0" y1="118" x2="200" y2="118" stroke="currentColor" strokeWidth="3" opacity="0.6" />
    </svg>
  );
}
