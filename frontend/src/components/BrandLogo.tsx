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
      <path
        d="M11.8 29.7 22.5 35v10.7l18.8 13.6c2.1 1.5 5 .1 5-2.5V29.7l-10.7 5.2v9.7L17.3 31.3c-2.2-1.6-5.5 0-5.5 2.8v21c0 2.2 1.8 4 4 4h6.7V46.2l-10.7-7.8v-8.7Z"
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
