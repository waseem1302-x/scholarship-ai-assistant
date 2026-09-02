import { NavLink } from "react-router-dom";

function BrandLogoIcon({ className = "", size = 40 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="tns-logo-primary" x1="8" y1="8" x2="53" y2="58" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1677F2" />
          <stop offset="1" stopColor="#2563EB" />
        </linearGradient>
        <linearGradient id="tns-logo-secondary" x1="14" y1="30" x2="45" y2="58" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563EB" />
          <stop offset="1" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
      <path
        d="M4.7 18.2 29.2 6.3a6 6 0 0 1 5.3 0l24.6 11.9c1.8.9 1.8 3.4 0 4.3L34.5 34.4a6 6 0 0 1-5.3 0L4.7 22.5c-1.8-.9-1.8-3.4 0-4.3Z"
        fill="url(#tns-logo-primary)"
      />
      <path d="m11.8 29.6 10.7 5.2v24.3h-6.7a4 4 0 0 1-4-4V29.6Z" fill="url(#tns-logo-primary)" />
      <path
        d="m41.5 31 10.7-5.2v27.8c0 3.2-1.8 5.9-4.5 7.2a5.9 5.9 0 0 1-6.2-.9V31Z"
        fill="url(#tns-logo-secondary)"
      />
      <path
        d="M16.5 31.1c1.2-.4 2.5-.2 3.5.5l28.2 20.6a5.1 5.1 0 0 1 1.2 6.3c-1.6 2.7-5.2 3.3-7.7 1.4L16.1 40.7c-3.8-2.8-3.5-8.1.4-9.6Z"
        fill="url(#tns-logo-secondary)"
      />
      <path d="M53.1 22.3v15.2" stroke="#FACC15" strokeWidth="2.6" strokeLinecap="round" />
      <path
        className="tns-brand-opportunity-accent"
        d="m53.1 35.4 2.1 4.3 4.3 2.1-4.3 2.1-2.1 4.3-2.1-4.3-4.3-2.1 4.3-2.1 2.1-4.3Z"
        fill="#FACC15"
      />
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
        <BrandLogoIcon />
      </span>
      <span className="tns-brand-text-block">
        <span className="tns-brand-title">
          <span className="tns-brand-title-line">The Next</span>
          <span className="tns-brand-title-line tns-brand-title-line--accent">Scholar</span>
        </span>
        {showDomain ? <span className="tns-brand-domain">thenextscholar.com</span> : null}
      </span>
    </NavLink>
  );
}
